import io
import json
import os
from typing import Any, Dict, List

import pytest

# Configure environment variables before importing the handler module.
os.environ.setdefault("COLLECTOR_LAMBDA_ARN", "arn:aws:lambda:collector")
os.environ.setdefault("PREPROCESSOR_LAMBDA_ARN", "arn:aws:lambda:preprocessor")
os.environ.setdefault("SUMMARIZER_LAMBDA_ARN", "arn:aws:lambda:summarizer")
os.environ.setdefault("STORE_LAMBDA_ARN", "arn:aws:lambda:postprocess")

from backend.lambdas.queue_worker import handler as queue_worker  # noqa: E402  pylint: disable=wrong-import-position


class StubLambdaClient:
    def __init__(self) -> None:
        self.invocations: List[Dict[str, Any]] = []
        self.fail_after: int | None = None

    def invoke(self, *, FunctionName: str, InvocationType: str, Payload: bytes) -> Dict[str, Any]:  # noqa: N803
        assert InvocationType == "RequestResponse"
        payload = json.loads(Payload.decode("utf-8"))
        self.invocations.append({"FunctionName": FunctionName, "payload": payload})

        if self.fail_after is not None and len(self.invocations) >= self.fail_after:
            raise RuntimeError("simulated failure")

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


def test_detail_failure_marks_dynamo_and_publishes_alert(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(queue_worker, "SUMMARY_TABLE_NAME", "summary-table", raising=False)
    update_calls: List[Dict[str, Any]] = []

    class StubTable:
        def update_item(self, **kwargs: Any) -> None:  # noqa: ANN401
            update_calls.append(kwargs)

    class StubDynamo:
        def Table(self, name: str) -> StubTable:  # noqa: N802
            if name != "summary-table":
                raise AssertionError("unexpected table name")
            return StubTable()

    monkeypatch.setattr(queue_worker, "dynamodb", StubDynamo(), raising=False)

    published: Dict[str, Any] = {}

    class StubSNS:
        def publish(self, **kwargs: Any) -> None:  # noqa: ANN401
            published.update(kwargs)

    monkeypatch.setattr(queue_worker, "ALERT_TOPIC_ARN", "arn:aws:sns:::alerts", raising=False)
    monkeypatch.setattr(queue_worker, "sns_client", StubSNS(), raising=False)

    payload = {
        "source": {"id": "bbc-world"},
        "item": {"id": "cluster-1"},
        "generate_detailed_summary": True,
    }

    stub_lambda = StubLambdaClient()
    stub_lambda.fail_after = 1
    monkeypatch.setattr(queue_worker, "lambda_client", stub_lambda)

    with pytest.raises(RuntimeError):
        queue_worker.handle(payload, context=None)

    assert update_calls, "DynamoDB update_item should be called"
    assert published["TopicArn"] == "arn:aws:sns:::alerts"
    assert "cluster-1" in published["Message"]
