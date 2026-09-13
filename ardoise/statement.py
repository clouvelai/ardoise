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

from ardoise import attribution, paths, roster
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


def _md_attribution(summary: dict[str, Any]) -> list[str]:
    if not attribution.any_present(summary):
        return []
    lines = [
        "Present only when a transcript or hook named the dimension. Missing fields stay unattributed.",
        "",
    ]
    titles = {"agent": "Agent", "skill": "Skill", "effort": "Effort"}
    for dim in attribution.DIMENSIONS:
        rows = attribution.present(summary.get(f"by_{dim}"), dim)
        if not rows:
            continue
        extra = 0
        if len(rows) > 8:
            extra = len(rows) - 8
            rows = rows[:8]
        lines += [
            f"### By {titles[dim].lower()}",
            "",
            f"| {titles[dim]} | Entries | T0 estimate USD | Allocated billed USD |",
            "|---|---:|---:|---:|",
        ]
        for row in rows:
            lines.append(
                "| {name} | {entries} | {est:.4f} | {alloc} |".format(
                    name=row[dim],
                    entries=row["entries"],
                    est=float(row["cost_usd"]),
                    alloc=_alloc_cell(row.get("allocated_billed_usd")),
                )
            )
        if extra:
            lines.append(f"| … | {extra} more | — | — |")
        lines.append("")
    return lines


def _html_attribution(summary: dict[str, Any], cell) -> str:
    if not attribution.any_present(summary):
        return ""
    titles = {"agent": "Agent", "skill": "Skill", "effort": "Effort"}
    blocks: list[str] = []
    for dim in attribution.DIMENSIONS:
        rows = attribution.present(summary.get(f"by_{dim}"), dim)
        if not rows:
            continue
        extra = 0
        if len(rows) > 8:
            extra = len(rows) - 8
            rows = rows[:8]
        body = "".join(
            (
                "<tr>"
                f"<td>{cell(r[dim])}</td>"
                f'<td class="num">{r["entries"]}</td>'
                f'<td class="num">{float(r["cost_usd"]):.4f}</td>'
                f'<td class="num">{_alloc_cell(r.get("allocated_billed_usd"))}</td>'
                "</tr>"
            )
            for r in rows
        )
        if extra:
            body += (
                f'<tr><td>…</td><td class="num">{extra} more</td>'
                '<td class="num">—</td><td class="num">—</td></tr>'
            )
        blocks.append(
            f"<h3>By {titles[dim].lower()}</h3>"
            '<div class="alloc">'
            "<table>"
            "<thead><tr>"
            f"<th>{titles[dim]}</th>"
            '<th class="num">Entries</th>'
            '<th class="num">T0 estimate</th>'
            '<th class="num">Allocated billed</th>'
            "</tr></thead>"
            f"<tbody>{body}</tbody>"
            "</table></div>"
        )
    if not blocks:
        return ""
    return (
        '<section class="quiet attr">'
        "<h2>Attribution</h2>"
        '<p class="lede">Present only when a transcript or hook named the dimension. '
        "Missing fields stay unattributed.</p>"
        f"{''.join(blocks)}"
        "</section>"
    )


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


def _filter_label(summary: dict[str, Any]) -> str | None:
    filt = summary.get("filter")
    if not filt:
        return None
    return roster.display(filt.get("canonical") or filt.get("query"))


def _md(summary: dict[str, Any]) -> str:
    month = summary["month"]
    section_a = summary.get("section_a") or []
    billed_usd = float(summary.get("billed_usd") or 0)
    estimated = float(summary.get("estimated_usd") or summary.get("cost_usd") or 0)
    seat = _filter_label(summary)
    lines = [
        f"# Ardoise statement {month}",
        "",
    ]
    if seat:
        lines += [f"Seat **{seat}** · view only — ledger unchanged.", ""]
    lines += [
        _LEGEND,
        "",
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

    models = summary.get("by_model") or []
    if models:
        lines += [
            "",
            "### By model",
            "",
            "| Model | Entries | T0 estimate USD | Allocated billed USD | Tier |",
            "|---|---:|---:|---:|---|",
        ]
        for row in models:
            lines.append(
                "| {model} | {entries} | {est:.4f} | {alloc} | {tier} |".format(
                    model=row.get("model") or "",
                    entries=row["entries"],
                    est=float(row["cost_usd"]),
                    alloc=_alloc_cell(row.get("allocated_billed_usd")),
                    tier=_tier_md(row.get("tier") or "T0"),
                )
            )

    lines += [
        "",
        "### Per-event detail",
        "",
        f"Event-level rows are in `{summary.get('month')}.csv` next to this file.",
    ]
    attr_bits = _md_attribution(summary)
    if attr_bits:
        lines += [
            "",
            "## Attribution",
            "",
        ] + attr_bits
    notes = [str(item) for item in (summary.get("notes") or []) if item]
    if notes:
        lines += [
            "",
            "## Notes (soft)",
            "",
            "Informational only. Soft caps and anomaly flags never block the editor.",
            "",
        ]
        for note in notes:
            lines.append(f"- {note}")
        lines.append("")

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
    seat = _filter_label(summary)
    seat_chip = (
        f'<p class="seat"><span class="badge seat">{html.escape(seat)}</span> view only</p>'
        if seat
        else ""
    )

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

    notes = [str(item) for item in (summary.get("notes") or []) if item]
    if notes:
        items = "".join(f"<li>{html.escape(note)}</li>" for note in notes)
        notes_block = (
            '<section class="notes">'
            "<h2>Notes (soft)</h2>"
            "<p>Informational only. Soft caps and anomaly flags never block the editor.</p>"
            f"<ul>{items}</ul>"
            "</section>"
        )
    else:
        notes_block = ""
    attr_block = _html_attribution(summary, cell)

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

    model_rows = "".join(
        (
            "<tr>"
            f"<td>{cell(r.get('model'))}</td>"
            f'<td class="num">{r["entries"]}</td>'
            f'<td class="num">{float(r["cost_usd"]):.4f}</td>'
            f'<td class="num">{_alloc_cell(r.get("allocated_billed_usd"))}</td>'
            f"<td>{_badge(r.get('tier') or 'T0')}</td>"
            "</tr>"
        )
        for r in summary.get("by_model") or []
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Ardoise {month}{f" · {html.escape(seat)}" if seat else ""}</title>
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
.seat {{ margin: 0.35rem 0 0; color: var(--muted); font-size: 0.82rem; }}
.badge.seat {{ background: #f6f4f8; color: #5c5666; border-color: rgba(23, 20, 31, 0.1); }}
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
.notes {{
  margin-top: 1.6rem;
  padding: 1rem 1.15rem 1.1rem;
  border: 1px solid rgba(180, 120, 40, 0.22);
  background: #fff8ee;
  border-radius: 14px;
}}
.notes h2 {{ margin: 0 0 0.35rem; font-size: 0.95rem; }}
.notes p {{ margin: 0 0 0.55rem; color: var(--muted); font-size: 0.86rem; }}
.notes ul {{ margin: 0; padding-left: 1.15rem; color: #8a5a12; }}
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
    {seat_chip}
    {hero}
    <ul class="legend" aria-label="Tiers of truth">
      <li>{_badge("T2")} billed events</li>
      <li>{_badge("T1")} seat usage</li>
      <li>{_badge("T0")} local estimate</li>
      <li>{_badge("invoice")} paste-in</li>
    </ul>
  </header>
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
    {"<h3>By model</h3><div class=\"alloc\"><table><thead><tr><th>Model</th><th class=\"num\">Entries</th><th class=\"num\">T0 estimate</th><th class=\"num\">Allocated billed</th><th>Tier</th></tr></thead><tbody>" + model_rows + "</tbody></table></div>" if model_rows else ""}
    <p class="lede">Per-event rows are in <code>{month}.csv</code> next to this statement.</p>
  </section>
  {attr_block}
  {notes_block}
  <p class="foot">Generated locally. Prompts and credentials are not stored.</p>
</main>
</body>
</html>
"""


def _csv_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seat = _filter_label(summary)
    if seat:
        rows.append(
            {
                "section": "notes",
                "tier": "soft",
                "vendor": "",
                "person": (summary.get("filter") or {}).get("person") or "",
                "cycle": summary.get("month"),
                "source": f"seat filter {seat} (view only)",
                "usd_cents": "",
                "billed_usd": "",
                "invoice_grade": "",
                "project": "",
                "model": "",
                "occurred_at": "",
                "message_id": "",
                "request_id": "",
                "input_tokens": "",
                "output_tokens": "",
                "estimated_usd": "",
                "allocated_billed_usd": "",
                "agent": "",
                "skill": "",
                "effort": "",
            }
        )
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
                "agent": "",
                "skill": "",
                "effort": "",
            }
        )
    for note in summary.get("notes") or []:
        if not note:
            continue
        rows.append(
            {
                "section": "notes",
                "tier": "soft",
                "vendor": "",
                "person": "",
                "cycle": summary.get("month"),
                "source": note,
                "usd_cents": "",
                "billed_usd": "",
                "invoice_grade": "",
                "project": "",
                "model": "",
                "occurred_at": "",
                "message_id": "",
                "request_id": "",
                "input_tokens": "",
                "output_tokens": "",
                "estimated_usd": "",
                "allocated_billed_usd": "",
                "agent": "",
                "skill": "",
                "effort": "",
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
                "agent": row.get("agent") or "",
                "skill": row.get("skill") or "",
                "effort": row.get("effort") or "",
            }
        )
    return rows


def write_statement(
    month: str | None = None,
    *,
    out_dir: Path | None = None,
    person: str | None = None,
) -> dict[str, str]:
    month = month or current_month()
    summary = summarize(month, person=person)
    dest = out_dir or paths.statements_dir()
    dest.mkdir(parents=True, exist_ok=True)
    stem = roster.filename_for(month, summary.get("filter"))
    md_path = dest / f"{stem}.md"
    html_path = dest / f"{stem}.html"
    csv_path = dest / f"{stem}.csv"
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
        "agent",
        "skill",
        "effort",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in _csv_rows(summary):
            writer.writerow({k: row.get(k) for k in fieldnames})
    written = {"md": str(md_path), "html": str(html_path), "csv": str(csv_path), "month": month}
    if summary.get("filter"):
        written["person"] = str((summary.get("filter") or {}).get("canonical") or "")
        written["stem"] = stem
    return written
