"""Offline tests for the single-call, metadata-only ICORE probe."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest import TestCase

from product_eval import icore_transport_onecall as diagnostic


class ConnectError(Exception):
    pass


class APIConnectionError(Exception):
    pass


class FakeRaw:
    status_code = 200
    headers = {"x-request-id": "req_synthetic123"}

    def __init__(self, usage: object) -> None:
        self.usage = usage

    def parse(self) -> object:
        return SimpleNamespace(
            choices=[SimpleNamespace(
                finish_reason="stop", message=SimpleNamespace(content="private response body"))],
            usage=self.usage,
        )


class FakeCreate:
    def __init__(self, result: object) -> None:
        self.result = result
        self.calls: list[dict] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def fake_client(create: FakeCreate) -> object:
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        with_raw_response=SimpleNamespace(create=create.create))))


class OneCallTests(TestCase):
    def test_exception_receipt_contains_only_allowlisted_types(self) -> None:
        secret = "iba_secret_material_must_never_appear"
        cause = ConnectError(secret)
        exc = APIConnectionError(secret)
        exc.__cause__ = cause
        exc.request_id = secret
        receipt = diagnostic.sanitized_exception(exc, elapsed_ms=19)
        self.assertEqual(receipt["exception_class"], "APIConnectionError")
        self.assertEqual(receipt["cause_classes"], ["ConnectError"])
        self.assertIsNone(receipt["request_id"])
        self.assertIsNone(receipt["http_status"])
        self.assertNotIn(secret, json.dumps(receipt))

    def test_success_is_one_synthetic_call_without_content_receipt(self) -> None:
        usage = SimpleNamespace(prompt_tokens=8, completion_tokens=2, total_tokens=10)
        create = FakeCreate(FakeRaw(usage))
        receipt, code = diagnostic.probe(fake_client(create))
        self.assertEqual(code, 0)
        self.assertEqual(len(create.calls), 1)
        self.assertEqual(create.calls[0]["model"], "innobot-luna-6")
        self.assertLessEqual(create.calls[0]["max_tokens"], 64)
        self.assertLessEqual(create.calls[0]["timeout"], 30)
        self.assertEqual(receipt["http_status"], 200)
        self.assertEqual(receipt["request_id"], "req_synthetic123")
        self.assertEqual(receipt["total_tokens"], 10)
        self.assertNotIn("private response body", json.dumps(receipt))

    def test_missing_usage_stops_without_retry(self) -> None:
        create = FakeCreate(FakeRaw(None))
        receipt, code = diagnostic.probe(fake_client(create))
        self.assertEqual(code, 2)
        self.assertEqual(len(create.calls), 1)
        self.assertIsNone(receipt["prompt_tokens"])
        self.assertIsNone(receipt["completion_tokens"])
        self.assertIsNone(receipt["total_tokens"])

    def test_request_id_rejects_key_like_and_header_markup(self) -> None:
        self.assertIsNone(diagnostic._request_id("req_iba_secret_material_must_never_appear"))
        self.assertIsNone(diagnostic._request_id("req_ok\nAuthorization: secret"))
