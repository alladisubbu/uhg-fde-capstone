import json
import os
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from dotenv import load_dotenv
from fastmcp import FastMCP

from services.database import execute, fetch_all, fetch_one, write_audit

load_dotenv()

mcp = FastMCP("workflow-mcp")


@mcp.tool()
def get_workload(role: str) -> list"""Return active staff and current workloads."""
    return fetch_all(
        """
        SELECT full_name, email, role, approval_limit, active_cases
        FROM staff
        WHERE role = %s AND active = TRUE
        ORDER BY active_cases, approval_limit
        """,
        (role,),
    )


@mcp.tool()
def assign_case(
    case_id: str,
    adjuster_email: str,
    approver_email: str,
) -> dict:
    """Assign an adjuster and approver. This tool does not approve."""
    before = fetch_one("SELECT * FROM cases WHERE case_id = %s", (case_id,))

    adjuster = fetch_one(
        """
        SELECT * FROM staff
        WHERE email = %s AND role = 'adjuster' AND active = TRUE
        """,
        (adjuster_email,),
    )
    approver = fetch_one(
        """
        SELECT * FROM staff
        WHERE email = %s AND role = 'approver' AND active = TRUE
        """,
        (approver_email,),
    )

    if not adjuster:
        return {"error": "Valid adjuster not found"}

    if not approver:
        return {"error": "Valid approver not found"}

    claim_amount = float(before["claim_amount"])

    if float(approver["approval_limit"]) < claim_amount:
        return {
            "error": "Approver limit is below claim amount",
            "claim_amount": claim_amount,
            "approval_limit": float(approver["approval_limit"]),
        }

    after = execute(
        """
        UPDATE cases
        SET assigned_adjuster = %s,
            assigned_approver = %s,
            status = 'assigned',
            next_step = 'approval',
            updated_at = NOW()
        WHERE case_id = %s
        RETURNING *
        """,
        (adjuster_email, approver_email, case_id),
    )

    write_audit(
        case_id=case_id,
        actor="routing-agent",
        action="case_assigned",
        before_state=before,
        after_state=after,
    )
    return after


@mcp.tool()
def request_approval(case_id: str, approver_email: str) -> dict:
    """Create an approval request without making a decision."""
    row = execute(
        """
        INSERT INTO approvals(case_id, approver_email)
        VALUES (%s, %s)
        RETURNING *
        """,
        (case_id, approver_email),
    )

    write_audit(
        case_id=case_id,
        actor="routing-agent",
        action="approval_requested",
        after_state={
            "approver_email": approver_email,
            "approval_id": str(row["approval_id"]),
        },
    )
    return row


@mcp.tool()
def schedule_sla(
    case_id: str,
    sla_type: str = "approval",
    hours: int = 24,
) -> dict:
    """Create an SLA timer."""
    due_at = datetime.now(timezone.utc) + timedelta(hours=hours)

    row = execute(
        """
        INSERT INTO sla_events(case_id, sla_type, due_at)
        VALUES (%s, %s, %s)
        RETURNING *
        """,
        (case_id, sla_type, due_at),
    )

    write_audit(
        case_id=case_id,
        actor="sla-agent",
        action="sla_scheduled",
        after_state={
            "sla_type": sla_type,
            "due_at": due_at.isoformat(),
        },
    )

    return {
        "case_id": case_id,
        "sla_type": sla_type,
        "due_at": due_at.isoformat(),
    }


@mcp.tool()
def send_notification(
    case_id: str,
    recipient: str,
    subject: str,
    message: str,
) -> dict:
    """Send a lab notification through Mailpit."""
    email = EmailMessage()
    email["From"] = "claims-agent@lab.local"
    email["To"] = recipient
    email["Subject"] = subject
    email.set_content(message)

    with smtplib.SMTP(
        os.getenv("MAILPIT_HOST", "localhost"),
        int(os.getenv("MAILPIT_SMTP_PORT", "1025")),
    ) as smtp:
        smtp.send_message(email)

    write_audit(
        case_id=case_id,
        actor="sla-comms-agent",
        action="notification_sent",
        after_state={
            "recipient": recipient,
            "subject": subject,
        },
    )

    return {
        "sent": True,
        "recipient": recipient,
        "subject": subject,
    }


@mcp.tool()
def request_documents(
    case_id: str,
    recipient: str,
    missing_documents: list[str],
) -> dict:
    """Request missing documents and return the case to a waiting state."""
    execute(
        """
        UPDATE cases
        SET status = 'awaiting_documents',
            next_step = 'await_documents',
            missing_documents = %s::jsonb,
            updated_at = NOW()
        WHERE case_id = %s
        """,
        (json.dumps(missing_documents), case_id),
    )

    return send_notification(
        case_id=case_id,
        recipient=recipient,
        subject=f"Documents required for claim {case_id}",
        message=(
            "Please provide the following documents:\n"
            + "\n".join(f"- {item}" for item in missing_documents)
        ),
    )


@mcp.resource("staff://directory")
def staff_directory() -> str:
    rows = fetch_all(
        """
        SELECT full_name, email, role, approval_limit, active_cases
        FROM staff
        WHERE active = TRUE
        """
    )
    return json.dumps(rows, default=str, indent=2)


@mcp.resource("sla://rules")
def sla_rules() -> str:
    return json.dumps(
        {
            "intake_hours": 4,
            "document_review_hours": 8,
            "approval_hours": 24,
            "escalation_hours": 48,
        },
        indent=2,
    )


@mcp.prompt()
def claimant_letter(case_id: str, status: str) -> str:
    return f"""
Write a clear and courteous claimant update for case {case_id}.
Current status: {status}.
Do not expose internal risk flags.
Do not promise claim approval or payment.
"""


@mcp.prompt()
def approver_brief(case_id: str) -> str:
    return f"""
Prepare a concise approval brief for case {case_id}.
Include facts, evidence, missing information, risks and policy citations.
Do not make or imply an approval decision.
"""


if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "http":
        mcp.run(
            transport="http",
            host="0.0.0.0",
            port=int(os.getenv("MCP_PORT", "8004")),
        )
    else:
        mcp.run()
