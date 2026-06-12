"""
Load test: /health + /chat/message via Locust headless mode.

Usage:
    BENCH_TOKEN=<jwt> python tests/bench_load.py [50|100]
"""
import os, sys, subprocess, tempfile, time

BASE_URL   = "http://localhost:8000"
TOKEN      = os.environ.get("BENCH_TOKEN", "")
LEVELS     = [int(x) for x in sys.argv[1:]] or [50, 100]
DURATION_S = 20        # seconds per run


LOCUSTFILE = """
import uuid
from locust import HttpUser, task, between, constant_pacing

TOKEN = "{token}"

class HealthUser(HttpUser):
    weight        = 70          # 70 % of virtual users hit /health
    wait_time     = constant_pacing(0.5)

    @task
    def health(self):
        self.client.get("/health")

    @task(2)
    def root(self):
        self.client.get("/")


class ChatUser(HttpUser):
    weight        = 30          # 30 % hit /chat/message
    wait_time     = between(1, 2)

    def on_start(self):
        self.session_id = str(uuid.uuid4())
        self.headers    = {{"Authorization": f"Bearer {{TOKEN}}"}}

    @task
    def chat(self):
        self.client.post(
            "/api/v1/chat/message",
            json={{"message": "hello", "session_id": self.session_id}},
            headers=self.headers,
        )
""".format(token=TOKEN)


def run_level(users: int) -> dict:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(LOCUSTFILE)
        lf = f.name

    csv_pfx = f"/tmp/locust_{users}"
    cmd = [
        sys.executable, "-m", "locust",
        "-f", lf,
        "--host", BASE_URL,
        "--headless",
        "-u", str(users),
        "-r", str(max(5, users // 5)),  # ramp-up rate
        "--run-time", f"{DURATION_S}s",
        "--csv", csv_pfx,
        "--only-summary",
    ]
    t0 = time.perf_counter()
    res = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = time.perf_counter() - t0
    os.unlink(lf)

    # parse CSV stats
    stats_file = csv_pfx + "_stats.csv"
    rows = []
    if os.path.exists(stats_file):
        import csv as _csv
        with open(stats_file) as fh:
            reader = _csv.DictReader(fh)
            for row in reader:
                if row.get("Name") == "Aggregated":
                    rows.append(row)

    out = {"users": users, "elapsed": elapsed, "stdout": res.stdout[-2000:], "csv": rows}
    for f in [stats_file, csv_pfx + "_stats_history.csv",
              csv_pfx + "_failures.csv", csv_pfx + "_exceptions.csv"]:
        try: os.unlink(f)
        except FileNotFoundError: pass
    return out


def hdr(s): print(f"\n{'='*68}\n {s}\n{'='*68}")

if __name__ == "__main__":
    hdr("LOAD TEST — Locust headless")

    if not TOKEN:
        print("  [WARN] BENCH_TOKEN not set — chat requests will get 401 (expected)")

    all_ok = True
    for users in LEVELS:
        print(f"\n  Running {users} concurrent users for {DURATION_S}s …")
        result = run_level(users)

        if result["csv"]:
            row = result["csv"][0]
            rps       = float(row.get("Requests/s", 0))
            fails     = float(row.get("Failure Count", 0))
            total     = float(row.get("Request Count", 1))
            err_pct   = 100 * fails / max(total, 1)
            p50       = row.get("50%", "?")
            p95       = row.get("95%", "?")
            p99       = row.get("99%", "?")
            avg       = row.get("Average (ms)", "?")

            print(f"  Users={users} | RPS={rps:.1f} | p50={p50}ms | "
                  f"p95={p95}ms | p99={p99}ms | avg={avg}ms | err={err_pct:.1f}%")

            # Accept: error rate < 5% (401s on /chat without token are expected)
            if err_pct > 5:
                print(f"  [FAIL] error rate {err_pct:.1f}% > 5%")
                all_ok = False
            else:
                print(f"  [PASS] error rate within threshold")
        else:
            # Fallback: check stdout for summary
            for line in result["stdout"].splitlines():
                if "Aggregated" in line or "RPS" in line or "requests" in line.lower():
                    print(f"  {line}")
            print("  [INFO] CSV stats not available — check stdout above")

    sys.exit(0 if all_ok else 1)
