import os
import re
from typing import Any, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt


class ClaimState(TypedDict, total=False):
    case_id: str
    claim: dict[str, Any]
    documents: list[dict[str, Any]]
    document_results: list[dict[str, Any]]
    messages: list[str]
    warnings: list[str]
    errors: list[str]
    agent_hops: list[str]
    stage_results: dict[str, Any]
    status: str
    next_step: str
    human_decision: dict[str, Any]


REQUIRED_DOCUMENTS = {
    "claim_form",
    "invoice",
    "medical_report",
}


INJECTION_PATTERNS = (
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"approve\s+this\s+claim",
    r"reject\s+this\s+claim",
    r"reveal\s+(the\s+)?system\s+prompt",
    r"override\s+policy",
)


def normalise(value):
    return re.sub(
        r"\s+",
        " ",
        str(value or "").strip().lower(),
    )


def contains_injection(text):
    lowered = text.lower()

    return any(
        re.search(pattern, lowered)
        for pattern in INJECTION_PATTERNS
    )


def classify_document(file_name, text):
    combined = f"{file_name} {text}".lower()

    if (
        "medical report" in combined
        or "medical_report" in combined
        or "diagnosis" in combined
    ):
        return "medical_report"

    if (
        "invoice" in combined
        or "total amount" in combined
    ):
        return "invoice"

    if (
        "claim form" in combined
        or "claim_form" in combined
        or "claim number" in combined
    ):
        return "claim_form"

    return "unknown"


def extract_amount(text):
    patterns = (
        r"(?:total amount|claim amount|amount)"
        r"\s*:\s*([0-9,]+(?:\.[0-9]{1,2})?)",
        r"(?:total amount|claim amount|amount)"
        r"\s*=\s*([0-9,]+(?:\.[0-9]{1,2})?)",
    )

    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            re.IGNORECASE,
        )

        if match:
            return float(
                match.group(1).replace(",", "")
            )

    return None


def extract_name(text):
    pattern = (
        r"(?:claimant name|"
        r"patient\s*/\s*claimant name|"
        r"patient name)"
        r"\s*:\s*([^\n\r]+)"
    )

    match = re.search(
        pattern,
        text,
        re.IGNORECASE,
    )

    if match:
        return match.group(1).strip()

    return None


def intake_node(state):
    claim = state["claim"]

    errors = list(state.get("errors", []))
    warnings = list(state.get("warnings", []))
    messages = list(state.get("messages", []))
    agent_hops = list(state.get("agent_hops", []))

    policy_number = claim.get("policy_number")
    claim_amount = float(
        claim.get("claim_amount", 0)
    )
    claim_type = normalise(
        claim.get("claim_type")
    )

    if policy_number != "POL-10001":
        errors.append(
            "Policy number was not found in "
            "the seeded capstone policy data."
        )

    if claim_amount <= 0:
        errors.append(
            "Claim amount must be greater than zero."
        )

    if claim_amount > 100000:
        warnings.append(
            "Claim amount exceeds the seeded "
            "policy coverage limit of 100000."
        )

    if claim_type == "experimental treatment":
        warnings.append(
            "Experimental treatment requires "
            "policy or pre-authorisation review."
        )

    agent_hops.append("intake")

    if errors:
        messages.append(
            "Claim intake validation failed."
        )

        return {
            **state,
            "status": "validation_failed",
            "next_step": "error_review",
            "errors": errors,
            "warnings": warnings,
            "messages": messages,
            "agent_hops": agent_hops,
        }

    messages.append(
        "Claim intake validation completed."
    )

    return {
        **state,
        "status": "intake_complete",
        "next_step": "document_review",
        "errors": errors,
        "warnings": warnings,
        "messages": messages,
        "agent_hops": agent_hops,
        "stage_results": {
            **state.get("stage_results", {}),
            "intake": {
                "valid": True,
                "warnings": warnings,
            },
        },
    }


def route_after_intake(state):
    if state.get("errors"):
        return "error_review"

    return "document_review"


def document_review_node(state):
    claim = state["claim"]
    documents = state.get("documents", [])

    results = []
    errors = list(state.get("errors", []))
    warnings = list(state.get("warnings", []))
    messages = list(state.get("messages", []))
    agent_hops = list(state.get("agent_hops", []))

    if not documents:
        errors.append(
            "No supporting documents were uploaded."
        )

    for document in documents:
        file_name = document.get(
            "file_name",
            "unnamed",
        )
        text = document.get("text", "")

        document_type = classify_document(
            file_name,
            text,
        )

        confidence = float(
            document.get(
                "ocr_confidence",
                0.95,
            )
        )

        injection_detected = contains_injection(
            text
        )

        extracted_amount = extract_amount(text)
        extracted_name = extract_name(text)

        if document_type == "unknown":
            warnings.append(
                f"Could not classify {file_name}."
            )

        threshold = float(
            os.getenv(
                "OCR_CONFIDENCE_THRESHOLD",
                "0.75",
            )
        )

        if confidence < threshold:
            errors.append(
                f"Low OCR confidence for "
                f"{file_name}: {confidence:.2f}."
            )

        if injection_detected:
            errors.append(
                "Potential prompt injection detected "
                f"in {file_name}. Embedded instructions "
                "were ignored."
            )

        if extracted_name:
            if normalise(extracted_name) != normalise(
                claim.get("claimant_name")
            ):
                errors.append(
                    "Claimant name mismatch "
                    f"in {file_name}."
                )

        if (
            extracted_amount is not None
            and document_type
            in {"claim_form", "invoice"}
        ):
            entered_amount = float(
                claim.get("claim_amount", 0)
            )

            if abs(
                extracted_amount - entered_amount
            ) > 1:
                errors.append(
                    "Claim amount mismatch "
                    f"in {file_name}. "
                    f"Extracted amount: "
                    f"{extracted_amount:.2f}."
                )

        results.append(
            {
                "file_name": file_name,
                "document_type": document_type,
                "ocr_confidence": confidence,
                "injection_detected":
                    injection_detected,
                "extracted_amount":
                    extracted_amount,
                "extracted_name":
                    extracted_name,
            }
        )

    available_types = {
        item["document_type"]
        for item in results
    }

    missing_documents = sorted(
        REQUIRED_DOCUMENTS - available_types
    )

    if missing_documents:
        errors.append(
            "Missing required documents: "
            + ", ".join(missing_documents)
            + "."
        )

    agent_hops.append("document")

    if errors:
        serious_error = any(
            (
                "ocr" in item.lower()
                or "injection" in item.lower()
                or "mismatch" in item.lower()
            )
            for item in errors
        )

        if serious_error:
            status = "manual_review"
            next_step = "manual_review"
        else:
            status = "awaiting_documents"
            next_step = "await_documents"

        messages.append(
            "Document validation found issues "
            "requiring attention."
        )

        return {
            **state,
            "status": status,
            "next_step": next_step,
            "document_results": results,
            "errors": errors,
            "warnings": warnings,
            "messages": messages,
            "agent_hops": agent_hops,
            "stage_results": {
                **state.get(
                    "stage_results",
                    {},
                ),
                "documents": {
                    "valid": False,
                    "missing_documents":
                        missing_documents,
                    "results": results,
                },
            },
        }

    messages.append(
        "All required documents passed validation."
    )

    return {
        **state,
        "status": "documents_complete",
        "next_step": "summary",
        "document_results": results,
        "errors": [],
        "warnings": warnings,
        "messages": messages,
        "agent_hops": agent_hops,
        "stage_results": {
            **state.get("stage_results", {}),
            "documents": {
                "valid": True,
                "missing_documents": [],
                "results": results,
            },
        },
    }


def route_after_documents(state):
    return state.get(
        "next_step",
        "manual_review",
    )


def summary_node(state):
    claim = state["claim"]

    agent_hops = list(
        state.get("agent_hops", [])
    )
    messages = list(
        state.get("messages", [])
    )

    agent_hops.append("summary")
    messages.append(
        "Grounded case summary created."
    )

    document_names = [
        item.get("file_name")
        for item
        in state.get(
            "document_results",
            [],
        )
    ]

    summary = {
        "facts": [
            "Policy: "
            + str(
                claim.get("policy_number")
            ),
            "Claimant: "
            + str(
                claim.get("claimant_name")
            ),
            "Claim type: "
            + str(
                claim.get("claim_type")
            ),
            "Claim amount: "
            + f"{float(claim.get('claim_amount', 0)):.2f}",
        ],
        "evidence": document_names,
        "missing_information": [],
        "risks": state.get("warnings", []),
        "policy_citations": [
            "POL-10001 coverage and "
            "documentation rules"
        ],
        "next_action": (
            "Route to a qualified approver "
            "for human review."
        ),
    }

    return {
        **state,
        "status": "summarised",
        "next_step": "routing",
        "messages": messages,
        "agent_hops": agent_hops,
        "stage_results": {
            **state.get("stage_results", {}),
            "summary": summary,
        },
    }


def routing_node(state):
    amount = float(
        state["claim"].get(
            "claim_amount",
            0,
        )
    )

    if amount <= 50000:
        approver = "approver@lab.local"
    else:
        approver = (
            "senior.approver@lab.local"
        )

    agent_hops = list(
        state.get("agent_hops", [])
    )
    messages = list(
        state.get("messages", [])
    )

    agent_hops.append("routing")
    messages.append(
        f"Claim routed to {approver}."
    )

    routing = {
        "adjuster": "adjuster@lab.local",
        "approver": approver,
        "approval_limit_checked": True,
    }

    return {
        **state,
        "status": "assigned",
        "next_step": "sla_comms",
        "messages": messages,
        "agent_hops": agent_hops,
        "stage_results": {
            **state.get("stage_results", {}),
            "routing": routing,
        },
    }


def sla_comms_node(state):
    agent_hops = list(
        state.get("agent_hops", [])
    )
    messages = list(
        state.get("messages", [])
    )

    agent_hops.append("sla_comms")
    messages.append(
        "Claim is ready for "
        "authorized human review."
    )

    return {
        **state,
        "status": "approval_pending",
        "next_step": "human_review",
        "messages": messages,
        "agent_hops": agent_hops,
        "stage_results": {
            **state.get("stage_results", {}),
            "sla_comms": {
                "approval_sla_hours": 24,
                "notification_required": True,
            },
        },
    }


def human_review_node(state):
    decision = interrupt(
        {
            "type": "claim_approval",
            "case_id": state["case_id"],
            "summary": (
                state
                .get("stage_results", {})
                .get("summary", {})
            ),
            "routing": (
                state
                .get("stage_results", {})
                .get("routing", {})
            ),
            "allowed_decisions": [
                "approve",
                "reject",
                "request_information",
            ],
        }
    )

    decision_name = decision.get("decision")

    valid_decisions = {
        "approve",
        "reject",
        "request_information",
    }

    if decision_name not in valid_decisions:
        return {
            **state,
            "status": "approval_pending",
            "errors": [
                "Invalid human decision."
            ],
        }

    status_map = {
        "approve": "approved",
        "reject": "rejected",
        "request_information":
            "information_requested",
    }

    messages = list(
        state.get("messages", [])
    )

    messages.append(
        "Human decision recorded: "
        + decision_name
        + "."
    )

    return {
        **state,
        "status": status_map[decision_name],
        "next_step": "end",
        "human_decision": decision,
        "messages": messages,
    }


def issue_review_node(state):
    agent_hops = list(
        state.get("agent_hops", [])
    )
    messages = list(
        state.get("messages", [])
    )

    agent_hops.append(
        state.get(
            "next_step",
            "error_review",
        )
    )

    messages.append(
        "Claim stopped before approval "
        "because validation issues "
        "must be corrected."
    )

    return {
        **state,
        "messages": messages,
        "agent_hops": agent_hops,
    }


def build_graph(checkpointer=None):
    builder = StateGraph(ClaimState)

    builder.add_node(
        "intake",
        intake_node,
    )

    builder.add_node(
        "document_review",
        document_review_node,
    )

    builder.add_node(
        "summary",
        summary_node,
    )

    builder.add_node(
        "routing",
        routing_node,
    )

    builder.add_node(
        "sla_comms",
        sla_comms_node,
    )

    builder.add_node(
        "human_review",
        human_review_node,
    )

    builder.add_node(
        "manual_review",
        issue_review_node,
    )

    builder.add_node(
        "await_documents",
        issue_review_node,
    )

    builder.add_node(
        "error_review",
        issue_review_node,
    )

    builder.add_edge(
        START,
        "intake",
    )

    builder.add_conditional_edges(
        "intake",
        route_after_intake,
        {
            "document_review":
                "document_review",
            "error_review":
                "error_review",
        },
    )

    builder.add_conditional_edges(
        "document_review",
        route_after_documents,
        {
            "summary": "summary",
            "manual_review":
                "manual_review",
            "await_documents":
                "await_documents",
        },
    )

    builder.add_edge(
        "summary",
        "routing",
    )

    builder.add_edge(
        "routing",
        "sla_comms",
    )

    builder.add_edge(
        "sla_comms",
        "human_review",
    )

    builder.add_edge(
        "manual_review",
        END,
    )

    builder.add_edge(
        "await_documents",
        END,
    )

    builder.add_edge(
        "error_review",
        END,
    )

    builder.add_edge(
        "human_review",
        END,
    )

    return builder.compile(
        checkpointer=(
            checkpointer
            or InMemorySaver()
        )
    )
