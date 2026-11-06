from mcp_servers.policy_server import check_coverage


def test_claim_within_limit_is_covered():
    result = check_coverage(
        policy_number="POL-10001",
        claim_amount=25000,
        claim_type="Health claim",
    )
    assert result["covered"] is True


def test_claim_above_limit_is_not_covered():
    result = check_coverage(
        policy_number="POL-10001",
        claim_amount=150000,
        claim_type="Health claim",
    )
    assert result["covered"] is False


def test_experimental_treatment_needs_authorisation():
    result = check_coverage(
        policy_number="POL-10001",
        claim_amount=10000,
        claim_type="Experimental treatment",
    )
    assert result["covered"] is False
