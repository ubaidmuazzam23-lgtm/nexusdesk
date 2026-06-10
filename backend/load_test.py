#!/usr/bin/env python3
# Production-level load test for NexusDesk
# Simulates N concurrent Slack users hitting process_message directly
# No HTTP, no auth — exactly how the Slack bot works
#
# Run from: /Users/ubaidkundlik/Downloads/ai-it-support/backend
# Usage:    python load_test.py
# Usage:    python load_test.py --users 50
# Usage:    python load_test.py --users 100 --think-time 0

import asyncio
import time
import uuid
import argparse
import sys
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import List

# ── Config ────────────────────────────────────────────────────────────────────
DEFAULT_USERS     = 20       # concurrent simulated Slack users
DEFAULT_THINK     = 0.3      # seconds between messages (realistic typing delay)
RAMP_UP_SECONDS   = 2        # spread user start over N seconds (realistic)

# ── Realistic conversation scripts ────────────────────────────────────────────
SCRIPTS = [
    ["BGP session dropped with ISP", "no", "yes broken", "tried restarting interface"],
    ["DNS not resolving internal hostnames", "no", "no customers affected", "NXDOMAIN"],
    ["VPN keeps disconnecting every 30 mins", "no", "only me", "reconnects automatically"],
    ["Cannot access Salesforce from office", "yes", "yes multiple users", "started this morning"],
    ["Netskope blocking GitHub traffic", "no", "just me", "192.168.1.1 is the IP"],
    ["OSPF neighbour stuck in INIT state", "no", "no", "checked interface logs"],
    ["Firewall dropping packets on port 443", "yes", "no just one customer", "no recent changes"],
    ["Switch port not coming up after reboot", "no", "no customers", "port shows err-disabled"],
    ["BGP route not propagating to peers", "no", "no", "route exists locally"],
    ["Cannot ping default gateway from server", "yes", "yes users affected", "no only 2 users"],
    ["DHCP not assigning IPs in VLAN 20", "no", "yes multiple users", "started after maintenance"],
    ["Packet loss on WAN link to Singapore", "yes", "yes customers", "yes more than 10 customers"],
    ["QoS not prioritising voice traffic", "no", "no", "noticed in Teams calls"],
    ["MPLS circuit down between sites", "yes", "yes multiple customers", "yes widespread outage"],
    ["SSL VPN certificate expired", "no", "yes users", "no only 3 users"],
]

# ── Result tracking ───────────────────────────────────────────────────────────
@dataclass
class UserResult:
    user_id:      str
    messages:     int   = 0
    errors:       int   = 0
    total_ms:     float = 0.0
    msg_times:    List[float] = field(default_factory=list)
    error_detail: List[str]   = field(default_factory=list)


def simulate_user(user_index: int, think_time: float) -> UserResult:
    """Simulate one Slack user — runs in a thread."""
    result     = UserResult(user_id=f"U{user_index:04d}")
    session_id = f"loadtest_{uuid.uuid4().hex}"
    script     = SCRIPTS[user_index % len(SCRIPTS)]

    try:
        # Bootstrap Django-style app context
        sys.path.insert(0, os.getcwd())
        os.environ.setdefault("TESTING", "1")

        from app.core.database import SessionLocal
        from app.services import chat_service
        from app.schemas.chat import ChatMessageRequest

        db = SessionLocal()

        # Fake Slack user (same as slack_chat_bridge does)
        class FakeUser:
            id        = None
            full_name = f"Load Test User {user_index}"
            email     = f"loadtest{user_index}@testsoftware.com"
            city      = "Mumbai"
            country   = "India"
            timezone  = "Asia/Kolkata"
            role      = type("r", (), {"value": "user"})()

        fake_user = FakeUser()

        for msg_text in script:
            t0 = time.time()
            try:
                req = ChatMessageRequest(
                    session_id = session_id,
                    message    = msg_text,
                    user_name  = fake_user.full_name,
                    user_email = fake_user.email,
                    screenshot = None,
                )
                chat_service.process_message(db, fake_user, req)
                elapsed_ms = (time.time() - t0) * 1000
                result.msg_times.append(elapsed_ms)
                result.messages += 1

            except Exception as e:
                result.errors += 1
                result.error_detail.append(f"msg '{msg_text[:30]}': {str(e)[:80]}")

            if think_time > 0:
                time.sleep(think_time)

        db.close()

    except Exception as e:
        result.errors += 1
        result.error_detail.append(f"setup error: {str(e)[:120]}")

    result.total_ms = sum(result.msg_times)
    return result


def print_results(results: List[UserResult], wall_time: float, n_users: int):
    all_times   = [t for r in results for t in r.msg_times]
    total_msgs  = sum(r.messages for r in results)
    total_errs  = sum(r.errors   for r in results)
    success     = total_msgs - total_errs

    avg_ms      = sum(all_times) / len(all_times) if all_times else 0
    p50         = sorted(all_times)[int(len(all_times)*0.50)] if all_times else 0
    p95         = sorted(all_times)[int(len(all_times)*0.95)] if all_times else 0
    p99         = sorted(all_times)[int(len(all_times)*0.99)] if all_times else 0
    max_ms      = max(all_times) if all_times else 0
    throughput  = total_msgs / wall_time if wall_time > 0 else 0

    print(f"\n{'═'*60}")
    print(f"  NEXUSDESK LOAD TEST RESULTS")
    print(f"{'═'*60}")
    print(f"  Concurrent users  : {n_users}")
    print(f"  Total messages    : {total_msgs}")
    print(f"  Successful        : {success}  ({'%.1f' % (success/total_msgs*100 if total_msgs else 0)}%)")
    print(f"  Errors            : {total_errs}")
    print(f"  Wall time         : {wall_time:.2f}s")
    print(f"  Throughput        : {throughput:.1f} msg/s")
    print(f"{'─'*60}")
    print(f"  Response times (per message, includes Claude API):")
    print(f"    Avg  : {avg_ms/1000:.2f}s")
    print(f"    P50  : {p50/1000:.2f}s")
    print(f"    P95  : {p95/1000:.2f}s")
    print(f"    P99  : {p99/1000:.2f}s")
    print(f"    Max  : {max_ms/1000:.2f}s")
    print(f"{'─'*60}")

    # Memory estimate
    print(f"  Session memory    : ~{n_users * 5}KB (est. {n_users} active sessions)")
    print(f"  500-user estimate : ~{500 * 5}KB sessions + Claude API concurrency")
    print(f"{'─'*60}")

    if total_errs > 0:
        print(f"\n  ERRORS:")
        for r in results:
            if r.errors:
                for e in r.error_detail:
                    print(f"    [{r.user_id}] {e}")

    verdict = "✓ PASS" if total_errs == 0 else "✗ FAIL"
    color   = "\033[92m" if total_errs == 0 else "\033[91m"
    print(f"\n  {color}{verdict}\033[0m — {'System handles concurrent load fine' if total_errs == 0 else 'Errors detected — see above'}")
    print(f"{'═'*60}\n")


def main():
    parser = argparse.ArgumentParser(description="NexusDesk load test")
    parser.add_argument("--users",      type=int,   default=DEFAULT_USERS, help="Concurrent users")
    parser.add_argument("--think-time", type=float, default=DEFAULT_THINK,  help="Delay between messages (s)")
    args = parser.parse_args()

    n      = args.users
    think  = args.think_time
    ramp   = min(RAMP_UP_SECONDS, n * 0.1)

    print(f"\n{'═'*60}")
    print(f"  NEXUSDESK PRODUCTION LOAD TEST")
    print(f"{'═'*60}")
    print(f"  Users      : {n} concurrent")
    print(f"  Think time : {think}s between messages")
    print(f"  Ramp-up    : {ramp:.1f}s")
    print(f"  Method     : Direct service call (same as Slack bot)")
    print(f"{'═'*60}\n")

    results   = []
    wall_start = time.time()

    # Use threads — one per user — same as real Slack (each user = separate thread)
    with ThreadPoolExecutor(max_workers=n) as pool:
        futures = {}
        for i in range(n):
            # Stagger starts slightly to simulate realistic ramp-up
            delay = (i / n) * ramp
            time.sleep(delay / n)
            f = pool.submit(simulate_user, i, think)
            futures[f] = i
            sys.stdout.write(f"\r  Started {i+1}/{n} users...")
            sys.stdout.flush()

        print(f"\n  All {n} users running...\n")

        completed = 0
        for f in as_completed(futures):
            result = f.result()
            results.append(result)
            completed += 1
            status = "✓" if result.errors == 0 else "✗"
            sys.stdout.write(f"\r  Completed {completed}/{n} [{status} User {futures[f]:02d}]  ")
            sys.stdout.flush()

    wall_time = time.time() - wall_start
    print_results(results, wall_time, n)


if __name__ == "__main__":
    main()