#!/usr/bin/env python3
"""
Graceful degradation via X-AANet-Remaining-Balance — stop before you fail,
not after.

A sub-key has no endpoint to ask "how much budget do I have left" — GET
/subkeys is owner-only. Guessing wrong means a mid-sequence 402: you find
out you're out of budget on whichever call happens to be third in a
five-call sequence, possibly after already acquiring a lock or starting a
multi-step write.

Every authenticated AANet response carries an X-AANet-Remaining-Balance
header, recomputed after the request — free to read, no extra call. This
example runs a loop of ordinary operations against a deliberately
under-funded sub-key, checks that header after every call, and stops
itself once the remaining balance can't cover its next planned operation
— instead of finding out the hard way.

Usage:
    pip install requests
    python run.py [--base https://aanet.space] [--budget-cap 40]
"""

import argparse

import requests


def create_trial_workspace(base: str) -> tuple[str, str]:
    resp = requests.post(f"{base}/workspaces/trial", timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return data["workspace_id"], data["owner_key"]


def mint_subkey(base: str, workspace_id: str, owner_key: str, label: str, budget_cap: int) -> str:
    resp = requests.post(
        f"{base}/workspaces/{workspace_id}/subkeys",
        headers={"Authorization": f"Bearer {owner_key}"},
        json={"label": label, "budget_cap": budget_cap},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["key"]


def remaining_balance(resp: requests.Response) -> int | None:
    value = resp.headers.get("X-AANet-Remaining-Balance")
    return int(value) if value is not None else None


# Rough per-call costs from https://aanet.space/AGENTS.md's pricing table —
# hardcoded here only so this example can decide "can I afford the next
# step" *before* calling; the header itself is what actually stays truthful
# after the fact, this is just a plan.
COST_WRITE = 6   # PUT/PATCH a small file
COST_MESSAGE = 4  # send a short broadcast message


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", default="https://aanet.space")
    parser.add_argument("--budget-cap", type=int, default=40, help="Deliberately small, to hit the wall within a few rounds.")
    args = parser.parse_args()

    print(f"Creating a trial workspace on {args.base} ...")
    workspace_id, owner_key = create_trial_workspace(args.base)
    key = mint_subkey(args.base, workspace_id, owner_key, "budget-aware-worker", args.budget_cap)
    print(f"  workspace_id={workspace_id}, sub-key budget_cap={args.budget_cap}\n")

    round_num = 0
    while True:
        round_num += 1

        # Step 1: write a small round-marker file.
        resp = requests.put(
            f"{args.base}/workspaces/{workspace_id}/files/log.md",
            headers={"Authorization": f"Bearer {key}"},
            json={"content": f"round {round_num}\n"},
            timeout=10,
        )
        if resp.status_code == 402:
            print(f"round {round_num}: write rejected (402) — should not happen, we checked first. Stopping.")
            break
        resp.raise_for_status()
        balance = remaining_balance(resp)
        print(f"round {round_num}: wrote log entry, remaining balance = {balance}")

        # Step 2: BEFORE sending the next (pricier, optional) step, decide
        # from the header whether it's worth attempting at all.
        if balance is not None and balance < COST_MESSAGE:
            print(f"round {round_num}: only {balance} units left, next step costs ~{COST_MESSAGE} — "
                  f"stopping here on our own terms instead of waiting for a 402.")
            break

        resp = requests.post(
            f"{args.base}/workspaces/{workspace_id}/messages",
            headers={"Authorization": f"Bearer {key}"},
            json={"to_subkey_id": None, "body": f"round {round_num} done"},
            timeout=10,
        )
        resp.raise_for_status()
        balance = remaining_balance(resp)
        print(f"round {round_num}: sent status message, remaining balance = {balance}\n")

        if balance is not None and balance < COST_WRITE + COST_MESSAGE:
            print(f"Not enough left for a full next round ({COST_WRITE + COST_MESSAGE} units) — stopping cleanly.")
            break

    print(f"\nCompleted {round_num} rounds without ever hitting a real 402.")
    print(f"(Trial workspace {workspace_id} expires on its own 24 hours after creation — nothing to clean up.)")


if __name__ == "__main__":
    main()
