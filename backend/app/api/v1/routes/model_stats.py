# File: backend/app/api/v1/routes/model_stats.py
# Returns per-ticket model predictions + aggregate stats for Model Stats page

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.database import get_db
from app.core.dependencies import require_role
from app.models.user import User, UserRole

router = APIRouter(prefix="/model-stats", tags=["model_stats"])


@router.get("/predictions")
def get_all_predictions(db: Session = Depends(get_db), current_user: User = Depends(require_role(UserRole.ADMIN))):
    """
    Returns all stored model predictions with ticket context.
    Each row = one ticket, with predictions from all 4 models.
    """
    rows = db.execute(text("""
        SELECT
            t.ticket_number,
            t.title,
            t.domain,
            t.priority,
            t.complexity,
            t.created_at,
            t.model_predictions
        FROM tickets t
        WHERE t.model_predictions IS NOT NULL
        ORDER BY t.created_at DESC
        LIMIT 100
    """)).fetchall()

    result = []
    for row in rows:
        import json
        preds = row.model_predictions if isinstance(row.model_predictions, dict) else {}
        try:
            if isinstance(row.model_predictions, str):
                preds = json.loads(row.model_predictions)
        except Exception:
            preds = {}

        result.append({
            "ticket_number": row.ticket_number,
            "title":         row.title,
            "domain":        row.domain,
            "priority":      row.priority,
            "actual":        row.complexity,
            "created_at":    row.created_at.isoformat() if row.created_at else None,
            "predictions":   preds,
        })

    return result


@router.get("/aggregate")
def get_aggregate_stats(db: Session = Depends(get_db), current_user: User = Depends(require_role(UserRole.ADMIN))):
    """
    Aggregate accuracy stats per model across all tickets that have model_predictions stored.
    """
    rows = db.execute(text("""
        SELECT complexity, model_predictions
        FROM tickets
        WHERE model_predictions IS NOT NULL AND complexity IS NOT NULL
    """)).fetchall()

    if not rows:
        return {"total_predictions": 0, "models": {}}

    import json
    models = ['bilstm', 'lstm', 'gru', 'rnn']
    stats  = {m: {"correct": 0, "total": 0, "by_class": {"simple": {"correct":0,"total":0}, "moderate": {"correct":0,"total":0}, "complex": {"correct":0,"total":0}}} for m in models}

    for row in rows:
        actual = row.complexity
        try:
            preds = row.model_predictions if isinstance(row.model_predictions, dict) else json.loads(row.model_predictions or '{}')
        except Exception:
            continue

        model_preds = preds.get('models', preds)
        for m in models:
            if m not in model_preds: continue
            pred = model_preds[m]
            if 'error' in pred: continue
            predicted = pred.get('complexity')
            if not predicted: continue
            stats[m]['total'] += 1
            if actual in stats[m]['by_class']:
                stats[m]['by_class'][actual]['total'] += 1
            if predicted == actual:
                stats[m]['correct'] += 1
                if actual in stats[m]['by_class']:
                    stats[m]['by_class'][actual]['correct'] += 1

    result = {}
    for m, s in stats.items():
        acc = round(s['correct'] / s['total'] * 100, 1) if s['total'] > 0 else 0
        result[m] = {
            "accuracy":   acc,
            "correct":    s['correct'],
            "total":      s['total'],
            "by_class":   {
                cls: {
                    "accuracy": round(v['correct'] / v['total'] * 100, 1) if v['total'] > 0 else 0,
                    "correct":  v['correct'],
                    "total":    v['total'],
                } for cls, v in s['by_class'].items()
            }
        }

    return {"total_predictions": len(rows), "models": result}

@router.delete("/predictions/{ticket_number}")
def delete_prediction(ticket_number: str, db: Session = Depends(get_db), current_user: User = Depends(require_role(UserRole.ADMIN))):
    from app.models.ticket import Ticket
    ticket = db.execute(text("SELECT id FROM tickets WHERE ticket_number = :tn"), {"tn": ticket_number}).fetchone()
    if not ticket:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Ticket not found")
    db.execute(text("DELETE FROM tickets WHERE ticket_number = :tn"), {"tn": ticket_number})
    db.commit()
    return {"deleted": True}

    