FROM python:3.11-slim

# Apply all available OS security patches before installing app deps.
# This eliminates CVEs in base packages (openssl, libexpat, libcap, etc.)
# that can't be fixed by upgrading Python packages alone.
RUN apt-get update && apt-get upgrade -y --no-install-recommends && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Readiness probe: /ready (returns 503 until startup completes)
# Liveness probe: /health (DB ping)
# start.sh auto-selects workers=4 when Redis is reachable, workers=1 otherwise.
CMD ["/bin/bash", "/app/start.sh"]
