import operator
import os
from typing import Annotated, Any, Literal, TypedDict

from dotenv import load_dotenv
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send, interrupt

load_dotenv()


class ClaimState(TypedDict, total=False):
    case_id: str
    claim: dict[str, Any]
    documents: list[dict[str, Any]]
    document_results: Annotated[list[dict[str, Any]], operator.add]
    messages: Annotated[list[str], operator.add]
    status: str
    next_step: str
    agent_hops: Annotated[list[str], operator.add]
    stage_results: dict[str, Any]
    human_decision: dict[str, Any] | None
    errors: Annotated[list[str], operator.add]
    failure_count: int
    token_usage: int


ALLOWED_TRANSITIONS = {
    "submitted": {"intake", "manual_review"},
    "intake_complete": {"document", "manual_review"},
    "documents_complete": {"summary", "await_documents", "manual_review"},
    "summarised": {"routing", "manual_review"},
    "assigned": {"sla_comms", "human_review", "manual_review"},
    "approval_pending": {"human_review", "manual_review"},
    "awaiting_documents": {"await_documents", "manual_review"},
    "approved": {"finalize"},
    "rejected": {"finalize"},
    "information_requested": {"await_documents"},
}


def guarded_goto(state: ClaimState, requested_node: str) -> str:
    status = state.get("status", "submitted")
    allowed = ALLOWED_TRANSITIONS.get(status, set())

    if requested_node not in allowed:
        return "manual_review"

    return requested_node


def intake_node(state: ClaimState):
    claim = state["claim"]

    duplicate = (
        claim.get("force_duplicate", False)
        or claim.get("duplicate_case_id") is not None
    )
    coverage_issue = claim.get("covered") is False

    risks = []
    if duplicate:
        risks.append("Possible duplicate claim")
    if coverage_issue:
        risks.append("Potentially outside policy coverage")

    return {
        "status": "intake_complete",
        "next_step": "document",
        "agent_hops": ["intake"],
        "messages": ["Intake checks completed"],
        "stage_results": {
            **state.get("stage_results", {}),
            "intake": {
                "duplicate": duplicate,
                "coverage_issue": coverage_issue,
                "risks": risks,
            },
        },
    }


def fan_out_documents(state: ClaimState):
    documents = state.get("documents", [])

    if not documents:
        return "no_documents"

    return [
        Send(
            "process_document",
            {
                "case_id": state["case_id"],
                "document": document,
            },
        )
        for document in documents
    ]


def process_document(state: dict):
    document = state["document"]
    confidence = float(document.get("ocr_confidence", 0.90))
    injection = bool(document.get("injection_detected", False))

    result = {
        "document_id": document.get("document_id"),
        "file_name": document.get("file_name"),
        "document_type": document.get("document_type", "unknown"),
        "ocr_confidence": confidence,
        "injection_detected": injection,
    }

    return {
        "document_results": [result],
        "agent_hops": ["document"],
    }


def join_documents(state: ClaimState):
    results = state.get("document_results", [])
    threshold = float(os.getenv("OCR_CONFIDENCE_THRESHOLD", "0.75"))

    low_confidence = any(
        float(item.get("ocr_confidence", 0)) < threshold
        for item in results
    )
    injection_detected = any(
        item.get("injection_detected", False)
        for item in results
    )

    available_types = {
        item.get("document_type")
        for item in results
    }
    required_types = {"claim_form", "invoice", "medical_report"}
    missing_documents = sorted(required_types - available_types)

    if low_confidence:
        return {
            "status": "documents_complete",
            "next_step": "manual_review",
            "messages": ["Low OCR confidence detected"],
            "stage_results": {
                **state.get("stage_results", {}),
                "documents": {
                    "low_confidence": True,
                    "injection_detected": injection_detected,
                    "missing_documents": missing_documents,
                },
            },
        }

    if missing_documents:
        return {
            "status": "documents_complete",
            "next_step": "await_documents",
            "messages": [
                "Missing documents: " + ", ".join(missing_documents)
            ],
            "stage_results": {
                **state.get("stage_results", {}),
                "documents": {
                    "low_confidence": False,
                    "injection_detected": injection_detected,
                    "missing_documents": missing_documents,
                },
            },
        }

    return {
        "status": "documents_complete",
        "next_step": "summary",
        "messages": ["Document processing completed"],
        "stage_results": {
            **state.get("stage_results", {}),
            "documents": {
                "low_confidence": False,
                "injection_detected": injection_detected,
                "missing_documents": [],
            },
        },
    }


def no_documents_node(state: ClaimState):
    return {
        "status": "documents_complete",
        "next_step": "await_documents",
        "messages": ["No documents were supplied"],
    }


def summary_node(state: ClaimState):
    document_stage = state.get("stage_results", {}).get("documents", {})
    intake_stage = state.get("stage_results", {}).get("intake", {})

    risks = list(intake_stage.get("risks", []))

    if document_stage.get("injection_detected"):
        risks.append(
            "Prompt-injection instruction detected and ignored"
        )

    summary = {
        "facts": [
            f"Case ID: {state['case_id']}",
            f"Claim amount: {state['claim'].get('claim_amount')}",
            f"Claim type: {state['claim'].get('claim_type')}",
        ],
        "evidence": [
            item.get("file_name", "document")
            for item in state.get("document_results", [])
        ],
        "missing_information": document_stage.get(
            "missing_documents",
            [],
        ),
        "risks": risks,
        "policy_citations": state["claim"].get(
            "policy_citations",
            ["Policy coverage and limits clause"],
        ),
        "next_action": "Route to a qualified adjuster and approver",
    }

    return {
        "status": "summarised",
        "next_step": "routing",
        "agent_hops": ["summary"],
        "stage_results": {
            **state.get("stage_results", {}),
            "summary": summary,
        },
        "messages": ["Grounded case summary prepared"],
    }


def routing_node(state: ClaimState):
    amount = float(state["claim"].get("claim_amount", 0))

    if amount <= 50000:
        approver = "approver@lab.local"
    else:
        approver = "senior.approver@lab.local"

    return {
        "status": "assigned",
        "next_step": "sla_comms",
        "agent_hops": ["routing"],
        "stage_results": {
            **state.get("stage_results", {}),
            "routing": {
                "adjuster": "adjuster@lab.local",
                "approver": approver,
                "approval_limit_checked": True,
            },
        },
        "messages": [f"Case assigned to {approver} for approval"],
    }


def sla_comms_node(state: ClaimState):
    return {
        "status": "approval_pending",
        "next_step": "human_review",
        "agent_hops": ["sla_comms"],
        "stage_results": {
            **state.get("stage_results", {}),
            "sla_comms": {
                "approval_sla_hours": 24,
                "notification_required": True,
            },
        },
        "messages": ["Approval SLA scheduled"],
    }


def human_review_node(state: ClaimState):
    decision = interrupt(
        {
            "type": "claim_approval",
            "case_id": state["case_id"],
            "summary": state.get("stage_results", {}).get("summary", {}),
            "routing": state.get("stage_results", {}).get("routing", {}),
            "allowed_decisions": [
                "approve",
                "reject",
                "request_information",
            ],
        }
    )

    decision_name = decision.get("decision")
    rationale = decision.get("rationale")
    approver = decision.get("approver")

    if decision_name not in {
        "approve",
        "reject",
        "request_information",
    }:
        return {
            "status": "approval_pending",
            "errors": ["Invalid human decision"],
        }

    status_map = {
        "approve": "approved",
        "reject": "rejected",
        "request_information": "information_requested",
    }

    return {
        "status": status_map[decision_name],
        "next_step": (
            "await_documents"
            if decision_name == "request_information"
            else "finalize"
        ),
        "human_decision": {
            "decision": decision_name,
            "rationale": rationale,
            "approver": approver,
        },
        "messages": [
            f"Human decision recorded: {decision_name}"
        ],
    }


def await_documents_node(state: ClaimState):
    response = interrupt(
        {
            "type": "await_documents",
            "case_id": state["case_id"],
            "missing_documents": state.get(
                "stage_results",
                {},
            ).get("documents", {}).get("missing_documents", []),
            "message": "Upload the requested documents before resuming.",
        }
    )

    if not response.get("documents_received"):
        return {
            "status": "awaiting_documents",
            "next_step": "await_documents",
            "messages": ["Still waiting for documents"],
        }

    return {
        "status": "intake_complete",
        "next_step": "document",
        "documents": response.get(
            "documents",
            state.get("documents", []),
        ),
        "messages": ["Requested documents received"],
    }


def manual_review_node(state: ClaimState):
    return {
        "status": "manual_review",
        "next_step": "end",
        "messages": ["Case moved to manual review"],
        "agent_hops": ["manual_review"],
    }


def finalize_node(state: ClaimState):
    return {
        "status": state["status"],
        "next_step": "end",
        "messages": ["Claim workflow finalised after human decision"],
        "agent_hops": ["finalize"],
    }


def route_after_intake(state: ClaimState):
    return guarded_goto(state, state.get("next_step", "manual_review"))


def route_after_documents(state: ClaimState):
    requested = state.get("next_step", "manual_review")
    return guarded_goto(state, requested)


def route_after_summary(state: ClaimState):
    return guarded_goto(state, state.get("next_step", "manual_review"))


def route_after_routing(state: ClaimState):
    return guarded_goto(state, state.get("next_step", "manual_review"))


def route_after_sla(state: ClaimState):
    return guarded_goto(state, state.get("next_step", "manual_review"))


def route_after_human(state: ClaimState):
    if state["status"] == "information_requested":
        return "await_documents"
    return "finalize"


def build_graph(checkpointer=None):
    builder = StateGraph(ClaimState)

    builder.add_node("intake", intake_node)
    builder.add_node("process_document", process_document)
    builder.add_node("join_documents", join_documents)
    builder.add_node("no_documents", no_documents_node)
    builder.add_node("summary", summary_node)
    builder.add_node("routing", routing_node)
    builder.add_node("sla_comms", sla_comms_node)
    builder.add_node("human_review", human_review_node)
    builder.add_node("await_documents", await_documents_node)
    builder.add_node("manual_review", manual_review_node)
    builder.add_node("finalize", finalize_node)

    builder.add_edge(START, "intake")

    builder.add_conditional_edges(
        "intake",
        route_after_intake,
        {
            "document": "process_document_fanout",
            "manual_review": "manual_review",
        },
    )

    builder.add_node(
        "process_document_fanout",
        lambda state: {},
    )

    builder.add_conditional_edges(
        "process_document_fanout",
        fan_out_documents,
        {
            "process_document": "process_document",
            "no_documents": "no_documents",
        },
    )

    builder.add_edge("process_document", "join_documents")
    builder.add_edge("no_documents", "await_documents")

    builder.add_conditional_edges(
        "join_documents",
        route_after_documents,
        {
            "summary": "summary",
            "await_documents": "await_documents",
            "manual_review": "manual_review",
        },
    )

    builder.add_conditional_edges(
        "summary",
        route_after_summary,
        {
            "routing": "routing",
            "manual_review": "manual_review",
        },
    )

    builder.add_conditional_edges(
        "routing",
        route_after_routing,
        {
            "sla_comms": "sla_comms",
            "manual_review": "manual_review",
        },
    )

    builder.add_conditional_edges(
        "sla_comms",
        route_after_sla,
        {
            "human_review": "human_review",
            "manual_review": "manual_review",
        },
    )

    builder.add_conditional_edges(
        "human_review",
        route_after_human,
        {
            "finalize": "finalize",
            "await_documents": "await_documents",
        },
    )

    builder.add_edge("manual_review", END)
    builder.add_edge("finalize", END)

    return builder.compile(
        checkpointer=checkpointer or InMemorySaver()
    )
