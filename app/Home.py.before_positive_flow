import uuid

import streamlit as st
from langgraph.types import Command

from graph.claims_graph import build_graph
from services.document_validation import (
    analyze_uploaded_files,
    save_uploaded_files,
)


st.set_page_config(
    page_title="UHG Intelligent Claims",
    layout="wide",
)

st.title("UHG Intelligent Claims Processing")

st.caption(
    "AI prepares the claim. "
    "An authorised person makes the decision."
)

if "graph" not in st.session_state:
    st.session_state.graph = build_graph()

if "case_config" not in st.session_state:
    st.session_state.case_config = None

if "last_state" not in st.session_state:
    st.session_state.last_state = None

if "validation_report" not in st.session_state:
    st.session_state.validation_report = None


tab_submit, tab_case, tab_approval = st.tabs(
    [
        "Submit Claim",
        "Case Workspace",
        "Human Approval",
    ]
)


with tab_submit:
    st.subheader("Submit a claim")

    st.info(
        "For the positive test, upload a claim form, "
        "invoice and medical report together."
    )

    with st.form("claim_form"):
        policy_number = st.text_input(
            "Policy number",
            value="POL-10001",
        )

        claimant_name = st.text_input(
            "Claimant name",
            value="John Test Customer",
        )

        claimant_email = st.text_input(
            "Claimant email",
            value="claimant@lab.local",
        )

        claim_type = st.selectbox(
            "Claim type",
            [
                "Health claim",
                "Experimental treatment",
            ],
        )

        claim_amount = st.number_input(
            "Claim amount",
            min_value=1.0,
            value=25000.0,
        )

        description = st.text_area(
            "Description",
            value=(
                "Hospital treatment claim "
                "for covered services."
            ),
        )

        uploaded_files = st.file_uploader(
            "Upload claim documents",
            type=["txt", "md", "csv"],
            accept_multiple_files=True,
        )

        submitted = st.form_submit_button(
            "Validate and process claim"
        )


    if submitted:
        if not uploaded_files:
            st.error(
                "Upload at least one claim document."
            )

        else:
            case_id = str(uuid.uuid4())

            saved_paths = save_uploaded_files(
                uploaded_files,
                case_id,
            )

            report = analyze_uploaded_files(
                uploaded_files=uploaded_files,
                submitted_claimant=claimant_name,
                submitted_amount=claim_amount,
            )

            covered = (
                claim_type
                != "Experimental treatment"
                and claim_amount <= 100000
            )

            coverage_risks = []

            if claim_type == "Experimental treatment":
                coverage_risks.append(
                    "Experimental treatment requires "
                    "policy or pre-authorisation review."
                )

            if claim_amount > 100000:
                coverage_risks.append(
                    "Claim exceeds the seeded "
                    "POL-10001 coverage limit."
                )

            report["risks"].extend(
                coverage_risks
            )

            initial_state = {
                "case_id": case_id,
                "claim": {
                    "policy_number": policy_number,
                    "claimant_name": claimant_name,
                    "claimant_email": claimant_email,
                    "claim_type": claim_type,
                    "claim_amount": claim_amount,
                    "description": description,
                    "covered": covered,
                    "policy_citations": [
                        "POL-10001 coverage, "
                        "documentation and limit clauses"
                    ],
                },
                "documents": report["documents"],
                "status": "submitted",
                "next_step": "intake",
                "agent_hops": [],
                "stage_results": {},
                "errors": [],
                "failure_count": 0,
                "token_usage": 0,
            }

            config = {
                "configurable": {
                    "thread_id": case_id,
                },
                "recursion_limit": 30,
            }

            with st.spinner(
                "Validating documents and "
                "running claim workflow..."
            ):
                result = (
                    st.session_state.graph.invoke(
                        initial_state,
                        config=config,
                    )
                )

            st.session_state.case_config = config
            st.session_state.last_state = result
            st.session_state.validation_report = report


            status = result.get(
                "status",
                "unknown",
            )

            st.markdown("### Validation result")

            if report["injection_detected"]:
                st.error(
                    "Security warning: Potential prompt "
                    "injection detected. Embedded "
                    "instructions were ignored."
                )

            if report["low_confidence"]:
                st.error(
                    "Document-quality warning: OCR "
                    "confidence is below 0.75. "
                    "Manual review is required."
                )

            if report["missing_documents"]:
                st.warning(
                    "Missing required documents: "
                    + ", ".join(
                        report["missing_documents"]
                    )
                )

            if report["risks"]:
                st.markdown("#### Risks identified")

                for risk in report["risks"]:
                    st.write(f"- {risk}")

            if status == "manual_review":
                st.error(
                    "Claim requires manual review. "
                    "No automated claim decision was made."
                )

            elif status in {
                "awaiting_documents",
                "documents_complete",
            } and report["missing_documents"]:
                st.warning(
                    "Additional documents are required "
                    "before processing can continue."
                )

            elif status in {
                "approval_pending",
                "assigned",
            }:
                st.success(
                    "Claim preparation completed. "
                    "The case is ready for human review."
                )

            else:
                st.info(
                    f"Current workflow status: {status}"
                )

            st.caption(
                f"Case ID: {case_id}"
            )

            st.caption(
                "Saved files: "
                + ", ".join(saved_paths)
            )


with tab_case:
    st.subheader("Case workspace")

    if not st.session_state.last_state:
        st.warning("Submit a claim first.")

    else:
        state = st.session_state.last_state
        report = (
            st.session_state.validation_report
            or {}
        )

        col1, col2, col3 = st.columns(3)

        col1.metric(
            "Case ID",
            state.get("case_id"),
        )

        col2.metric(
            "Status",
            state.get("status"),
        )

        col3.metric(
            "Agent hops",
            len(state.get("agent_hops", [])),
        )

        st.markdown("### Agent trajectory")

        trajectory = state.get(
            "agent_hops",
            [],
        )

        st.write(
            " -> ".join(trajectory)
            if trajectory
            else "No trajectory available"
        )

        st.markdown("### Document validation")

        for document in report.get(
            "documents",
            [],
        ):
            with st.expander(
                document["file_name"]
            ):
                st.write(
                    "Type:",
                    document["document_type"],
                )

                st.write(
                    "OCR confidence:",
                    document["ocr_confidence"],
                )

                st.write(
                    "Injection detected:",
                    document[
                        "injection_detected"
                    ],
                )

                st.write(
                    "Extracted claimant:",
                    document[
                        "extracted_claimant_name"
                    ],
                )

                st.write(
                    "Extracted amount:",
                    document[
                        "extracted_amount"
                    ],
                )

                st.write(
                    "Policy number:",
                    document[
                        "extracted_policy_number"
                    ],
                )

        st.markdown("### Risks")

        risks = report.get("risks", [])

        if risks:
            for risk in risks:
                st.error(risk)
        else:
            st.success(
                "No document-validation risks detected."
            )

        st.markdown("### Summary")

        st.json(
            state.get(
                "stage_results",
                {},
            ).get(
                "summary",
                {},
            )
        )

        st.markdown("### Routing")

        st.json(
            state.get(
                "stage_results",
                {},
            ).get(
                "routing",
                {},
            )
        )


with tab_approval:
    st.subheader("Human approval")

    if not st.session_state.last_state:
        st.warning(
            "No case is available for review."
        )

    elif st.session_state.last_state.get(
        "status"
    ) == "manual_review":
        st.error(
            "This case is in manual review because "
            "validation or security risks were found."
        )

    elif st.session_state.validation_report.get(
        "missing_documents"
    ):
        st.warning(
            "The case cannot proceed to approval "
            "until all required documents are supplied."
        )

    else:
        summary = (
            st.session_state.last_state
            .get("stage_results", {})
            .get("summary", {})
        )

        st.json(summary)

        decision = st.radio(
            "Human decision",
            [
                "approve",
                "reject",
                "request_information",
            ],
        )

        rationale = st.text_area(
            "Decision rationale"
        )

        approver = st.text_input(
            "Approver identity",
            value="approver@lab.local",
        )

        if st.button(
            "Submit human decision"
        ):
            if not rationale.strip():
                st.error(
                    "A rationale is required."
                )

            else:
                result = (
                    st.session_state.graph.invoke(
                        Command(
                            resume={
                                "decision": decision,
                                "rationale": rationale,
                                "approver": approver,
                            }
                        ),
                        config=(
                            st.session_state
                            .case_config
                        ),
                    )
                )

                st.session_state.last_state = (
                    result
                )

                st.success(
                    "Human decision recorded. "
                    f"Status: "
                    f"{result.get('status')}"
                )

                st.json(result)
