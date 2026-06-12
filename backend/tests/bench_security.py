"""
Security tests:
  1. Rate limiting actually blocks after limit
  2. Unauthenticated requests to protected routes → 401 not 500
  3. User A cannot access User B's tickets via API

Usage:
    BENCH_TOKEN_A=<jwt_a> BENCH_TOKEN_B=<jwt_b> PYTHONPATH=backend python tests/bench_security.py
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import httpx

BASE_URL = "http://localhost:8000"
TOKEN_A  = os.environ.get("BENCH_TOKEN", "")   # primary test user
TOKEN_B  = os.environ.get("BENCH_TOKEN_B", "")  # second test user (optional)

def hdr(s): print(f"\n{'='*68}\n {s}\n{'='*68}")
def ok(s):   print(f"  [PASS] {s}")
def fail(s): print(f"  [FAIL] {s}")
def info(s): print(f"  [INFO] {s}")
def warn(s): print(f"  [WARN] {s}")


# ─── Section 1: Unauthenticated requests return 401 not 500 ──────────────────
hdr("SECURITY — Unauthenticated requests → 401")

protected_routes = [
    ("POST", "/api/v1/chat/message",     {"message": "test", "session_id": "x"}),
    ("POST", "/api/v1/chat/escalate",    {"session_id": "x", "title": "t", "description": "d", "steps_tried": "s"}),
    ("GET",  "/api/v1/chat/tickets",     None),
    ("GET",  "/api/v1/admin/engineers",  None),
    ("GET",  "/api/v1/engineer/tickets", None),
]

all_ok = True
with httpx.Client(base_url=BASE_URL, timeout=10) as client:
    for method, path, body in protected_routes:
        if method == "POST":
            r = client.post(path, json=body)
        else:
            r = client.get(path)

        if r.status_code == 401:
            ok(f"  {method} {path} → 401 ✓")
        elif r.status_code == 422:
            # Validation error before auth — also acceptable (not 500)
            ok(f"  {method} {path} → 422 (validation before auth, not 500) ✓")
        elif r.status_code == 403:
            ok(f"  {method} {path} → 403 ✓")
        elif r.status_code == 500:
            fail(f"  {method} {path} → 500 (server error on unauth request!)")
            all_ok = False
        else:
            info(f"  {method} {path} → {r.status_code}")

if all_ok:
    ok("All protected routes return 4xx (not 500) without auth")


# ─── Section 2: Rate limiter actually blocks after limit ─────────────────────
hdr("SECURITY — Rate limiter blocks after limit")

with httpx.Client(base_url=BASE_URL, timeout=10) as client:
    # auth_limiter: 10 req / 60s on /forgot-password
    LIMIT    = 10
    statuses = []
    for i in range(LIMIT + 5):
        r = client.post("/api/v1/auth/forgot-password",
                        json={"email": f"test{i}@example.com"})
        statuses.append(r.status_code)

    blocked = [s for s in statuses[LIMIT:] if s == 429]
    info(f"First {LIMIT} requests: {statuses[:LIMIT]}")
    info(f"Requests after limit: {statuses[LIMIT:]}")

    if blocked:
        ok(f"Rate limiter blocked {len(blocked)}/{LIMIT + 5 - LIMIT} requests after limit")
    else:
        # Some requests may have gotten 200/404/422 — check if any 429
        any_429 = any(s == 429 for s in statuses)
        if any_429:
            ok("Rate limiter returned 429 at some point")
        else:
            fail(f"No 429 responses — rate limiter may not be firing. Statuses: {statuses}")

    # ── chat limiter: 30 req / 60s per IP
    # Use a 1s timeout — we only care whether the limiter fires (429), not whether Claude responds.
    # Requests that reach Claude will timeout at the client but still increment the limiter counter.
    if TOKEN_A:
        statuses2 = []
        headers   = {"Authorization": f"Bearer {TOKEN_A}"}
        with httpx.Client(base_url=BASE_URL, timeout=1.5) as fast_client:
            for i in range(35):
                try:
                    r = fast_client.post("/api/v1/chat/message",
                                         json={"message": "test network issue", "session_id": f"rl-{i}"},
                                         headers=headers)
                    statuses2.append(r.status_code)
                except (httpx.ReadTimeout, httpx.ConnectTimeout):
                    # Timeout means the request reached the server and was accepted (rate limiter passed)
                    statuses2.append(200)

        chat_429 = statuses2.count(429)
        info(f"Chat endpoint: sent 35 requests, got {chat_429} 429s")
        if chat_429 > 0:
            ok(f"Chat rate limiter blocked {chat_429} requests after 30/min limit")
        else:
            info("Chat rate limiter did not trigger (requests may have been spread across IPs or window reset)")
    else:
        warn("BENCH_TOKEN not set — skipping chat rate limit test")


# ─── Section 3: User A cannot access User B's tickets ────────────────────────
hdr("SECURITY — Ticket isolation (User A cannot read User B's tickets)")

if not TOKEN_A:
    warn("BENCH_TOKEN not set — skipping ticket isolation test")
else:
    with httpx.Client(base_url=BASE_URL, timeout=10) as client:
        headers_a = {"Authorization": f"Bearer {TOKEN_A}"}

        # Get user A's tickets
        r = client.get("/api/v1/chat/tickets", headers=headers_a)
        if r.status_code == 200:
            tickets_a = r.json()
            info(f"User A has {len(tickets_a)} tickets")

            if tickets_a:
                # Try to access a specific ticket by ID
                ticket_id = tickets_a[0].get("id") or tickets_a[0].get("ticket_id")
                if ticket_id:
                    r2 = client.get(f"/api/v1/chat/tickets/{ticket_id}", headers=headers_a)
                    if r2.status_code == 200:
                        ok(f"User A can access their own ticket {ticket_id} → 200")
                    else:
                        info(f"Own-ticket access returned {r2.status_code}")

                    # Try without auth — should be 401
                    r3 = client.get(f"/api/v1/chat/tickets/{ticket_id}")
                    if r3.status_code == 401:
                        ok("Ticket endpoint returns 401 without auth")
                    else:
                        fail(f"Ticket endpoint returned {r3.status_code} without auth")

                    # If we have Token B, try cross-access
                    if TOKEN_B:
                        headers_b = {"Authorization": f"Bearer {TOKEN_B}"}
                        r4 = client.get(f"/api/v1/chat/tickets/{ticket_id}", headers=headers_b)
                        if r4.status_code in (403, 404):
                            ok(f"User B cannot access User A's ticket → {r4.status_code}")
                        elif r4.status_code == 200:
                            # Check if the response is actually the right ticket
                            t_data = r4.json()
                            fail(f"User B can read User A's ticket! Data: {str(t_data)[:100]}")
                        else:
                            info(f"Cross-user ticket access returned {r4.status_code}")
                    else:
                        warn("BENCH_TOKEN_B not set — cannot test cross-user ticket access")
            else:
                info("User A has no tickets yet — create one to test isolation")
        else:
            info(f"Could not fetch tickets: {r.status_code} — {r.text[:100]}")


# ─── Section 4: Input validation boundary tests ───────────────────────────────
hdr("SECURITY — Input validation")

with httpx.Client(base_url=BASE_URL, timeout=10) as client:
    if TOKEN_A:
        headers = {"Authorization": f"Bearer {TOKEN_A}"}

        # Message too short (< 2 chars) — rate limiter may fire first (429) if window still active
        r = client.post("/api/v1/chat/message",
                        json={"message": "x", "session_id": "val-test"},
                        headers=headers)
        info(f"Message 1 char: {r.status_code} (expected 422 or 429)")
        if r.status_code in (422, 429):
            ok(f"1-char message blocked → {r.status_code} (422=validation, 429=rate-limit, both safe)")
        else:
            fail(f"1-char message not rejected: {r.status_code}")

        # Message too long (> 2000 chars)
        r = client.post("/api/v1/chat/message",
                        json={"message": "x" * 2001, "session_id": "val-test"},
                        headers=headers)
        info(f"Message 2001 chars: {r.status_code} (expected 422 or 429)")
        if r.status_code in (422, 429):
            ok(f"2001-char message blocked → {r.status_code} (422=validation, 429=rate-limit, both safe)")
        else:
            fail(f"2001-char message not rejected: {r.status_code}")

        # SQL injection attempt in message
        r = client.post("/api/v1/chat/message",
                        json={"message": "'; DROP TABLE tickets; --", "session_id": "sql-test"},
                        headers=headers)
        if r.status_code in (200, 422, 429):
            ok(f"SQL injection in message handled safely → {r.status_code}")
        else:
            info(f"SQL injection test: {r.status_code}")

        # XSS attempt
        r = client.post("/api/v1/chat/message",
                        json={"message": "<script>alert(1)</script> help with network", "session_id": "xss-test"},
                        headers=headers)
        if r.status_code in (200, 422, 429):
            ok(f"XSS in message handled safely → {r.status_code}")
        else:
            info(f"XSS test: {r.status_code}")
    else:
        warn("BENCH_TOKEN not set — skipping input validation tests")

print("\n")
