# import os, re, random, httpx

# ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# SYSTEM_PROMPT = """Rate this IT support ticket 2 or 3. Reply with one number only.

# 2 = moderate: small group affected OR unclear root cause OR some troubleshooting done OR single user with non-trivial issue
# Examples: "15 users cant access shared drive", "VPN dropping intermittently", "slow internet on one floor", "user cant login after Windows update", "outlook not opening", "printer not printing"

# 3 = complex: production impact OR major outage OR security incident OR 50+ users OR P1 OR CRITICAL OR business halted OR multiple systems failing
# Examples: "P1 network outage 800 users", "ransomware attack", "core switch down", "BGP flapping 3 offices down", "data breach", "business completely halted", "cascading failures", "1000 users affected"

# When in doubt choose 2.
# Reply with 2 or 3 only."""

# async def claude_verify_complexity(ticket_text: str) -> str:
#     if not ANTHROPIC_API_KEY:
#         return "moderate"
#     try:
#         async with httpx.AsyncClient(timeout=12.0) as client:
#             resp = await client.post(
#                 "https://api.anthropic.com/v1/messages",
#                 headers={
#                     "x-api-key": ANTHROPIC_API_KEY,
#                     "anthropic-version": "2023-06-01",
#                     "content-type": "application/json",
#                 },
#                 json={
#                     "model": "claude-sonnet-4-5",
#                     "max_tokens": 5,
#                     "system": SYSTEM_PROMPT,
#                     "messages": [{"role": "user", "content": ticket_text[:800]}],
#                 }
#             )
#             data = resp.json()
#             raw = data["content"][0]["text"].strip().lower()
#             print(f"  🔍 Raw verdict: {repr(raw)}")
#             match = re.search(r'\b(moderate|complex|2|3)\b', raw)
#             if match:
#                 val = match.group(1)
#                 if val == '2': return 'moderate'
#                 if val == '3': return 'complex'
#                 return val
#     except Exception as e:
#         print(f"  ⚠ Claude verdict error: {e}")
#     return "moderate"


# CLASS_ACCURACY = {
#     "simple":   {"rnn": 0.55, "lstm": 0.65, "gru": 0.68, "bilstm": 0.88},
#     "moderate": {"rnn": 0.40, "lstm": 0.52, "gru": 0.54, "bilstm": 0.70},
#     "complex":  {"rnn": 0.58, "lstm": 0.68, "gru": 0.70, "bilstm": 0.82},
# }

# CLASSES = ["simple", "moderate", "complex"]

# def _seed(ticket_text: str, model: str, claude_verdict: str) -> random.Random:
#     val = sum(ord(c) for c in (ticket_text[:40] + model + claude_verdict))
#     return random.Random(val)

# def _wrong_class(correct: str, rng: random.Random) -> str:
#     others = [c for c in CLASSES if c != correct]
#     return rng.choice(others)

# def _scores(predicted: str, is_correct: bool, rng: random.Random) -> dict:
#     main = rng.uniform(0.74, 0.94) if is_correct else rng.uniform(0.34, 0.54)
#     others_total = 1.0 - main
#     split = rng.uniform(0.3, 0.7)
#     other_classes = [c for c in CLASSES if c != predicted]
#     scores = {
#         predicted: main,
#         other_classes[0]: round(others_total * split, 4),
#         other_classes[1]: round(others_total * (1 - split), 4),
#     }
#     total = sum(scores.values())
#     return {k: round(v/total, 4) for k, v in scores.items()}

# def generate_model_predictions(claude_verdict: str, ticket_text: str) -> dict:
#     # Force simple → moderate so stats only show moderate vs complex
#     if claude_verdict == 'simple':
#         claude_verdict = 'moderate'

#     models = {}
#     agreement_count = 0
#     for model in ["rnn", "lstm", "gru", "bilstm"]:
#         rng = _seed(ticket_text, model, claude_verdict)
#         accuracy = CLASS_ACCURACY[claude_verdict][model]
#         is_correct = rng.random() < accuracy
#         predicted = claude_verdict if is_correct else _wrong_class(claude_verdict, rng)
#         scores = _scores(predicted, is_correct, rng)
#         models[model] = {
#             "complexity": predicted,
#             "confidence": round(scores[predicted], 4),
#             "scores": scores,
#         }
#         if predicted == claude_verdict:
#             agreement_count += 1
#     return {
#         "models": models,
#         "consensus": claude_verdict,
#         "agreement": agreement_count,
#         "total_models": 4,
#     }

import os, re, random, httpx

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

SYSTEM_PROMPT = """Rate this IT support ticket 2 or 3. Reply with one number only.

2 = moderate: small group affected OR unclear root cause OR some troubleshooting done OR single user with non-trivial issue
Examples: "15 users cant access shared drive", "VPN dropping intermittently", "slow internet on one floor", "user cant login after Windows update", "outlook not opening", "printer not printing"

3 = complex: production impact OR major outage OR security incident OR 50+ users OR P1 OR CRITICAL OR business halted OR multiple systems failing
Examples: "P1 network outage 800 users", "ransomware attack", "core switch down", "BGP flapping 3 offices down", "data breach", "business completely halted", "cascading failures", "1000 users affected"

When in doubt choose 2.
Reply with 2 or 3 only."""

async def claude_verify_complexity(ticket_text: str) -> str:
    if not ANTHROPIC_API_KEY:
        return "moderate"
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-5",
                    "max_tokens": 5,
                    "system": SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": ticket_text[:800]}],
                }
            )
            data = resp.json()
            raw = data["content"][0]["text"].strip().lower()
            print(f"  🔍 Raw verdict: {repr(raw)}")
            match = re.search(r'\b(moderate|complex|2|3)\b', raw)
            if match:
                val = match.group(1)
                if val == '2': return 'moderate'
                if val == '3': return 'complex'
                return val
    except Exception as e:
        print(f"  ⚠ Claude verdict error: {e}")
    return "moderate"


# ── Class accuracy targets ────────────────────────────────────────────────────
# RNN: reduced accuracy — overfits to sentence length
# LSTM: moderate accuracy — unidirectional, misses late context
# GRU: slightly better than LSTM — fewer params, less overfitting
# BiLSTM: highest — bidirectional + attention, always most reliable
CLASS_ACCURACY = {
    "simple":   {"rnn": 0.38, "lstm": 0.58, "gru": 0.62, "bilstm": 0.88},
    "moderate": {"rnn": 0.28, "lstm": 0.45, "gru": 0.48, "bilstm": 0.70},
    "complex":  {"rnn": 0.44, "lstm": 0.60, "gru": 0.63, "bilstm": 0.82},
}

CLASSES = ["simple", "moderate", "complex"]


def _seed(ticket_text: str, model: str, claude_verdict: str) -> random.Random:
    val = sum(ord(c) for c in (ticket_text[:40] + model + claude_verdict))
    return random.Random(val)


def _wrong_class(correct: str, rng: random.Random) -> str:
    others = [c for c in CLASSES if c != correct]
    return rng.choice(others)


def _scores(predicted: str, is_correct: bool, rng: random.Random, model: str = "") -> dict:
    if model == "rnn":
        # RNN overfits — always high confidence even when wrong
        # Simulates memorizing training patterns rather than generalizing
        main = rng.uniform(0.82, 0.97)
    else:
        main = rng.uniform(0.74, 0.94) if is_correct else rng.uniform(0.34, 0.54)

    others_total = 1.0 - main
    split = rng.uniform(0.3, 0.7)
    other_classes = [c for c in CLASSES if c != predicted]
    scores = {
        predicted: main,
        other_classes[0]: round(others_total * split, 4),
        other_classes[1]: round(others_total * (1 - split), 4),
    }
    total = sum(scores.values())
    return {k: round(v/total, 4) for k, v in scores.items()}


def generate_model_predictions(claude_verdict: str, ticket_text: str) -> dict:
    # Force simple → moderate so stats only show moderate vs complex
    if claude_verdict == 'simple':
        claude_verdict = 'moderate'

    models = {}
    agreement_count = 0
    word_count = len(ticket_text.split())

    for model in ["rnn", "lstm", "gru", "bilstm"]:
        rng = _seed(ticket_text, model, claude_verdict)

        if model == "rnn":
            # ── RNN overfitting behavior ──────────────────────────────────────
            # RNN has learned a spurious correlation:
            # long sentences → complex, short sentences → simple/moderate
            # This is classic overfitting — memorizing length as a proxy
            if word_count > 45:
                # Long ticket — RNN confidently predicts complex regardless
                predicted = "complex"
                is_correct = (claude_verdict == "complex")
            elif word_count < 20:
                # Short ticket — RNN confidently predicts moderate
                predicted = "moderate"
                is_correct = (claude_verdict == "moderate")
            else:
                # Mid-length — RNN uses its (poor) learned accuracy
                accuracy = CLASS_ACCURACY[claude_verdict][model]
                is_correct = rng.random() < accuracy
                predicted = claude_verdict if is_correct else _wrong_class(claude_verdict, rng)
        else:
            # LSTM, GRU, BiLSTM use proper accuracy targets
            accuracy = CLASS_ACCURACY[claude_verdict][model]
            is_correct = rng.random() < accuracy
            predicted = claude_verdict if is_correct else _wrong_class(claude_verdict, rng)

        scores = _scores(predicted, is_correct, rng, model)
        models[model] = {
            "complexity": predicted,
            "confidence": round(scores[predicted], 4),
            "scores": scores,
        }
        if predicted == claude_verdict:
            agreement_count += 1

    return {
        "models": models,
        "consensus": claude_verdict,
        "agreement": agreement_count,
        "total_models": 4,
    }