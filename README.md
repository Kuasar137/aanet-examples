# AANet Examples

Runnable, tested patterns for coordinating a swarm of autonomous agents
through [AANet](https://aanet.space) — a metered coordination service
(shared workspaces, budgeted sub-keys, distributed locks, file storage,
messaging) billed per operation via [x402](https://www.x402.org/).

Every script here creates a real, free **trial workspace** on the live
service and runs against it — nothing to configure, nothing to fund. Read
the full API at [aanet.space/AGENTS.md](https://aanet.space/AGENTS.md).

## Examples

### [`task_dedup`](examples/task_dedup) — N workers, each task done exactly once

The classic multi-agent problem: a shared task list, several workers, no
task should be done twice. Shows the naive version breaking (a lock only
proves nobody holds it *right now*, not that the work behind it was never
done) and the one-line fix (check for the result before trusting a freshly
acquired lock).

```bash
cd examples/task_dedup
pip install -r ../../requirements.txt
python run.py                        # correct version — every task done once
python run.py --skip-result-check    # same code, fix disabled — watch it duplicate work
```

### [`budget_aware_backoff`](examples/budget_aware_backoff) — stop before you fail, not after

A sub-key can't ask "how much budget do I have left" (that's owner-only) —
but every response carries an `X-AANet-Remaining-Balance` header. This
example reads it after every call and winds a multi-step loop down on its
own terms once it can't afford the next step, instead of finding out via a
mid-sequence `402`.

```bash
cd examples/budget_aware_backoff
pip install -r ../../requirements.txt
python run.py --budget-cap 40
```

## Why these two

Both patterns came out of real dogfooding on the live service, not
hypotheticals — multi-agent swarm tests that hit exactly these two
failure modes in practice. They're documented as idioms in
[AGENTS.md](https://aanet.space/AGENTS.md); these are the runnable version.

## License

MIT — copy, adapt, use these patterns with or without AANet.
