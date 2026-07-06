# Architecture and threat model

## Design principle

FormBridge separates evidence collection, policy interpretation, adversarial review, validation, and presentation. A single general-purpose chatbot would have authority to silently infer values and hide uncertainty; FormBridge makes each boundary explicit and auditable.

## Workflow

1. `formbridge_coordinator` initializes session state and executes deterministic stages.
2. `privacy_guardian` classifies the request and loads only a sanitized synthetic packet.
3. `specialist_parallel` runs three independent views concurrently:
   - `form_analyst`: field requirements and untrusted-document instructions;
   - `evidence_miner`: line-addressed claims and contradictions;
   - `policy_interpreter`: cited requirements without eligibility reasoning.
4. `quality_loop` runs a bounded skeptic and typed reviser pass.
5. `validate_latest_revision` validates every field, status, value, and citation against deterministic ground truth.
6. `draft_builder` exposes errors rather than silently repairing them and always ends at a human-review gate.

Session state keys (`intake_report`, specialist analyses, `skeptic_review`, `revised_draft`, `validation_receipt`, `security_flags`) form the audit trail between stages. Parallel agents use distinct output keys, preventing state races.

## Threat boundaries

| Threat | Control | Evidence |
| --- | --- | --- |
| Prompt injection inside documents | Document content is explicitly untrusted; callback records `prompt_injection`; skeptic verifies it was ignored | `UTILITY-JUN:L3` fixture and adversarial eval |
| PII leakage | Regex redaction before model calls and after model/tool boundaries | Unit tests for email, phone, SSN, and nested tool payloads |
| Unsupported field inference | Typed statuses plus deterministic ground-truth/citation validator | Validator unit tests and contract metric |
| Eligibility overreach | Shared agent rules, safety classifier, final authority statement | Adversarial eval case |
| Autonomous submission | No submission tool exists; human-review gate is mandatory | Architecture and final response contract |
| Hallucinated citations | Validator rejects unknown or missing citations | `validate_evidence_table` |

## Authentication

The local model adapter retrieves a short-lived OAuth token by invoking `gcloud auth print-access-token`; it never writes the token. Cloud Run omits the local adapter flag and uses workload identity/Application Default Credentials. The supplied Google API key was retrieved and configured through `gcloud`, but its prepaid Gemini API credits were depleted, so verified runtime calls use Vertex AI OAuth instead.

## Why local retrieval instead of managed RAG

The capstone corpus is deliberately small and deterministic. Managed vector search would add provisioning and ingestion complexity without improving the core demonstration. The `get_case_evidence_index` tool makes retrieval observable, line-addressable, testable, and cheap. A production policy corpus could replace it behind the same interface with Agent Platform Search.
