"""Month statement as Markdown, HTML, and CSV.

Section A: one vendor line each, preferring invoice → T2 → T1 → T0 estimated.
Each line prints its tier of truth. Section B uses T0 as weights only when
reconciling to an invoice / T1 / T2 total.
"""

from __future__ import annotations

import csv
import html
from pathlib import Path
from typing import Any

from ardoise import paths
from ardoise.status import current_month, summarize

_LEGEND = "T2 billed events · T1 seat usage · T0 local estimate · Invoice paste-in"


def _tier(row: dict[str, Any]) -> str:
    return str(row.get("tier_of_truth") or row.get("tier") or "T0")


def _amount(row: dict[str, Any]) -> float:
    if row.get("billed_usd") is not None:
        return float(row["billed_usd"])
    cents = row.get("usd_cents") or row.get("billed_cents")
    if cents not in (None, ""):
        return int(cents) / 100.0
    return 0.0


def _tier_key(value: Any) -> str:
    raw = str(value or "").strip()
    if raw.lower() == "invoice":
        return "invoice"
    upper = raw.upper()
    if upper in {"T0", "T1", "T2"}:
        return upper
    return raw or "T0"


def _tier_md(value: Any) -> str:
    key = _tier_key(value)
    if key == "invoice":
        return "invoice"
    return f"[{key}]"


def _alloc_cell(value: Any, *, places: int = 2) -> str:
    if value is None:
        return "—"
    return f"{float(value):.{places}f}"


def _when(value: Any) -> str:
    text = "" if value is None else str(value)
    if len(text) >= 19 and text[10] == "T":
        return f"{text[:10]} {text[11:16]}"
    return text


def _source_note(row: dict[str, Any]) -> str:
    invoice_id = str(row.get("invoice_id") or "").strip()
    source = str(row.get("source") or "").strip()
    tier = _tier_key(_tier(row))
    if invoice_id and source and invoice_id not in source and source not in {"paste", "t1", "t2"}:
        return f"{source} · {invoice_id}"
    if invoice_id:
        return f"Invoice {invoice_id}"
    if source in {"paste", "t1", "t2"}:
        return {"paste": "Invoice paste-in", "t1": "T1 seat usage", "t2": "T2 billed events"}[source]
    if source:
        return source
    if tier == "invoice":
        return "Invoice paste-in"
    if tier == "T1":
        return "T1 seat usage"
    if tier == "T2":
        return "T2 billed events"
    return ""


def _alert_items(summary: dict[str, Any]) -> list[str]:
    items: list[str] = []
    for row in summary.get("budgets") or []:
        metric = str(row.get("metric") or "usd")
        period = str(row.get("period") or "month")
        state = str(row.get("state") or "ok")
        limit = float(row.get("limit") or 0)
        used = float(row.get("used") or 0)
        remaining = float(row.get("remaining") or 0)
        if metric == "tokens":
            body = f"{period} tokens {int(round(used))}/{int(round(limit))} remaining {int(round(remaining))} ({state})"
        else:
            body = f"{period} usd ${used:.2f}/${limit:.2f} remaining ${remaining:.2f} ({state})"
        items.append(body)
    for flag in summary.get("flags") or []:
        kind = str(flag.get("kind") or "")
        if kind.startswith("budget_"):
            continue
        items.append(str(flag.get("message") or kind or "flag"))
    return items


def _md_alerts(summary: dict[str, Any]) -> list[str]:
    items = _alert_items(summary)
    if not items:
        return []
    lines = [
        "## Alerts",
        "",
        "Soft budgets and anomaly flags. They never block the CLI.",
        "",
    ]
    for item in items:
        lines.append(f"- {item}")
    lines.append("")
    return lines


def _md(summary: dict[str, Any]) -> str:
    month = summary["month"]
    section_a = summary.get("section_a") or []
    billed_usd = float(summary.get("billed_usd") or 0)
    estimated = float(summary.get("estimated_usd") or summary.get("cost_usd") or 0)
    lines = [
        f"# Ardoise statement {month}",
        "",
        _LEGEND,
        "",
    ]
    lines += _md_alerts(summary)
    lines += [
        "## A. Vendor lines (invoice / T2 / T1)",
        "",
        "Prefer pasted invoice, else T2 billed events, else T1 snapshot.",
        "Each line prints its **tier of truth**. T0 list-price estimates are not billed truth.",
        "",
    ]
    if section_a:
        invoice_grade = [row for row in section_a if row.get("invoice_grade")]
        if invoice_grade:
            lines.append(f"**Invoice-grade total (invoice / T1 / T2): ${billed_usd:.2f}**")
        else:
            lines.append("**Invoice-grade total: none** — add an invoice or wait for T1/T2.")
        lines += [
            "",
            "| Vendor | Scope | Cycle | USD | Tier | Source |",
            "|---|---|---|---:|---|---|",
        ]
        for row in section_a:
            lines.append(
                "| {vendor} | {person} | {cycle} | {usd:.4f} | {tier} | {source} |".format(
                    vendor=row.get("vendor") or "",
                    person=row.get("person") or "",
                    cycle=row.get("cycle") or "",
                    usd=_amount(row),
                    tier=_tier(row),
                    source=row.get("source") or "",
                )
            )
    else:
        lines += [
            "No invoice, T2 billed events, or T1 snapshot for this cycle.",
            "T0 estimates in section B are allocation weights only — not billed totals.",
            "",
        ]

    lines += [
        "",
        "## B. T0 allocation",
        "",
        "T0 token weights attribute an invoice / T1 / T2 total across projects.",
        "When a vendor line is T0 estimated, there is no billed total to allocate.",
        f"T0 estimated total: **${estimated:.4f}**.",
        "",
        "### By project",
        "",
        "| Project | Entries | T0 estimate USD | Allocated billed USD | Tier |",
        "|---|---:|---:|---:|---|",
    ]
    for row in summary.get("by_project") or []:
        lines.append(
            "| {project} | {entries} | {est:.4f} | {alloc} | {tier} |".format(
                project=row["project"],
                entries=row["entries"],
                est=float(row["cost_usd"]),
                alloc=_alloc_cell(row.get("allocated_billed_usd")),
                tier=_tier_md(row.get("tier") or "T0"),
            )
        )
    if not summary.get("by_project"):
        lines.append("| (none) | 0 | 0.0000 | — | [T0] |")

    lines += [
        "",
        "### Lines",
        "",
        "| When | Project | Source | Model | In | Out | T0 estimate | Allocated billed | Tier |",
        "|---|---|---|---|---:|---:|---:|---:|---|",
    ]
    for row in summary.get("lines") or []:
        lines.append(
            "| {occurred_at} | {project} | {source} | {model} | {input_tokens} | {output_tokens} | {est:.4f} | {alloc} | {tier} |".format(
                occurred_at=row.get("occurred_at") or "",
                project=row.get("project") or "",
                source=row.get("source") or "",
                model=row.get("model") or "",
                input_tokens=int(row.get("input_tokens") or 0),
                output_tokens=int(row.get("output_tokens") or 0),
                est=float(row.get("estimated_usd") or row.get("cost_usd") or 0),
                alloc=_alloc_cell(row.get("allocated_billed_usd")),
                tier=_tier_md(row.get("origin_tier") or row.get("tier") or "T0"),
            )
        )
    lines += [
        "",
        "_Generated locally by Ardoise. Prompts and credentials are not stored._",
        "",
    ]
    return "\n".join(lines)


def _badge(value: Any) -> str:
    key = _tier_key(value)
    label = "Invoice" if key == "invoice" else key
    cls = {
        "invoice": "badge invoice",
        "T2": "badge t2",
        "T1": "badge t1",
        "T0": "badge t0",
    }.get(key, "badge")
    return f'<span class="{cls}">{html.escape(label)}</span>'


def _html_page(summary: dict[str, Any]) -> str:
    def cell(value: Any) -> str:
        return html.escape("" if value is None else str(value))

    month = cell(summary["month"])
    section_a = summary.get("section_a") or []
    billed_usd = float(summary.get("billed_usd") or 0)
    estimated = float(summary.get("estimated_usd") or summary.get("cost_usd") or 0)
    entries = int(summary.get("month_entries") or 0)
    grade = any(row.get("invoice_grade") for row in section_a)

    if section_a:
        if grade:
            hero = (
                f'<p class="hero-amt">${billed_usd:.2f} <small>invoice-grade</small></p>'
                f'<p class="hero-sub">T0 estimate ${estimated:.4f} · allocation only · {entries} lines</p>'
            )
        else:
            hero = (
                '<p class="hero-amt">— <small>no invoice-grade total</small></p>'
                f'<p class="hero-sub">T0 estimate ${estimated:.4f} · allocation only · {entries} lines</p>'
            )
        cards = []
        for row in section_a:
            tier = _tier(row)
            kind = _tier_key(tier)
            person = str(row.get("person") or "").strip()
            meta_bits = [str(row.get("cycle") or "").strip()]
            if person:
                meta_bits.append(person)
            note = _source_note(row)
            if note:
                meta_bits.append(note)
            extra = " invoice" if kind == "invoice" else ""
            cards.append(
                '<article class="card{extra}">'
                '<div class="card-top">'
                '<div><p class="vendor">{vendor}</p>{badge}</div>'
                '<p class="amt">${amount:.2f}</p>'
                "</div>"
                '<p class="meta">{meta}</p>'
                "</article>".format(
                    extra=extra,
                    vendor=cell(row.get("vendor") or "vendor"),
                    badge=_badge(tier),
                    amount=_amount(row),
                    meta=cell(" · ".join(bit for bit in meta_bits if bit)),
                )
            )
        billed_block = f'<div class="stack">{"".join(cards)}</div>'
    else:
        hero = (
            '<p class="hero-amt">— <small>no billed total</small></p>'
            f'<p class="hero-sub">T0 estimate ${estimated:.4f} · allocation only · {entries} lines</p>'
        )
        billed_block = (
            '<div class="empty">'
            "<p>No invoice, T2 billed events, or T1 snapshot for this cycle.</p>"
            "<p>T0 estimates in section B are allocation weights only.</p>"
            "</div>"
        )

    project_rows = "".join(
        (
            "<tr>"
            f"<td>{cell(r['project'])}</td>"
            f'<td class="num">{r["entries"]}</td>'
            f'<td class="num">{float(r["cost_usd"]):.4f}</td>'
            f'<td class="num">{_alloc_cell(r.get("allocated_billed_usd"))}</td>'
            f"<td>{_badge(r.get('tier') or 'T0')}</td>"
            "</tr>"
        )
        for r in summary.get("by_project") or []
    ) or '<tr><td colspan="5">(none)</td></tr>'

    alert_items = _alert_items(summary)
    has_flags = bool(summary.get("flags"))
    if alert_items:
        alert_lis = "".join(f"<li>{cell(item)}</li>" for item in alert_items)
        warn_cls = " warn" if has_flags else ""
        alerts_block = (
            f'<section class="alerts{warn_cls}" aria-label="Alerts">'
            "<h2>Alerts</h2>"
            f"<ul>{alert_lis}</ul>"
            "</section>"
        )
    else:
        alerts_block = ""

    line_rows = "".join(
        (
            "<tr>"
            f"<td>{cell(_when(r.get('occurred_at')))}</td>"
            f"<td>{cell(r.get('project'))}</td>"
            f"<td>{cell(r.get('source'))}</td>"
            f"<td>{cell(r.get('model'))}</td>"
            f'<td class="num">{int(r.get("input_tokens") or 0)}</td>'
            f'<td class="num">{int(r.get("output_tokens") or 0)}</td>'
            f'<td class="num">{float(r.get("estimated_usd") or r.get("cost_usd") or 0):.4f}</td>'
            f'<td class="num">{_alloc_cell(r.get("allocated_billed_usd"))}</td>'
            f"<td>{_badge(r.get('origin_tier') or r.get('tier') or 'T0')}</td>"
            "</tr>"
        )
        for r in summary.get("lines") or []
    ) or '<tr><td colspan="9">(none)</td></tr>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Ardoise {month}</title>
<style>
:root {{
  --ink: #17141f;
  --muted: #6d6778;
  --grape: #7C5CFF;
  --grape-deep: #6244e6;
  --paper: #fffcfe;
  --hair: rgba(23, 20, 31, 0.08);
}}
* {{ box-sizing: border-box; }}
html {{ background: #f4f0fb; }}
body {{
  margin: 0;
  color: var(--ink);
  font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  font-size: 15px;
  line-height: 1.5;
  background:
    radial-gradient(880px 420px at 88% 0%, rgba(167, 139, 250, 0.16), transparent 58%),
    linear-gradient(180deg, #f4f0fb 0%, #f7f3fc 42%, #f3eef8 100%);
  min-height: 100vh;
}}
.wrap {{ max-width: 52rem; margin: 0 auto; padding: 3.25rem 2rem 4.5rem; }}
.brand {{
  margin: 0;
  font-size: 0.74rem;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--grape);
  font-weight: 650;
}}
h1 {{
  margin: 0.4rem 0 0.55rem;
  font-size: 2rem;
  font-weight: 650;
  letter-spacing: -0.035em;
}}
.hero-amt {{
  margin: 0;
  font-size: 2.15rem;
  font-weight: 650;
  letter-spacing: -0.04em;
  font-variant-numeric: tabular-nums;
}}
.hero-amt small {{
  font-size: 0.92rem;
  color: var(--muted);
  font-weight: 500;
  letter-spacing: 0;
}}
.hero-sub {{ margin: 0.35rem 0 0; color: var(--muted); font-size: 0.92rem; }}
.legend {{
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem 0.95rem;
  margin: 1.35rem 0 0;
  padding: 0;
  list-style: none;
  color: var(--muted);
  font-size: 0.8rem;
}}
.legend li {{ display: flex; align-items: center; gap: 0.4rem; }}
.badge {{
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 0.12rem 0.55rem;
  font-size: 0.7rem;
  font-weight: 650;
  letter-spacing: 0.04em;
  background: #efe8fb;
  color: var(--grape-deep);
  border: 1px solid rgba(124, 92, 255, 0.18);
}}
.badge.t2 {{ background: #ece6ff; color: #5234d2; }}
.badge.t1 {{ background: #f3eef8; color: #6244e6; }}
.badge.t0 {{ background: #f6f4f8; color: #6d6778; border-color: rgba(23, 20, 31, 0.08); }}
.badge.invoice {{ background: #7C5CFF; color: #fff; border-color: transparent; }}
section {{ margin: 2.5rem 0 0; }}
section.quiet {{ margin-top: 2.85rem; }}
h2 {{
  margin: 0 0 0.7rem;
  font-size: 0.74rem;
  font-weight: 650;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--muted);
}}
h3 {{
  margin: 1.35rem 0 0.45rem;
  font-size: 0.92rem;
  font-weight: 600;
}}
.lede {{ margin: 0 0 1.05rem; max-width: 38rem; color: var(--muted); font-size: 0.92rem; }}
.stack {{ display: flex; flex-direction: column; gap: 0.7rem; }}
.card {{
  background: var(--paper);
  border: 1px solid var(--hair);
  border-radius: 16px;
  padding: 1.05rem 1.2rem;
  box-shadow: 0 8px 28px rgba(76, 29, 149, 0.045);
}}
.card.invoice {{
  border-color: rgba(124, 92, 255, 0.22);
  box-shadow: 0 10px 32px rgba(124, 92, 255, 0.08);
}}
.card-top {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; }}
.vendor {{ margin: 0 0 0.4rem; font-weight: 650; }}
.amt {{ margin: 0; font-variant-numeric: tabular-nums; font-weight: 650; font-size: 1.2rem; }}
.meta {{ margin: 0.4rem 0 0; color: var(--muted); font-size: 0.82rem; }}
.empty {{
  border: 1px dashed rgba(124, 92, 255, 0.28);
  border-radius: 16px;
  padding: 1.05rem 1.2rem;
  color: var(--muted);
}}
.empty p {{ margin: 0 0 0.35rem; }}
.empty p:last-child {{ margin: 0; }}
.alloc {{
  background: rgba(255, 252, 254, 0.55);
  border: 1px solid var(--hair);
  border-radius: 16px;
  overflow: hidden;
}}
table {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; }}
th, td {{
  padding: 0.48rem 0.7rem;
  text-align: left;
  border-bottom: 1px solid rgba(23, 20, 31, 0.055);
  vertical-align: baseline;
}}
th {{
  color: var(--muted);
  font-weight: 550;
  font-size: 0.7rem;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}}
td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
tbody tr:last-child td {{ border-bottom: none; }}
.lines {{ margin-top: 0.15rem; }}
.alerts {{
  margin: 1.45rem 0 0;
  padding: 0.85rem 1.05rem;
  border-radius: 14px;
  background: rgba(255, 252, 254, 0.62);
  border: 1px solid var(--hair);
}}
.alerts.warn {{
  border-color: rgba(124, 92, 255, 0.22);
}}
.alerts h2 {{ margin-bottom: 0.45rem; }}
.alerts ul {{
  margin: 0;
  padding: 0;
  list-style: none;
}}
.alerts li {{
  color: var(--muted);
  font-size: 0.86rem;
  padding: 0.12rem 0;
}}
.foot {{ margin-top: 2.8rem; color: var(--muted); font-size: 0.78rem; }}
@media print {{
  html, body {{ background: #fff; }}
  body {{ background: #fff; }}
  .wrap {{ max-width: none; padding: 0.55in 0.65in; }}
  .card, .alloc, .empty {{ box-shadow: none; break-inside: avoid; }}
  .badge.invoice {{
    color: var(--grape-deep);
    background: #efe8fb;
    border: 1px solid rgba(124, 92, 255, 0.28);
  }}
}}
</style>
</head>
<body>
<main class="wrap">
  <header>
    <p class="brand">Ardoise</p>
    <h1>Statement {month}</h1>
    {hero}
    <ul class="legend" aria-label="Tiers of truth">
      <li>{_badge("T2")} billed events</li>
      <li>{_badge("T1")} seat usage</li>
      <li>{_badge("T0")} local estimate</li>
      <li>{_badge("invoice")} paste-in</li>
    </ul>
  </header>
  {alerts_block}
  <section>
    <h2>A. Vendor lines</h2>
    <p class="lede">Prefer pasted invoice, else T2 billed events, else T1 snapshot. T0 token × list price is not billed truth.</p>
    {billed_block}
  </section>
  <section class="quiet">
    <h2>B. T0 allocation</h2>
    <p class="lede">T0 token weights attribute an invoice / T1 / T2 total across projects. Estimated total <strong>${estimated:.4f}</strong>.</p>
    <h3>By project</h3>
    <div class="alloc">
      <table>
        <thead>
          <tr>
            <th>Project</th>
            <th class="num">Entries</th>
            <th class="num">T0 estimate</th>
            <th class="num">Allocated billed</th>
            <th>Tier</th>
          </tr>
        </thead>
        <tbody>{project_rows}</tbody>
      </table>
    </div>
    <h3>Lines</h3>
    <div class="alloc lines">
      <table>
        <thead>
          <tr>
            <th>When</th>
            <th>Project</th>
            <th>Source</th>
            <th>Model</th>
            <th class="num">In</th>
            <th class="num">Out</th>
            <th class="num">T0 estimate</th>
            <th class="num">Allocated billed</th>
            <th>Tier</th>
          </tr>
        </thead>
        <tbody>{line_rows}</tbody>
      </table>
    </div>
  </section>
  <p class="foot">Generated locally. Prompts and credentials are not stored.</p>
</main>
</body>
</html>
"""


def _csv_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in summary.get("section_a") or []:
        rows.append(
            {
                "section": "A_vendor",
                "tier": _tier(row),
                "vendor": row.get("vendor"),
                "person": row.get("person"),
                "cycle": row.get("cycle"),
                "source": row.get("source"),
                "usd_cents": row.get("usd_cents") or row.get("billed_cents"),
                "billed_usd": _amount(row),
                "invoice_grade": row.get("invoice_grade"),
                "project": "",
                "model": "",
                "occurred_at": "",
                "message_id": "",
                "request_id": "",
                "input_tokens": "",
                "output_tokens": "",
                "estimated_usd": "" if row.get("invoice_grade") else _amount(row),
                "allocated_billed_usd": "",
            }
        )
    for row in summary.get("lines") or []:
        rows.append(
            {
                "section": "B_t0_allocation",
                "tier": "T0",
                "vendor": row.get("vendor"),
                "person": row.get("person"),
                "cycle": row.get("cycle"),
                "source": row.get("source"),
                "usd_cents": row.get("billed_cents"),
                "billed_usd": "",
                "invoice_grade": "",
                "project": row.get("project"),
                "model": row.get("model"),
                "occurred_at": row.get("occurred_at"),
                "message_id": row.get("message_id"),
                "request_id": row.get("request_id"),
                "input_tokens": row.get("input_tokens"),
                "output_tokens": row.get("output_tokens"),
                "estimated_usd": row.get("estimated_usd") or row.get("cost_usd"),
                "allocated_billed_usd": row.get("allocated_billed_usd"),
            }
        )
    return rows


def write_statement(month: str | None = None, *, out_dir: Path | None = None) -> dict[str, str]:
    month = month or current_month()
    summary = summarize(month)
    dest = out_dir or paths.statements_dir()
    dest.mkdir(parents=True, exist_ok=True)
    md_path = dest / f"{month}.md"
    html_path = dest / f"{month}.html"
    csv_path = dest / f"{month}.csv"
    md_path.write_text(_md(summary), encoding="utf-8")
    html_path.write_text(_html_page(summary), encoding="utf-8")
    fieldnames = [
        "section",
        "tier",
        "vendor",
        "person",
        "cycle",
        "source",
        "usd_cents",
        "billed_usd",
        "invoice_grade",
        "project",
        "model",
        "occurred_at",
        "message_id",
        "request_id",
        "input_tokens",
        "output_tokens",
        "estimated_usd",
        "allocated_billed_usd",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in _csv_rows(summary):
            writer.writerow({k: row.get(k) for k in fieldnames})
    return {"md": str(md_path), "html": str(html_path), "csv": str(csv_path), "month": month}
