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


def _tier(row: dict[str, Any]) -> str:
    return str(row.get("tier_of_truth") or row.get("tier") or "T0")


def _amount(row: dict[str, Any]) -> float:
    if row.get("billed_usd") is not None:
        return float(row["billed_usd"])
    cents = row.get("usd_cents") or row.get("billed_cents")
    if cents not in (None, ""):
        return int(cents) / 100.0
    return 0.0


def _md(summary: dict[str, Any]) -> str:
    month = summary["month"]
    section_a = summary.get("section_a") or []
    billed_usd = float(summary.get("billed_usd") or 0)
    estimated = float(summary.get("estimated_usd") or summary.get("cost_usd") or 0)
    lines = [
        f"# Ardoise statement {month}",
        "",
        "## A. Vendor lines (invoice / T2 / T1 / T0)",
        "",
        "Prefer pasted invoice, else T2 billed events, else T1 snapshot, else T0 estimated.",
        "Each line prints its **tier of truth**. T0 is list-price estimate, not invoice-grade.",
        "",
    ]
    if section_a:
        invoice_grade = [row for row in section_a if row.get("invoice_grade")]
        if invoice_grade:
            lines.append(f"**Invoice-grade total (invoice / T1 / T2): ${billed_usd:.2f}**")
        else:
            lines.append("**Invoice-grade total: none** — vendor lines below are T0 estimated.")
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
        lines += ["No vendor activity for this cycle.", ""]

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
        alloc = row.get("allocated_billed_usd")
        alloc_s = f"{float(alloc):.2f}" if alloc is not None else "—"
        lines.append(
            f"| {row['project']} | {row['entries']} | {row['cost_usd']:.4f} | {alloc_s} | T0 |"
        )
    if not summary.get("by_project"):
        lines.append("| (none) | 0 | 0.0000 | — | T0 |")

    lines += [
        "",
        "### Lines",
        "",
        "| When | Project | Source | Model | In | Out | T0 estimate | Allocated billed | Tier |",
        "|---|---|---|---|---:|---:|---:|---:|---|",
    ]
    for row in summary.get("lines") or []:
        alloc = row.get("allocated_billed_usd")
        alloc_s = f"{float(alloc):.2f}" if alloc is not None else "—"
        lines.append(
            "| {occurred_at} | {project} | {source} | {model} | {input_tokens} | {output_tokens} | {est:.4f} | {alloc} | T0 |".format(
                occurred_at=row.get("occurred_at") or "",
                project=row.get("project") or "",
                source=row.get("source") or "",
                model=row.get("model") or "",
                input_tokens=int(row.get("input_tokens") or 0),
                output_tokens=int(row.get("output_tokens") or 0),
                est=float(row.get("estimated_usd") or row.get("cost_usd") or 0),
                alloc=alloc_s,
            )
        )
    lines += [
        "",
        "_Generated locally by Ardoise. Prompts and credentials are not stored._",
        "",
    ]
    return "\n".join(lines)


def _html_page(summary: dict[str, Any]) -> str:
    def cell(value: Any) -> str:
        return html.escape("" if value is None else str(value))

    section_a = summary.get("section_a") or []
    billed_usd = float(summary.get("billed_usd") or 0)
    estimated = float(summary.get("estimated_usd") or summary.get("cost_usd") or 0)
    if section_a:
        billed_rows = "".join(
            (
                "<tr>"
                f"<td>{cell(r.get('vendor'))}</td>"
                f"<td>{cell(r.get('person'))}</td>"
                f"<td>{cell(r.get('cycle'))}</td>"
                f"<td>{_amount(r):.4f}</td>"
                f"<td>{cell(_tier(r))}</td>"
                f"<td>{cell(r.get('source'))}</td>"
                "</tr>"
            )
            for r in section_a
        )
        grade = any(r.get("invoice_grade") for r in section_a)
        headline = (
            f"<p>Invoice-grade total <strong>${billed_usd:.2f}</strong> (invoice / T1 / T2)</p>"
            if grade
            else "<p>Invoice-grade total: none. Vendor lines below are T0 estimated.</p>"
        )
        billed_block = (
            headline
            + "<table><thead><tr><th>Vendor</th><th>Scope</th><th>Cycle</th>"
            + "<th>USD</th><th>Tier</th><th>Source</th></tr></thead>"
            + f"<tbody>{billed_rows}</tbody></table>"
        )
    else:
        billed_block = "<p>No vendor activity for this cycle.</p>"

    project_rows = "".join(
        (
            "<tr>"
            f"<td>{cell(r['project'])}</td><td>{r['entries']}</td>"
            f"<td>{r['cost_usd']:.4f}</td>"
            f"<td>{('%.2f' % float(r['allocated_billed_usd'])) if r.get('allocated_billed_usd') is not None else '—'}</td>"
            "<td>T0</td>"
            "</tr>"
        )
        for r in summary.get("by_project") or []
    ) or "<tr><td colspan='5'>(none)</td></tr>"

    line_rows = "".join(
        (
            "<tr>"
            f"<td>{cell(r.get('occurred_at'))}</td>"
            f"<td>{cell(r.get('project'))}</td>"
            f"<td>{cell(r.get('source'))}</td>"
            f"<td>{cell(r.get('model'))}</td>"
            f"<td>{int(r.get('input_tokens') or 0)}</td>"
            f"<td>{int(r.get('output_tokens') or 0)}</td>"
            f"<td>{float(r.get('estimated_usd') or r.get('cost_usd') or 0):.4f}</td>"
            f"<td>{('%.2f' % float(r['allocated_billed_usd'])) if r.get('allocated_billed_usd') is not None else '—'}</td>"
            "<td>T0</td>"
            "</tr>"
        )
        for r in summary.get("lines") or []
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Ardoise {cell(summary['month'])}</title>
<style>
body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 2rem; color: #111; }}
table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
th, td {{ border-bottom: 1px solid #ddd; padding: 0.4rem 0.5rem; text-align: left; }}
th {{ text-align: left; }}
.muted {{ color: #555; }}
.note {{ color: #444; max-width: 48rem; }}
</style>
</head>
<body>
<h1>Ardoise statement {cell(summary['month'])}</h1>
<h2>A. Vendor lines (invoice / T2 / T1 / T0)</h2>
<p class="note">Prefer pasted invoice, else T2 billed events, else T1 snapshot, else T0 estimated.
Each line prints its tier of truth. T0 is list-price estimate, not invoice-grade.</p>
{billed_block}
<h2>B. T0 allocation</h2>
<p class="note">T0 token weights attribute an invoice / T1 / T2 total across projects.
When a vendor line is T0 estimated, there is no billed total to allocate.
T0 estimated total <strong>${estimated:.4f}</strong>.</p>
<h3>By project</h3>
<table><thead><tr><th>Project</th><th>Entries</th><th>T0 estimate USD</th><th>Allocated billed USD</th><th>Tier</th></tr></thead>
<tbody>{project_rows}</tbody></table>
<h3>Lines</h3>
<table>
<thead><tr><th>When</th><th>Project</th><th>Source</th><th>Model</th><th>In</th><th>Out</th><th>T0 estimate</th><th>Allocated billed</th><th>Tier</th></tr></thead>
<tbody>{line_rows}</tbody>
</table>
<p class="muted">Generated locally. Prompts and credentials are not stored.</p>
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
