from core.runtime.runtime_capability_tokens import (
    ACCESS_ALLOWED,
    ACCESS_DENIED,
    CAP_AUTHORITY,
    CAP_MUTATION,
    TOKEN_EXPIRED,
    TOKEN_REVOKED,
    ZONE_AUTHORITY,
    ZONE_MUTATION,
    RuntimeCapabilityTokenManager,
)


def test_capability_token_allows_matching_access():
    runtime = RuntimeCapabilityTokenManager()

    token = runtime.issue_token(
        capability=CAP_MUTATION,
        zone=ZONE_MUTATION,
    )

    result = runtime.validate_access(
        token_id=token.token_id,
        required_capability=CAP_MUTATION,
        target_zone=ZONE_MUTATION,
    )

    payload = result.to_dict()

    assert payload["verified"] is True
    assert payload["access_status"] == ACCESS_ALLOWED
    assert payload["allowed"] is True


def test_capability_token_rejects_capability_mismatch():
    runtime = RuntimeCapabilityTokenManager()

    token = runtime.issue_token(
        capability=CAP_MUTATION,
        zone=ZONE_MUTATION,
    )

    result = runtime.validate_access(
        token_id=token.token_id,
        required_capability=CAP_AUTHORITY,
        target_zone=ZONE_MUTATION,
    )

    assert result.access_status == ACCESS_DENIED
    assert result.reason == "capability_mismatch"


def test_capability_token_rejects_zone_mismatch():
    runtime = RuntimeCapabilityTokenManager()

    token = runtime.issue_token(
        capability=CAP_AUTHORITY,
        zone=ZONE_AUTHORITY,
    )

    result = runtime.validate_access(
        token_id=token.token_id,
        required_capability=CAP_AUTHORITY,
        target_zone=ZONE_MUTATION,
    )

    assert result.access_status == ACCESS_DENIED
    assert result.reason == "zone_mismatch"


def test_capability_token_can_be_revoked():
    runtime = RuntimeCapabilityTokenManager()

    token = runtime.issue_token(
        capability=CAP_MUTATION,
        zone=ZONE_MUTATION,
    )

    revoked = runtime.revoke_token(
        token_id=token.token_id,
        reason="unsafe_behavior",
    )

    result = runtime.validate_access(
        token_id=token.token_id,
        required_capability=CAP_MUTATION,
        target_zone=ZONE_MUTATION,
    )

    assert revoked.status == TOKEN_REVOKED
    assert result.access_status == ACCESS_DENIED
    assert result.reason == "token_revoked"


def test_capability_token_expires():
    runtime = RuntimeCapabilityTokenManager()

    token = runtime.issue_token(
        capability=CAP_MUTATION,
        zone=ZONE_MUTATION,
        expires_in_minutes=-1,
    )

    result = runtime.validate_access(
        token_id=token.token_id,
        required_capability=CAP_MUTATION,
        target_zone=ZONE_MUTATION,
    )

    assert result.access_status == ACCESS_DENIED
    assert result.reason == "token_expired"
    assert result.token["status"] == TOKEN_EXPIRED
