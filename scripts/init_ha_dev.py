"""
Init script for HA dev instance.
Called by the ha-init service in docker-compose.yml.
Waits for HA to be ready, then runs the onboarding API to create an admin account.
Skips silently if onboarding is already done.
"""
import json
import sys
import time
import urllib.error
import urllib.request

HA_URL = "http://localhost:8123"
CLIENT_ID = f"{HA_URL}/"
USERNAME = "admin"
PASSWORD = "admin"


def get(path: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(f"{HA_URL}{path}", timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception:
        return 0, {}


def post(path: str, payload: dict, token: str | None = None) -> tuple[int, dict]:
    data = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{HA_URL}{path}", data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        return e.code, {"error": body}


def wait_for_ha() -> None:
    print("Waiting for Home Assistant...", flush=True)
    for _ in range(60):
        status, _ = get("/api/")
        if status == 200:
            print("Home Assistant is ready.", flush=True)
            return
        time.sleep(3)
    print("ERROR: HA did not start in time.", flush=True)
    sys.exit(1)


def main() -> None:
    wait_for_ha()

    # Check if onboarding is still pending
    status, data = get("/api/onboarding")
    if status != 200:
        print("Onboarding endpoint not available — already initialized, nothing to do.", flush=True)
        return

    steps = {s["step"]: s["done"] for s in data}
    if all(steps.values()):
        print("Onboarding already completed, nothing to do.", flush=True)
        return

    print("Running onboarding...", flush=True)

    # Step 1: create admin user
    status, resp = post("/api/onboarding/users", {
        "client_id": CLIENT_ID,
        "name": "Admin",
        "username": USERNAME,
        "password": PASSWORD,
        "language": "fr",
    })
    if status not in (200, 201):
        print(f"ERROR creating user (HTTP {status}): {resp}", flush=True)
        sys.exit(1)

    token = resp.get("auth_code") or resp.get("access_token")

    # Step 2: core_config
    post("/api/onboarding/core_config", {"client_id": CLIENT_ID}, token)

    # Step 3: analytics
    post("/api/onboarding/analytics", {"client_id": CLIENT_ID}, token)

    # Step 4: integration
    post("/api/onboarding/integration", {
        "client_id": CLIENT_ID,
        "redirect_uri": f"{HA_URL}/?auth_callback=1",
    }, token)

    print(f"\nDone! Login at {HA_URL} with {USERNAME} / {PASSWORD}", flush=True)


if __name__ == "__main__":
    main()
