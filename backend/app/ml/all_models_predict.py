# File: backend/app/ml/all_models_predict.py
# Runs all 4 complexity models on a given ticket text.
# Called when a ticket is escalated — results stored in DB.

def predict_all(text: str) -> dict:
    """
    Run all 4 models on ticket text.
    Returns dict with predictions from each model.
    Models that haven't been trained yet return error gracefully.
    """
    results = {}

    # BiLSTM
    try:
        from app.ml.bilstm.predict import predict_complexity as bilstm_pred
        results['bilstm'] = bilstm_pred(text)
    except Exception as e:
        results['bilstm'] = {"complexity": "moderate", "confidence": 0.0,
                              "scores": {"simple": 0.33, "moderate": 0.34, "complex": 0.33},
                              "error": str(e)}

    # LSTM
    try:
        from app.ml.lstm.predict import predict_complexity as lstm_pred
        results['lstm'] = lstm_pred(text)
    except Exception as e:
        results['lstm'] = {"complexity": "moderate", "confidence": 0.0,
                            "scores": {"simple": 0.33, "moderate": 0.34, "complex": 0.33},
                            "error": str(e)}

    # GRU
    try:
        from app.ml.gru.predict import predict_complexity as gru_pred
        results['gru'] = gru_pred(text)
    except Exception as e:
        results['gru'] = {"complexity": "moderate", "confidence": 0.0,
                           "scores": {"simple": 0.33, "moderate": 0.34, "complex": 0.33},
                           "error": str(e)}

    # RNN
    try:
        from app.ml.rnn.predict import predict_complexity as rnn_pred
        results['rnn'] = rnn_pred(text)
    except Exception as e:
        results['rnn'] = {"complexity": "moderate", "confidence": 0.0,
                           "scores": {"simple": 0.33, "moderate": 0.34, "complex": 0.33},
                           "error": str(e)}

    # Majority vote across trained models
    votes = {}
    for model_name, result in results.items():
        if 'error' not in result:
            c = result['complexity']
            votes[c] = votes.get(c, 0) + 1

    consensus = max(votes, key=votes.get) if votes else 'moderate'

    return {
        "models":    results,
        "consensus": consensus,
        "agreement": len([r for r in results.values() if r.get('complexity') == consensus and 'error' not in r]),
        "total_models": len([r for r in results.values() if 'error' not in r]),
    }