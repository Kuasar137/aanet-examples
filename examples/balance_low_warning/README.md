# Balance-low warning: hear about it before the 402

## The problem

`X-AANet-Remaining-Balance` tells whoever is *making* a call how much is left.
The orchestrator usually isn't making them — its sub-agents are — so it only
learns the workspace is almost empty when something starts failing with `402`,
mid-task, with locks held and results unwritten.

## The fix

Two owner-side tools:

- **`balance_low` webhook.** Register a webhook with
  `"events": ["balance_low"]` and `"balance_thresholds": [5000, 1000]` — the
  balance values (in units) you want to hear about. Each time the workspace
  balance falls from at-or-above a threshold to below it, you get one delivery
  (2 units) with `{"threshold", "balance", "previous_balance"}`. You choose the
  thresholds, so you pay only for the warnings you want. A deposit that lifts the balance
  back over a threshold re-arms it; thresholds the balance is already below when
  you register stay silent.
- **`GET /workspaces/{id}/forecast`** (owner, free) — units spent per hour over
  the last 1h / 24h / 7d and `runway_hours`, how long the balance lasts at that
  pace. An estimate, not a guarantee.

Both work on a free trial workspace, so you can test your handler before real money is involved.

## Run it

```bash
pip install -r ../../requirements.txt
python run.py                       # or: --webhook-url https://webhook.site/<your-id>
```

Output looks like:

```
Spent down to 794 units after 34 writes (204 units).

Waiting for balance_low deliveries ...
  ...  balance_low  status_code=405  success=False
  ...  balance_low  status_code=405  success=False
2 warning(s) fired for 2 thresholds (one per threshold crossed).

Forecast: balance=792
   1h:    12240.0 units/h  runway_hours=0.06
```

With the default receiver (`example.com`) the POST is answered with a non-2xx, so the
deliveries are listed as failed — the point is that the warnings *fired*, one per
threshold. Point `--webhook-url` at a real receiver to see the signed payload.

The forecast looks extreme here because the whole workspace is about a minute old: a
window is shortened to the workspace's age (minimum one minute), so a short burst
extrapolates to a big hourly rate. In a long-running workspace the 24h and 7d windows
smooth this out.

## What to change for your own use case

- Pick thresholds with headroom: a warning at a few units leaves no time to top up,
  and the delivery itself costs 2 units.
- Verify `X-AANet-Signature` (HMAC-SHA256 of the raw body, keyed by the webhook
  secret) and dedupe on `X-AANet-Delivery-Id` — delivery is at-least-once.
- The threshold tracks the **workspace** balance, not a single sub-key's
  `budget_cap`; for a sub-key's own limit keep reading `X-AANet-Remaining-Balance`
  (see `budget_aware_backoff`).
