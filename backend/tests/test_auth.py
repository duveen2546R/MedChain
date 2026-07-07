from __future__ import annotations

from datetime import timedelta

from backend.app.models import Invitation, PasswordResetToken, User, utcnow
from backend.tests.test_api import TEST_PASSWORD, TEST_SECRET, auth, client, login


def _settings():
    from backend.app.config import Settings

    return Settings(secret_key=TEST_SECRET)


# --------------------------------------------------------------------------- access requests


def test_access_request_submit_and_approve_flow() -> None:
    with client() as test_client:
        submit = test_client.post(
            "/auth/access-requests",
            json={
                "organization_name": "Mercy General",
                "organization_type": "hospital",
                "contact_name": "Dana Ops",
                "email": "dana@mercy.example",
                "message": "We want to join.",
            },
        )
        assert submit.status_code == 201
        request_id = submit.json()["request_id"]

        # Listing is platform-admin only.
        assert test_client.get("/auth/access-requests").status_code == 401
        auditor = login(test_client, "auditor@example.com")
        assert test_client.get("/auth/access-requests", headers=auth(auditor)).status_code == 403

        admin = login(test_client)
        listing = test_client.get("/auth/access-requests", headers=auth(admin))
        assert listing.status_code == 200
        assert any(req["id"] == request_id for req in listing.json())

        approve = test_client.post(
            f"/auth/access-requests/{request_id}/approve", headers=auth(admin)
        )
        assert approve.status_code == 200
        token = approve.json()["invitation"]["token"]
        assert approve.json()["invitation"]["role"] == "hospital_admin"
        assert any(m.get("token") == token for m in test_client.notifications.sent)

        register = test_client.post(
            "/auth/register",
            json={"token": token, "name": "Dana Ops", "password": "supersecret1"},
        )
        assert register.status_code == 201
        assert register.json()["role"] == "hospital_admin"

        # Double approve is a conflict.
        assert (
            test_client.post(
                f"/auth/access-requests/{request_id}/approve", headers=auth(admin)
            ).status_code
            == 409
        )


def test_access_request_reject_and_duplicate_pending() -> None:
    with client() as test_client:
        payload = {
            "organization_name": "Lab X",
            "organization_type": "research",
            "contact_name": "Sam",
            "email": "sam@labx.example",
        }
        assert test_client.post("/auth/access-requests", json=payload).status_code == 201
        # Duplicate pending request for the same email is rejected.
        assert test_client.post("/auth/access-requests", json=payload).status_code == 409

        admin = login(test_client)
        request_id = test_client.get(
            "/auth/access-requests", headers=auth(admin)
        ).json()[0]["id"]
        reject = test_client.post(
            f"/auth/access-requests/{request_id}/reject",
            json={"reason": "Out of scope"},
            headers=auth(admin),
        )
        assert reject.status_code == 200
        assert reject.json()["request"]["status"] == "rejected"


# --------------------------------------------------------------------------- invitations


def _invite(test_client, token, **body):
    return test_client.post("/auth/invitations", json=body, headers=auth(token))


def test_invitation_permissions() -> None:
    with client() as test_client:
        admin = login(test_client)
        # platform_admin can invite any role with a new org.
        assert _invite(
            test_client, admin, email="ha@h.example", role="hospital_admin",
            new_org={"name": "H Org", "type": "hospital"},
        ).status_code == 201

        # Register the hospital_admin so we can test their limited powers.
        ha_token = _register_and_login(test_client, "ha@h.example")

        # hospital_admin can invite a hospital_node in their own org.
        ok = _invite(test_client, ha_token, email="node@h.example", role="hospital_node")
        assert ok.status_code == 201
        # ... but not another hospital_admin.
        assert _invite(
            test_client, ha_token, email="ha2@h.example", role="hospital_admin"
        ).status_code == 403
        # ... nor a foreign org.
        assert _invite(
            test_client, ha_token, email="x@h.example", role="hospital_node", org_id="org_platform"
        ).status_code == 403
        # ... nor create a new org.
        assert _invite(
            test_client, ha_token, email="y@h.example", role="hospital_node",
            new_org={"name": "Sneaky", "type": "hospital"},
        ).status_code == 403


def test_invitation_conflicts_and_lifecycle() -> None:
    with client() as test_client:
        admin = login(test_client)
        # Existing user email -> 409.
        assert _invite(
            test_client, admin, email="admin@example.com", role="auditor"
        ).status_code == 409

        first = _invite(
            test_client, admin, email="dup@x.example", role="clinic_user",
            new_org={"name": "C", "type": "clinic"},
        )
        assert first.status_code == 201
        # A live invitation for the same email -> 409.
        assert _invite(
            test_client, admin, email="dup@x.example", role="clinic_user",
            new_org={"name": "C2", "type": "clinic"},
        ).status_code == 409

        invitation_id = first.json()["invitation"]["id"]
        token = first.json()["invitation"]["token"]
        # Revoke, then the token can no longer preview or register.
        assert test_client.post(
            f"/auth/invitations/{invitation_id}/revoke", headers=auth(admin)
        ).status_code == 200
        assert test_client.get(f"/auth/invitations/token/{token}").status_code == 410
        assert test_client.post(
            "/auth/register", json={"token": token, "name": "X", "password": "supersecret1"}
        ).status_code == 410


def test_expired_invitation_is_gone() -> None:
    with client() as test_client:
        admin = login(test_client)
        created = _invite(
            test_client, admin, email="late@x.example", role="clinic_user",
            new_org={"name": "Late", "type": "clinic"},
        ).json()["invitation"]
        # Force expiry directly in the repo.
        invitation = Invitation(**created)
        invitation.expires_at = utcnow() - timedelta(minutes=1)
        import asyncio

        asyncio.run(
            test_client.repo.put("invitations", invitation)
        )
        assert test_client.get(f"/auth/invitations/token/{invitation.token}").status_code == 410


# --------------------------------------------------------------------------- token pair


def test_token_pair_and_refresh() -> None:
    with client() as test_client:
        pair = test_client.post(
            "/auth/login", json={"email": "admin@example.com", "password": TEST_PASSWORD}
        ).json()
        assert pair["access_token"] and pair["refresh_token"]

        # Refresh token cannot be used as a bearer access token.
        assert test_client.get("/me", headers=auth(pair["refresh_token"])).status_code == 401
        # Access token cannot be used in the refresh body.
        assert test_client.post(
            "/auth/refresh", json={"refresh_token": pair["access_token"]}
        ).status_code == 401

        refreshed = test_client.post(
            "/auth/refresh", json={"refresh_token": pair["refresh_token"]}
        )
        assert refreshed.status_code == 200
        new_access = refreshed.json()["access_token"]
        assert test_client.get("/me", headers=auth(new_access)).status_code == 200


def test_decode_token_treats_missing_type_as_access() -> None:
    import base64
    import hashlib
    import hmac
    import json

    from backend.app.security import decode_token

    settings = _settings()
    claims = {"sub": "usr_admin", "exp": int((utcnow() + timedelta(minutes=5)).timestamp())}
    body = base64.urlsafe_b64encode(json.dumps(claims, separators=(",", ":")).encode()).decode().rstrip("=")
    sig = hmac.new(settings.secret_key.encode(), body.encode(), hashlib.sha256).digest()
    token = f"{body}.{base64.urlsafe_b64encode(sig).decode().rstrip('=')}"
    assert decode_token(token, settings, expected_type="access") is not None
    assert decode_token(token, settings, expected_type="refresh") is None


def test_refresh_rejected_for_deactivated_user() -> None:
    with client() as test_client:
        refresh_token = test_client.post(
            "/auth/login", json={"email": "admin@example.com", "password": TEST_PASSWORD}
        ).json()["refresh_token"]

        import asyncio

        async def deactivate():
            user = await test_client.repo.get("users", "usr_admin", User)
            user.active = False
            await test_client.repo.put("users", user)

        asyncio.run(deactivate())
        assert test_client.post(
            "/auth/refresh", json={"refresh_token": refresh_token}
        ).status_code == 401


# --------------------------------------------------------------------------- password reset


def _register_and_login(test_client, email: str) -> str:
    """Register a fresh account through the last live invitation for `email` and return its access token."""
    invitations = test_client.get(
        "/auth/invitations", headers=auth(login(test_client))
    ).json()
    token = next(inv["token"] for inv in invitations if inv["email"] == email and inv["status"] == "pending")
    test_client.post(
        "/auth/register", json={"token": token, "name": email, "password": "supersecret1"}
    )
    return login(test_client, email, "supersecret1")


def test_forgot_password_is_anti_enumerating() -> None:
    with client() as test_client:
        unknown = test_client.post("/auth/forgot-password", json={"email": "nobody@nowhere.example"})
        assert unknown.status_code == 200 and unknown.json() == {"ok": True}

        import asyncio

        async def token_count():
            return await test_client.repo.count("password_reset_tokens")

        assert asyncio.run(token_count()) == 0

        known = test_client.post("/auth/forgot-password", json={"email": "admin@example.com"})
        assert known.status_code == 200 and known.json() == {"ok": True}
        assert any(m.get("kind") == "password_reset" for m in test_client.notifications.sent)


def test_password_reset_completes_and_is_single_use() -> None:
    with client() as test_client:
        test_client.post("/auth/forgot-password", json={"email": "admin@example.com"})
        reset_token = next(
            m["token"] for m in test_client.notifications.sent if m.get("kind") == "password_reset"
        )
        done = test_client.post(
            "/auth/reset-password", json={"token": reset_token, "password": "brandnewpass1"}
        )
        assert done.status_code == 200

        # Old password no longer works; new one does.
        assert test_client.post(
            "/auth/login", json={"email": "admin@example.com", "password": TEST_PASSWORD}
        ).status_code == 401
        assert test_client.post(
            "/auth/login", json={"email": "admin@example.com", "password": "brandnewpass1"}
        ).status_code == 200

        # Token is single-use.
        assert test_client.post(
            "/auth/reset-password", json={"token": reset_token, "password": "another1234"}
        ).status_code == 400


def test_second_forgot_invalidates_first_token() -> None:
    with client() as test_client:
        test_client.post("/auth/forgot-password", json={"email": "admin@example.com"})
        first_token = test_client.notifications.sent[-1]["token"]
        test_client.post("/auth/forgot-password", json={"email": "admin@example.com"})
        # The first token should now be invalid.
        assert test_client.post(
            "/auth/reset-password", json={"token": first_token, "password": "willfail123"}
        ).status_code == 400


def test_expired_reset_token_is_rejected() -> None:
    with client() as test_client:
        import asyncio

        async def make_expired():
            token = PasswordResetToken(
                user_id="usr_admin", expires_at=utcnow() - timedelta(minutes=1)
            )
            await test_client.repo.put("password_reset_tokens", token)
            return token.token

        expired_token = asyncio.run(make_expired())
        assert test_client.post(
            "/auth/reset-password", json={"token": expired_token, "password": "whatever123"}
        ).status_code == 400


def test_audit_trail_records_auth_events() -> None:
    with client() as test_client:
        admin = login(test_client)
        invite = _invite(
            test_client, admin, email="audit@x.example", role="clinic_user",
            new_org={"name": "Audit Clinic", "type": "clinic"},
        )
        token = invite.json()["invitation"]["token"]
        test_client.post(
            "/auth/register", json={"token": token, "name": "Audit", "password": "supersecret1"}
        )
        test_client.post("/auth/forgot-password", json={"email": "admin@example.com"})

        events = test_client.get("/audit/events", headers=auth(admin)).json()
        actions = {event["action"] for event in events}
        assert {
            "invitation.created",
            "invitation.accepted",
            "auth.registered",
            "auth.password_reset_requested",
        } <= actions
