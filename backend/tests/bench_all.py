"""
Comprehensive benchmark + security test suite.
Run: python tests/bench_all.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

BASE_URL  = "http://localhost:8000"
AUTH_TOKEN = os.environ.get("BENCH_TOKEN", "")

# ─── colours ──────────────────────────────────────────────────────────────────
def _hdr(title): print(f"\n{'='*70}\n {title}\n{'='*70}")
def _ok(msg):    print(f"  [PASS] {msg}")
def _fail(msg):  print(f"  [FAIL] {msg}")
def _info(msg):  print(f"  [INFO] {msg}")
