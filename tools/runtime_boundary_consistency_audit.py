from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "runtime_boundary_matrix.txt"
REPORT = ROOT / "runtime_boundary_consistency_audit.txt"

CRITICAL_DIRECTIONS = {
    "scheduler -> operator": "review_required",
    "task_runner -> operator": "review_required",
    "dispatcher -> scheduler": "review_required",
}

EXPECTED_BRIDGES = {
    "scheduler -> dispatcher",
    "scheduler -> task_runner",
    "task_runner -> dispatcher",
    "dispatcher -> task_runner",
    "operator -> dispatcher",
}

AUTHORITY_FAMILIES = {
    "authority",
    "identity",
    "recovery",
}

ROW_RE = re.compile(
    r"^- (?P<direction>[^|]+?) \| "
    r"(?P<path>[^:]+):(?P<line>\d+) \| "
    r"symbol=(?P<symbol>[^|]+) \| "
    r"call=(?P<call>[^|]+) \| "
    r"family=(?P<family>[^|]+) \| "
    r"status=(?P<status>.+)$"
)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _parse_matrix_rows(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    in_rows = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line == "Boundary Matrix Rows":
            in_rows = True
            continue
        if in_rows and line.startswith("Cross Component Text Samples"):
            break
        if not in_rows:
            continue

        match = ROW_RE.match(line)
        if not match:
            continue

        row = {key: value.strip() for key, value in match.groupdict().items()}
        row["direction"] = " ".join(row["direction"].split()).lower()
        rows.append(row)
    return rows


def _classify(row: dict[str, str]) -> tuple[str, str]:
    direction = row["direction"]
    family = row["family"].strip().lower()
    status = row["status"].strip().lower()
    call = row["call"].strip().lower()
    symbol = row["symbol"].strip().lower()

    if direction in CRITICAL_DIRECTIONS:
        if "bridge" in call or "bridge" in symbol or status == "boundary_bridge":
            return "allowed_bridge", "critical direction is mediated by bridge/bridge-status"
        return "manual_review", "critical cross-boundary direction without obvious bridge marker"

    if direction in EXPECTED_BRIDGES:
        return "expected_bridge", "expected runtime boundary direction"

    if family in AUTHORITY_FAMILIES:
        return "authority_identity_recovery_review", "authority/identity/recovery boundary should stay single-entry and explicit"

    if "operator" in direction and status != "boundary_bridge":
        return "operator_boundary_review", "operator boundary reference is not classified as bridge"

    return "documented_reference", "documented cross-component reference"


def _audit(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    audited: list[dict[str, str]] = []
    for row in rows:
        verdict, reason = _classify(row)
        copied = dict(row)
        copied["verdict"] = verdict
        copied["reason"] = reason
        audited.append(copied)
    return audited


def _counts(rows: list[dict[str, str]], key: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in rows:
        value = row.get(key, "")
        result[value] = result.get(value, 0) + 1
    return result


def _write_report() -> dict[str, object]:
    if not MATRIX.exists():
        raise FileNotFoundError(
            f"{MATRIX} not found. Run tools/runtime_boundary_matrix.py first."
        )

    matrix_text = _read_text(MATRIX)
    rows = _parse_matrix_rows(matrix_text)
    audited = _audit(rows)

    verdict_counts = _counts(audited, "verdict")
    direction_counts = _counts(audited, "direction")
    family_counts = _counts(audited, "family")

    manual_review = [row for row in audited if row["verdict"] == "manual_review"]
    authority_reviews = [
        row for row in audited if row["verdict"] == "authority_identity_recovery_review"
    ]
    operator_reviews = [
        row for row in audited if row["verdict"] == "operator_boundary_review"
    ]

    lines: list[str] = []
    lines.append("Runtime Boundary Consistency Audit")
    lines.append("")
    lines.append("Scope")
    lines.append("-----")
    lines.append("Inventory/audit only. No production code modified.")
    lines.append("Input: runtime_boundary_matrix.txt")
    lines.append("")

    lines.append("Summary")
    lines.append("-------")
    lines.append(f"boundary_rows: {len(audited)}")
    lines.append(f"manual_review_rows: {len(manual_review)}")
    lines.append(f"authority_identity_recovery_review_rows: {len(authority_reviews)}")
    lines.append(f"operator_boundary_review_rows: {len(operator_reviews)}")
    lines.append("")

    lines.append("Verdict Counts")
    lines.append("--------------")
    if verdict_counts:
        for key in sorted(verdict_counts):
            lines.append(f"- {key}: {verdict_counts[key]}")
    else:
        lines.append("- <none>")
    lines.append("")

    lines.append("Direction Counts")
    lines.append("----------------")
    if direction_counts:
        for key in sorted(direction_counts):
            lines.append(f"- {key}: {direction_counts[key]}")
    else:
        lines.append("- <none>")
    lines.append("")

    lines.append("Family Counts")
    lines.append("-------------")
    if family_counts:
        for key in sorted(family_counts):
            lines.append(f"- {key}: {family_counts[key]}")
    else:
        lines.append("- <none>")
    lines.append("")

    lines.append("Manual Review Rows")
    lines.append("------------------")
    if manual_review:
        for row in manual_review:
            lines.append(
                f"- {row['direction']} | {row['path']}:{row['line']} | "
                f"symbol={row['symbol']} | call={row['call']} | "
                f"family={row['family']} | status={row['status']} | reason={row['reason']}"
            )
    else:
        lines.append("- <none>")
    lines.append("")

    lines.append("Authority / Identity / Recovery Review Rows")
    lines.append("-------------------------------------------")
    if authority_reviews:
        for row in authority_reviews:
            lines.append(
                f"- {row['direction']} | {row['path']}:{row['line']} | "
                f"symbol={row['symbol']} | call={row['call']} | "
                f"family={row['family']} | status={row['status']} | reason={row['reason']}"
            )
    else:
        lines.append("- <none>")
    lines.append("")

    lines.append("Operator Boundary Review Rows")
    lines.append("-----------------------------")
    if operator_reviews:
        for row in operator_reviews:
            lines.append(
                f"- {row['direction']} | {row['path']}:{row['line']} | "
                f"symbol={row['symbol']} | call={row['call']} | "
                f"family={row['family']} | status={row['status']} | reason={row['reason']}"
            )
    else:
        lines.append("- <none>")
    lines.append("")

    lines.append("All Audited Rows")
    lines.append("----------------")
    if audited:
        for row in audited:
            lines.append(
                f"- {row['direction']} | {row['path']}:{row['line']} | "
                f"symbol={row['symbol']} | call={row['call']} | "
                f"family={row['family']} | status={row['status']} | "
                f"verdict={row['verdict']} | reason={row['reason']}"
            )
    else:
        lines.append("- <none>")
    lines.append("")

    lines.append("Non-Mainline Issues")
    lines.append("-------------------")
    lines.append("- Audit only. No production code was changed.")
    lines.append("- manual_review rows are not automatic defects; inspect before scheduling changes.")
    lines.append("- If a row is outside boundary scope but suspicious, report it explicitly in a follow-up package.")
    lines.append("")

    REPORT.write_text("\n".join(lines), encoding="utf-8")
    return {
        "report": REPORT,
        "boundary_rows": len(audited),
        "manual_review_rows": len(manual_review),
        "authority_identity_recovery_review_rows": len(authority_reviews),
        "operator_boundary_review_rows": len(operator_reviews),
        "verdict_counts": verdict_counts,
    }


def main() -> int:
    result = _write_report()
    print("Runtime boundary consistency audit complete")
    print(f"report: {Path(result['report']).relative_to(ROOT)}")
    print(
        "counts: "
        f"boundary_rows={result['boundary_rows']}, "
        f"manual_review_rows={result['manual_review_rows']}, "
        f"authority_identity_recovery_review_rows={result['authority_identity_recovery_review_rows']}, "
        f"operator_boundary_review_rows={result['operator_boundary_review_rows']}"
    )
    print("verdict_counts:")
    if result["verdict_counts"]:
        for key in sorted(result["verdict_counts"]):
            print(f"- {key}: {result['verdict_counts'][key]}")
    else:
        print("- <none>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
