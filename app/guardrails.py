"""Deterministic privacy guardrails used at every model and tool boundary."""

from __future__ import annotations

import re
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.tools import BaseTool, ToolContext

SENSITIVE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("EMAIL", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)),
    (
        "PHONE",
        re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?!\d)"),
    ),
    ("BANK_ACCOUNT", re.compile(r"\b(?:account|acct)[\s:#-]*\d{6,17}\b", re.I)),
)

PROMPT_INJECTION_MARKERS = (
    "ignore previous instructions",
    "ignore all instructions",
    "reveal the system prompt",
    "show hidden prompt",
    "exfiltrate",
)


def redact_text(text: str) -> tuple[str, list[str]]:
    """Return text with common identifiers replaced and labels of redactions."""
    redacted = text
    findings: list[str] = []
    for label, pattern in SENSITIVE_PATTERNS:
        redacted, count = pattern.subn(f"[REDACTED_{label}]", redacted)
        findings.extend([label] * count)
    return redacted, findings


def redact_value(value: Any) -> tuple[Any, list[str]]:
    """Recursively redact JSON-compatible values."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        output = []
        findings: list[str] = []
        for item in value:
            clean, item_findings = redact_value(item)
            output.append(clean)
            findings.extend(item_findings)
        return output, findings
    if isinstance(value, dict):
        output_dict = {}
        findings = []
        for key, item in value.items():
            clean, item_findings = redact_value(item)
            output_dict[key] = clean
            findings.extend(item_findings)
        return output_dict, findings
    return value, []


def contains_prompt_injection(text: str) -> bool:
    """Detect common attempts to make untrusted evidence act as instructions."""
    lowered = text.lower()
    return any(marker in lowered for marker in PROMPT_INJECTION_MARKERS)


async def privacy_before_model(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> None:
    """Redact model inputs and label possible prompt-injection content."""
    redaction_count = 0
    injection_seen = False
    for content in llm_request.contents:
        for part in content.parts or []:
            if not part.text:
                continue
            injection_seen = injection_seen or contains_prompt_injection(part.text)
            clean, findings = redact_text(part.text)
            part.text = clean
            redaction_count += len(findings)

    if redaction_count:
        callback_context.state["privacy_redactions"] = (
            callback_context.state.get("privacy_redactions", 0) + redaction_count
        )
    if injection_seen:
        flags = list(callback_context.state.get("security_flags", []))
        if "prompt_injection" not in flags:
            flags.append("prompt_injection")
        callback_context.state["security_flags"] = flags


async def redact_after_model(
    callback_context: CallbackContext, llm_response: LlmResponse
) -> LlmResponse | None:
    """Prevent sensitive identifiers from leaving a model boundary."""
    if not llm_response.content:
        return None
    findings: list[str] = []
    for part in llm_response.content.parts or []:
        if part.text:
            part.text, part_findings = redact_text(part.text)
            findings.extend(part_findings)
    if findings:
        callback_context.state["privacy_redactions"] = callback_context.state.get(
            "privacy_redactions", 0
        ) + len(findings)
        return llm_response
    return None


async def redact_after_tool(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
    tool_response: dict[str, Any],
) -> dict[str, Any] | None:
    """Prevent tool results from leaking identifiers into agent traces."""
    del tool, args
    clean, findings = redact_value(tool_response)
    if findings:
        tool_context.state["privacy_redactions"] = tool_context.state.get(
            "privacy_redactions", 0
        ) + len(findings)
        return clean
    return None
