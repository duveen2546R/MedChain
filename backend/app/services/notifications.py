from __future__ import annotations

from html import escape
import logging
from typing import Any

from ..config import Settings
from ..models import AccessRequest, Invitation, User

logger = logging.getLogger("medchain.notifications")

BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"

# Landing-page brand palette (frontend/src/index.css): pure black, dark panels,
# white text with a pink accent, and a white primary button with black text.
_BG = "#000000"
_CARD = "#0d0d0d"
_BORDER = "#212121"
_TEXT = "#ffffff"
_TEXT_DIM = "#b3b3b3"
_TEXT_FAINT = "#6f6f6f"
_PINK = "#f399b3"
_FONT = (
    "'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
)


def _button(label: str, url: str) -> str:
    # Bulletproof, table-based CTA — white button with black text, like the landing page.
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        'style="margin:28px 0 4px;"><tr><td '
        f'style="border-radius:12px;background:{_TEXT};">'
        f'<a href="{escape(url, quote=True)}" target="_blank" '
        f'style="display:inline-block;padding:14px 30px;font-family:{_FONT};'
        f'font-size:15px;font-weight:600;color:#000000;text-decoration:none;'
        'border-radius:12px;">'
        f"{escape(label)}</a></td></tr></table>"
    )


def render_email(
    *,
    heading: str,
    body_html: str,
    button_label: str | None = None,
    button_url: str | None = None,
    footnote: str | None = None,
    preheader: str = "",
) -> str:
    """Wrap message content in the MedChain-branded email shell (dark, Inter, pink accent)."""
    cta = _button(button_label, button_url) if button_label and button_url else ""
    foot = (
        f'<p style="margin:22px 0 0;font-family:{_FONT};font-size:12.5px;line-height:1.6;'
        f'color:{_TEXT_FAINT};">{footnote}</p>'
        if footnote
        else ""
    )
    fallback_link = (
        f'<p style="margin:16px 0 0;font-family:{_FONT};font-size:12.5px;line-height:1.6;'
        f'color:{_TEXT_FAINT};">Or paste this link into your browser:<br>'
        f'<a href="{escape(button_url, quote=True)}" style="color:{_PINK};'
        f'word-break:break-all;">{escape(button_url)}</a></p>'
        if button_url
        else ""
    )
    return f"""\
<!doctype html>
<html>
  <body style="margin:0;padding:0;background:{_BG};">
    <span style="display:none!important;opacity:0;color:{_BG};height:0;width:0;overflow:hidden;">{escape(preheader)}</span>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{_BG};padding:40px 16px;">
      <tr>
        <td align="center">
          <table role="presentation" width="520" cellpadding="0" cellspacing="0" border="0" style="max-width:520px;width:100%;">
            <tr><td style="height:3px;background:linear-gradient(120deg,#ffd9e1,{_PINK});border-radius:16px 16px 0 0;"></td></tr>
            <tr>
              <td style="background:{_CARD};border:1px solid {_BORDER};border-top:none;border-radius:0 0 16px 16px;padding:36px 36px 40px;">
                <p style="margin:0 0 26px;font-family:{_FONT};font-size:19px;font-weight:600;letter-spacing:-0.02em;color:{_TEXT};">
                  MedChain <span style="color:{_PINK};font-style:italic;">AI</span>
                </p>
                <h1 style="margin:0 0 14px;font-family:{_FONT};font-size:23px;font-weight:600;letter-spacing:-0.02em;line-height:1.3;color:{_TEXT};">{escape(heading)}</h1>
                <div style="font-family:{_FONT};font-size:15px;line-height:1.65;color:{_TEXT_DIM};">{body_html}</div>
                {cta}
                {fallback_link}
                {foot}
              </td>
            </tr>
            <tr>
              <td style="padding:20px 36px 0;font-family:{_FONT};font-size:11.5px;line-height:1.6;color:{_TEXT_FAINT};">
                Privacy-preserving federated learning for medical AI. You are receiving this because someone used your email with MedChain.
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""


class NotificationService:
    """Transactional email via Brevo. Degrades to logging when unconfigured so the
    invite/reset flows stay testable without any email provider."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: Any = None

    @property
    def enabled(self) -> bool:
        return bool(self.settings.brevo_api_key and self.settings.mail_from_email)

    async def connect(self) -> None:
        if not self.enabled:
            return
        import httpx

        self._client = httpx.AsyncClient(timeout=10.0)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
        self._client = None

    def invite_url(self, token: str) -> str:
        return f"{self.settings.frontend_base_url}/register?token={token}"

    def reset_url(self, token: str) -> str:
        return f"{self.settings.frontend_base_url}/reset-password?token={token}"

    async def send(self, to_email: str, to_name: str, subject: str, html: str) -> bool:
        if not self.enabled or self._client is None:
            logger.info("email disabled; would send %r to %s", subject, to_email)
            return False
        payload = {
            "sender": {"name": self.settings.mail_from_name, "email": self.settings.mail_from_email},
            "to": [{"email": to_email, "name": to_name}],
            "subject": subject,
            "htmlContent": html,
        }
        try:
            response = await self._client.post(
                BREVO_ENDPOINT,
                headers={"api-key": self.settings.brevo_api_key, "accept": "application/json"},
                json=payload,
            )
            response.raise_for_status()
        except Exception:  # noqa: BLE001 - email must never break the request path
            logger.exception("Brevo send failed for %s", to_email)
            return False
        return True

    async def send_invitation(self, invitation: Invitation, org_name: str) -> bool:
        url = self.invite_url(invitation.token)
        role = invitation.role.replace("_", " ")
        body = (
            f"<p style='margin:0 0 12px;'>You've been invited to join "
            f"<strong style='color:#ffffff;'>{escape(org_name)}</strong> on MedChain "
            f"as <strong style='color:#ffffff;'>{escape(role)}</strong>.</p>"
            f"<p style='margin:0;'>Accept the invitation to set a password and sign in.</p>"
        )
        html = render_email(
            heading="You've been invited to MedChain",
            body_html=body,
            button_label="Accept invitation",
            button_url=url,
            footnote=f"This invitation expires on {invitation.expires_at:%B %d, %Y at %H:%M UTC}.",
            preheader=f"Join {org_name} on MedChain as {role}.",
        )
        return await self.send(invitation.email, invitation.email, "Your MedChain invitation", html)

    async def send_password_reset(self, user: User, token: str) -> bool:
        url = self.reset_url(token)
        if not self.enabled:
            # Surface the link server-side only so operators can test without email.
            logger.info("password reset link for %s: %s", user.email, url)
        body = (
            "<p style='margin:0 0 12px;'>We received a request to reset your MedChain password.</p>"
            "<p style='margin:0;'>Choose a new password using the button below. "
            "If you didn't request this, you can safely ignore this email.</p>"
        )
        html = render_email(
            heading="Reset your password",
            body_html=body,
            button_label="Reset password",
            button_url=url,
            footnote=f"This link expires in {self.settings.reset_token_minutes} minutes.",
            preheader="Reset your MedChain password.",
        )
        return await self.send(user.email, user.name, "Reset your MedChain password", html)

    async def send_access_request_rejected(self, access_request: AccessRequest) -> bool:
        reason = access_request.rejection_reason or "No additional details were provided."
        body = (
            f"<p style='margin:0 0 12px;'>Thank you for your interest in MedChain. After review, we're "
            f"unable to approve access for <strong style='color:#ffffff;'>"
            f"{escape(access_request.organization_name)}</strong> at this time.</p>"
            f"<p style='margin:0;'>{escape(reason)}</p>"
        )
        html = render_email(
            heading="Update on your access request",
            body_html=body,
            preheader="An update on your MedChain access request.",
        )
        return await self.send(
            access_request.email,
            access_request.contact_name,
            "Update on your MedChain access request",
            html,
        )
