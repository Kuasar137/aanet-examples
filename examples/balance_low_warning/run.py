#!/usr/bin/env python3
"""
Get warned before the 402 — balance_low webhook + spend forecast.

X-AANet-Remaining-Balance tells a worker how much is left *after* each call.
The orchestrator, which isn't making those calls, has the opposite problem:
it only finds out the workspace is nearly empty when something starts failing
with 402. Two owner-side tools fix that:

  * a `balance_low` webhook with `balance_thresholds` you choose (in units) —
    one delivery (2 units) each time the workspace balance falls through one
    of them, instead of polling;
  * `GET /workspaces/{id}/forecast` — spend per hour and hours of runway left.

This script creates a trial workspace (1000 units), registers a balance_low
webhook for [900, 800], spends the balance down with small writes, then shows
(a) the balance_low deliveries the service made (listed under
/webhooks/{id}/deliveries — the receiver does not have to be reachable for
the attempt to be recorded) and (b) the forecast.

Usage:
    pip install requests
    python run.py [--base https://aanet.space] [--webhook-url https://example.com/aanet-hook]

--webhook-url must be public https. With the default (example.com) the POST is
answered with a non-2xx, so the delivery shows as failed — that is fine here, it
still proves the warning fired. Point it at a real receiver (e.g. webhook.site) to see
the signed payload: {"event": "balance_low", "data": {"threshold", "balance", "previous_balance"}}.
"""

import argparse
import time

import requests

THRESHOLDS = [900, 800]
WRITE_COST = 6  # PUT of a small file, per AGENTS.md pricing


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", default="https://aanet.space")
    parser.add_argument("--webhook-url", default="https://example.com/aanet-hook")
    args = parser.parse_args()
    base = args.base

    print(f"Creating a trial workspace on {base} ...")
    resp = requests.post(f"{base}/workspaces/trial", timeout=10)
    resp.raise_for_status()
    workspace_id, owner_key = resp.json()["workspace_id"], resp.json()["owner_key"]
    auth = {"Authorization": f"Bearer {owner_key}"}

    resp = requests.post(
        f"{base}/workspaces/{workspace_id}/webhooks",
        headers=auth,
        json={"url": args.webhook_url, "events": ["balance_low"], "balance_thresholds": THRESHOLDS},
        timeout=10,
    )
    resp.raise_for_status()
    webhook_id = resp.json()["webhook_id"]
    print(f"  workspace_id={workspace_id}, balance_low webhook {webhook_id} for thresholds {THRESHOLDS}\n")

    # Spend the balance down past the last threshold.
    balance, n = 1000, 0
    while balance >= min(THRESHOLDS):
        n += 1
        resp = requests.put(
            f"{base}/workspaces/{workspace_id}/files/work/{n}.md",
            headers=auth, json={"content": f"step {n}"}, timeout=10,
        )
        resp.raise_for_status()
        balance = int(resp.headers["X-AANet-Remaining-Balance"])
    print(f"Spent down to {balance} units after {n} writes ({n * WRITE_COST} units).\n")

    # Deliveries are made by a background worker (polls every few seconds).
    print("Waiting for balance_low deliveries ...")
    deliveries = []
    for _ in range(15):
        time.sleep(2)
        resp = requests.get(f"{base}/workspaces/{workspace_id}/webhooks/{webhook_id}/deliveries", headers=auth, timeout=10)
        resp.raise_for_status()
        deliveries = [d for d in resp.json() if d["event_type"] == "balance_low"]
        if len(deliveries) >= len(THRESHOLDS):
            break
    for d in reversed(deliveries):
        print(f"  {d['ts']}  balance_low  status_code={d['status_code']}  success={d['success']}")
    print(f"{len(deliveries)} warning(s) fired for {len(THRESHOLDS)} thresholds (one per threshold crossed).\n")

    resp = requests.get(f"{base}/workspaces/{workspace_id}/forecast", headers=auth, timeout=10)
    resp.raise_for_status()
    fc = resp.json()
    print(f"Forecast: balance={fc['balance']}")
    for w in fc["windows"]:
        print(f"  {w['window']:>3}: {w['units_per_hour']:>10} units/h  runway_hours={w['runway_hours']}")
    print("\n(The trial workspace expires on its own 24 hours after creation — nothing to clean up.)")


if __name__ == "__main__":
    main()
