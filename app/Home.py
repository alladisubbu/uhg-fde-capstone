import uuid

import streamlit as st
from langgraph.types import Command

from graph.claims_graph import build_graph


st.set_page_config(
    page_title="UHG Intelligent Claims",
    layout="wide",
)

st.title(
    "UHG Intelligent Claims Processing"
)

st.caption(
    "Agents prepare evidence and recommendations. "
    "Authorized people make claim decisions."
)


if "graph" not in st.session_state:
    st.session_state.graph = build_graph()

if "case_config" not in st.session_state:
    st.session_state.case_config = None

if "last_state" not in st.session_state:
    st.session_state.last_state = None


submit_tab, workspace_tab, approval_tab = (
    st.tabs(
        [
            "Submit Claim",
            "Case Workspace",
            "Human Approval",
        ]
    )
)


with submit_tab:
    st.subheader("Submit a claim")

    with st.form(
        "claim_form",
        clear_on_submit=False,
    ):
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
                "for covered inpatient services."
            ),
        )

        uploaded_files = st.file_uploader(
            (
                "Upload claim form, invoice "
                "and medical report"
            ),
            type=["txt", "pdf", "docx"],
            accept_multiple_files=True,
        )

        submitted = st.form_submit_button(
            "Review and process claim",
            type="primary",
        )

    if submitted:
        case_id = str(uuid.uuid4())
        documents = []

        for index, uploaded_file in enumerate(
            uploaded_files or []
        ):
            raw_data = uploaded_file.getvalue()

            try:
                text = raw_data.decode(
                    "utf-8",
                    errors="ignore",
                )
            except Exception:
                text = ""

            if text.strip():
                confidence = 0.95
            else:
                confidence = 0.30

            documents.append(
                {
                    "document_id":
                        f"DOC-{index + 1:03d}",
                    "file_name":
                        uploaded_file.name,
                    "text": text,
                    "ocr_confidence":
                        confidence,
                }
            )

        initial_state = {
            "case_id": case_id,
            "claim": {
                "policy_number":
                    policy_number.strip(),
                "claimant_name":
                    claimant_name.strip(),
                "claimant_email":
                    claimant_email.strip(),
                "claim_type":
                    claim_type,
                "claim_amount":
                    float(claim_amount),
                "description":
                    description.strip(),
            },
            "documents": documents,
            "document_results": [],
            "messages": [],
            "warnings": [],
            "errors": [],
            "agent_hops": [],
            "stage_results": {},
            "status": "submitted",
            "next_step": "intake",
        }

        config = {
            "configurable": {
                "thread_id": case_id,
            },
            "recursion_limit": 30,
        }

        with st.spinner(
            "Validating claim and "
            "supporting documents..."
        ):
            result = (
                st.session_state.graph.invoke(
                    initial_state,
                    config=config,
                )
            )

        st.session_state.case_config = config
        st.session_state.last_state = result

        errors = result.get("errors", [])
        warnings = result.get("warnings", [])
        current_status = result.get("status")

        if errors:
            st.error(
                "Claim processing stopped because "
                "validation issues were found."
            )

            for error in errors:
                st.error(error)

        elif (
            current_status == "approval_pending"
            or result.get("__interrupt__")
        ):
            st.success(
                "Genuine claim successfully reviewed "
                "and prepared for human approval."
            )

            for warning in warnings:
                st.warning(warning)

            st.info(
                "Open the Human Approval tab "
                "to make the authorized decision."
            )

        else:
            st.info(
                "Claim processed with status: "
                + str(current_status)
            )


with workspace_tab:
    st.subheader("Case workspace")

    state = st.session_state.last_state

    if not state:
        st.info(
            "Submit a claim to view "
            "the workspace."
        )

    else:
        col1, col2, col3 = st.columns(3)

        col1.metric(
            "Case ID",
            state.get("case_id", ""),
        )

        col2.metric(
            "Status",
            state.get("status", ""),
        )

        col3.metric(
            "Agent hops",
            len(
                state.get(
                    "agent_hops",
                    [],
                )
            ),
        )

        if state.get("errors"):
            st.error("Validation issues")

            for error in state.get(
                "errors",
                [],
            ):
                st.write(f"- {error}")

        if state.get("warnings"):
            st.warning("Review observations")

            for warning in state.get(
                "warnings",
                [],
            ):
                st.write(f"- {warning}")

        st.markdown(
            "### Agent trajectory"
        )

        st.write(
            " -> ".join(
                state.get(
                    "agent_hops",
                    [],
                )
            )
        )

        st.markdown(
            "### Document validation"
        )

        st.json(
            state
            .get("stage_results", {})
            .get("documents", {})
        )

        st.markdown("### Summary")

        st.json(
            state
            .get("stage_results", {})
            .get("summary", {})
        )

        st.markdown("### Routing")

        st.json(
            state
            .get("stage_results", {})
            .get("routing", {})
        )

        st.markdown("### Messages")

        for message in state.get(
            "messages",
            [],
        ):
            st.write(f"- {message}")


with approval_tab:
    st.subheader("Human approval")

    state = st.session_state.last_state

    if not state:
        st.info(
            "No claim has been submitted."
        )

    elif state.get("errors"):
        st.error(
            "This claim is not eligible for "
            "approval until validation issues "
            "are corrected."
        )

    elif not (
        state.get("status")
        == "approval_pending"
        or state.get("__interrupt__")
    ):
        st.warning(
            "Claim is not waiting for approval. "
            "Current status: "
            + str(state.get("status"))
        )

    else:
        st.success(
            "Claim validation completed. "
            "Authorized human decision is required."
        )

        st.json(
            state
            .get("stage_results", {})
            .get("summary", {})
        )

        decision = st.radio(
            "Decision",
            [
                "approve",
                "reject",
                "request_information",
            ],
        )

        rationale = st.text_area(
            "Rationale"
        )

        approver = st.text_input(
            "Approver identity",
            value="approver@lab.local",
        )

        if st.button(
            "Submit human decision",
            type="primary",
        ):
            if not rationale.strip():
                st.error(
                    "A rationale is required."
                )

            else:
                result = (
                    st.session_state
                    .graph
                    .invoke(
                        Command(
                            resume={
                                "decision":
                                    decision,
                                "rationale":
                                    rationale.strip(),
                                "approver":
                                    approver.strip(),
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
                    "Final status: "
                    + str(
                        result.get("status")
                    )
                )

                st.rerun()
