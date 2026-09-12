#!/bin/sh
# Offline mock smoke: health + Checkout Session (STRIPE_MOCK / no secret).
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
. .venv/bin/activate
pip install -q -r requirements.txt

export STRIPE_MOCK=true
unset STRIPE_SECRET_KEY || true
export SUPABASE_JWT_SECRET="${SUPABASE_JWT_SECRET:-test-supabase-jwt-secret-for-local-smoke}"
export SUPABASE_URL="${SUPABASE_URL:-https://example.supabase.co}"
export ARDOISE_LAB_AUTH_BYPASS=false
export ARDOISE_ENV=development
export ARDOISE_PUBLIC_URL="${ARDOISE_PUBLIC_URL:-http://127.0.0.1:8787}"

python3 -m unittest discover -s tests -v

# Live HTTP path (same mocks) so curl-based checks stay green.
python3 <<'PY'
import os, sys, time, json, threading
from pathlib import Path
import tempfile

import jwt
import uvicorn
from fastapi.testclient import TestClient

root = Path(__file__).resolve().parent if False else Path.cwd()
sys.path.insert(0, str(root))
from ardoise_api.main import create_app
from ardoise_api.settings import Settings
from ardoise_api.store import Store

secret = os.environ["SUPABASE_JWT_SECRET"]
settings = Settings.from_env()
fd, db = tempfile.mkstemp(suffix=".db")
os.close(fd)
app = create_app(settings=settings, store=Store(db))

# In-process client (authoritative)
client = TestClient(app)
health = client.get("/health")
assert health.status_code == 200 and health.json()["ok"], health.text
assert health.json()["stripe_mock"] is True

now = int(time.time())
token = jwt.encode(
    {
        "aud": "authenticated",
        "role": "authenticated",
        "sub": "user-smoke",
        "email": "smoke@example.com",
        "iss": f"{settings.supabase_url}/auth/v1",
        "exp": now + 3600,
        "iat": now,
    },
    secret,
    algorithm="HS256",
)
created = client.post(
    "/v1/checkout/sessions",
    json={},
    headers={"Authorization": f"Bearer {token}"},
)
assert created.status_code == 200, created.text
body = created.json()
assert body["mock"] and body["mode"] == "payment", body
sid = body["stripe_session_id"]
hook = client.post(
    "/v1/stripe/webhook",
    content=json.dumps(
        {"type": "checkout.session.completed", "data": {"object": {"id": sid}}}
    ),
)
assert hook.status_code == 200 and hook.json()["ok"], hook.text
me = client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
assert me.json()["credits"] == body["credits"], me.text

# Bind uvicorn briefly and curl /health (matches "run locally" README).
host, port = "127.0.0.1", int(os.environ.get("ARDOISE_API_PORT", "8787"))
config = uvicorn.Config(app, host=host, port=port, log_level="warning")
server = uvicorn.Server(config)
thread = threading.Thread(target=server.run, daemon=True)
thread.start()
for _ in range(50):
    if server.started:
        break
    time.sleep(0.05)
else:
    raise SystemExit("uvicorn did not start")

import urllib.request
with urllib.request.urlopen(f"http://{host}:{port}/health", timeout=5) as resp:
    live = json.loads(resp.read().decode())
assert live["ok"] and live["stripe_mock"], live
server.should_exit = True
thread.join(timeout=5)
os.unlink(db)
print("SMOKE-OK health+mock-checkout")
PY
