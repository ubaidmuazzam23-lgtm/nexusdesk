#!/bin/bash
# Smart startup: run 4 workers when Redis is reachable, 1 worker otherwise.
# In-memory sessions and rate-limit state are not safe to share across workers
# without Redis, so we stay single-worker when Redis is unavailable.

set -e

WORKERS=1

if [ -n "$REDIS_URL" ]; then
    if python -c "
import sys, redis as r
try:
    c = r.from_url('$REDIS_URL', socket_connect_timeout=3, socket_timeout=3)
    c.ping()
    sys.exit(0)
except Exception as e:
    print(f'[startup] Redis ping failed: {e}', file=sys.stderr)
    sys.exit(1)
" 2>/dev/null; then
        WORKERS=4
        echo "[startup] Redis reachable — starting $WORKERS workers (session sharing enabled)"
    else
        echo "[startup] Redis unreachable — starting $WORKERS worker (in-memory mode)"
    fi
else
    echo "[startup] No REDIS_URL — starting $WORKERS worker (in-memory mode)"
fi

exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers "$WORKERS" \
    --timeout-keep-alive 30
