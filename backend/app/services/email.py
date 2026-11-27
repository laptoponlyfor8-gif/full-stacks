from email.message import EmailMessage

import aiosmtplib

from app.core.config import Settings


class EmailDeliveryError(Exception):
    pass


class EmailProvider:
    async def send(self, recipient: str, subject: str, body: str) -> None:
        raise NotImplementedError


class SMTPEmailProvider(EmailProvider):
    def __init__(self, settings: Settings) -> None:
        if not settings.smtp_host or not settings.smtp_from_email:
            raise ValueError("SMTP host and sender address must be configured.")
        self._settings = settings

    async def send(self, recipient: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self._settings.smtp_from_email
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)
        try:
            await aiosmtplib.send(
                message,
                hostname=self._settings.smtp_host,
                port=self._settings.smtp_port,
                username=self._settings.smtp_username,
                password=(
                    self._settings.smtp_password.get_secret_value()
                    if self._settings.smtp_password
                    else None
                ),
                start_tls=self._settings.smtp_starttls,
                timeout=10,
            )
        except (aiosmtplib.SMTPException, OSError, TimeoutError) as exc:
            raise EmailDeliveryError from exc


def get_email_provider(settings: Settings) -> EmailProvider | None:
    if not settings.smtp_host or not settings.smtp_from_email:
        return None
    return SMTPEmailProvider(settings)
