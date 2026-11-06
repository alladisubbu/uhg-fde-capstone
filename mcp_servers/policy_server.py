import json
import os
from datetime import date, datetime
from decimal import Decimal

from dotenv import load_dotenv
from fastmcp import FastMCP

from services.database import fetch_all, fetch_one

load_dotenv()

mcp = FastMCP("policy-mcp")


def serialise(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError


@mcp.tool()
def get_policy(policy_number: str) -> dict:
    """Retrieve policy details."""
    policy = fetch_one(
        "SELECT * FROM policies WHERE policy_number = %s",
        (policy_number,),
    )
    if not policy:
        return {"error": "Policy not found", "policy_number": policy_number}
    return json.loads(json.dumps(policy, default=serialise))


@mcp.tool()
def check_coverage(
    policy_number: str,
    claim_amount: float,
    claim_type: str,
) -> dict:
    """Check active status, claim limit and simple exclusions."""
    policy = get_policy(policy_number)

    if "error" in policy:
        return {
            "covered": False,
            "reason": "Policy does not exist",
            "clause": None,
        }

    if not policy["active"]:
        return {
            "covered": False,
            "reason": "Policy is inactive",
            "clause": "Policy active-status requirement",
        }

    if claim_amount > float(policy["coverage_limit"]):
        return {
            "covered": False,
            "reason": "Claim exceeds the policy coverage limit",
            "clause": f"Coverage limit is {policy['coverage_limit']}",
        }

    if "experimental" in claim_type.lower():
        return {
            "covered": False,
            "reason": "Experimental treatment requires pre-authorisation",
            "clause": "Experimental treatment exclusion",
        }

    return {
        "covered": True,
        "reason": "Claim is within the basic policy conditions",
        "clause": "Policy coverage and limit clauses",
    }


@mcp.tool()
def search_policy_wording(product: str, query: str) -> list:
    """Search policy wording for relevant clauses."""
    rows = fetch_all(
        """
        SELECT policy_number, product, wording
        FROM policies
        WHERE LOWER(product) LIKE LOWER(%s)
          AND LOWER(wording) LIKE LOWER(%s)
        """,
        (f"%{product}%", f"%{query}%"),
    )
    return json.loads(json.dumps(rows, default=serialise))


@mcp.resource("policy://{policy_number}")
def policy_resource(policy_number: str) -> str:
    return json.dumps(get_policy(policy_number), indent=2)


@mcp.tool()
def search_policy_wording(product: str, query: str) -> list:
    rows = fetch_all(
        "SELECT product, wording FROM policies WHERE LOWER(product) = LOWER(%s)",
        (product,),
    )
    return json.dumps(rows, indent=2)


if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "http":
        mcp.run(
            transport="http",
            host="0.0.0.0",
            port=int(os.getenv("MCP_PORT", "8002")),
        )
    else:
        mcp.run()
