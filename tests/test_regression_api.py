from fastapi.testclient import TestClient

from agentops_api.main import create_app


def _subject(run_id: str, version: str, metrics: list[dict]) -> dict:
    return {
        "run_id": run_id,
        "version": version,
        "prompt_version": f"prompt-{version}",
        "model_version": "gpt-test",
        "evaluation": {
            "answer": "The policy applies to enterprise users.",
            "metrics": metrics,
        },
    }


def test_compare_regression_flags_candidate_regression(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "agentops.db"))

    response = client.post(
        "/v1/regressions/compare",
        json={
            "baseline": _subject(
                "baseline-run",
                "v1",
                [
                    {"name": "groundedness", "score": 0.9},
                    {"name": "hallucination_risk", "score": 0.1},
                ],
            ),
            "candidate": _subject(
                "candidate-run",
                "v2",
                [
                    {"name": "groundedness", "score": 0.75},
                    {"name": "hallucination_risk", "score": 0.2},
                ],
            ),
            "regression_tolerance": 0.05,
        },
    )

    assert response.status_code == 200
    report = response.json()
    assert report["status"] == "regressed"
    assert report["baseline_version"] == "v1"
    assert report["candidate_version"] == "v2"
    assert [metric["regressed"] for metric in report["metrics"]] == [True, True]


def test_compare_regression_flags_candidate_improvement(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "agentops.db"))

    response = client.post(
        "/v1/regressions/compare",
        json={
            "baseline": _subject(
                "baseline-run",
                "v1",
                [{"name": "trustworthiness", "score": 0.72}],
            ),
            "candidate": _subject(
                "candidate-run",
                "v2",
                [{"name": "trustworthiness", "score": 0.9}],
            ),
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "improved"


def test_compare_regression_rejects_metric_mismatch(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "agentops.db"))

    response = client.post(
        "/v1/regressions/compare",
        json={
            "baseline": _subject(
                "baseline-run",
                "v1",
                [{"name": "groundedness", "score": 0.8}],
            ),
            "candidate": _subject(
                "candidate-run",
                "v2",
                [{"name": "trustworthiness", "score": 0.8}],
            ),
        },
    )

    assert response.status_code == 422
