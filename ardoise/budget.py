"""Soft monthly USD caps (person and/or project). Warn only — never blocks."""

from __future__ import annotations

from typing import Any

from ardoise import config as config_mod


def month_spend(summary: dict[str, Any]) -> tuple[float, str]:
    """Prefer invoice-grade billed truth; otherwise T0 estimated."""
    section_a = summary.get("section_a") or []
    if any(row.get("invoice_grade") for row in section_a):
        return round(float(summary.get("billed_usd") or 0), 6), "billed"
    return round(float(summary.get("estimated_usd") or summary.get("cost_usd") or 0), 6), "estimated"


def _line_spend(row: dict[str, Any], *, basis: str) -> float:
    if basis == "billed" and row.get("allocated_billed_usd") is not None:
        return float(row["allocated_billed_usd"] or 0)
    return float(row.get("estimated_usd") or row.get("cost_usd") or 0)


def _person_spend(summary: dict[str, Any], person: str, *, basis: str) -> float:
    if basis == "billed":
        billed = sum(
            float(row.get("billed_usd") or 0)
            for row in (summary.get("section_a") or [])
            if str(row.get("person") or "") == person
        )
        if billed:
            return round(billed, 6)
    return round(
        sum(
            _line_spend(row, basis=basis)
            for row in (summary.get("lines") or [])
            if str(row.get("person") or "") == person
        ),
        6,
    )


def _project_spend(summary: dict[str, Any], project: str, *, basis: str) -> float:
    for row in summary.get("by_project") or []:
        if str(row.get("project") or "") == project:
            if basis == "billed" and row.get("allocated_billed_usd") is not None:
                return round(float(row["allocated_billed_usd"]), 6)
            return round(float(row.get("cost_usd") or 0), 6)
    return round(
        sum(
            _line_spend(row, basis=basis)
            for row in (summary.get("lines") or [])
            if str(row.get("project") or "") == project
        ),
        6,
    )


def _check(
    *,
    kind: str,
    scope: str,
    spent: float,
    cap: float,
    basis: str,
) -> dict[str, Any]:
    pct = round(100.0 * spent / cap, 2) if cap else None
    over = bool(cap and spent > cap)
    label = scope or "(default)"
    pct_txt = f"{pct:.0f}%" if pct is not None else "—"
    note = f"soft cap {kind} {label}: ${spent:.2f} / ${cap:.2f} ({pct_txt}"
    if over:
        note += ") — over (warn only, never blocks)"
    else:
        note += ")"
    return {
        "kind": kind,
        "scope": scope,
        "cap_usd": round(float(cap), 6),
        "spent_usd": round(float(spent), 6),
        "pct": pct,
        "over": over,
        "basis": basis,
        "note": note,
    }


def evaluate(summary: dict[str, Any], cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg if cfg is not None else config_mod.load()
    budgets = cfg.get("budgets") or {}
    spent, basis = month_spend(summary)
    checks: list[dict[str, Any]] = []

    monthly = budgets.get("monthly_usd")
    if monthly:
        checks.append(
            _check(
                kind="month",
                scope=str(summary.get("month") or ""),
                spent=spent,
                cap=float(monthly),
                basis=basis,
            )
        )

    for person, cap in (budgets.get("person") or {}).items():
        checks.append(
            _check(
                kind="person",
                scope=str(person),
                spent=_person_spend(summary, str(person), basis=basis),
                cap=float(cap),
                basis=basis,
            )
        )

    for project, cap in (budgets.get("project") or {}).items():
        checks.append(
            _check(
                kind="project",
                scope=str(project),
                spent=_project_spend(summary, str(project), basis=basis),
                cap=float(cap),
                basis=basis,
            )
        )

    over = any(item["over"] for item in checks)
    notes = [item["note"] for item in checks if item["over"]]
    return {
        "configured": config_mod.has_soft_caps(cfg),
        "basis": basis,
        "spent_usd": spent,
        "checks": checks,
        "over_cap": over,
        "blocks": False,
        "notes": notes,
    }


def notes_from(budgets: dict[str, Any] | None) -> list[str]:
    if not budgets:
        return []
    if budgets.get("over_cap"):
        return list(budgets.get("notes") or [])
    # Under-cap checks still belong on the JSON payload; text status prints %.
    return []
