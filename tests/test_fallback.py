import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from google.genai import errors, types

from test_documents import NS


class FallbackTests(unittest.TestCase):
    def setUp(self):
        self.config = {"GEMINI_FREE_API_KEY": "free-key"}
        self.request = Mock(return_value=[{"ok": True}])
        self.status = Mock()
        self.scope = patch.dict(NS, {
            "setting": lambda name, default="": self.config.get(name, default),
            "generate_with_key": self.request,
        })
        self.scope.start()
        self.addCleanup(self.scope.stop)

    def run_generation(self):
        return NS["generate_with_fallback"]("paid-key", ["document"], {}, self.status)

    def test_primary_success_never_uses_free_key(self):
        self.run_generation()
        self.request.assert_called_once_with("paid-key", ["document"], {}, "GEMINI_MODEL")

    def test_quota_switches_once_and_next_request_starts_with_primary(self):
        self.request.side_effect = [errors.ClientError(429, {}), ["free-result"], ["paid-result"]]
        self.assertEqual(self.run_generation(), ["free-result"])
        self.assertEqual(self.run_generation(), ["paid-result"])
        self.assertEqual([c.args[0] for c in self.request.call_args_list],
                         ["paid-key", "free-key", "paid-key"])
        self.assertEqual(self.request.call_args_list[1].args[3], "GEMINI_FREE_MODEL")

    def test_both_quotas_stop_after_two_calls(self):
        self.request.side_effect = errors.ClientError(429, {})
        with self.assertRaisesRegex(ValueError, "모두 요청 한도"):
            self.run_generation()
        self.assertEqual(self.request.call_count, 2)

    def test_missing_or_duplicate_free_key_does_not_retry(self):
        self.request.side_effect = errors.ClientError(429, {})
        for key in ("", "paid-key"):
            with self.subTest(key=key):
                self.config["GEMINI_FREE_API_KEY"] = key
                self.request.reset_mock()
                with self.assertRaisesRegex(ValueError, "GEMINI_FREE_API_KEY"):
                    self.run_generation()
                self.request.assert_called_once()

    def test_non_quota_errors_do_not_use_free_key(self):
        for exc in (errors.ClientError(403, {}), errors.ServerError(500, {}),
                    ValueError("invalid generated document")):
            with self.subTest(error=type(exc)):
                self.request.reset_mock()
                self.request.side_effect = exc
                with self.assertRaises((ValueError, RuntimeError)):
                    self.run_generation()
                self.request.assert_called_once()


class ProjectRequestTests(unittest.TestCase):
    def test_quota_on_first_two_models_still_tries_third(self):
        client = Mock()
        client.models.list.return_value = [SimpleNamespace(
            name=name, supported_actions=["generateContent"])
            for name in ("gemini-3-flash", "gemini-2-flash", "gemini-1-flash")]
        client.models.generate_content.side_effect = [
            errors.ClientError(429, {}), errors.ClientError(429, {}),
            SimpleNamespace(text='[{"ok": true}]')]
        with patch.dict(NS, {"genai": SimpleNamespace(Client=Mock(return_value=client)),
                             "types": types, "json": json,
                             "validate_days": lambda data: data,
                             "setting": lambda *args: ""}):
            self.assertEqual(NS["generate_with_key"]("key", [], {}, "GEMINI_MODEL"), [{"ok": True}])
        self.assertEqual(client.models.generate_content.call_count, 3)
        client.close.assert_called_once()

    def test_diagnostic_contains_quota_but_not_raw_error_or_key(self):
        exc = errors.ClientError(429, {"error": {
            "message": "secret-key-do-not-display", "details": [
                {"violations": [{"quotaId": "RequestsPerMinute", "quotaValue": "0"}]},
                {"retryDelay": "30s"}]}})
        result = NS["error_diagnostic"](exc, "gemini-test-flash")
        for value in ("gemini-test-flash", "429", "RequestsPerMinute", "30s"):
            self.assertIn(value, result)
        self.assertNotIn("secret-key", result)

    def test_model_list_quota_propagates_and_client_closes(self):
        client = Mock()
        client.models.list.side_effect = errors.ClientError(429, {})
        with patch.dict(NS, {"genai": SimpleNamespace(Client=Mock(return_value=client)),
                             "types": types, "setting": lambda *args: ""}):
            with self.assertRaises(errors.ClientError) as raised:
                NS["generate_with_key"]("paid-key", [], {}, "GEMINI_MODEL")
        self.assertEqual(raised.exception.code, 429)
        client.close.assert_called_once()
        client.models.generate_content.assert_not_called()

    def test_free_model_setting_is_independent_and_result_validated(self):
        client = Mock()
        client.models.generate_content.return_value = SimpleNamespace(text='[{"ok": true}]')
        config = {"GEMINI_MODEL": "paid-model", "GEMINI_FREE_MODEL": "free-model"}
        validate = Mock(side_effect=ValueError("missing document fields"))
        with patch.dict(NS, {"genai": SimpleNamespace(Client=Mock(return_value=client)),
                             "types": types, "json": json, "validate_days": validate,
                             "setting": lambda name: config[name]}):
            with self.assertRaisesRegex(ValueError, "missing document fields"):
                NS["generate_with_key"]("free-key", [], {}, "GEMINI_FREE_MODEL")
        self.assertEqual(client.models.generate_content.call_args.kwargs["model"], "free-model")
        client.models.list.assert_not_called()
        client.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
