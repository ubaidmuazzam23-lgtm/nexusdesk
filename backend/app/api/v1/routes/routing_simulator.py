# File: backend/app/api/v1/routes/routing_simulator.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
import pytz
from datetime import datetime

from app.core.database import get_db
from app.core.dependencies import require_role
from app.models.user import User, UserRole
from app.models.engineer import Engineer, AvailabilityStatus

router = APIRouter(prefix="/routing", tags=["routing"])


@router.get("/users")
def get_users_for_simulation(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN))
):
    users = db.query(User).filter(
        User.role == UserRole.USER,
        User.is_active == True,
    ).order_by(User.full_name).all()
    return [
        {
            "id": str(u.id),
            "name": u.full_name,
            "email": u.email,
            "city": u.city or "Unknown",
            "country": u.country or "",
            "timezone": u.timezone or "UTC",
        }
        for u in users
    ]


class SimulateRequest(BaseModel):
    domain: str
    severity: str
    user_timezone: str
    user_city: str
    user_country: str


@router.post("/simulate")
def simulate_routing(
    data: SimulateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN))
):
    engineers = db.query(Engineer, User).join(
        User, Engineer.user_id == User.id
    ).filter(
        Engineer.is_activated == True,
        User.is_active == True,
        Engineer.availability_status == AvailabilityStatus.AVAILABLE,
    ).all()

    if not engineers:
        return {
            "assigned_engineer": None,
            "all_candidates": [],
            "routing_reason": "No available engineers in the system.",
            "user_city": data.user_city,
            "user_timezone": data.user_timezone,
            "domain": data.domain,
            "severity": data.severity,
        }

    candidates = []
    # Use naive datetime for correct utcoffset calculation
    now_naive = datetime.utcnow()

    for eng, usr in engineers:
        score = 0
        domain_match = 0
        timezone_score = 0
        tz_diff_hours = 0
        workload_score = 0
        city_bonus = 0

        # Domain match — highest priority
        if data.domain in (eng.domain_expertise or []):
            score += 10
            domain_match = 10

        # Timezone proximity
        try:
            user_tz = pytz.timezone(data.user_timezone)
            eng_tz  = pytz.timezone(usr.timezone or "UTC")
            user_offset = user_tz.utcoffset(now_naive).total_seconds() / 3600
            eng_offset  = eng_tz.utcoffset(now_naive).total_seconds() / 3600
            tz_diff_hours = round(abs(user_offset - eng_offset))

            if tz_diff_hours == 0:
                score += 5
                timezone_score = 5
            elif tz_diff_hours <= 3:
                score += 3
                timezone_score = 3
            elif tz_diff_hours <= 6:
                score += 1
                timezone_score = 1
        except Exception:
            pass

        # City match tiebreaker
        if usr.city and data.user_city and usr.city.strip().lower() == data.user_city.strip().lower():
            score += 2
            city_bonus = 2

        # Workload penalty
        workload_score = -eng.active_ticket_count
        score += workload_score

        candidates.append({
            "engineer_id": eng.engineer_id or str(eng.user_id)[:8],
            "name": usr.full_name,
            "city": usr.city or "",
            "country": usr.country or "",
            "timezone": usr.timezone or "UTC",
            "domain": (eng.domain_expertise or ["unknown"])[0],
            "active_tickets": eng.active_ticket_count,
            "max_capacity": eng.max_ticket_capacity or 10,
            "score": score,
            "score_breakdown": {
                "domain_match": domain_match,
                "timezone_score": timezone_score,
                "workload_score": workload_score,
                "tz_diff_hours": tz_diff_hours,
                "city_bonus": city_bonus,
            }
        })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    winner = candidates[0]

    # Build routing reason
    bd = winner["score_breakdown"]
    reasons = []
    if bd["domain_match"] > 0:
        reasons.append(f"domain match (+{bd['domain_match']}pts)")
    if bd.get("city_bonus", 0) > 0:
        reasons.append(f"same city tiebreaker (+{bd['city_bonus']}pts)")
    if bd["timezone_score"] > 0:
        reasons.append(f"timezone proximity {bd['tz_diff_hours']}h difference (+{bd['timezone_score']}pts)")
    if bd["workload_score"] < 0:
        reasons.append(f"workload penalty ({bd['workload_score']}pts)")
    else:
        reasons.append("no active tickets")

    routing_reason = (
        f"{winner['name']} selected with score {winner['score']}pts — "
        + ", ".join(reasons) + "."
    )

    return {
        "assigned_engineer": winner,
        "all_candidates": candidates,
        "routing_reason": routing_reason,
        "user_city": data.user_city,
        "user_timezone": data.user_timezone,
        "domain": data.domain,
        "severity": data.severity,
    }