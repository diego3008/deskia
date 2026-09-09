import base64
import os
import stat
import tempfile
import unittest
from email import policy
from email.parser import BytesParser
from pathlib import Path
from unittest.mock import MagicMock, patch


class GmailSendTests(unittest.TestCase):
    def test_sends_encoded_spanish_content_and_returns_provider_id(self):
        from src.utils.gmail_utils import send_email

        service = MagicMock()
        request = service.users.return_value.messages.return_value.send
        request.return_value.execute.return_value = {"id": "gmail-1"}

        with patch(
            "src.utils.gmail_utils._get_gmail_service", return_value=service
        ), patch.dict(
            os.environ, {"GMAIL_SENDER_EMAIL": "booker@example.com"}
        ):
            result = send_email(
                "ana@example.com", "Cita confirmada", "Tu cita está confirmada."
            )

        self.assertEqual(result, "gmail-1")
        payload = request.call_args.kwargs
        self.assertEqual(payload["userId"], "me")
        message = BytesParser(policy=policy.default).parsebytes(
            base64.urlsafe_b64decode(payload["body"]["raw"])
        )
        self.assertEqual(message["To"], "ana@example.com")
        self.assertEqual(message["From"], "booker@example.com")
        self.assertEqual(message["Subject"], "Cita confirmada")
        self.assertIn("está confirmada", message.get_content())
        request.return_value.execute.assert_called_once_with(num_retries=0)
        service.close.assert_called_once_with()

    def test_rejects_invalid_headers_before_service_creation(self):
        from src.utils.gmail_utils import send_email

        invalid_messages = (
            ("ana@example.com\r\nBcc: attacker@example.com", "Cita"),
            ("ana@example.com, bob@example.com", "Cita"),
            ("ana@example.com", "Cita\r\nBcc: attacker@example.com"),
        )
        with patch.dict(
            os.environ, {"GMAIL_SENDER_EMAIL": "booker@example.com"}
        ), patch("src.utils.gmail_utils._get_gmail_service") as get_service:
            for recipient, subject in invalid_messages:
                with self.subTest(recipient=recipient, subject=subject):
                    with self.assertRaises(ValueError):
                        send_email(recipient, subject, "Body")

        get_service.assert_not_called()

    def test_missing_sender_is_a_configuration_error(self):
        from src.utils.gmail_utils import GmailConfigurationError, send_email

        with patch.dict(os.environ, {}, clear=True), patch(
            "src.utils.gmail_utils._get_gmail_service"
        ) as get_service:
            with self.assertRaisesRegex(
                GmailConfigurationError, "gmail_sender_missing"
            ):
                send_email("ana@example.com", "Cita", "Body")

        get_service.assert_not_called()

    def test_missing_response_id_never_reports_success(self):
        from src.utils.gmail_utils import send_email

        for response in ({}, {"id": "  "}, None):
            service = MagicMock()
            service.users.return_value.messages.return_value.send.return_value.execute.return_value = response
            with self.subTest(response=response), patch(
                "src.utils.gmail_utils._get_gmail_service", return_value=service
            ), patch.dict(
                os.environ, {"GMAIL_SENDER_EMAIL": "booker@example.com"}
            ):
                with self.assertRaisesRegex(RuntimeError, "gmail_message_id_missing"):
                    send_email("ana@example.com", "Cita", "Body")
            service.close.assert_called_once_with()

    def test_closes_service_when_gmail_send_fails(self):
        from src.utils.gmail_utils import send_email

        service = MagicMock()
        service.users.return_value.messages.return_value.send.return_value.execute.side_effect = OSError(
            "transport failed"
        )
        with patch(
            "src.utils.gmail_utils._get_gmail_service", return_value=service
        ), patch.dict(
            os.environ, {"GMAIL_SENDER_EMAIL": "booker@example.com"}
        ):
            with self.assertRaises(OSError):
                send_email("ana@example.com", "Cita", "Body")

        service.close.assert_called_once_with()


class GmailServiceTests(unittest.TestCase):
    def test_missing_token_is_configuration_error_without_interactive_oauth(self):
        from src.utils.gmail_utils import GmailConfigurationError, _get_gmail_service

        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"GMAIL_TOKEN_PATH": str(Path(directory) / "missing.json")}
        ), patch(
            "src.utils.gmail_utils.Credentials.from_authorized_user_file",
            side_effect=FileNotFoundError,
        ), patch("src.utils.gmail_utils.InstalledAppFlow") as flow:
            with self.assertRaisesRegex(
                GmailConfigurationError, "gmail_authorization_unavailable"
            ):
                _get_gmail_service()

        flow.assert_not_called()

    def test_malformed_token_shape_is_a_configuration_error(self):
        from src.utils.gmail_utils import GmailConfigurationError, _get_gmail_service

        with tempfile.TemporaryDirectory() as directory:
            token_path = Path(directory) / "token.json"
            token_path.write_text("[]")
            with patch.dict(
                os.environ, {"GMAIL_TOKEN_PATH": str(token_path)}
            ), patch("src.utils.gmail_utils.InstalledAppFlow") as flow:
                with self.assertRaisesRegex(
                    GmailConfigurationError, "gmail_authorization_unavailable"
                ):
                    _get_gmail_service()

        flow.assert_not_called()

    def test_refreshes_in_memory_and_builds_finite_timeout_service(self):
        from src.utils.gmail_utils import SCOPES, _get_gmail_service

        credentials = MagicMock(valid=False, expired=True, refresh_token="refresh")
        request = MagicMock()
        raw_http = MagicMock()
        transport = MagicMock()
        service = MagicMock()

        with patch.dict(os.environ, {"GMAIL_TOKEN_PATH": "/tmp/synthetic-token.json"}), patch(
            "src.utils.gmail_utils.Credentials.from_authorized_user_file",
            return_value=credentials,
        ) as load, patch(
            "src.utils.gmail_utils.Request", return_value=request
        ), patch(
            "src.utils.gmail_utils.httplib2.Http", return_value=raw_http
        ) as http, patch(
            "src.utils.gmail_utils.AuthorizedHttp", return_value=transport
        ) as authorize, patch(
            "src.utils.gmail_utils.build", return_value=service
        ) as build, patch("builtins.open") as open_file:
            result = _get_gmail_service()

        self.assertIs(result, service)
        load.assert_called_once_with("/tmp/synthetic-token.json", SCOPES)
        credentials.refresh.assert_called_once_with(request)
        http.assert_called_once_with(timeout=30)
        authorize.assert_called_once_with(credentials, http=raw_http)
        build.assert_called_once_with(
            "gmail", "v1", http=transport, cache_discovery=False
        )
        open_file.assert_not_called()

    def test_unrefreshable_token_requires_authorization(self):
        from src.utils.gmail_utils import GmailConfigurationError, _get_gmail_service

        credentials = MagicMock(valid=False, expired=False, refresh_token=None)
        with patch(
            "src.utils.gmail_utils.Credentials.from_authorized_user_file",
            return_value=credentials,
        ):
            with self.assertRaisesRegex(
                GmailConfigurationError, "gmail_authorization_required"
            ):
                _get_gmail_service()

    def test_revoked_refresh_is_a_configuration_error(self):
        from google.auth.exceptions import RefreshError

        from src.utils.gmail_utils import GmailConfigurationError, _get_gmail_service

        credentials = MagicMock(valid=False, expired=True, refresh_token="revoked")
        credentials.refresh.side_effect = RefreshError("revoked")
        with patch(
            "src.utils.gmail_utils.Credentials.from_authorized_user_file",
            return_value=credentials,
        ), patch("src.utils.gmail_utils.Request"):
            with self.assertRaisesRegex(
                GmailConfigurationError, "gmail_authorization_unavailable"
            ):
                _get_gmail_service()


class GmailAuthorizationTests(unittest.TestCase):
    def test_authorize_writes_owner_only_token(self):
        from src.utils.gmail_utils import SCOPES, authorize_gmail

        flow = MagicMock()
        flow.run_local_server.return_value.to_json.return_value = '{"token":"synthetic"}'
        with tempfile.TemporaryDirectory() as directory:
            credentials_path = Path(directory) / "credentials.json"
            token_path = Path(directory) / "token.json"
            with patch.dict(
                os.environ,
                {
                    "GMAIL_CREDENTIALS_PATH": str(credentials_path),
                    "GMAIL_TOKEN_PATH": str(token_path),
                },
            ), patch(
                "src.utils.gmail_utils.InstalledAppFlow.from_client_secrets_file",
                return_value=flow,
            ) as make_flow:
                authorize_gmail()

            self.assertEqual(token_path.read_text(), '{"token":"synthetic"}')
            self.assertEqual(stat.S_IMODE(token_path.stat().st_mode), 0o600)

        make_flow.assert_called_once_with(str(credentials_path), SCOPES)
        flow.run_local_server.assert_called_once_with(port=0)


if __name__ == "__main__":
    unittest.main()
