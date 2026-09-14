"""Month statement as Markdown, HTML, and CSV.

Orb-floor spend statement (not a tax invoice): From / Prepared for, number,
period, Description × Quantity × Rate × Amount, vendor → model → token meters.
Section A billed truth still prefers invoice → T2 → T1; T0 is list-price weight.
"""

from __future__ import annotations

import csv
import html
from pathlib import Path
from typing import Any

from ardoise import attribution, config as config_mod, document, paths, roster
from ardoise.status import current_month, summarize


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


def _filter_label(summary: dict[str, Any]) -> str | None:
    filt = summary.get("filter")
    if not filt:
        return None
    return roster.display(filt.get("canonical") or filt.get("query"))


def _filter_kind(summary: dict[str, Any]) -> str:
    return str((summary.get("filter") or {}).get("kind") or "person")


def _money(value: Any, *, places: int = 2) -> str:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        number = 0.0
    if places == 2:
        return f"${number:,.2f}"
    return f"${number:,.{places}f}"


def _doc_for(summary: dict[str, Any]) -> dict[str, Any]:
    cfg = config_mod.load()
    return document.build_document(summary, config=cfg)


def _party_lines(party: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    name = str(party.get("name") or "").strip()
    if name:
        lines.append(name)
    for item in party.get("address") or []:
        text = str(item or "").strip()
        if text:
            lines.append(text)
    email = str(party.get("email") or "").strip()
    if email:
        lines.append(email)
    return lines


def _md(summary: dict[str, Any]) -> str:
    doc = _doc_for(summary)
    from_lines = _party_lines(doc.get("from") or {})
    prepared_lines = _party_lines(doc.get("prepared_for") or {})
    period = (doc.get("period") or {}).get("label") or ""
    total = doc.get("total_usd")
    grade = bool(doc.get("invoice_grade"))

    lines = [
        f"# {doc.get('title') or 'Statement'} {doc.get('number')}",
        "",
        "## From",
        "",
    ]
    lines += [f"- {item}" for item in from_lines] or ["- Ardoise"]
    lines += ["", "## Prepared for", ""]
    if prepared_lines:
        lines += [f"- {item}" for item in prepared_lines]
    else:
        lines.append("- —")
    lines += [
        "",
        "| | |",
        "|---|---|",
        f"| Statement number | {doc.get('number')} |",
        f"| Statement date | {doc.get('statement_date')} |",
        f"| Usage period | {period} |",
        f"| Truth | {'Billed' if grade else 'Estimate'} |",
        f"| Total | {_money(total, places=2 if grade else 4)} |",
        "",
        "| Description | Quantity | Rate | Amount |",
        "|---|---:|---:|---:|",
    ]

    groups = doc.get("groups") or []
    if not groups:
        lines.append("| (no usage this period) | — | — | — |")
    for group in groups:
        vendor = group.get("label") or group.get("vendor") or "vendor"
        group_places = 2 if group.get("invoice_grade") else 4
        lines.append(
            f"| **{vendor}** |  |  | **{_money(group.get('subtotal_usd'), places=group_places)}** |"
        )
        period_bits = [group.get("period_label") or period]
        if group.get("tier"):
            period_bits.append(str(group.get("tier")))
        lines.append(f"| {' · '.join(bit for bit in period_bits if bit)} |  |  |  |")
        for model in group.get("models") or []:
            model_name = model.get("model") or "(none)"
            lines.append(f"| {model_name} |  |  | {_money(model.get('subtotal_usd'), places=4)} |")
            for meter in model.get("lines") or []:
                lines.append(
                    "| {desc} | {qty} | {rate} | {amt} |".format(
                        desc=meter.get("description") or "",
                        qty=meter.get("quantity_label") or "—",
                        rate=meter.get("rate_label") or "—",
                        amt=_money(meter.get("amount_usd"), places=4),
                    )
                )
        adj = group.get("adjustment")
        if adj:
            lines.append(
                "| {desc} | — | — | {amt} |".format(
                    desc=adj.get("description") or "Reconciling adjustment",
                    amt=_money(adj.get("amount_usd"), places=4),
                )
            )

    totals = doc.get("totals") or {}
    if totals.get("show_reconciliation"):
        lines += [
            f"| List price |  |  | {_money(totals.get('list_usd'), places=4)} |",
            f"| Reconciling adjustment |  |  | {_money(totals.get('adjustment_usd'), places=4)} |",
        ]
    lines.append(
        f"| **Total** |  |  | **{_money(total, places=2 if grade else 4)}** |"
    )

    lines += ["", "## Memo", ""]
    for item in doc.get("memo") or []:
        lines.append(f"- {item}")

    if attribution.any_present(summary):
        lines += ["", "## Attribution", ""]
        titles = {"agent": "Agent", "skill": "Skill", "effort": "Effort"}
        for dim in attribution.DIMENSIONS:
            rows = attribution.present(summary.get(f"by_{dim}"), dim)
            if not rows:
                continue
            lines += [
                f"### By {titles[dim].lower()}",
                "",
                f"| {titles[dim]} | Entries | T0 estimate USD | Allocated billed USD |",
                "|---|---:|---:|---:|",
            ]
            for row in rows[:8]:
                alloc = row.get("allocated_billed_usd")
                alloc_s = "—" if alloc is None else f"{float(alloc):.2f}"
                lines.append(
                    f"| {row[dim]} | {row['entries']} | {float(row['cost_usd']):.4f} | {alloc_s} |"
                )
            if len(rows) > 8:
                lines.append(f"| … | {len(rows) - 8} more | — | — |")
            lines.append("")

    notes = [str(item) for item in (doc.get("notes") or summary.get("notes") or []) if item]
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

    lines += [
        "",
        f"Per-event rows are in `{summary.get('month')}.csv` next to this file.",
        "",
        "Copy totals into your invoice. Print the HTML → Save as PDF for a portable statement.",
        "",
        "_Generated locally by Ardoise. Prompts and credentials are not stored._",
        "",
    ]
    return "\n".join(lines)


def _party_html(party: dict[str, Any], cell) -> str:
    bits = _party_lines(party)
    if not bits:
        return "<p class=\"muted\">—</p>"
    first, *rest = bits
    body = f"<p class=\"party-name\">{cell(first)}</p>"
    if rest:
        body += "".join(f"<p class=\"party-line\">{cell(item)}</p>" for item in rest)
    return body


def _html_page(summary: dict[str, Any]) -> str:
    def cell(value: Any) -> str:
        return html.escape("" if value is None else str(value))

    doc = _doc_for(summary)
    month = cell(summary.get("month") or "")
    number = cell(doc.get("number") or "")
    period = cell((doc.get("period") or {}).get("label") or "")
    grade = bool(doc.get("invoice_grade"))
    total = doc.get("total_usd")
    total_s = _money(total, places=2 if grade else 4)
    totals = doc.get("totals") or {}

    group_blocks: list[str] = []
    for group in doc.get("groups") or []:
        vendor = cell(group.get("label") or group.get("vendor") or "vendor")
        group_places = 2 if group.get("invoice_grade") else 4
        sub = _money(group.get("subtotal_usd"), places=group_places)
        tier = cell(group.get("tier") or "T0")
        period_label = cell(group.get("period_label") or "")
        rows_html: list[str] = [
            "<tr class=\"group\">"
            f"<td colspan=\"3\"><strong>{vendor}</strong></td>"
            f'<td class="num"><strong>{sub}</strong></td>'
            "</tr>",
            "<tr class=\"group-period\">"
            f'<td colspan="4"><span class="period">{period_label}</span>'
            f'<span class="tier"> · {tier}</span></td>'
            "</tr>",
        ]
        for model in group.get("models") or []:
            model_name = cell(model.get("model") or "(none)")
            rows_html.append(
                "<tr class=\"sku\">"
                f"<td colspan=\"3\">{model_name}</td>"
                f'<td class="num">{_money(model.get("subtotal_usd"), places=4)}</td>'
                "</tr>"
            )
            for meter in model.get("lines") or []:
                rows_html.append(
                    "<tr class=\"meter\">"
                    f"<td class=\"indent\">{cell(meter.get('description'))}</td>"
                    f'<td class="num">{cell(meter.get("quantity_label"))}</td>'
                    f'<td class="num">{cell(meter.get("rate_label"))}</td>'
                    f'<td class="num">{_money(meter.get("amount_usd"), places=4)}</td>'
                    "</tr>"
                )
        adj = group.get("adjustment")
        if adj:
            rows_html.append(
                "<tr class=\"adj\">"
                f"<td class=\"indent\">{cell(adj.get('description'))}</td>"
                '<td class="num">—</td>'
                '<td class="num">—</td>'
                f'<td class="num">{_money(adj.get("amount_usd"), places=4)}</td>'
                "</tr>"
            )
        group_blocks.append(f'<tbody class="section">{"".join(rows_html)}</tbody>')

    if not group_blocks:
        table_body = (
            '<tbody><tr><td colspan="4" class="empty-row">'
            "No usage this period.</td></tr></tbody>"
        )
    else:
        table_body = "".join(group_blocks)

    foot_rows: list[str] = []
    if totals.get("show_reconciliation"):
        foot_rows += [
            "<tr class=\"tot-sub\">"
            '<td colspan="3">List price</td>'
            f'<td class="num">{_money(totals.get("list_usd"), places=4)}</td>'
            "</tr>",
            "<tr class=\"tot-adj\">"
            '<td colspan="3">Reconciling adjustment</td>'
            f'<td class="num">{_money(totals.get("adjustment_usd"), places=4)}</td>'
            "</tr>",
        ]
    foot_rows.append(
        "<tr class=\"tot-grand\">"
        "<td colspan=\"3\"><strong>Total</strong></td>"
        f'<td class="num"><strong>{total_s}</strong></td>'
        "</tr>"
    )
    table_foot = f"<tfoot>{''.join(foot_rows)}</tfoot>"

    memo_items = "".join(f"<li>{cell(item)}</li>" for item in (doc.get("memo") or []))
    notes = [str(item) for item in (doc.get("notes") or summary.get("notes") or []) if item]
    if notes:
        notes_block = (
            '<section class="notes">'
            "<h2>Notes (soft)</h2>"
            "<p>Informational only. Soft caps and anomaly flags never block the editor.</p>"
            f"<ul>{''.join(f'<li>{cell(n)}</li>' for n in notes)}</ul>"
            "</section>"
        )
    else:
        notes_block = ""

    attr_block = ""
    if attribution.any_present(summary):
        titles = {"agent": "Agent", "skill": "Skill", "effort": "Effort"}
        blocks: list[str] = []
        for dim in attribution.DIMENSIONS:
            rows = attribution.present(summary.get(f"by_{dim}"), dim)
            if not rows:
                continue
            body = "".join(
                (
                    "<tr>"
                    f"<td>{cell(r[dim])}</td>"
                    f'<td class="num">{r["entries"]}</td>'
                    f'<td class="num">{float(r["cost_usd"]):.4f}</td>'
                    f'<td class="num">'
                    f'{"—" if r.get("allocated_billed_usd") is None else f"{float(r["allocated_billed_usd"]):.2f}"}'
                    "</td>"
                    "</tr>"
                )
                for r in rows[:8]
            )
            blocks.append(
                f"<h3>By {titles[dim].lower()}</h3>"
                '<table class="attr"><thead><tr>'
                f"<th>{titles[dim]}</th><th class=\"num\">Entries</th>"
                '<th class="num">T0 estimate</th><th class="num">Allocated billed</th>'
                f"</tr></thead><tbody>{body}</tbody></table>"
            )
        if blocks:
            attr_block = (
                '<section class="quiet">'
                "<h2>Attribution</h2>"
                '<p class="lede">Present only when a transcript or hook named the dimension.</p>'
                f"{''.join(blocks)}</section>"
            )

    grade_label = "Billed" if grade else "Estimate"
    badge_kind = "billed" if grade else "estimate"
    copy_totals = html.escape(
        f"Statement {summary.get('month') or number} · {grade_label} · Total {total_s}",
        quote=True,
    )
    from_html = _party_html(doc.get("from") or {}, cell)
    prepared_html = _party_html(doc.get("prepared_for") or {}, cell)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Statement {number}</title>
<style>
:root {{
  --ink: #17141f;
  --muted: #6d6778;
  --hair: #ece8f2;
  --rule: #17141f;
  --paper: #ffffff;
  --mist: #f7f3fb;
}}
* {{ box-sizing: border-box; }}
html, body {{ background: #f4f0fb; }}
body {{
  margin: 0;
  color: var(--ink);
  font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  font-size: 14px;
  line-height: 1.45;
}}
.wrap {{
  max-width: 52rem;
  margin: 1.5rem auto 3rem;
  padding: 2rem 2.35rem 2.4rem;
  background: var(--paper);
  border: 1px solid #e9e1f6;
}}
.letterhead {{
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 1rem 2rem;
  align-items: start;
  margin-bottom: 1.35rem;
}}
.wordmark {{
  margin: 0;
  font-size: 1.15rem;
  font-weight: 650;
  letter-spacing: -0.03em;
}}
.kicker {{
  margin: 0.15rem 0 0;
  font-size: 0.72rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--muted);
  font-weight: 650;
}}
.doc-kind-wrap {{ text-align: right; }}
.doc-kind {{
  margin: 0;
  font-size: 1.85rem;
  font-weight: 650;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  line-height: 1;
}}
.chrome {{
  max-width: 52rem;
  margin: 1.1rem auto 0;
  padding: 0 0.2rem;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.55rem 1rem;
}}
.chrome-actions {{
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem 1rem;
}}
.badge {{
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 0.18rem 0.68rem;
  font-size: 0.68rem;
  font-weight: 650;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}}
.badge-estimate {{ background: #f3eef8; color: #5234d2; }}
.badge-billed {{ background: #7c5cff; color: #fff; }}
.letterhead .badge {{ margin-top: 0.55rem; }}
.print-btn {{
  border: 0;
  border-radius: 999px;
  background: #7c5cff;
  color: #fff;
  font: inherit;
  font-size: 0.84rem;
  font-weight: 650;
  padding: 0.45rem 1rem;
  cursor: pointer;
}}
.whisper {{
  border: 0;
  background: none;
  color: var(--muted);
  font: inherit;
  font-size: 0.8rem;
  cursor: pointer;
  padding: 0;
}}
.whisper:hover {{ color: var(--ink); }}
.top {{
  display: grid;
  grid-template-columns: 1.15fr 0.95fr;
  gap: 1.35rem 2rem;
  align-items: start;
}}
.party-label {{
  margin: 0 0 0.25rem;
  font-size: 0.72rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
  font-weight: 600;
}}
.party-name {{ margin: 0; font-weight: 650; }}
.party-line, .muted {{ margin: 0.1rem 0 0; color: var(--muted); }}
.prepared {{ margin-top: 1.05rem; }}
.meta {{
  margin: 0;
  width: 100%;
  border-collapse: collapse;
  font-size: 0.92rem;
}}
.meta th {{
  text-align: left;
  font-weight: 500;
  color: var(--muted);
  padding: 0.18rem 0.6rem 0.18rem 0;
}}
.meta td {{
  text-align: right;
  font-variant-numeric: tabular-nums;
  padding: 0.18rem 0;
}}
.meta tr.total td, .meta tr.total th {{
  padding-top: 0.55rem;
  font-weight: 700;
  font-size: 1.05rem;
  color: var(--ink);
}}
.hero-amt {{ font-variant-numeric: tabular-nums; }}
.lines {{
  margin-top: 1.6rem;
  width: 100%;
  border-collapse: collapse;
  font-size: 0.86rem;
}}
.col-desc {{ width: 52%; }}
.col-qty, .col-rate {{ width: 16%; }}
.col-amt {{ width: 16%; }}
.lines th {{
  text-align: left;
  border-bottom: 1px solid var(--rule);
  padding: 0.28rem 0.4rem 0.4rem;
  font-size: 0.7rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
  font-weight: 600;
}}
.lines th.num, .lines td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
.lines td {{
  padding: 0.22rem 0.4rem;
  border-bottom: 1px solid var(--hair);
  vertical-align: baseline;
}}
.lines tr.group td {{
  padding-top: 0.85rem;
  padding-bottom: 0.05rem;
  border-bottom: none;
}}
.lines tr.group-period td {{
  padding-top: 0;
  padding-bottom: 0.4rem;
  border-bottom: 1px solid #d8d2e4;
  color: var(--muted);
  font-size: 0.8rem;
}}
.lines tr.sku td {{ color: var(--ink); font-weight: 550; border-bottom-color: transparent; }}
.lines tr.meter td {{ border-bottom-color: #f3eef8; }}
.lines tr.meter td.indent,
.lines tr.adj td.indent {{ padding-left: 1.15rem; color: #4b4558; }}
.lines tr.adj td {{ color: var(--muted); }}
.lines .empty-row {{ color: var(--muted); padding: 1rem 0.4rem; }}
.lines tfoot td {{
  border-bottom: none;
  padding-top: 0.35rem;
}}
.lines tr.tot-sub td,
.lines tr.tot-adj td {{
  color: var(--muted);
  border-bottom: none;
}}
.lines tr.tot-grand td {{
  padding-top: 0.55rem;
  border-top: 1px solid var(--rule);
  font-size: 0.95rem;
}}
.memo {{
  margin-top: 1.75rem;
  color: var(--muted);
  font-size: 0.82rem;
}}
.memo h2, .quiet h2, .notes h2 {{
  margin: 0 0 0.45rem;
  font-size: 0.72rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--muted);
}}
.memo ul {{ margin: 0; padding-left: 1.1rem; }}
.quiet {{ margin-top: 1.75rem; }}
.lede {{ margin: 0 0 0.7rem; color: var(--muted); font-size: 0.86rem; }}
.attr {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; margin-bottom: 0.8rem; }}
.attr th, .attr td {{ padding: 0.3rem 0.4rem; border-bottom: 1px solid var(--hair); text-align: left; }}
.attr .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
.notes {{
  margin-top: 1.4rem;
  padding: 0.85rem 1rem;
  border: 1px solid #e9e1f6;
  background: var(--mist);
}}
.notes p {{ margin: 0 0 0.45rem; color: var(--muted); font-size: 0.82rem; }}
.notes ul {{ margin: 0; padding-left: 1.1rem; color: #5234d2; }}
.foot {{ margin-top: 1.8rem; color: var(--muted); font-size: 0.75rem; }}
@page {{
  size: letter;
  margin: 14mm 16mm 16mm;
}}
@page {{
  @bottom-center {{
    content: counter(page) " of " counter(pages);
    font-size: 9pt;
    color: #6d6778;
  }}
}}
@media print {{
  html, body {{ background: #fff; }}
  body {{
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }}
  .print-hide {{ display: none !important; }}
  .wrap {{
    margin: 0;
    max-width: none;
    border: none;
    padding: 0;
  }}
  thead {{ display: table-header-group; }}
  tfoot {{ display: table-footer-group; }}
  tbody.section {{ break-inside: avoid; page-break-inside: avoid; }}
  tr.group, tr.group-period, tr.sku {{ break-after: avoid; page-break-after: avoid; }}
  .notes, .quiet, .memo {{ break-inside: avoid; }}
}}
</style>
</head>
<body>
<div class="chrome print-hide">
  <span class="badge badge-{badge_kind}">{grade_label}</span>
  <div class="chrome-actions">
    <button type="button" class="whisper" data-copy-totals="{copy_totals}" onclick="copyTotals(this)">Copy totals into your invoice</button>
    <button type="button" class="print-btn" onclick="window.print()">Print statement</button>
  </div>
</div>
<main class="wrap">
  <header class="letterhead">
    <div>
      <p class="wordmark">Ardoise</p>
      <p class="kicker">Spend statement</p>
    </div>
    <div class="doc-kind-wrap">
      <h1 class="doc-kind">Statement</h1>
      <p class="badge badge-{badge_kind}">{grade_label}</p>
    </div>
  </header>
  <div class="top">
    <div>
      <p class="party-label">From</p>
      {from_html}
      <div class="prepared">
        <p class="party-label">Prepared for</p>
        {prepared_html}
      </div>
    </div>
    <div>
      <table class="meta">
        <tr><th>Statement number</th><td>{number}</td></tr>
        <tr><th>Statement date</th><td>{cell(doc.get("statement_date"))}</td></tr>
        <tr><th>Usage period</th><td>{period}</td></tr>
        <tr class="total"><th>Total <span class="badge badge-{badge_kind}">{grade_label}</span></th>
            <td class="hero-amt">{total_s}</td></tr>
      </table>
    </div>
  </div>
  <table class="lines">
    <colgroup>
      <col class="col-desc"/>
      <col class="col-qty"/>
      <col class="col-rate"/>
      <col class="col-amt"/>
    </colgroup>
    <thead>
      <tr>
        <th>Description</th>
        <th class="num">Quantity</th>
        <th class="num">Rate</th>
        <th class="num">Amount</th>
      </tr>
    </thead>
    {table_body}
    {table_foot}
  </table>
  <section class="memo">
    <h2>Memo</h2>
    <ul>{memo_items}</ul>
  </section>
  {attr_block}
  {notes_block}
  <p class="foot">Generated locally. Prompts and credentials are not stored.
  Per-event rows are in <code>{month}.csv</code>. Print statement → Save as PDF for a portable copy.</p>
</main>
<script>
function copyTotals(btn) {{
  var text = btn.getAttribute("data-copy-totals") || "";
  function done() {{
    var prior = btn.getAttribute("data-label") || btn.textContent;
    if (!btn.getAttribute("data-label")) btn.setAttribute("data-label", prior);
    btn.textContent = "Copied";
    setTimeout(function () {{ btn.textContent = btn.getAttribute("data-label"); }}, 1600);
  }}
  if (navigator.clipboard && navigator.clipboard.writeText) {{
    navigator.clipboard.writeText(text).then(done).catch(function () {{ fallback(); }});
  }} else {{
    fallback();
  }}
  function fallback() {{
    var area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.left = "-9999px";
    document.body.appendChild(area);
    area.select();
    try {{ document.execCommand("copy"); }} catch (e) {{}}
    area.remove();
    done();
  }}
}}
</script>
</body>
</html>
"""


def _csv_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seat = _filter_label(summary)
    if seat:
        role = "agent" if _filter_kind(summary) == "agent" else "seat"
        rows.append(
            {
                "section": "notes",
                "tier": "soft",
                "vendor": "",
                "person": (summary.get("filter") or {}).get("person") or "",
                "cycle": summary.get("month"),
                "source": f"{role} filter {seat} (view only)",
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
