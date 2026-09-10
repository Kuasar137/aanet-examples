#!/usr/bin/env python3
"""
Task dedup via AANet locks — the "N workers, each task done exactly once" pattern.

The naive version of this pattern is broken: a lock only proves nobody else
holds it *right now* — it does not prove the task behind it was never done.
A worker that reads the task list, sees a name is unclaimed, and races to
acquire its lock can win the lock *after* another worker already finished
and released it. Two workers then both "successfully" claim the same task.

The fix costs one extra read: after acquiring the lock, check whether the
result already exists before doing any work. If it does, someone beat you
to it between your list-read and your lock-acquire — release the lock and
move on, don't redo the work.

This script spins up a real trial workspace on AANet, seeds a shared task
list, and runs N worker threads (real concurrent HTTP requests, not
simulated) against it. Run it more than once and diff the output — with
the check, every task is completed exactly once no matter how the workers
interleave; pass --skip-result-check to see it break.

A free trial workspace caps active sub-keys at 2 (see AGENTS.md at
https://aanet.space — it's meant to demonstrate the mechanism, not host a
real swarm for free), so this defaults to 2 workers. To see the race with
a bigger swarm, fund a real workspace (POST /workspaces) and pass its
credentials with --workspace-id/--owner-key — sub-keys aren't capped there.

Usage:
    pip install requests
    python run.py                                   # 2 workers, trial workspace
    python run.py --workers 8 --workspace-id ... --owner-key ...   # real workspace
"""

import argparse
import threading

import requests


def create_trial_workspace(base: str) -> tuple[str, str]:
    resp = requests.post(f"{base}/workspaces/trial", timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return data["workspace_id"], data["owner_key"]


def mint_subkey(base: str, workspace_id: str, owner_key: str, label: str) -> str:
    resp = requests.post(
        f"{base}/workspaces/{workspace_id}/subkeys",
        headers={"Authorization": f"Bearer {owner_key}"},
        json={"label": label},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["key"]


def get_file(base: str, workspace_id: str, key: str, path: str) -> dict | None:
    resp = requests.get(
        f"{base}/workspaces/{workspace_id}/files/{path}",
        headers={"Authorization": f"Bearer {key}"},
        timeout=10,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def put_file(base: str, workspace_id: str, key: str, path: str, content: str) -> None:
    resp = requests.put(
        f"{base}/workspaces/{workspace_id}/files/{path}",
        headers={"Authorization": f"Bearer {key}"},
        json={"content": content},
        timeout=10,
    )
    resp.raise_for_status()


def acquire_lock(base: str, workspace_id: str, key: str, name: str, lease_seconds: int = 20) -> bool:
    resp = requests.post(
        f"{base}/workspaces/{workspace_id}/locks/{name}/acquire",
        headers={"Authorization": f"Bearer {key}"},
        json={"lease_seconds": lease_seconds},
        timeout=10,
    )
    return resp.status_code == 200


def release_lock(base: str, workspace_id: str, key: str, name: str) -> None:
    requests.post(
        f"{base}/workspaces/{workspace_id}/locks/{name}/release",
        headers={"Authorization": f"Bearer {key}"},
        timeout=10,
    )


def worker(base: str, workspace_id: str, key: str, worker_id: int, tasks: list[str], rounds: int, log: list[str], lock: threading.Lock, skip_result_check: bool):
    # Looping over the *same* task list for several rounds is what actually
    # exercises the bug: a lock is released as soon as its holder is done, so
    # by round 2 every task's lock is free again — acquiring it tells you
    # nothing about whether the work already happened in round 1. A worker
    # that only ever tried each task once wouldn't reliably hit this; a
    # long-running or restarted worker re-scanning a shared list will.
    for round_num in range(1, rounds + 1):
        for task in tasks:
            if not acquire_lock(base, workspace_id, key, f"task-{task}"):
                continue  # someone else holds it right now — try the next task

            try:
                if not skip_result_check:
                    # THE FIX: a successfully-acquired lock only means "free
                    # right now" — it says nothing about whether the work is
                    # already done. Check for the actual result first.
                    existing = get_file(base, workspace_id, key, f"results/{task}.txt")
                    if existing is not None:
                        with lock:
                            log.append(f"worker-{worker_id} round {round_num}: {task} already done — skipping")
                        continue

                # Do the "work" (here: just write a result naming the winner).
                # Note: with --skip-result-check, redoing already-finished
                # work also burns through the workspace's budget for nothing
                # — a 402 here means the bug wasted the balance a correct
                # worker would have spent on tasks still left to do.
                put_file(base, workspace_id, key, f"results/{task}.txt", f"done by worker-{worker_id} in round {round_num}\n")
                with lock:
                    log.append(f"worker-{worker_id} round {round_num}: completed {task}")
            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code == 402:
                    with lock:
                        log.append(f"worker-{worker_id} round {round_num}: out of budget (402) — stopping this worker")
                    return
                raise
            finally:
                release_lock(base, workspace_id, key, f"task-{task}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", default="https://aanet.space")
    parser.add_argument("--workers", type=int, default=2, help="Trial workspaces cap active sub-keys at 2; use --workspace-id/--owner-key with a funded workspace to go higher.")
    parser.add_argument("--tasks", type=int, default=8)
    parser.add_argument("--rounds", type=int, default=3, help="Each worker re-scans the full task list this many times, to exercise the bug reliably.")
    parser.add_argument("--workspace-id", default=None, help="Use an existing (funded) workspace instead of creating a trial.")
    parser.add_argument("--owner-key", default=None, help="Owner key for --workspace-id.")
    parser.add_argument(
        "--skip-result-check", action="store_true",
        help="Disable the fix, to demonstrate the race it prevents (expect duplicate completions).",
    )
    args = parser.parse_args()

    if args.workspace_id and args.owner_key:
        workspace_id, owner_key = args.workspace_id, args.owner_key
        print(f"Using existing workspace {workspace_id} on {args.base} ...")
    else:
        print(f"Creating a trial workspace on {args.base} ...")
        workspace_id, owner_key = create_trial_workspace(args.base)
        print(f"  workspace_id={workspace_id} (trial — capped at 2 active sub-keys)")

    task_names = [f"item-{i}" for i in range(args.tasks)]
    put_file(args.base, workspace_id, owner_key, "tasks.md", "\n".join(task_names) + "\n")

    print(f"Minting {args.workers} sub-keys and racing them over {args.tasks} tasks "
          f"(result-check {'DISABLED' if args.skip_result_check else 'enabled'}) ...\n")

    log: list[str] = []
    log_lock = threading.Lock()
    threads = []
    for i in range(args.workers):
        key = mint_subkey(args.base, workspace_id, owner_key, f"worker-{i}")
        # Every worker races over the SAME full task list — that's the point:
        # whoever gets there first wins, the rest should back off cleanly.
        t = threading.Thread(target=worker, args=(args.base, workspace_id, key, i, task_names, args.rounds, log, log_lock, args.skip_result_check))
        threads.append(t)
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    for line in log:
        print(" ", line)

    completions = [l for l in log if ": completed " in l]
    per_task = {}
    for l in completions:
        task = l.split(": completed ")[1]
        per_task[task] = per_task.get(task, 0) + 1
    duplicates = {t: c for t, c in per_task.items() if c > 1}

    print()
    if duplicates:
        print(f"DUPLICATE COMPLETIONS: {duplicates} — the race happened.")
    else:
        print(f"Every one of {len(task_names)} tasks was completed exactly once.")
    print(f"\n(Trial workspace {workspace_id} expires on its own in 1 hour — nothing to clean up.)")


if __name__ == "__main__":
    main()
