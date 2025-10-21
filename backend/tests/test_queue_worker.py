import io
import json
import os
import pathlib
import sys
from typing import Any, Dict, List

import pytest

# Configure environment variables before importing the handler module.
os.environ.setdefault("COLLECTOR_LAMBDA_ARN", "arn:aws:lambda:collector")
os.environ.setdefault("PREPROCESSOR_LAMBDA_ARN", "arn:aws:lambda:preprocessor")
os.environ.setdefault("SUMMARIZER_LAMBDA_ARN", "arn:aws:lambda:summarizer")
os.environ.setdefault("DIFF_VALIDATOR_LAMBDA_ARN", "arn:aws:lambda:diff-validator")
os.environ.setdefault("STORE_LAMBDA_ARN", "arn:aws:lambda:postprocess")

sys.path.append(str(pathlib.Path(__file__).resolve().parents[2]))

from backend.lambdas.queue_worker import handler as queue_worker  # noqa: E402  pylint: disable=wrong-import-position


class StubLambdaClient:
    def __init__(self) -> None:
        self.invocations: List[Dict[str, Any]] = []

    def invoke(self, *, FunctionName: str, InvocationType: str, Payload: bytes) -> Dict[str, Any]:  # noqa: N803
        assert InvocationType == "RequestResponse"
        payload = json.loads(Payload.decode("utf-8"))
        self.invocations.append({"FunctionName": FunctionName, "payload": payload})

        updated = dict(payload)
        steps = list(updated.get("steps", []))
        steps.append(FunctionName)
        updated["steps"] = steps

        body = json.dumps(updated).encode("utf-8")
        return {
            "Payload": io.BytesIO(body),
            "ResponseMetadata": {"RequestId": f"req-{len(self.invocations)}"},
        }


@pytest.fixture(name="stub_lambda")
def fixture_stub_lambda(monkeypatch: pytest.MonkeyPatch) -> StubLambdaClient:
    stub = StubLambdaClient()
    monkeypatch.setattr(queue_worker, "lambda_client", stub)
    return stub


def test_handle_direct_event_runs_full_pipeline(stub_lambda: StubLambdaClient) -> None:
    event = {
        "source": {"id": "bbc-world"},
        "item": {"id": "cluster-1", "link": "https://example.com"},
        "article_body": "Example article",
    }

    result = queue_worker.handle(event, context=None)

    expected_arns = [arn for _, arn in queue_worker.STEP_DEFINITIONS]
    assert result["steps"] == expected_arns
    assert [call["FunctionName"] for call in stub_lambda.invocations] == expected_arns


def test_handle_sqs_records_processes_each_message(stub_lambda: StubLambdaClient) -> None:
    event = {
        "Records": [
            {"body": json.dumps({"item": {"id": "a"}}), "messageId": "a"},
            {"body": json.dumps({"item": {"id": "b"}}), "messageId": "b"},
        ]
    }

    result = queue_worker.handle(event, context=None)

    assert result["processed"] == 2
    assert len(result["results"]) == 2
    expected_arns = [arn for _, arn in queue_worker.STEP_DEFINITIONS]
    # Each record should trigger the full pipeline.
    assert len(stub_lambda.invocations) == len(expected_arns) * 2
