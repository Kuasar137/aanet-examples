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

### [`balance_low_warning`](examples/balance_low_warning) — hear about it before the 402

The orchestrator isn't the one making the calls, so it has no balance header to
read. Register a `balance_low` webhook with thresholds you choose (in units) and
read `GET /workspaces/{id}/forecast` for burn rate and runway — warned ahead of
time, paying only for the warnings you asked for.

```bash
cd examples/balance_low_warning
pip install -r ../../requirements.txt
python run.py
```

## Why these

The first two patterns came out of real dogfooding on the live service, not
hypotheticals — multi-agent swarm tests that hit exactly these two failure
modes in practice. The third is the orchestrator-side counterpart of the second. They're documented as idioms in
[AGENTS.md](https://aanet.space/AGENTS.md); these are the runnable version.

## License

MIT — copy, adapt, use these patterns with or without AANet.
