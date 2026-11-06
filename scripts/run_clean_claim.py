import json
import uuid

from langgraph.types import Command

from graph.claims_graph import build_graph


case_id = str(uuid.uuid4())
config = {
    "configurable": {
        "thread_id": case_id,
    },
    "recursion_limit": 30,
}

initial_state = {
    "case_id": case_id,
    "claim": {
        "policy_number": "POL-10001",
        "claimant_name": "John Test Customer",
        "claimant_email": "claimant@lab.local",
        "claim_type": "Health claim",
        "claim_amount": 25000,
        "incident_date": "2026-10-01",
        "description": "Hospital treatment claim",
        "covered": True,
        "policy_citations": [
            "Completed claim form, invoice and medical report required"
        ],
    },
    "documents": [
        {
            "document_id": "DOC-001",
            "file_name": "claim-form.txt",
            "document_type": "claim_form",
            "ocr_confidence": 0.99,
            "injection_detected": False,
        },
        {
            "document_id": "DOC-002",
            "file_name": "invoice.txt",
            "document_type": "invoice",
            "ocr_confidence": 0.98,
            "injection_detected": False,
        },
        {
            "document_id": "DOC-003",
            "file_name": "medical-report.txt",
            "document_type": "medical_report",
            "ocr_confidence": 0.97,
            "injection_detected": False,
        },
    ],
    "status": "submitted",
    "next_step": "intake",
    "agent_hops": [],
    "stage_results": {},
    "errors": [],
    "failure_count": 0,
    "token_usage": 0,
}

graph = build_graph()

print("\nStarting case:", case_id)

result = graph.invoke(initial_state, config=config)
print("\nState before human approval:")
print(json.dumps(result, indent=2, default=str))

print("\nResuming using a HUMAN decision...")

final_result = graph.invoke(
    Command(
        resume={
            "decision": "approve",
            "rationale": "Evidence is complete and policy conditions are met.",
            "approver": "approver@lab.local",
        }
    ),
    config=config,
)

print("\nFinal state:")
print(json.dumps(final_result, indent=2, default=str))
