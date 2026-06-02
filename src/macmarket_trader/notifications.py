"""User-scoped notification delivery for operational Agent Mode events."""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta

from macmarket_trader.config import settings
from macmarket_trader.data.providers.base import EmailMessage, EmailProvider
from macmarket_trader.data.providers.registry import build_email_provider
from macmarket_trader.domain.time import utc_now
from macmarket_trader.storage.db import SessionLocal
from macmarket_trader.storage.repositories import NotificationAttemptRepository


AGENT_NOTIFICATION_EVENTS = {
    "agent_run_completed",
    "agent_run_failed",
    "agent_run_skipped",
    "agent_paper_trade_created",
    "agent_paper_trade_blocked",
    "agent_daily_summary",
    "agent_test_notification",
}


def redact_email(value: str | None) -> str:
    email = (value or "").strip()
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    prefix = local[:2] if len(local) > 2 else local[:1]
    return f"{prefix}***@{domain}"


def redact_phone(value: str | None) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if not digits:
        return "***"
    return f"***{digits[-4:]}"


class TwilioSmsClient:
    def send(self, *, to_number: str, body: str) -> str:
        account_sid = settings.twilio_account_sid.strip()
        auth_token = settings.twilio_auth_token.strip()
        if not account_sid or not auth_token:
            raise RuntimeError("twilio_config_incomplete")
        target = f"https://api.twilio.com/2010-04-01/Accounts/{urllib.parse.quote(account_sid)}/Messages.json"
        form: dict[str, str] = {"To": to_number, "Body": body[:1500]}
        service_sid = settings.twilio_messaging_service_sid.strip()
        if service_sid:
            form["MessagingServiceSid"] = service_sid
        else:
            from_number = settings.twilio_from_number.strip()
            if not from_number or from_number == "+1XXXXXXXXXX":
                raise RuntimeError("twilio_sender_missing")
            form["From"] = from_number
        encoded = urllib.parse.urlencode(form).encode("utf-8")
        basic = base64.b64encode(f"{account_sid}:{auth_token}".encode("utf-8")).decode("ascii")
        request = urllib.request.Request(
            target,
            data=encoded,
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=settings.twilio_request_timeout_seconds) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"twilio_http_{exc.code}") from exc
        except Exception as exc:  # noqa: BLE001 - convert provider details into safe status codes.
            raise RuntimeError("twilio_request_failed") from exc
        sid = str(payload.get("sid") or "").strip()
        return sid or "twilio_message"


class NotificationService:
    def __init__(
        self,
        *,
        repo: NotificationAttemptRepository | None = None,
        email_provider: EmailProvider | None = None,
        sms_client: TwilioSmsClient | None = None,
    ) -> None:
        self.repo = repo or NotificationAttemptRepository(SessionLocal)
        self.email_provider = email_provider or build_email_provider()
        self.sms_client = sms_client or TwilioSmsClient()

    @staticmethod
    def sms_readiness() -> dict[str, object]:
        provider = settings.sms_provider.strip().lower() or "twilio"
        configured = bool(
            provider == "twilio"
            and settings.twilio_account_sid.strip()
            and settings.twilio_auth_token.strip()
            and (
                settings.twilio_messaging_service_sid.strip()
                or (
                    settings.twilio_from_number.strip()
                    and settings.twilio_from_number.strip() != "+1XXXXXXXXXX"
                )
            )
        )
        enabled = bool(settings.sms_notifications_enabled)
        return {
            "provider": provider,
            "enabled": enabled,
            "configured": configured,
            "accountSidPresent": bool(settings.twilio_account_sid.strip()),
            "authTokenPresent": bool(settings.twilio_auth_token.strip()),
            "messagingServiceSidPresent": bool(settings.twilio_messaging_service_sid.strip()),
            "fromNumberPresent": bool(
                settings.twilio_from_number.strip()
                and settings.twilio_from_number.strip() != "+1XXXXXXXXXX"
            ),
            "status": "ready" if enabled and configured else "disabled" if not enabled else "unconfigured",
        }

    def _sms_allowed(self, *, app_user_id: int, run_id: str | None) -> str | None:
        now = utc_now()
        daily_count = self.repo.count_recent(
            app_user_id=app_user_id,
            channel="sms",
            since=now - timedelta(days=1),
            statuses=["sent", "failed", "skipped", "disabled"],
        )
        if daily_count >= max(0, int(settings.sms_max_messages_per_user_per_day)):
            return "sms_daily_rate_limit"
        if run_id:
            run_count = self.repo.count_for_run(app_user_id=app_user_id, channel="sms", run_id=run_id)
            if run_count >= max(0, int(settings.sms_max_messages_per_run)):
                return "sms_run_rate_limit"
        return None

    def send_event(
        self,
        *,
        user,
        settings_payload: dict[str, object],
        event_type: str,
        title: str,
        body: str,
        email_html: str | None = None,
        sms_body: str | None = None,
        run_id: str | None = None,
        payload: dict[str, object] | None = None,
    ) -> list[dict[str, object]]:
        if event_type not in AGENT_NOTIFICATION_EVENTS:
            event_type = "agent_test_notification"
        preference = str(settings_payload.get("notification_preference") or "none").strip().lower()
        if preference not in {"none", "email", "sms", "both"}:
            preference = "none"
        if preference == "none":
            return []
        channels: list[str] = []
        if preference in {"email", "both"} and bool(settings_payload.get("email_notifications_enabled", preference in {"email", "both"})):
            channels.append("email")
        if preference in {"sms", "both"} and bool(settings_payload.get("sms_notifications_enabled", preference in {"sms", "both"})):
            channels.append("sms")

        attempts: list[dict[str, object]] = []
        for channel in channels:
            if channel == "email":
                attempts.append(
                    self._send_email(
                        user=user,
                        event_type=event_type,
                        title=title,
                        body=body,
                        html=email_html,
                        run_id=run_id,
                        payload=payload,
                    )
                )
            elif channel == "sms":
                attempts.append(
                    self._send_sms(
                        user=user,
                        settings_payload=settings_payload,
                        event_type=event_type,
                        body=sms_body or body,
                        run_id=run_id,
                        payload=payload,
                    )
                )
        return attempts

    def _record(
        self,
        *,
        app_user_id: int,
        provider: str,
        channel: str,
        recipient_redacted: str,
        event_type: str,
        status: str,
        run_id: str | None,
        failure_reason: str | None,
        payload: dict[str, object] | None,
    ) -> dict[str, object]:
        sent_at = utc_now() if status == "sent" else None
        row = self.repo.create(
            app_user_id=app_user_id,
            provider=provider,
            channel=channel,
            recipient_redacted=recipient_redacted,
            event_type=event_type,
            status=status,
            run_id=run_id,
            failure_reason=failure_reason,
            payload_json=payload or {},
            sent_at=sent_at,
        )
        return {
            "id": row.id,
            "provider": row.provider,
            "channel": row.channel,
            "recipientRedacted": row.recipient_redacted,
            "eventType": row.event_type,
            "status": row.status,
            "runId": row.run_id,
            "failureReason": row.failure_reason,
            "createdAt": row.created_at.isoformat() if row.created_at else None,
            "sentAt": row.sent_at.isoformat() if row.sent_at else None,
        }

    def _send_email(
        self,
        *,
        user,
        event_type: str,
        title: str,
        body: str,
        html: str | None,
        run_id: str | None,
        payload: dict[str, object] | None,
    ) -> dict[str, object]:
        email = str(getattr(user, "email", "") or "").strip()
        if not email or "@" not in email:
            return self._record(
                app_user_id=user.id,
                provider=settings.email_provider.strip().lower() or "console",
                channel="email",
                recipient_redacted="***",
                event_type=event_type,
                status="skipped",
                run_id=run_id,
                failure_reason="email_missing",
                payload=payload,
            )
        try:
            self.email_provider.send(
                EmailMessage(
                    to_email=email,
                    subject=title[:160],
                    body=body,
                    template_name=event_type,
                    html=html,
                )
            )
        except Exception:  # noqa: BLE001 - keep provider exception details out of API/log payloads.
            return self._record(
                app_user_id=user.id,
                provider=settings.email_provider.strip().lower() or "console",
                channel="email",
                recipient_redacted=redact_email(email),
                event_type=event_type,
                status="failed",
                run_id=run_id,
                failure_reason="email_provider_failed",
                payload=payload,
            )
        return self._record(
            app_user_id=user.id,
            provider=settings.email_provider.strip().lower() or "console",
            channel="email",
            recipient_redacted=redact_email(email),
            event_type=event_type,
            status="sent",
            run_id=run_id,
            failure_reason=None,
            payload=payload,
        )

    def _send_sms(
        self,
        *,
        user,
        settings_payload: dict[str, object],
        event_type: str,
        body: str,
        run_id: str | None,
        payload: dict[str, object] | None,
    ) -> dict[str, object]:
        phone = str(settings_payload.get("notification_phone_number") or "").strip()
        readiness = self.sms_readiness()
        if readiness["status"] != "ready":
            return self._record(
                app_user_id=user.id,
                provider=str(readiness["provider"]),
                channel="sms",
                recipient_redacted=redact_phone(phone),
                event_type=event_type,
                status="disabled" if readiness["status"] == "disabled" else "skipped",
                run_id=run_id,
                failure_reason=f"sms_{readiness['status']}",
                payload=payload,
            )
        if not phone:
            return self._record(
                app_user_id=user.id,
                provider="twilio",
                channel="sms",
                recipient_redacted="***",
                event_type=event_type,
                status="skipped",
                run_id=run_id,
                failure_reason="sms_phone_missing",
                payload=payload,
            )
        if not bool(settings_payload.get("sms_consent_confirmed")):
            return self._record(
                app_user_id=user.id,
                provider="twilio",
                channel="sms",
                recipient_redacted=redact_phone(phone),
                event_type=event_type,
                status="skipped",
                run_id=run_id,
                failure_reason="sms_consent_missing",
                payload=payload,
            )
        limited_reason = self._sms_allowed(app_user_id=user.id, run_id=run_id)
        if limited_reason:
            return self._record(
                app_user_id=user.id,
                provider="twilio",
                channel="sms",
                recipient_redacted=redact_phone(phone),
                event_type=event_type,
                status="skipped",
                run_id=run_id,
                failure_reason=limited_reason,
                payload=payload,
            )
        try:
            self.sms_client.send(to_number=phone, body=body)
        except RuntimeError as exc:
            return self._record(
                app_user_id=user.id,
                provider="twilio",
                channel="sms",
                recipient_redacted=redact_phone(phone),
                event_type=event_type,
                status="failed",
                run_id=run_id,
                failure_reason=str(exc)[:80],
                payload=payload,
            )
        return self._record(
            app_user_id=user.id,
            provider="twilio",
            channel="sms",
            recipient_redacted=redact_phone(phone),
            event_type=event_type,
            status="sent",
            run_id=run_id,
            failure_reason=None,
            payload=payload,
        )
