"""Month statement as Markdown, HTML, and CSV."""

from __future__ import annotations

import csv
import html
from pathlib import Path
from typing import Any

from ardoise import db, paths
from ardoise.status import _month_bounds, current_month, summarize


def _rows(month: str) -> list[dict[str, Any]]:
    start, end = _month_bounds(month)
    with db.session() as conn:
        cur = conn.execute(
            """
            SELECT occurred_at, project, source, model, message_id, request_id,
                   input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens,
                   cost_usd
            FROM entries
            WHERE occurred_at >= ? AND occurred_at < ?
            ORDER BY occurred_at ASC, id ASC
            """,
            (start, end),
        )
        return [dict(r) for r in cur.fetchall()]


def _md(summary: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    lines = [
        f"# Ardoise statement {summary['month']}",
        "",
        f"- Spend: **${summary['cost_usd']:.4f}**",
        f"- Entries: {summary['month_entries']}",
        f"- Tokens in/out: {summary['input_tokens']} / {summary['output_tokens']}",
        f"- Cache read / write: {summary['cache_read_tokens']} / {summary['cache_creation_tokens']}",
        "",
        "## By project",
        "",
        "| Project | Entries | Cost USD |",
        "|---|---:|---:|",
    ]
    for row in summary["by_project"]:
        lines.append(f"| {row['project']} | {row['entries']} | {row['cost_usd']:.4f} |")
    if not summary["by_project"]:
        lines.append("| (none) | 0 | 0.0000 |")
    lines += [
        "",
        "## By model",
        "",
        "| Model | Entries | Cost USD |",
        "|---|---:|---:|",
    ]
    for row in summary["by_model"]:
        lines.append(f"| {row['model']} | {row['entries']} | {row['cost_usd']:.4f} |")
    lines += [
        "",
        "## Lines",
        "",
        "| When | Project | Source | Model | In | Out | Cost |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {occurred_at} | {project} | {source} | {model} | {input_tokens} | {output_tokens} | {cost_usd:.4f} |".format(
                occurred_at=row.get("occurred_at") or "",
                project=row.get("project") or "",
                source=row.get("source") or "",
                model=row.get("model") or "",
                input_tokens=int(row.get("input_tokens") or 0),
                output_tokens=int(row.get("output_tokens") or 0),
                cost_usd=float(row.get("cost_usd") or 0),
            )
        )
    lines += [
        "",
        "_Generated locally by Ardoise. Prompts and credentials are not stored._",
        "",
    ]
    return "\n".join(lines)


def _html_page(summary: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    def cell(value: Any) -> str:
        return html.escape("" if value is None else str(value))

    project_rows = "".join(
        f"<tr><td>{cell(r['project'])}</td><td>{r['entries']}</td><td>{r['cost_usd']:.4f}</td></tr>"
        for r in summary["by_project"]
    ) or "<tr><td colspan='3'>(none)</td></tr>"
    line_rows = "".join(
        (
            "<tr>"
            f"<td>{cell(r.get('occurred_at'))}</td>"
            f"<td>{cell(r.get('project'))}</td>"
            f"<td>{cell(r.get('source'))}</td>"
            f"<td>{cell(r.get('model'))}</td>"
            f"<td>{int(r.get('input_tokens') or 0)}</td>"
            f"<td>{int(r.get('output_tokens') or 0)}</td>"
            f"<td>{float(r.get('cost_usd') or 0):.4f}</td>"
            "</tr>"
        )
        for r in rows
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
td:nth-child(n+5), th:nth-child(n+5) {{ text-align: right; }}
.muted {{ color: #555; }}
</style>
</head>
<body>
<h1>Ardoise statement {cell(summary['month'])}</h1>
<p>Spend <strong>${summary['cost_usd']:.4f}</strong> · {summary['month_entries']} entries</p>
<h2>By project</h2>
<table><thead><tr><th>Project</th><th>Entries</th><th>Cost USD</th></tr></thead>
<tbody>{project_rows}</tbody></table>
<h2>Lines</h2>
<table>
<thead><tr><th>When</th><th>Project</th><th>Source</th><th>Model</th><th>In</th><th>Out</th><th>Cost</th></tr></thead>
<tbody>{line_rows}</tbody>
</table>
<p class="muted">Generated locally. Prompts and credentials are not stored.</p>
</body>
</html>
"""


def write_statement(month: str | None = None, *, out_dir: Path | None = None) -> dict[str, str]:
    month = month or current_month()
    summary = summarize(month)
    rows = _rows(month)
    dest = out_dir or paths.statements_dir()
    dest.mkdir(parents=True, exist_ok=True)
    md_path = dest / f"{month}.md"
    html_path = dest / f"{month}.html"
    csv_path = dest / f"{month}.csv"
    md_path.write_text(_md(summary, rows), encoding="utf-8")
    html_path.write_text(_html_page(summary, rows), encoding="utf-8")
    fieldnames = [
        "occurred_at",
        "project",
        "source",
        "model",
        "message_id",
        "request_id",
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_creation_tokens",
        "cost_usd",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in fieldnames})
    return {"md": str(md_path), "html": str(html_path), "csv": str(csv_path), "month": month}
