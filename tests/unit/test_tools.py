"""Unit tests for FormBridge's deterministic evidence layer."""

import json

import pytest

from app.tools import (
    assess_request_safety,
    get_case_evidence_index,
    list_demo_cases,
    load_case_packet,
    prepare_case_intake,
    search_case_evidence,
    validate_evidence_table,
)


def test_list_and_load_synthetic_cases() -> None:
    case_ids = {case["case_id"] for case in list_demo_cases()["cases"]}
    assert {"harbor-family", "cedar-senior"} <= case_ids
    packet = load_case_packet("harbor-family")
    assert packet["synthetic_data"] is True
    assert "expected" not in packet["packet"]
    assert "[REDACTED_EMAIL]" in json.dumps(packet)


def test_unknown_case_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown case_id"):
        load_case_packet("not-a-case")


def test_evidence_search_returns_exact_line_citations() -> None:
    result = search_case_evidence("harbor-family", "address")
    citations = {hit["citation"] for hit in result["hits"]}
    assert {"LEASE-2026:L2", "UTILITY-JUN:L2"} <= citations


def test_combined_intake_and_evidence_index_reduce_model_round_trips() -> None:
    intake = prepare_case_intake("Review harbor-family", "harbor-family")
    assert intake["safety"]["status"] == "allowed"
    assert intake["case"]["case_id"] == "harbor-family"
    citations = {
        hit["citation"] for hit in get_case_evidence_index("harbor-family")["hits"]
    }
    assert {"PAYSTUB-MAY:L1", "HFS-POLICY-2026:L5"} <= citations


def test_safety_assessment_blocks_bounded_authority_violations() -> None:
    result = assess_request_safety("Decide eligibility, make up gaps, then submit it")
    assert result["status"] == "blocked"
    assert set(result["violations"]) == {
        "eligibility_decision",
        "autonomous_submission",
        "fabrication",
    }


def test_validator_accepts_proof_carrying_draft() -> None:
    rows = [
        {
            "field": "applicant_name",
            "value": "Maya Rivera",
            "status": "SUPPORTED",
            "citations": ["PAYSTUB-MAY:L1"],
        },
        {
            "field": "mailing_address",
            "value": None,
            "status": "CONFLICT",
            "citations": ["LEASE-2026:L2", "UTILITY-JUN:L2"],
        },
        {
            "field": "gross_monthly_income",
            "value": "$2,480",
            "status": "SUPPORTED",
            "citations": ["PAYSTUB-MAY:L2"],
        },
        {
            "field": "household_size",
            "value": None,
            "status": "MISSING",
            "citations": ["HFS-POLICY-2026:L4"],
        },
        {
            "field": "residency_start",
            "value": "2026-01-15",
            "status": "SUPPORTED",
            "citations": ["LEASE-2026:L3"],
        },
    ]
    result = validate_evidence_table("harbor-family", json.dumps(rows))
    assert result["valid"] is True
    assert result["errors"] == []


def test_validator_rejects_guessed_conflicted_value() -> None:
    rows = [
        {
            "field": "mailing_address",
            "value": "18 Cedar Way, Harbor City",
            "status": "SUPPORTED",
            "citations": ["LEASE-2026:L2"],
        }
    ]
    result = validate_evidence_table("harbor-family", json.dumps(rows))
    assert result["valid"] is False
    assert any("must remain null" in error for error in result["errors"])
