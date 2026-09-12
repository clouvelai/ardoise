"""Month statement as Markdown, HTML, and CSV.

Section A is billed truth (invoice / T1 / T2) with explicit tiers of truth.
T0 list-price estimates only allocate/attribute; they are never section A billed totals.
"""

from __future__ import annotations

import csv
import html
from pathlib import Path
from typing import Any

from ardoise import paths
from ardoise.status import current_month, summarize


def _md(summary: dict[str, Any]) -> str:
    month = summary["month"]
    section_a = summary.get("section_a") or []
    billed_usd = float(summary.get("billed_usd") or 0)
    estimated = float(summary.get("estimated_usd") or summary.get("cost_usd") or 0)
    lines = [
        f"# Ardoise statement {month}",
        "",
        "## A. Billed truth (invoice / T1 / T2)",
        "",
        "These dollars come from pasted invoices, T1 vendor snapshots, or T2 billed events.",
        "T0 token × list-price estimates are **not** billed truth.",
        "",
    ]
    if section_a:
        lines += [
            f"**Billed total: ${billed_usd:.2f}**",
            "",
            "| Vendor | Person | Cycle | Billed USD | Tier of truth | Source |",
            "|---|---|---|---:|---|---|",
        ]
        for row in section_a:
            lines.append(
                "| {vendor} | {person} | {cycle} | {billed_usd:.2f} | {tier} | {source} |".format(
                    vendor=row.get("vendor") or "",
                    person=row.get("person") or "",
                    cycle=row.get("cycle") or "",
                    billed_usd=float(row.get("billed_usd") or 0),
                    tier=row.get("tier_of_truth") or row.get("tier") or "",
                    source=row.get("source") or "",
                )
            )
    else:
        lines += [
            "No invoice, T1 snapshot, or T2 billed events for this cycle.",
            "Section A billed total is empty — T0 estimates below are allocation only.",
            "",
        ]

    lines += [
        "",
        "## B. T0 allocation (not billed)",
        "",
        "Local token × list price. Used only to attribute billed dollars across projects.",
        f"T0 estimated total: **${estimated:.4f}** (not invoice-grade).",
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
                f"<td>{float(r.get('billed_usd') or 0):.2f}</td>"
                f"<td>{cell(r.get('tier_of_truth') or r.get('tier'))}</td>"
                f"<td>{cell(r.get('source'))}</td>"
                "</tr>"
            )
            for r in section_a
        )
        billed_block = (
            f"<p>Billed total <strong>${billed_usd:.2f}</strong></p>"
            "<table><thead><tr><th>Vendor</th><th>Person</th><th>Cycle</th>"
            "<th>Billed USD</th><th>Tier of truth</th><th>Source</th></tr></thead>"
            f"<tbody>{billed_rows}</tbody></table>"
        )
    else:
        billed_block = (
            "<p>No invoice, T1 snapshot, or T2 billed events for this cycle. "
            "T0 estimates below are allocation only — not billed truth.</p>"
        )

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
<h2>A. Billed truth (invoice / T1 / T2)</h2>
<p class="note">These dollars come from pasted invoices, T1 vendor snapshots, or T2 billed events.
T0 token × list-price estimates are not billed truth.</p>
{billed_block}
<h2>B. T0 allocation (not billed)</h2>
<p class="note">Local token × list price. Used only to attribute billed dollars across projects.
T0 estimated total <strong>${estimated:.4f}</strong> (not invoice-grade).</p>
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
                "section": "A_billed",
                "tier": row.get("tier_of_truth") or row.get("tier"),
                "vendor": row.get("vendor"),
                "person": row.get("person"),
                "cycle": row.get("cycle"),
                "source": row.get("source"),
                "invoice_id": row.get("invoice_id"),
                "billed_cents": row.get("billed_cents"),
                "billed_usd": row.get("billed_usd"),
                "project": "",
                "model": "",
                "occurred_at": "",
                "message_id": "",
                "request_id": "",
                "input_tokens": "",
                "output_tokens": "",
                "estimated_usd": "",
                "allocated_billed_usd": "",
            }
        )
    for row in summary.get("lines") or []:
        rows.append(
            {
                "section": "T0_allocation",
                "tier": "T0",
                "vendor": row.get("vendor"),
                "person": row.get("person"),
                "cycle": row.get("cycle"),
                "source": row.get("source"),
                "invoice_id": "",
                "billed_cents": row.get("billed_cents"),
                "billed_usd": "",
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
        "invoice_id",
        "billed_cents",
        "billed_usd",
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
