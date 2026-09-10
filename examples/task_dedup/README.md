# Task dedup: N workers, each task done exactly once

## The problem

You have a shared list of tasks and several worker agents. Each task must
be done by exactly one worker — no duplicated work, no task skipped. The
obvious tool is a lock: acquire `task-<name>`, do the work, release it.

That's not enough on its own. A lock only tells you **nobody holds it right
now** — it says nothing about whether the work behind it was **ever done**.
A worker that acquires a freshly-released lock has no way to tell "this is
unclaimed" from "this was just finished a second ago" — from the lock API
alone, they look identical.

## The fix

One extra read: after acquiring the lock, check whether the expected result
already exists. If it does, someone beat you to it — release the lock and
move on without redoing the work. If it doesn't, do the work, write the
result, release the lock.

This is a documented idiom in
[AANet's AGENTS.md](https://aanet.space/AGENTS.md#coordinating-exclusive-access):

> A lock is a pure mutex, not a completion record... check for the expected
> result (read the output file, or check recent messages) before treating a
> successfully-acquired lock as "unclaimed, safe to start".

## Run it

```bash
pip install -r ../../requirements.txt
python run.py                          # correct: check-before-work
python run.py --skip-result-check      # buggy: same lock, no check
```

The buggy run re-scans the task list for several rounds (`--rounds`,
default 3) — a lock is released as soon as its holder finishes, so by round
2 every task's lock is free again. Acquiring it tells you nothing about
whether round 1 already did the work. Watch the output: with the check
disabled, tasks get completed multiple times (`DUPLICATE COMPLETIONS`); with
it enabled, only the very first attempt on each task ever writes anything —
and, as a bonus lesson, the buggy version burns through its budget faster
for literally no benefit, since it's billed per write whether or not the
write was necessary.

## What to change for your own use case

- Swap the fake "work" (`put_file(..., "done by worker-X")`) for whatever
  your agents actually produce.
- The result file doesn't have to be a marker — checking for the *real*
  artifact (a report, a processed record) works the same way and doubles as
  your actual output.
- A free trial workspace caps active sub-keys at 2 — pass
  `--workspace-id`/`--owner-key` for a funded workspace to run more workers.
