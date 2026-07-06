"""Deterministic FormBridge tools over synthetic, line-addressable evidence."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from .guardrails import redact_value

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "cases.json"
ALLOWED_STATUSES = {"SUPPORTED", "CONFLICT", "MISSING"}


def _cases() -> dict[str, dict[str, Any]]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["cases"]


def _require_case(case_id: str) -> dict[str, Any]:
    cases = _cases()
    if case_id not in cases:
        raise ValueError(f"Unknown case_id {case_id!r}. Available: {', '.join(cases)}")
    return deepcopy(cases[case_id])


def list_demo_cases() -> dict[str, Any]:
    """List privacy-safe synthetic cases available for a FormBridge review."""
    return {
        "status": "success",
        "cases": [
            {"case_id": case_id, "title": case["title"], "scenario": case["scenario"]}
            for case_id, case in _cases().items()
        ],
        "example_prompt": "Review demo case harbor-family and show your evidence.",
    }


def load_case_packet(case_id: str) -> dict[str, Any]:
    """Load a synthetic form, evidence documents, and policy excerpts by case id."""
    case = _require_case(case_id)
    case.pop("expected", None)
    clean, findings = redact_value(case)
    return {
        "status": "success",
        "case_id": case_id,
        "synthetic_data": True,
        "privacy_redactions": len(findings),
        "packet": clean,
        "authority_boundary": (
            "Drafting support only; no eligibility decision and no submission."
        ),
    }


def prepare_case_intake(request: str, case_id: str) -> dict[str, Any]:
    """Assess request safety and load a sanitized synthetic case in one step."""
    return {
        "safety": assess_request_safety(request),
        "case": load_case_packet(case_id),
    }


def search_case_evidence(case_id: str, query: str) -> dict[str, Any]:
    """Search line-addressable synthetic evidence and return exact citations."""
    case = _require_case(case_id)
    terms = {
        term.lower() for term in re.findall(r"[A-Za-z0-9$-]+", query) if len(term) > 2
    }
    if terms.intersection({"address", "residence", "mailing"}):
        terms.update({"address", "premises", "residence", "mailing"})
    if terms.intersection({"income", "pay", "earnings"}):
        terms.update({"income", "pay", "benefit", "earnings"})
    hits: list[dict[str, str]] = []
    for document in case["documents"]:
        for line_id, text in document["lines"].items():
            haystack = f"{document['type']} {line_id} {text}".lower()
            if not terms or any(term in haystack for term in terms):
                clean, _ = redact_value(text)
                hits.append(
                    {
                        "citation": f"{document['id']}:{line_id}",
                        "document_type": document["type"],
                        "text": clean,
                    }
                )
    for line_id, text in case["policy"]["lines"].items():
        haystack = f"policy {line_id} {text}".lower()
        if "policy" in terms or not terms or any(term in haystack for term in terms):
            hits.append(
                {
                    "citation": f"{case['policy']['id']}:{line_id}",
                    "document_type": "policy",
                    "text": text,
                }
            )
    return {"status": "success", "case_id": case_id, "query": query, "hits": hits[:20]}


def get_case_evidence_index(case_id: str) -> dict[str, Any]:
    """Return the complete sanitized line index for a synthetic demo case."""
    case = _require_case(case_id)
    hits: list[dict[str, str]] = []
    for document in case["documents"]:
        for line_id, text in document["lines"].items():
            clean, _ = redact_value(text)
            hits.append(
                {
                    "citation": f"{document['id']}:{line_id}",
                    "document_type": document["type"],
                    "text": clean,
                }
            )
    for line_id, text in case["policy"]["lines"].items():
        hits.append(
            {
                "citation": f"{case['policy']['id']}:{line_id}",
                "document_type": "policy",
                "text": text,
            }
        )
    return {"status": "success", "case_id": case_id, "hits": hits}


def assess_request_safety(request: str) -> dict[str, Any]:
    """Classify requests that exceed FormBridge's bounded drafting authority."""
    rules = {
        "eligibility_decision": ("am i eligible", "decide eligibility", "approve me"),
        "autonomous_submission": ("submit", "send the application", "file it"),
        "fabrication": ("make up", "invent", "guess the missing"),
        "pii_exposure": ("show raw pii", "reveal ssn", "unredact"),
    }
    lowered = request.lower()
    violations = [
        name for name, phrases in rules.items() if any(p in lowered for p in phrases)
    ]
    return {
        "status": "blocked" if violations else "allowed",
        "violations": violations,
        "safe_scope": "Evidence-backed drafting with citations and human review only.",
    }


def validate_evidence_table(case_id: str, draft_json: str) -> dict[str, Any]:
    """Validate a JSON evidence table against synthetic ground truth and citations."""
    case = _require_case(case_id)
    try:
        rows = json.loads(draft_json)
    except json.JSONDecodeError as exc:
        return {"valid": False, "errors": [f"Invalid JSON: {exc.msg}"], "checks": 0}
    if not isinstance(rows, list):
        return {
            "valid": False,
            "errors": ["Evidence table must be a JSON array."],
            "checks": 0,
        }

    expected = case["expected"]
    known_citations = {
        f"{document['id']}:{line_id}"
        for document in case["documents"]
        for line_id in document["lines"]
    } | {f"{case['policy']['id']}:{line_id}" for line_id in case["policy"]["lines"]}
    errors: list[str] = []
    seen_fields: set[str] = set()

    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"Row {index} must be an object.")
            continue
        field = row.get("field")
        value = row.get("value")
        status = row.get("status")
        citations = row.get("citations", [])
        if field not in expected:
            errors.append(f"Row {index} has unknown field {field!r}.")
            continue
        seen_fields.add(field)
        if status not in ALLOWED_STATUSES:
            errors.append(f"{field}: invalid status {status!r}.")
        if not isinstance(citations, list):
            errors.append(f"{field}: citations must be a list.")
            citations = []
        unknown = sorted(set(citations) - known_citations)
        if unknown:
            errors.append(f"{field}: unknown citations {unknown}.")

        truth = expected[field]
        if truth["status"] == "SUPPORTED":
            if status != "SUPPORTED" or value != truth["value"]:
                errors.append(f"{field}: unsupported or incorrect filled value.")
            if not set(truth["citations"]).intersection(citations):
                errors.append(f"{field}: missing required proof citation.")
        else:
            if value is not None:
                errors.append(
                    f"{field}: conflicted or missing values must remain null."
                )
            if status != truth["status"]:
                errors.append(f"{field}: expected status {truth['status']}.")

    missing_rows = sorted(set(expected) - seen_fields)
    if missing_rows:
        errors.append(f"Missing fields: {missing_rows}.")
    return {
        "valid": not errors,
        "errors": errors,
        "checks": len(rows),
        "human_review_required": True,
        "authority_boundary": "No eligibility decision; no submission.",
    }
