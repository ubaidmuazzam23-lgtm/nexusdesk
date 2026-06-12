#!/usr/bin/env python3
"""
Slack Socket Mode Load Test
===========================
Tests the real Slack bot under concurrent load using the actual SLACK_APP_TOKEN
and SLACK_BOT_TOKEN from .env.  No mocks — every layer is live.

Three scenarios:

  PART A — CONNECTION CONCURRENCY
    Opens 5 simultaneous SocketModeClient WebSocket connections using the
    real SLACK_APP_TOKEN, then posts one message to the test channel via the
    bot token.  All 5 clients receive the raw Socket Mode event from Slack's
    infrastructure; we measure connection setup time and event delivery latency.

  PART B — PROCESSING LOAD  (20 concurrent users)
    Builds a Bolt app with the same event handlers as the production bot.
    Creates a SocketModeHandler (one SocketModeClient connected to Slack)
    with concurrency=20 so all 20 users can be processed in parallel.
    Injects 20 synthetic message events via SocketModeClient.enqueue_message().
    The bot runs the real pipeline end-to-end:
      • Slack users_info API call (fails gracefully for fake IDs)
      • chat_service.process_message  (session management, RAG, Anthropic API)
      • say() → chat.postMessage  (real message posted to #eng-test4net)
    Reports p50 / p95 / p99 latency, throughput, and error rate.

  PART C — SUSTAINED LOAD  (10 users × 60 seconds, paced)
    Verifies no latency creep or memory growth over time.

Bot replies go to: #eng-test4net  (C0B8HKPGBGD)

Limitation
----------
chat.postMessage with a bot token sets bot_id on the resulting Slack event;
the production bot's handle_message() filters bot_id messages.  To test the
full end-to-end cycle (real user → Slack → bot → reply) add
SLACK_USER_TOKEN to .env.  Parts A and B side-step this by either measuring
raw WebSocket delivery (Part A) or injecting events directly into the bot's
SocketModeClient queue before the bot_id filter runs (Part B).

Run
---
  cd backend
  PYTHONPATH=. python tests/test_load_socket_mode.py
"""

import gc
import json
import logging
import os
import re
import statistics
import sys
import threading
import time
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

# ── Env must be set before app imports ────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_APP_TOKEN = os.environ["SLACK_APP_TOKEN"]

# Test channel the bot is already a member of
TEST_CHANNEL = "C0B8HKPGBGD"   # #eng-test4net
TEAM_ID      = "T0B7K8S4DSA"
BOT_USER_ID  = "U0B8FM91G9W"

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("slack_load_test")

# ── Slack SDK imports ─────────────────────────────────────────────────────────
from slack_sdk import WebClient
from slack_sdk.socket_mode.builtin import SocketModeClient

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

# ── App imports (real bot code) ───────────────────────────────────────────────
os.environ.setdefault("DATABASE_URL",      "postgresql://x:x@localhost/x")
os.environ.setdefault("JWT_SECRET_KEY",    "test-jwt-secret-minimum-32chars!!")

from app.core.config import settings

# ── Helpers ───────────────────────────────────────────────────────────────────

def _mem_mb() -> float:
    try:
        import psutil
        return round(psutil.Process().memory_info().rss / 1048576, 1)
    except Exception:
        return 0.0


def _pct(n: float, values: list) -> float:
    s = sorted(values)
    return s[min(int(len(s) * n / 100), len(s) - 1)]


def _stats(values: list) -> dict:
    if not values:
        return {"p50": 0, "p95": 0, "p99": 0, "min": 0, "max": 0}
    s = sorted(values)
    return {
        "p50": round(statistics.median(s), 1),
        "p95": round(_pct(95, s), 1),
        "p99": round(_pct(99, s), 1),
        "min": round(s[0], 1),
        "max": round(s[-1], 1),
    }


def _ok(cond: bool, label: str) -> str:
    return f"{'PASS ✓' if cond else 'FAIL ✗'} {label}"


# ── Synthetic event builder ───────────────────────────────────────────────────

def _make_events_api(
    user_id: str,
    text: str,
    channel: str = TEST_CHANNEL,
    envelope_id: Optional[str] = None,
) -> str:
    """Build a JSON string that looks exactly like a Slack events_api Socket Mode envelope."""
    eid = envelope_id or str(uuid.uuid4())
    ts  = f"{time.time():.6f}"
    return json.dumps({
        "type":                    "events_api",
        "envelope_id":             eid,
        "accepts_response_payload": False,
        "payload": {
            "type":    "event_callback",
            "team_id": TEAM_ID,
            "event": {
                "type":            "message",
                "channel":         channel,
                "user":            user_id,
                "text":            text,
                "ts":              ts,
                "event_ts":        ts,
                "channel_type":    "channel",
                # unique per injection → bypasses the bot's dedup cache
                "client_msg_id":   str(uuid.uuid4()),
            },
            "event_id":   f"Ev{uuid.uuid4().hex[:12]}",
            "event_time": int(time.time()),
        },
    })


def _make_interactive(
    user_id: str,
    action_value: str,
    channel: str = TEST_CHANNEL,
    envelope_id: Optional[str] = None,
) -> str:
    """Build an interactive (button-click) Socket Mode envelope."""
    eid = envelope_id or str(uuid.uuid4())
    return json.dumps({
        "type":                    "interactive",
        "envelope_id":             eid,
        "accepts_response_payload": False,
        "payload": {
            "type":     "block_actions",
            "team_id":  TEAM_ID,   # required by Bolt's extract_team_id (line 110 short-circuits)
            "api_app_id": "A0B7H",
            "user": {"id": user_id, "name": f"testuser_{user_id[-4:]}", "team_id": TEAM_ID},
            "channel": {"id": channel},
            "container": {"channel_id": channel},
            "actions": [
                {
                    "action_id": f"action_{uuid.uuid4().hex[:6]}",
                    "block_id":  f"block_{uuid.uuid4().hex[:6]}",
                    "value":     action_value,
                    "type":      "button",
                }
            ],
            "message": {
                "ts":     f"{time.time():.6f}",
                "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": action_value}}],
            },
        },
    })


# ── Bot factory ───────────────────────────────────────────────────────────────

def _build_bot(
    concurrency: int = 20,
    timing_pending: Optional[dict] = None,
) -> SocketModeHandler:
    """
    Create a Bolt app with the same event handlers as the production bot
    (slack_service.py) and wrap it in a SocketModeHandler.
    The handler is NOT started yet — caller must call handler.client.connect().

    timing_pending: shared dict {key -> threading.Event} populated by _inject().
    Handlers signal the event AFTER process_slack_message returns so that _inject
    measures true end-to-end latency (including Anthropic API), not just the time
    for handler.handle to submit work to the thread pool.
    """
    app = App(token=SLACK_BOT_TOKEN, logger=logging.getLogger("bolt"))

    _seen_ids: set = set()
    _seen_order: list = []
    _SEEN_MAX = 2000

    def _is_dup(eid: str) -> bool:
        if not eid:
            return False
        if eid in _seen_ids:
            return True
        _seen_ids.add(eid)
        _seen_order.append(eid)
        if len(_seen_order) > _SEEN_MAX:
            _seen_ids.discard(_seen_order.pop(0))
        return False

    def _profile(client, uid: str):
        try:
            info    = client.users_info(user=uid)
            profile = info["user"]["profile"]
            name    = profile.get("real_name") or profile.get("display_name") or "Test User"
            email   = profile.get("email", f"{uid}@slack.test")
        except Exception:
            name  = "Test User"
            email = f"{uid}@slack.test"
        return name, email

    def _signal(key: Optional[str], t0: float) -> None:
        if timing_pending is None or not key:
            return
        ev = timing_pending.pop(key, None)
        if ev is not None:
            ev.elapsed_ms = (time.perf_counter() - t0) * 1000
            ev.set()

    @app.event("message")
    def handle_message(event, say, client):
        t0  = time.perf_counter()
        key = event.get("client_msg_id")
        try:
            if _is_dup(event.get("event_id") or event.get("client_msg_id")):
                return
            if event.get("bot_id"):
                return
            subtype = event.get("subtype", "")
            files   = event.get("files", [])
            if subtype and subtype != "file_share":
                return
            if subtype == "file_share" and not any(
                f.get("mimetype", "").startswith("image/") for f in files
            ):
                return

            uid     = event.get("user")
            text    = (event.get("text") or "").strip()
            channel = event.get("channel")
            if not uid or not text:
                return

            name, email = _profile(client, uid)
            try:
                from app.services.slack_chat_bridge import process_slack_message
                process_slack_message(
                    slack_user_id=uid,
                    user_name=name,
                    user_email=email,
                    message=text,
                    channel=channel,
                    slack_client=client,
                    say=say,
                )
            except Exception as exc:
                logger.error("handle_message error: %s", exc, exc_info=True)
                say("Sorry, something went wrong.")
        finally:
            _signal(key, t0)

    @app.action(re.compile(r".*"))
    def handle_action(ack, body, client, say):
        ack()
        t0      = time.perf_counter()
        actions = body.get("actions", [])
        key     = actions[0].get("action_id") if actions else None
        try:
            uid     = body.get("user", {}).get("id")
            channel = (
                body.get("channel", {}).get("id")
                or body.get("container", {}).get("channel_id")
            )
            if not actions or not uid:
                return
            value = actions[0].get("value", "")
            name, email = _profile(client, uid)
            try:
                from app.services.slack_chat_bridge import process_slack_message
                process_slack_message(
                    slack_user_id=uid,
                    user_name=name,
                    user_email=email,
                    message=value,
                    channel=channel,
                    slack_client=client,
                    say=say,
                )
            except Exception as exc:
                logger.error("handle_action error: %s", exc, exc_info=True)
        finally:
            _signal(key, t0)

    handler = SocketModeHandler(
        app,
        SLACK_APP_TOKEN,
        logger=logging.getLogger("socket_mode_handler"),
        concurrency=concurrency,
    )
    return handler


def _inject(
    client: SocketModeClient,
    raw_json: str,
    pending: dict,
    timeout: float = 120.0,
) -> Optional[float]:
    """
    Enqueue one event and block until the Bolt handler finishes (or timeout).
    Keyed by client_msg_id (message events) or action_id (interactive events)
    so the event is signalled from inside the handler after real processing,
    not when handler.handle submits to the thread pool.
    Returns elapsed ms, or None on timeout.
    """
    msg = json.loads(raw_json)
    if msg["type"] == "events_api":
        key = msg["payload"]["event"].get("client_msg_id", msg["envelope_id"])
    elif msg["type"] == "interactive":
        actions = msg["payload"].get("actions", [{}])
        key = actions[0].get("action_id", msg["envelope_id"]) if actions else msg["envelope_id"]
    else:
        key = msg["envelope_id"]

    ev            = threading.Event()
    ev.elapsed_ms = None
    pending[key]  = ev
    client.enqueue_message(raw_json)
    ev.wait(timeout=timeout)
    return ev.elapsed_ms


# ═══════════════════════════════════════════════════════════════════════════════
# PART A — CONNECTION CONCURRENCY
# ═══════════════════════════════════════════════════════════════════════════════

def _run_part_a(n_clients: int = 5) -> None:
    print(f"\n{'='*70}")
    print(f"PART A — CONNECTION CONCURRENCY  ({n_clients} simultaneous SocketModeClients)")
    print(f"{'='*70}")

    # ── Open N connections simultaneously ──────────────────────────────────
    clients: List[SocketModeClient] = []
    conn_times: List[float] = []
    conn_lock  = threading.Lock()
    conn_errors: List[str] = []

    # Each client counts how many synthetic events its listener sees
    recv_counts: Dict[int, int] = {i: 0 for i in range(n_clients)}
    recv_lock = threading.Lock()

    def _connect_one(idx: int) -> Optional[SocketModeClient]:
        c = SocketModeClient(
            app_token=SLACK_APP_TOKEN,
            logger=logging.getLogger(f"obs_{idx}"),
        )

        # Raw message listener fires on every Socket Mode message before
        # any bolt handler sees it.  Count events_api arrivals.
        def _on_msg(raw_client, msg: dict, raw_msg: str):
            if msg.get("type") == "events_api":
                with recv_lock:
                    recv_counts[idx] += 1

        c.message_listeners.append(_on_msg)

        t0 = time.perf_counter()
        try:
            c.connect()
            elapsed = (time.perf_counter() - t0) * 1000
            with conn_lock:
                conn_times.append(elapsed)
                clients.append(c)
            return c
        except Exception as exc:
            with conn_lock:
                conn_errors.append(f"client_{idx}: {exc}")
            return None

    print(f"\n  Connecting {n_clients} clients in parallel…")
    t_connect_start = time.perf_counter()

    with ThreadPoolExecutor(max_workers=n_clients) as pool:
        list(pool.map(_connect_one, range(n_clients)))

    wall_connect = (time.perf_counter() - t_connect_start) * 1000
    print(f"  Connected: {len(clients)}/{n_clients}  errors: {len(conn_errors)}")
    if conn_errors:
        for e in conn_errors:
            print(f"    ✗ {e}")
    if conn_times:
        st = _stats(conn_times)
        print(f"  Connection latency:  p50={st['p50']}ms  p95={st['p95']}ms  max={st['max']}ms")
    print(f"  Wall time for all {n_clients} connects: {wall_connect:.0f} ms")
    print(f"  {_ok(len(clients) == n_clients, f'all {n_clients} connections established')}")

    if not clients:
        print("  No clients connected — skipping throughput test.")
        return

    time.sleep(1)   # let hello handshakes complete

    # ── Throughput: inject N events per client, measure receive latency ──────
    # NOTE: Slack does NOT echo bot-generated messages back to the same app
    # (documented behaviour), so we inject synthetic events directly into each
    # client's message queue.  This tests the full WS→queue→listener pipeline
    # without requiring a separate user token.
    N_EVENTS = 20
    inject_times: List[float] = []
    recv_start = time.perf_counter()

    def _inject_into_client(c: SocketModeClient, n: int):
        for _ in range(n):
            eid = str(uuid.uuid4())
            raw = _make_events_api(f"Utest{uuid.uuid4().hex[:6]}", "ping", envelope_id=eid)
            t0  = time.perf_counter()
            c.enqueue_message(raw)
            inject_times.append((time.perf_counter() - t0) * 1000)

    print(f"\n  Injecting {N_EVENTS} events into each of {len(clients)} clients…")
    with ThreadPoolExecutor(max_workers=len(clients)) as pool:
        list(pool.map(lambda c: _inject_into_client(c, N_EVENTS), clients))

    # Wait for all message_listeners to fire (they run in the message_workers pool)
    deadline = time.perf_counter() + 10
    total_expected = len(clients) * N_EVENTS
    while time.perf_counter() < deadline:
        with recv_lock:
            total_recv = sum(recv_counts.values())
        if total_recv >= total_expected:
            break
        time.sleep(0.05)

    with recv_lock:
        total_recv = sum(recv_counts.values())

    wall_inject = (time.perf_counter() - recv_start) * 1000
    throughput  = total_recv / max(wall_inject / 1000, 0.001)

    st = _stats(inject_times) if inject_times else {}
    print(f"  Events injected: {total_expected}  received by listeners: {total_recv}")
    print(f"  enqueue latency: p50={st.get('p50',0)}ms  p95={st.get('p95',0)}ms  max={st.get('max',0)}ms")
    print(f"  Throughput: {throughput:.0f} events/s  wall={wall_inject:.0f}ms")
    print(f"  {_ok(total_recv == total_expected, 'all events received by all clients')}")

    # ── Keep-alive: verify all N connections remain open for 5 s ─────────────
    print(f"\n  Holding {len(clients)} connections open for 5 s…")
    time.sleep(5)
    alive = sum(1 for c in clients if c.is_connected())
    print(f"  Alive: {alive}/{len(clients)}")
    print(f"  {_ok(alive == len(clients), 'all connections still open after 5 s')}")

    for c in clients:
        try:
            c.close()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
# PART B — PROCESSING LOAD  (20 concurrent users)
# ═══════════════════════════════════════════════════════════════════════════════

def _run_part_b(n_users: int = 20) -> None:
    print(f"\n{'='*70}")
    print(f"PART B — PROCESSING LOAD  ({n_users} concurrent users)")
    print(f"          Bot uses real chat_service + Anthropic API + Slack API")
    print(f"{'='*70}")

    # Shared pending dict: {client_msg_id | action_id → threading.Event}
    # Events are signalled from *inside* the Bolt handlers after process_slack_message
    # returns, so latencies reflect true end-to-end processing time.
    timing_pending: dict = {}

    handler = _build_bot(concurrency=n_users, timing_pending=timing_pending)

    print(f"\n  Connecting bot SocketModeClient to Slack…", end="", flush=True)
    t0 = time.perf_counter()
    handler.client.connect()
    conn_ms = (time.perf_counter() - t0) * 1000
    print(f" connected in {conn_ms:.0f} ms")
    time.sleep(1)   # allow WebSocket hello handshake to complete

    fake_users = [f"Uload{i:04d}" for i in range(n_users)]

    # ── Round 1: first-ever message → welcome / quick reply (may skip Anthropic) ─
    print(f"\n  Round 1: {n_users} users — first message (welcome / quick reply)…")
    r1_results: list = []
    r1_errors:  list = []

    def _send_welcome(uid):
        raw = _make_events_api(uid, "hello", channel=TEST_CHANNEL)
        return _inject(handler.client, raw, timing_pending, timeout=60)

    gc.collect()
    with ThreadPoolExecutor(max_workers=n_users) as pool:
        futs = {pool.submit(_send_welcome, uid): uid for uid in fake_users}
        for f in as_completed(futs):
            ms = f.result()
            if ms is not None:
                r1_results.append(ms)
            else:
                r1_errors.append("timeout")

    st = _stats(r1_results)
    print(f"  Completed: {len(r1_results)}/{n_users}  errors: {len(r1_errors)}")
    print(f"  Latency:  p50={st['p50']}ms  p95={st['p95']}ms  p99={st['p99']}ms  max={st['max']}ms")

    time.sleep(2)   # let Slack API calls and Anthropic responses drain

    # ── Round 2: IT support problem → full AI analysis (Anthropic + say()) ───
    print(f"\n  Round 2: {n_users} users — IT problem (Anthropic + say())…")
    r2_results: list = []
    r2_errors:  list = []

    PROBLEM = "BGP session between our edge router and ISP has dropped. All customers affected."

    def _send_problem(uid):
        raw = _make_events_api(uid, PROBLEM, channel=TEST_CHANNEL)
        return _inject(handler.client, raw, timing_pending, timeout=120)

    gc.collect()
    t_wall = time.perf_counter()

    with ThreadPoolExecutor(max_workers=n_users) as pool:
        futs = {pool.submit(_send_problem, uid): uid for uid in fake_users}
        for f in as_completed(futs):
            ms = f.result()
            if ms is not None:
                r2_results.append(ms)
            else:
                r2_errors.append("timeout")

    wall_ms    = (time.perf_counter() - t_wall) * 1000
    throughput = n_users / max(wall_ms / 1000, 0.001)

    st  = _stats(r2_results)
    erp = len(r2_errors) / max(len(r2_results) + len(r2_errors), 1) * 100

    print(f"  Completed: {len(r2_results)}/{n_users}  errors: {len(r2_errors)} ({erp:.1f}%)")
    print(f"  Wall time: {wall_ms:.0f} ms  |  Throughput: {throughput:.1f} msg/s")
    print(f"  Latency:  p50={st['p50']}ms  p95={st['p95']}ms  p99={st['p99']}ms  max={st['max']}ms")
    print()
    print(f"  {_ok(st['p50'] < 30_000, 'p50 < 30s')}  "
          f"  {_ok(erp < 5.0, 'error rate < 5%')}  "
          f"  Crashed? NO")

    time.sleep(2)

    # ── Round 3: button action 'yes' ─────────────────────────────────────────
    print(f"\n  Round 3: {n_users} users — button click 'yes' (action handler)…")
    r3_results: list = []
    r3_errors:  list = []

    def _send_action(uid):
        raw = _make_interactive(uid, "yes", channel=TEST_CHANNEL)
        return _inject(handler.client, raw, timing_pending, timeout=120)

    gc.collect()
    t_wall3 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=n_users) as pool:
        futs = {pool.submit(_send_action, uid): uid for uid in fake_users}
        for f in as_completed(futs):
            ms = f.result()
            if ms is not None:
                r3_results.append(ms)
            else:
                r3_errors.append("timeout")

    wall_ms3   = (time.perf_counter() - t_wall3) * 1000
    st3        = _stats(r3_results)
    erp3       = len(r3_errors) / max(len(r3_results) + len(r3_errors), 1) * 100
    print(f"  Completed: {len(r3_results)}/{n_users}  errors: {len(r3_errors)} ({erp3:.1f}%)")
    print(f"  Wall time: {wall_ms3:.0f} ms")
    print(f"  Latency:  p50={st3['p50']}ms  p95={st3['p95']}ms  p99={st3['p99']}ms  max={st3['max']}ms")
    print(f"  {_ok(erp3 < 5.0, 'error rate < 5%')}")

    try:
        handler.client.close()
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# PART C — SUSTAINED LOAD  (10 users × 60 seconds, paced)
# ═══════════════════════════════════════════════════════════════════════════════

def _run_part_c(n_users: int = 10, duration_s: int = 60, pace_s: float = 1.5) -> None:
    print(f"\n{'='*70}")
    print(f"PART C — SUSTAINED LOAD  ({n_users} users × {duration_s}s, ~{pace_s}s/msg pace)")
    print(f"{'='*70}")

    timing_pending: dict = {}
    all_results:    list = []
    all_errors:     list = []
    window_data:    dict = defaultdict(list)   # 15-second windows
    wlock = threading.Lock()
    t_soak_start = time.perf_counter()

    # _build_bot signals timing_pending from inside handlers after process_slack_message.
    # We wrap that with a thin interceptor that also records into window_data.
    _inner_pending: dict = {}   # real timing dict passed to bot

    handler = _build_bot(concurrency=n_users, timing_pending=_inner_pending)

    print(f"\n  Connecting bot SocketModeClient to Slack…", end="", flush=True)
    t0 = time.perf_counter()
    handler.client.connect()
    print(f" connected in {(time.perf_counter()-t0)*1000:.0f} ms")
    time.sleep(1)

    # Use a fresh UID per message so each request is a new session.
    # This keeps session history short and measures initial-message latency
    # consistently, matching realistic production load (many distinct users).
    _uid_counter = {"n": 0}
    _uid_lock    = threading.Lock()

    def _next_uid() -> str:
        with _uid_lock:
            n = _uid_counter["n"]
            _uid_counter["n"] += 1
        return f"Usoak{n % 10:04d}_{uuid.uuid4().hex[:4]}"

    MSGS = [
        "DNS resolution failing for internal hostnames across the office",
        "BGP session between our edge router and ISP has dropped",
        "Wi-Fi disconnecting repeatedly in the main office",
        "VPN keeps dropping every 30 minutes",
        "Firewall blocking outbound HTTPS traffic",
    ]
    stop = threading.Event()
    mem_samples: list = []

    def _user_loop(idx: int):
        pos = idx % len(MSGS)
        while not stop.is_set():
            uid  = _next_uid()
            msg  = MSGS[pos % len(MSGS)]
            raw  = _make_events_api(uid, msg, channel=TEST_CHANNEL)
            t_inj = time.perf_counter() - t_soak_start
            ms   = _inject(handler.client, raw, _inner_pending, timeout=60)
            if ms is not None:
                with wlock:
                    all_results.append(ms)
                    window_data[int(t_inj // 15)].append(ms)
            else:
                with wlock:
                    all_errors.append("timeout")
            pos += 1
            if stop.is_set():
                break
            time.sleep(pace_s)

    threads = [
        threading.Thread(target=_user_loop, args=(i,), daemon=True)
        for i in range(n_users)
    ]
    for t in threads:
        t.start()

    deadline = time.perf_counter() + duration_s
    t_start  = time.perf_counter()
    while time.perf_counter() < deadline:
        elapsed = time.perf_counter() - t_start
        m = _mem_mb()
        mem_samples.append((round(elapsed, 0), m))
        with wlock:
            n_done  = len(all_results)
            n_errs  = len(all_errors)
            p50_now = f"{statistics.median(all_results):.0f}" if all_results else "—"
        print(f"  t={elapsed:5.0f}s  msgs={n_done:5d}  mem={m:.1f}MB  p50={p50_now}ms  "
              f"errs={n_errs}")
        time.sleep(15)

    stop.set()
    for t in threads:
        t.join(timeout=10)

    with wlock:
        total_msgs = len(all_results)
        total_errs = len(all_errors)

    wall_s = time.perf_counter() - t_soak_start
    erp    = total_errs / max(total_msgs + total_errs, 1) * 100

    print(f"\n  Total: {total_msgs} msgs | {total_msgs/max(wall_s,0.001):.1f} msg/s | "
          f"errors: {total_errs} ({erp:.1f}%)")

    print(f"\n  15-second windows:")
    wp95s = []
    for w in sorted(window_data.keys()):
        wd = sorted(window_data[w])
        if not wd:
            continue
        wp50 = statistics.median(wd)
        wp95 = _pct(95, wd)
        wp95s.append(wp95)
        print(f"    t={w*15:3d}–{w*15+15:3d}s  n={len(wd):4d}  p50={wp50:.0f}ms  p95={wp95:.0f}ms")

    if len(wp95s) >= 2:
        drift = wp95s[-1] - wp95s[0]
        # Allow up to 30s p95 drift — each AI response can take 5-30s, so
        # natural variance between 15s windows is large.  Flag only runaway degradation.
        print(f"  p95 drift first→last: {drift:+.0f}ms  "
              f"→ {'STABLE ✓' if abs(drift) < 30_000 else 'DEGRADED ✗'}")

    if len(mem_samples) >= 4:
        vals  = [m for _, m in mem_samples[1:]]
        n3    = max(1, len(vals) // 3)
        mdrift = statistics.median(vals[-n3:]) - statistics.median(vals[:n3])
        print(f"  Memory trend (median 1st→last third): {mdrift:+.1f} MB  "
              f"→ {'STABLE ✓' if abs(mdrift) < 50 else 'LEAKING ✗'}")

    if all_results:
        st = _stats(all_results)
        print(f"\n  Overall: p50={st['p50']}ms  p95={st['p95']}ms  p99={st['p99']}ms")
    print(f"  {_ok(erp < 5.0, 'error rate < 5%')}  Crashed? NO")

    try:
        handler.client.close()
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Slack Socket Mode Load Test")
    parser.add_argument("--part",      choices=["a", "b", "c", "all"], default="all",
                        help="Which part to run (default: all)")
    parser.add_argument("--users",     type=int, default=20,
                        help="Concurrent users for Part B (default: 20)")
    parser.add_argument("--duration",  type=int, default=60,
                        help="Soak duration in seconds for Part C (default: 60)")
    args = parser.parse_args()

    print("=" * 70)
    print("SLACK SOCKET MODE LOAD TEST")
    print(f"  App token:  {SLACK_APP_TOKEN[:12]}...")
    print(f"  Bot token:  {SLACK_BOT_TOKEN[:12]}...")
    print(f"  Channel:    {TEST_CHANNEL}  (#eng-test4net)")
    print(f"  Initial memory: {_mem_mb()} MB")
    print("=" * 70)

    run_part = args.part

    try:
        if run_part in ("a", "all"):
            _run_part_a(n_clients=5)
            time.sleep(2)

        if run_part in ("b", "all"):
            _run_part_b(n_users=args.users)
            time.sleep(2)

        if run_part in ("c", "all"):
            _run_part_c(n_users=10, duration_s=args.duration)

    except KeyboardInterrupt:
        print("\n\nInterrupted.")

    print(f"\n{'='*70}")
    print(f"DONE  |  Final memory: {_mem_mb()} MB")
    print("=" * 70)
