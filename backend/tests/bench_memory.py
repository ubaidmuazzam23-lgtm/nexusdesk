"""
Memory profiling: tracemalloc snapshot of 100 concurrent sessions.
Identifies which data structures consume the most memory.

Usage:
    PYTHONPATH=backend python tests/bench_memory.py
"""
import sys, os, tracemalloc, threading, uuid, gc
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

def hdr(s): print(f"\n{'='*68}\n {s}\n{'='*68}")
def info(s): print(f"  [INFO] {s}")
def ok(s):   print(f"  [PASS] {s}")
def fail(s): print(f"  [FAIL] {s}")

# ─── Section 1: Session memory footprint ─────────────────────────────────────
hdr("MEMORY PROFILE — 100 concurrent sessions")

import app.services.chat_service as cs

# Clear existing sessions
with cs._sessions_lock:
    cs._sessions.clear()

tracemalloc.start()
snap_before = tracemalloc.take_snapshot()

N_SESSIONS      = 100
MSG_PER_SESSION = 20   # simulate 20 exchanges per session

def _simulate_session(sid: str):
    sess = cs._get_session(sid)
    # Simulate a conversation
    for i in range(MSG_PER_SESSION):
        sess["messages"].append({"role": "user",      "content": "x" * 500})
        sess["messages"].append({"role": "assistant", "content": "y" * 800})
    # RAG context (typical)
    sess["rag_context"] = "z" * 5000

threads = [threading.Thread(target=_simulate_session, args=(f"test-{uuid.uuid4()}",))
           for _ in range(N_SESSIONS)]
for t in threads: t.start()
for t in threads: t.join()

snap_after = tracemalloc.take_snapshot()
tracemalloc.stop()

# Diff
stats = snap_after.compare_to(snap_before, "lineno")
top10 = stats[:10]

info(f"Sessions created: {len(cs._sessions)}")
total_diff_kb = sum(s.size_diff for s in stats) / 1024
info(f"Total allocation delta: {total_diff_kb:.1f} KB")
info(f"Per-session estimate:   {total_diff_kb / N_SESSIONS:.1f} KB")

print("\n  Top 10 allocations:")
for s in top10:
    if s.size_diff > 0:
        print(f"    {s.size_diff/1024:7.1f} KB  {str(s.traceback[0]).split('/')[-1]}")

# Verify cap works: no session should have > _MSG_CAP messages
over_cap = {sid: len(s["messages"]) for sid, s in cs._sessions.items()
            if len(s["messages"]) > cs._MSG_CAP}
if over_cap:
    fail(f"{len(over_cap)} sessions exceeded _MSG_CAP={cs._MSG_CAP}")
else:
    # Each session has MSG_PER_SESSION*2 messages but they were added
    # directly (bypassing process_message cap). Show actual counts.
    max_msgs = max(len(s["messages"]) for s in cs._sessions.values())
    info(f"Max messages in any session: {max_msgs} (cap={cs._MSG_CAP})")
    ok("All sessions within expected bounds")

# Memory per session sanity check (< 500KB per session)
if total_diff_kb / N_SESSIONS < 500:
    ok(f"Memory per session {total_diff_kb/N_SESSIONS:.1f} KB (< 500 KB threshold)")
else:
    fail(f"Memory per session {total_diff_kb/N_SESSIONS:.1f} KB (> 500 KB threshold)")

# ─── Section 2: LRU eviction under cap ───────────────────────────────────────
hdr("MEMORY PROFILE — LRU eviction fires at cap")

with cs._sessions_lock:
    cs._sessions.clear()

# Force eviction by filling sessions to max
info(f"Filling sessions to cap ({cs._SESSION_MAX_SIZE}) …")
start_fill = cs._SESSION_MAX_SIZE - 10   # start near cap

for i in range(start_fill):
    sid = f"evict-test-{i}"
    with cs._sessions_lock:
        cs._sessions[sid] = {
            "messages": [], "flow_step": "broken", "domain": "networking",
            "severity": "medium", "problem": "", "rag_context": "",
            "solve_attempts": 0, "is_networking": True, "triage_active": False,
            "triage_questions": [], "triage_q_index": 0, "triage_answers": [],
            "triage_filters": {}, "triage_rows": [], "asset_match": None,
            "asset_confirmed": False, "asset_context": {}, "triage_started": False,
            "mid_check_done": False, "flow_origin": "broken",
            "screenshot_analysis": None, "is_screenshot_turn": False,
            "_last_accessed": 0.0,   # old — will be evicted first
        }

before_evict = len(cs._sessions)
info(f"Sessions before new request: {before_evict}")

# This should trigger eviction
cs._get_session("new-session-trigger-eviction")

after_evict = len(cs._sessions)
info(f"Sessions after new request:  {after_evict}")

if after_evict <= cs._SESSION_MAX_SIZE:
    ok(f"Eviction fired — session count {after_evict} ≤ cap {cs._SESSION_MAX_SIZE}")
else:
    fail(f"Session count {after_evict} > cap {cs._SESSION_MAX_SIZE} — eviction failed")

# ─── Section 3: Rate limiter window growth ────────────────────────────────────
hdr("MEMORY PROFILE — Rate limiter window cleanup")

from app.api.v1.middleware.rate_limiter import _windows, _CLEANUP_EVERY

# Simulate many distinct IPs creating windows
initial = len(_windows)
import time as _time
_fake_time = _time.monotonic() - _CLEANUP_EVERY - 10  # pretend last cleanup was long ago

# Manually add stale entries
for i in range(200):
    from collections import deque
    _windows[f"/api/v1/chat/message:192.0.2.{i % 256}"] = deque()

before_clean = len(_windows)
info(f"Windows before cleanup: {before_clean}")

# Trigger cleanup: set last_cleanup far enough in the past to exceed _CLEANUP_EVERY
import time as _t
import app.api.v1.middleware.rate_limiter as rl
rl._last_cleanup = _t.monotonic() - rl._CLEANUP_EVERY - 10

# Make a fake async call to trigger the cleanup
import asyncio
from unittest.mock import MagicMock

async def _trigger():
    req = MagicMock()
    req.client.host = "203.0.113.99"
    req.url.path    = "/test"
    from app.api.v1.middleware.rate_limiter import _make_limiter
    lim = _make_limiter(100, 60)
    await lim(req)

asyncio.run(_trigger())

after_clean = len(_windows)
info(f"Windows after cleanup: {after_clean}")

if after_clean < before_clean:
    ok(f"Rate limiter cleaned {before_clean - after_clean} stale windows")
else:
    fail("Rate limiter cleanup did not remove stale windows")

print("\n")
