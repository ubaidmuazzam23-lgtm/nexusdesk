"""
Concurrency tests:
  1. 20 users send messages simultaneously — verify zero session cross-contamination
  2. 10 concurrent escalations — verify no duplicate ticket numbers
  3. Session user binding — verify user A cannot access user B's session

Usage:
    PYTHONPATH=backend python tests/bench_concurrency.py
"""
import sys, os, threading, uuid, time
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

def hdr(s): print(f"\n{'='*68}\n {s}\n{'='*68}")
def ok(s):   print(f"  [PASS] {s}")
def fail(s): print(f"  [FAIL] {s}")
def info(s): print(f"  [INFO] {s}")

# ─── Section 1: Session isolation under concurrent access ─────────────────────
hdr("CONCURRENCY — Session isolation (20 simultaneous users)")

import app.services.chat_service as cs
from unittest.mock import patch, MagicMock

# Give each virtual user a distinct session ID and a unique "problem" string.
# After concurrent access, verify each session still holds its own problem.
N_USERS = 20
sessions = {f"user-{i}": f"unique-problem-for-user-{i}" for i in range(N_USERS)}
errors   = []

def _send_message(sid: str, problem: str):
    sess = cs._get_session(sid)
    # Simulate process_message writing the problem
    if not sess["problem"]:
        sess["problem"] = problem
    sess["messages"].append({"role": "user", "content": problem})
    # Small random sleep to force thread interleaving
    time.sleep(0.001 * (hash(sid) % 5))
    # Read back and verify
    if sess["problem"] != problem:
        errors.append(f"Session {sid} contaminated: expected '{problem}' got '{sess['problem']}'")
    if any(m["content"] != problem for m in sess["messages"] if m["role"] == "user"):
        errors.append(f"Session {sid} has foreign messages")

# Clear any existing sessions with these IDs
with cs._sessions_lock:
    for sid in sessions:
        cs._sessions.pop(sid, None)

threads = [
    threading.Thread(target=_send_message, args=(sid, prob))
    for sid, prob in sessions.items()
]
for t in threads: t.start()
for t in threads: t.join()

if errors:
    for e in errors:
        fail(e)
else:
    ok(f"Zero session cross-contamination across {N_USERS} concurrent users")

# ─── Section 2: Session user binding ─────────────────────────────────────────
hdr("CONCURRENCY — Session user binding (user A ≠ user B)")

from app.schemas.chat import ChatMessageRequest

# Build two mock users
class _MockUser:
    def __init__(self, uid: str):
        self.id       = uid
        self.timezone = "UTC"
        self.city     = None
        self.country  = None

user_a = _MockUser("user-a-uuid-000")
user_b = _MockUser("user-b-uuid-111")

shared_sid = f"shared-session-{uuid.uuid4()}"
with cs._sessions_lock:
    cs._sessions.pop(shared_sid, None)

# User A creates the session
def _fake_handle(session, sid, msg):
    return cs._make_response(sid, session, "ok")

with patch.object(cs, "_handle_broken", side_effect=_fake_handle):
    req_a = ChatMessageRequest(message="user A's problem", session_id=shared_sid)
    try:
        cs.process_message(None, user_a, req_a)
    except Exception:
        pass

# User B tries to access the same session_id
captured_sids = []
original_get_session = cs._get_session

def _track_sid(sid):
    result = original_get_session(sid)
    captured_sids.append(sid)
    return result

with patch.object(cs, "_get_session", side_effect=_track_sid), \
     patch.object(cs, "_handle_broken", side_effect=_fake_handle):
    req_b = ChatMessageRequest(message="user B hijack attempt", session_id=shared_sid)
    try:
        cs.process_message(None, user_b, req_b)
    except Exception:
        pass

# The session used for user B should NOT be shared_sid
if len(captured_sids) >= 2 and captured_sids[-1] != shared_sid:
    ok("User B redirected to new session — session hijack prevented")
elif len(captured_sids) >= 1:
    # Check if user binding actually created a different _user_id
    orig_sess = cs._sessions.get(shared_sid, {})
    if orig_sess.get("_user_id") == str(user_a.id):
        ok("Session still owned by user A after user B access attempt")
    else:
        fail(f"Session binding failed: _user_id={orig_sess.get('_user_id')}")
else:
    fail("Session binding test inconclusive")

# ─── Section 3: Concurrent ticket number generation ───────────────────────────
hdr("CONCURRENCY — No duplicate ticket numbers (10 concurrent escalations)")

# We cannot call escalate_to_ticket without a real DB, so we test
# _generate_ticket_number directly with a mocked DB session.

from app.services.chat_service import _generate_ticket_number, _ticket_creation_lock
from sqlalchemy.orm import Session as SASession

call_count   = 0
fake_max_seq = [0]  # mutable counter simulating MAX(ticket_number)

class _FakeDB:
    class _Query:
        def __init__(self, outer):
            self._outer = outer
        def scalar(self):
            # Simulate a real DB — returns the current max WITHOUT the lock
            # (so concurrent calls without the lock would produce duplicates)
            import time as _t; _t.sleep(0.001)  # simulate DB latency
            return f"T-{str(fake_max_seq[0]).zfill(4)}"

    class _QueryCount:
        def filter(self, *a, **kw): return self
        def count(self): return fake_max_seq[0]

    def query(self, *args):
        from app.models.ticket import Ticket as _T
        from sqlalchemy import func as _func
        # Check if this is a func.max call (for ticket number) or a count
        if args and hasattr(args[0], '__clause_element__'):
            return self._Query(self)
        return self._QueryCount()

generated_numbers = []
lock              = threading.Lock()

def _gen_one(db):
    with _ticket_creation_lock:   # exactly as escalate_to_ticket does
        num = _generate_ticket_number(db)
        # After reading MAX, simulate the commit that increments the real counter
        with lock:
            generated_numbers.append(num)
            # Extract numeric part and update fake_max_seq
            try:
                n = int(num.split("-")[1])
                if n > fake_max_seq[0]:
                    fake_max_seq[0] = n
            except Exception:
                pass

db_instances = [_FakeDB() for _ in range(10)]
threads      = [threading.Thread(target=_gen_one, args=(db_instances[i],)) for i in range(10)]
for t in threads: t.start()
for t in threads: t.join()

info(f"Generated numbers: {generated_numbers}")
duplicates = [n for n in generated_numbers if generated_numbers.count(n) > 1]
if duplicates:
    fail(f"Duplicate ticket numbers found: {set(duplicates)}")
else:
    ok(f"Zero duplicates across 10 concurrent ticket creations")

if len(set(generated_numbers)) == len(generated_numbers):
    ok(f"All {len(generated_numbers)} ticket numbers are unique")
else:
    fail(f"Ticket number collision detected")

# ─── Section 4: Slack session dict eviction thread-safety ────────────────────
hdr("CONCURRENCY — Slack session eviction (20 concurrent Slack users)")

from app.services.slack_chat_bridge import _get_or_create_session as _slack_get, _slack_to_session

# Clear existing
_slack_to_session.clear()

slack_errors = []

def _slack_user(uid: str):
    sid = _slack_get(uid)
    if not sid.startswith(f"slack_{uid}_"):
        slack_errors.append(f"Wrong session ID for {uid}: {sid}")

uids    = [f"U{uuid.uuid4().hex[:8]}" for _ in range(20)]
threads = [threading.Thread(target=_slack_user, args=(uid,)) for uid in uids]
for t in threads: t.start()
for t in threads: t.join()

if slack_errors:
    for e in slack_errors:
        fail(e)
else:
    ok(f"20 concurrent Slack users — all sessions correctly isolated")

# Verify mapping is 1:1
if len(_slack_to_session) == len(set(_slack_to_session.values())):
    ok("Slack session IDs are unique (no collisions)")
else:
    fail("Duplicate session IDs in Slack session map")

print("\n")
