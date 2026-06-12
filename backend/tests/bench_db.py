"""
Database query analysis: EXPLAIN ANALYZE on the most frequent queries,
missing index detection.

Usage:
    PYTHONPATH=backend python tests/bench_db.py
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

def hdr(s): print(f"\n{'='*68}\n {s}\n{'='*68}")
def ok(s):   print(f"  [PASS] {s}")
def fail(s): print(f"  [FAIL] {s}")
def info(s): print(f"  [INFO] {s}")
def warn(s): print(f"  [WARN] {s}")

try:
    from app.core.database import SessionLocal
    from sqlalchemy import text

    db = SessionLocal()

    # ── Helper ──────────────────────────────────────────────────────────────
    def explain(label: str, sql: str, threshold_ms: float = 100):
        try:
            db.rollback()   # ensure clean transaction after any prior failure
            t0  = time.perf_counter()
            res = db.execute(text(f"EXPLAIN ANALYZE {sql}")).fetchall()
            ms  = (time.perf_counter() - t0) * 1000
            plan_lines = [r[0] for r in res]
            # Find planning + execution time from EXPLAIN ANALYZE output
            exec_ms = None
            plan_ms = None
            for line in plan_lines:
                if "Execution Time:" in line:
                    try: exec_ms = float(line.split(":")[1].strip().split(" ")[0])
                    except: pass
                if "Planning Time:" in line:
                    try: plan_ms = float(line.split(":")[1].strip().split(" ")[0])
                    except: pass

            # Detect seq scans on large tables
            has_seqscan = any("Seq Scan" in l for l in plan_lines)
            rows_hint   = next((l for l in plan_lines if "rows=" in l), "")

            exec_display = f"{exec_ms:.1f}ms" if exec_ms is not None else f"~{ms:.1f}ms"
            status = "[SLOW]" if (exec_ms or ms) > threshold_ms else "[OK]  "
            scan   = "[SEQ SCAN]" if has_seqscan else "[INDEX]   "

            print(f"  {status} {scan} {label}: exec={exec_display}")
            if exec_ms and exec_ms > threshold_ms:
                fail(f"{label} query is slow ({exec_ms:.1f}ms > {threshold_ms}ms threshold)")
                # Print relevant plan lines
                for line in plan_lines[:8]:
                    print(f"           {line}")
            return exec_ms or ms, has_seqscan
        except Exception as e:
            warn(f"{label} EXPLAIN failed: {e}")
            return 0.0, False

    # ── Index introspection ──────────────────────────────────────────────────
    hdr("DATABASE — Index inventory")
    indexes = db.execute(text("""
        SELECT tablename, indexname, indexdef
        FROM pg_indexes
        WHERE tablename IN ('users','tickets','engineers','teams','team_members','assets')
        ORDER BY tablename, indexname
    """)).fetchall()

    if indexes:
        for row in indexes:
            uniq = "UNIQUE" if "UNIQUE" in (row.indexdef or "") else "      "
            info(f"  {uniq}  {row.tablename:20s}  {row.indexname:40s}")
    else:
        warn("No indexes found (empty DB or permission issue)")

    # ── EXPLAIN ANALYZE on frequent queries ──────────────────────────────────
    hdr("DATABASE — EXPLAIN ANALYZE on hot queries")

    queries = [
        ("health_check",        "SELECT 1"),
        ("login_by_email",      "SELECT * FROM users WHERE email = 'test@example.com' LIMIT 1"),
        ("max_ticket_number",   "SELECT MAX(ticket_number) FROM tickets"),
        ("open_tickets_count",  "SELECT COUNT(*) FROM tickets WHERE status = 'OPEN'::ticketstatus"),
        ("user_tickets",        "SELECT * FROM tickets WHERE user_id = '00000000-0000-0000-0000-000000000000' ORDER BY created_at DESC"),
        ("engineer_lookup",     "SELECT e.*, u.* FROM engineers e JOIN users u ON e.user_id = u.id WHERE e.is_activated = true AND u.is_active = true"),
        ("team_lookup",         "SELECT * FROM teams WHERE is_active = true"),
        ("ticket_by_id",        "SELECT * FROM tickets WHERE id = '00000000-0000-0000-0000-000000000000' LIMIT 1"),
    ]

    slow_queries  = []
    seqscan_large = []

    for label, sql in queries:
        ms, seqscan = explain(label, sql, threshold_ms=100)
        if ms > 100:
            slow_queries.append((label, ms))
        if seqscan and ms > 10:
            seqscan_large.append((label, ms))

    # ── Index recommendations ────────────────────────────────────────────────
    hdr("DATABASE — Missing index detection")

    # Check for indexes on columns used in WHERE clauses of hot queries
    critical_indexes = [
        ("users",        "email"),
        ("tickets",      "user_id"),
        ("tickets",      "status"),
        ("tickets",      "ticket_number"),
        ("engineers",    "user_id"),
        ("engineers",    "is_activated"),
        ("teams",        "is_active"),
    ]

    # Build set of (table, column_hint) from index definitions
    existing_idx_defs = [(row.tablename, row.indexdef or "") for row in indexes]

    missing = []
    for tbl, col in critical_indexes:
        covered = any(t == tbl and col in defn for t, defn in existing_idx_defs)
        if not covered:
            missing.append(f"{tbl}.{col}")

    if missing:
        for m in missing:
            warn(f"Potentially missing index: {m}")
    else:
        ok("All critical columns appear to have indexes")

    # ── Summary ──────────────────────────────────────────────────────────────
    hdr("DATABASE — Summary")
    if slow_queries:
        for label, ms in slow_queries:
            fail(f"Slow query: {label} = {ms:.1f}ms")
    else:
        ok("No queries exceeded 100ms threshold")

    if seqscan_large:
        for label, ms in seqscan_large:
            warn(f"Sequential scan (may need index): {label} = {ms:.1f}ms")
    else:
        ok("No problematic sequential scans detected")

    db.close()

except Exception as e:
    fail(f"DB analysis failed: {e}")
    import traceback; traceback.print_exc()

print("\n")
