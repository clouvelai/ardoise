# T0 list-price estimates

T0 is a **local list-price estimate**, not billed truth. `status` and
`estimate` read [`data/prices.fallback.json`](../data/prices.fallback.json)
(plus optional `~/.ardoise/prices.json`). They do not call the network and
do not require keys.

Override the bundled book with `~/.ardoise/prices.json` if you want newer
rates without waiting for a release. There is no LiteLLM refresh in this
build.

## Cursor model ids

Cursor hooks send a legacy `model` slug that is often the placeholder
`default` (Auto / unset). The real id, when Cursor named one, is usually
in `model_id` / `modelId`, `message.model`, or a longer slug such as
`cursor-grok-4.6-high`.

Capture and backfill persist that real string on `events.model`.
Placeholders (`default`, `auto`, empty) become the explicit sentinel
`unknown`. `unknown` prices at **$0** — it does **not** inherit Claude
Sonnet $3 / $15.

If the hook already set `model_params` `fast=true` and the slug has no
`fast` token, Ardoise appends `-fast` so Grok / Composer Fast list prices
apply. Effort tokens (`high`, `xhigh`, …) stay on the stored slug and
are peeled only for price lookup.

## Price book (Cursor first-party)

Cited 2026-09-14 from [Cursor Models & Pricing](https://cursor.com/docs/models-and-pricing)
and [Grok 4.6](https://cursor.com/docs/models/grok-4-6). USD per million
tokens:

| Book key | Input | Cache read | Output |
| --- | ---: | ---: | ---: |
| `grok-4-6` | $2 | $0.50 | $6 |
| `grok-4-6-fast` | $4 | $1 | $12 |
| `grok-4-5` | $2 | $0.50 | $6 |
| `grok-4-5-fast` | $4 | $1 | $18 |
| `composer-2-5` | $0.50 | $0.20 | $2.50 |
| `composer-2-5-fast` | $3 | $0.50 | $15 |
| `unknown` | $0 | $0 | $0 |

Cursor does not list a cache-write rate for those first-party SKUs. T0
does not invent one (cache writes add $0). Claude / GPT rows stay on
published API list prices, including cache writes.

Slugs such as `cursor-grok-4.6-high` and `cursor-grok-4.6-high-fast`
normalize to the keys above (`cursor-` prefix stripped; effort/speed
suffixes peeled).

## Still unknown / still not a bill

These rows stay `unknown` (or have no usage row at all):

- Cursor Auto / `model=default` with no `model_id` and no nested real slug
- Prompt-only cloud / box transcripts (no `usage` — not metered; not turned into zero-token join rows)
- sessionStart / sessionEnd hook join rows that carry a session id but no model
- SKUs not in the bundled book and not a prefix of one (priced $0, not Sonnet)
- Cache-write tokens on Cursor first-party SKUs (rate unpublished → $0)

T2 Admin charged cents, when present, remain billed truth and are not
re-priced from this book.

## Verify on a machine with Cursor logs

```bash
./install.sh
ardoise backfill --force
ardoise status --json --month YYYY-MM | python3 -m json.tool
ardoise estimate --model cursor-grok-4.6-high --input-tokens 1000 --output-tokens 400 --json
```

Check `by_model`: Cursor traffic should show `cursor-grok-*` / `composer-*`
/ `grok-*`, not a pile of `default`. `unknown` means the log never named
a real model. Estimate for `cursor-grok-4.6-high` should use $2 / $6, not
$3 / $15.

To inspect one hook-shaped file:

```bash
python3 - <<'PY'
from ardoise.adapters.hook_event import event_to_entry
from ardoise.prices import lookup
raw = {
    "hook_event_name": "stop",
    "model": "default",
    "model_id": "grok-4.6",
    "input_tokens": 1000,
    "output_tokens": 100,
}
print(event_to_entry(raw, default_source="cursor")["model"])
print(lookup("cursor-grok-4.6-high"))
PY
```
