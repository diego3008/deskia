import argparse
import base64
import os
from email.errors import HeaderParseError
from email.headerregistry import Address
from email.message import EmailMessage
from pathlib import Path

import httplib2
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_httplib2 import AuthorizedHttp
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


class GmailConfigurationError(RuntimeError):
    pass


def _get_gmail_service():
    try:
        creds = Credentials.from_authorized_user_file(
            os.getenv("GMAIL_TOKEN_PATH", "token.json"), SCOPES
        )
    except (OSError, ValueError, TypeError, AttributeError) as error:
        raise GmailConfigurationError("gmail_authorization_unavailable") from error

    try:
        if not creds.valid:
            if not (creds.expired and creds.refresh_token):
                raise GmailConfigurationError("gmail_authorization_required")
            creds.refresh(Request())
    except GoogleAuthError as error:
        raise GmailConfigurationError("gmail_authorization_unavailable") from error

    transport = AuthorizedHttp(creds, http=httplib2.Http(timeout=30))
    return build("gmail", "v1", http=transport, cache_discovery=False)


def send_email(to: str, subject: str, body: str) -> str:
    sender = os.getenv("GMAIL_SENDER_EMAIL", "")
    if not sender:
        raise GmailConfigurationError("gmail_sender_missing")

    for address in (to, sender):
        if "\r" in address or "\n" in address:
            raise ValueError("invalid email header")
        try:
            parsed = Address(addr_spec=address)
        except (HeaderParseError, ValueError) as error:
            raise ValueError("single mailbox address required") from error
        if not parsed.username or not parsed.domain:
            raise ValueError("single mailbox address required")

    message = EmailMessage()
    message["To"], message["From"], message["Subject"] = to, sender, subject
    message.set_content(body)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    service = _get_gmail_service()
    try:
        result = (
            service.users()
            .messages()
            .send(userId="me", body={"raw": raw})
            .execute(num_retries=0)
        )
    finally:
        service.close()

    message_id = result.get("id") if isinstance(result, dict) else None
    if not isinstance(message_id, str) or not message_id.strip():
        raise RuntimeError("gmail_message_id_missing")
    return message_id


def authorize_gmail():
    flow = InstalledAppFlow.from_client_secrets_file(
        os.getenv("GMAIL_CREDENTIALS_PATH", "credentials.json"), SCOPES
    )
    creds = flow.run_local_server(port=0)
    token_path = Path(os.getenv("GMAIL_TOKEN_PATH", "token.json"))
    fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as token:
        os.fchmod(token.fileno(), 0o600)
        token.write(creds.to_json())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorize", action="store_true", required=True)
    parser.parse_args()
    authorize_gmail()
