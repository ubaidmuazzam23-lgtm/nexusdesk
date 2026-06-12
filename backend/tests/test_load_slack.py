#!/usr/bin/env python3
"""
Slack Bot Load Test
===================
Measures process_message() performance with Anthropic API mocked to return
instant responses — isolates our code latency from Claude API network time.

Run:  PYTHONPATH=. python tests/test_load_slack.py

Scenarios:
  BASELINE    — 1 user,   10 msgs (latency floor)
  NORMAL      — 50 users,  5 msgs each (250 total)
  HEAVY       — 200 users, 3 msgs each (600 total)
  SPIKE       — 500 users, 1 msg  each (500 total, all simultaneous)
  SOAK        — 50 users, continuous for 300 s (memory stability)
"""

import os
import sys
import gc
import uuid
import time
import statistics
import threading
from collections import defaultdict

# ── Env must be set BEFORE any app import ────────────────────────────────────
os.environ.setdefault("DATABASE_URL",      "postgresql://x:x@localhost/x")
os.environ.setdefault("JWT_SECRET_KEY",    "test-jwt-secret-minimum-32chars!!")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-dummy")
os.environ.setdefault("FRONTEND_URL",      "http://localhost:3000")

import app.services.chat_service as cs
from app.schemas.chat import ChatMessageRequest

# ── Anthropic mock ─────────────────────────────────────────────────────────

_ANALYSIS_REPLY = (
    "Run this command to check the BGP session status:\n"
    "Mac/Linux: show ip bgp summary\n"
    "Windows:   show ip bgp summary\n\n"
    "Look for State/PfxRcd — Idle means the session is not established."
    "\n\n"
    '<meta>{"domain":"networking","severity":"high","is_networking":"true"}</meta>'
)


def _r(text: str):
    c = type("C", (), {"text": text})()
    return type("R", (), {"content": [c]})()


class _MockMessages:
    """
    Stateless mock that returns plausible responses based on max_tokens.

    max_tokens=5   → _should_count_attempt    → "YES" (count the attempt)
    max_tokens=10  → intent / resolved checks → "NO" (keep troubleshooting)
    max_tokens=30  → timeline extraction      → "NEXT_SPRINT_ONLY"
    max_tokens=120 → screenshot display text  → short description
    max_tokens=300 → screenshot vision        → description
    max_tokens=400 → main AI analysis         → full reply with <meta>
    """

    @staticmethod
    def create(**kwargs):
        mt  = kwargs.get("max_tokens", 400)
        msg = (kwargs.get("messages") or [{}])[-1].get("content", "")

        if mt <= 5:
            return _r("YES")            # count this step as an attempt

        if mt <= 10:
            # Several different classifiers share max_tokens=10.
            # Return "NO" (not resolved / not consult / not wanting ticket)
            # so the conversation keeps going — most realistic.
            content_lower = str(msg).lower()
            if "broken" in content_lower or "outage" in content_lower:
                return _r("BROKEN")
            return _r("NO")

        if mt <= 30:
            return _r("NEXT_SPRINT_ONLY")

        if mt <= 120:
            return _r("Screenshot shows a BGP routing error in the terminal.")

        if mt <= 300:
            return _r(
                "The screenshot shows a terminal with 'show ip bgp summary' output. "
                "The BGP peer at 10.0.0.1 is in Idle state, indicating the session is not established."
            )

        # mt == 400 — main analysis reply
        return _r(_ANALYSIS_REPLY)


class _MockClient:
    messages = _MockMessages()


# Patch the global client BEFORE any sessions are created
cs._client = _MockClient()


# ── Fake User ─────────────────────────────────────────────────────────────────

class _FakeUser:
    __slots__ = ("id", "email", "timezone", "city", "country")

    def __init__(self, idx: int):
        self.id       = uuid.uuid4()
        self.email    = f"loadtest{idx}@example.com"
        self.timezone = "UTC"
        self.city     = None
        self.country  = None


# ── Conversation scripts ──────────────────────────────────────────────────────

# A realistic 5-turn broken→impacting→single-customer→problem→ai_analysis flow.
# Message 1 hits broken (no Claude call — keyword "not working").
# Messages 2-3 answer Yes/No flow questions (no Claude calls).
# Message 4 triggers AI analysis (mock Claude).
# Message 5 continues AI analysis (mock Claude).

_MSGS_5 = [
    "VPN is not working for remote users",   # broken step, keyword match
    "yes",                                   # customer impacting
    "no only one customer",                  # NOT multi-customer → waiting_problem
    "Users cannot connect to the VPN — shows authentication failed",  # waiting_problem → AI
    "I tried restarting the VPN service but users still cannot connect",  # ai_analysis
]

_MSGS_3 = _MSGS_5[:3]   # up to waiting_problem
_MSGS_1 = _MSGS_5[:1]   # just the opening message


# ── Runner ────────────────────────────────────────────────────────────────────

def _run_user(user: _FakeUser, messages: list, results: list, errors: list):
    """Send a sequence of messages for one user and record per-message latency."""
    sid = f"load-{uuid.uuid4().hex}"
    for msg_text in messages:
        try:
            req = ChatMessageRequest(message=msg_text, session_id=sid)
            t0  = time.perf_counter()
            cs.process_message(None, user, req)
            ms  = (time.perf_counter() - t0) * 1000
            results.append(ms)
        except Exception as exc:
            errors.append(str(exc))

    # Clean up in-memory session immediately after user finishes
    with cs._sessions_lock:
        cs._sessions.pop(sid, None)


# ── Stats ─────────────────────────────────────────────────────────────────────

def _stats(samples: list[float]) -> dict:
    if not samples:
        return {"count": 0}
    s = sorted(samples)
    n = len(s)
    return {
        "count": n,
        "min":   round(s[0], 2),
        "p50":   round(statistics.median(s), 2),
        "p95":   round(s[int(n * 0.95)], 2),
        "p99":   round(s[min(int(n * 0.99), n - 1)], 2),
        "max":   round(s[-1], 2),
    }


def _mem_mb() -> float:
    try:
        import psutil
        return round(psutil.Process().memory_info().rss / 1048576, 1)
    except Exception:
        return 0.0


# ── Scenario runner ───────────────────────────────────────────────────────────

DIVIDER = "═" * 68
TARGETS = {"p50_max": 200, "p95_max": 500, "err_max_pct": 1.0}


def scenario(
    name: str,
    n_users: int,
    messages: list,
    stagger_ms: float = 0,
) -> dict:
    """
    Spawn n_users threads, each calling _run_user(messages).
    Return stats dict.
    """
    results: list[float] = []
    errors:  list[str]   = []
    lock = threading.Lock()

    def _collect_results(r_list, e_list):
        with lock:
            results.extend(r_list)
            errors.extend(e_list)

    gc.collect()
    mem_before = _mem_mb()
    t_wall_start = time.perf_counter()

    threads = []
    for i in range(n_users):
        r_i, e_i = [], []
        user = _FakeUser(i)
        t = threading.Thread(
            target=lambda u=user, r=r_i, e=e_i: (
                _run_user(u, messages, r, e),
                _collect_results(r, e),
            ),
            daemon=True,
        )
        threads.append(t)

    # Stagger launches if requested
    for t in threads:
        t.start()
        if stagger_ms > 0:
            time.sleep(stagger_ms / 1000)

    for t in threads:
        t.join(timeout=120)

    wall_s   = time.perf_counter() - t_wall_start
    mem_after = _mem_mb()

    expected  = n_users * len(messages)
    completed = len(results)
    err_count = len(errors)
    err_pct   = err_count / max(1, completed + err_count) * 100
    rps       = completed / max(0.001, wall_s)

    st = _stats(results)

    print(f"\n{DIVIDER}")
    print(f"SCENARIO: {name}")
    print(f"  Users: {n_users}  ×  {len(messages)} msgs = {expected} expected")
    print(f"  Completed: {completed}  |  Errors: {err_count} ({err_pct:.2f}%)")
    print(f"  Wall time: {wall_s:.2f}s  |  Throughput: {rps:.1f} msg/s")
    if st.get("count"):
        print(f"  Latency  — min={st['min']}ms  p50={st['p50']}ms  "
              f"p95={st['p95']}ms  p99={st['p99']}ms  max={st['max']}ms")
    print(f"  Memory   — before={mem_before} MB  after={mem_after} MB  "
          f"delta={mem_after - mem_before:+.1f} MB")

    # Target checks
    t_p50 = st.get("p50", 9999)
    t_p95 = st.get("p95", 9999)
    print(f"  {'✓' if t_p50 <= TARGETS['p50_max'] else '✗'} p50 ≤ {TARGETS['p50_max']}ms   → {t_p50}ms")
    print(f"  {'✓' if t_p95 <= TARGETS['p95_max'] else '✗'} p95 ≤ {TARGETS['p95_max']}ms  → {t_p95}ms")
    print(f"  {'✓' if err_pct <= TARGETS['err_max_pct'] else '✗'} error rate ≤ {TARGETS['err_max_pct']}%   → {err_pct:.2f}%")
    print(f"  Server crashed? NO")

    if errors:
        print(f"  First errors: {errors[:3]}")

    return {
        "name":       name,
        "n_users":    n_users,
        "completed":  completed,
        "errors":     err_count,
        "err_pct":    err_pct,
        "rps":        round(rps, 1),
        "wall_s":     round(wall_s, 2),
        "mem_delta":  round(mem_after - mem_before, 1),
        **{f"lat_{k}": v for k, v in st.items() if k != "count"},
    }


# ── Soak test ─────────────────────────────────────────────────────────────────

def soak_test(n_users: int = 50, duration_s: int = 300):
    """
    Run n_users concurrently for duration_s seconds.
    Each user sends messages in a loop.
    Track latency in 30-second windows and memory every 30 seconds.
    """
    print(f"\n{DIVIDER}")
    print(f"SCENARIO: SOAK — {n_users} users × {duration_s}s")

    stop_event = threading.Event()
    all_latencies: list[float] = []
    window_data: dict[int, list] = defaultdict(list)   # window_idx → [ms, ...]
    errors: list[str] = []
    lock = threading.Lock()
    t_start = time.perf_counter()

    def _soak_user(user_idx: int):
        user = _FakeUser(user_idx)
        msg_cycle = list(_MSGS_5)  # 5-turn cycle
        cycle_pos  = 0
        sid = f"soak-{uuid.uuid4().hex}"

        while not stop_event.is_set():
            msg_text = msg_cycle[cycle_pos % len(msg_cycle)]
            try:
                req = ChatMessageRequest(message=msg_text, session_id=sid)
                t0  = time.perf_counter()
                cs.process_message(None, user, req)
                ms  = (time.perf_counter() - t0) * 1000
                elapsed = t0 - t_start
                window  = int(elapsed // 30)
                with lock:
                    all_latencies.append(ms)
                    window_data[window].append(ms)
            except Exception as exc:
                with lock:
                    errors.append(str(exc))

            cycle_pos += 1

            # Reset session every 5 messages so we don't accumulate context forever
            if cycle_pos % 5 == 0:
                with cs._sessions_lock:
                    cs._sessions.pop(sid, None)
                sid = f"soak-{uuid.uuid4().hex}"

    # Launch soak users
    threads = [threading.Thread(target=_soak_user, args=(i,), daemon=True)
               for i in range(n_users)]

    mem_samples: list[tuple] = []  # (elapsed_s, mb)
    gc.collect()

    for t in threads:
        t.start()

    # Monitor memory every 30 s while the test runs
    deadline = time.perf_counter() + duration_s
    while time.perf_counter() < deadline:
        elapsed = time.perf_counter() - t_start
        mem_samples.append((round(elapsed, 0), _mem_mb()))
        time.sleep(30)

    stop_event.set()
    for t in threads:
        t.join(timeout=15)

    # Report
    total = len(all_latencies)
    wall_s = time.perf_counter() - t_start
    rps    = total / max(0.001, wall_s)
    err_pct = len(errors) / max(1, total + len(errors)) * 100

    print(f"  Total messages: {total}  |  Throughput: {rps:.1f} msg/s")
    print(f"  Errors: {len(errors)} ({err_pct:.2f}%)")
    print()

    # Per-window latency (check for degradation)
    print("  Latency per 30-second window:")
    windows_p95 = []
    for w in sorted(window_data.keys()):
        wdata = sorted(window_data[w])
        if not wdata:
            continue
        wp95 = wdata[int(len(wdata) * 0.95)]
        wp50 = statistics.median(wdata)
        windows_p95.append(wp95)
        t_offset = w * 30
        print(f"    t={t_offset:3d}–{t_offset+30:3d}s  "
              f"msgs={len(wdata):5d}  p50={wp50:.1f}ms  p95={wp95:.1f}ms")

    # Check degradation: last window p95 vs first window p95
    if len(windows_p95) >= 2:
        first, last = windows_p95[0], windows_p95[-1]
        degraded = last > first * 1.5   # >50% worse = degraded
        print(f"\n  Degradation check: first-window p95={first:.1f}ms  "
              f"last-window p95={last:.1f}ms  "
              f"→ {'DEGRADED ✗' if degraded else 'STABLE ✓'}")

    # Memory trend
    print(f"\n  Memory samples:")
    for ts, mb in mem_samples:
        print(f"    t={ts:4.0f}s  {mb:.1f} MB")
    if len(mem_samples) >= 4:
        # Skip the first sample (GC burst at startup). Compare median of first
        # third vs median of last third so GC cycle phase doesn't skew the result.
        vals = [m for _, m in mem_samples[1:]]
        n3 = max(1, len(vals) // 3)
        drift = statistics.median(vals[-n3:]) - statistics.median(vals[:n3])
        stable = drift < 30   # memory growing >30 MB sustained = possible leak
        print(f"  Memory trend (median first vs last third): {drift:+.1f} MB"
              f" → {'STABLE ✓' if stable else 'LEAKING ✗'}")

    # Overall targets
    st = _stats(all_latencies)
    print(f"\n  Overall latency: p50={st.get('p50')}ms  p95={st.get('p95')}ms  p99={st.get('p99')}ms")
    print(f"  {'✓' if st.get('p50', 9999) <= TARGETS['p50_max'] else '✗'} p50 ≤ {TARGETS['p50_max']}ms")
    print(f"  {'✓' if st.get('p95', 9999) <= TARGETS['p95_max'] else '✗'} p95 ≤ {TARGETS['p95_max']}ms")
    print(f"  {'✓' if err_pct <= TARGETS['err_max_pct'] else '✗'} error rate ≤ {TARGETS['err_max_pct']}%")
    print(f"  Server crashed? NO")

    # Cleanup soak sessions
    with cs._sessions_lock:
        stale = [k for k in list(cs._sessions.keys()) if k.startswith("soak-")]
        for k in stale:
            cs._sessions.pop(k, None)


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 68)
    print("SLACK BOT LOAD TEST  — Anthropic API mocked (0ms Claude latency)")
    print("=" * 68)
    print(f"  Initial memory: {_mem_mb()} MB")
    print(f"  Redis available: {cs._get_redis() is not None}")

    # ── BASELINE ─────────────────────────────────────────────────────────────
    scenario("BASELINE — 1 user, 10 messages",
             n_users=1, messages=_MSGS_5 * 2)

    time.sleep(0.5)

    # ── NORMAL LOAD ──────────────────────────────────────────────────────────
    scenario("NORMAL LOAD — 50 concurrent users × 5 msgs",
             n_users=50, messages=_MSGS_5)

    time.sleep(1)

    # ── HEAVY LOAD ───────────────────────────────────────────────────────────
    scenario("HEAVY LOAD — 200 concurrent users × 3 msgs",
             n_users=200, messages=_MSGS_3)

    time.sleep(1)

    # ── SPIKE ────────────────────────────────────────────────────────────────
    scenario("SPIKE — 500 users × 1 msg (simultaneous)",
             n_users=500, messages=_MSGS_1)

    time.sleep(1)

    # ── SOAK (5 minutes) ─────────────────────────────────────────────────────
    soak_test(n_users=50, duration_s=300)

    print(f"\n{DIVIDER}")
    print("LOAD TEST COMPLETE")
    print(f"  Final memory: {_mem_mb()} MB")
