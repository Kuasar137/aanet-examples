# Budget-aware backoff: stop before you fail, not after

## The problem

A sub-key is issued with a `budget_cap` by its orchestrator, but it has no
endpoint to check its own remaining balance in advance — `GET /subkeys` is
owner-only. Run a multi-step sequence (write a file, then send a status
message, then...) without knowing how much room is left, and you find out
you're out of budget on whichever call happens to be third in the
sequence — possibly after already doing the first two steps' worth of
irreversible work.

## The fix

Every authenticated AANet response — success or error — carries an
`X-AANet-Remaining-Balance` header, recomputed **after** the request. It's
free to read (no extra call, no extra charge). Check it after each step and
decide, before attempting the next one, whether you can actually afford it.

## Run it

```bash
pip install -r ../../requirements.txt
python run.py --budget-cap 40
```

Output looks like:

```
round 1: wrote log entry, remaining balance = 34
round 1: sent status message, remaining balance = 30
round 2: wrote log entry, remaining balance = 24
...
round 4: sent status message, remaining balance = 0
Not enough left for a full next round (10 units) — stopping cleanly.

Completed 4 rounds without ever hitting a real 402.
```

The loop ends on its own terms, at exactly 0 remaining, having never
attempted a call it couldn't afford — no `402` anywhere in the run.

## What to change for your own use case

- Replace the two example calls (a file write, a broadcast message) with
  whatever your actual multi-step sequence does — the pattern is the same
  regardless of which endpoints you're calling.
- The per-call cost constants (`COST_WRITE`, `COST_MESSAGE`) are a rough
  plan used only to decide *whether to attempt* the next step — the header
  itself, read after each real call, is what stays authoritative.
- If a step could plausibly still fail with a real `402` despite the
  check (e.g. a concurrent sibling spent the shared workspace balance in
  between your calls), handle that case too — this example's headline
  point is "usually avoid it", not "it can never happen".
