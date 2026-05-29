def _subject(run_id: str, version: str, metrics: list[dict]) -> dict:
    return {
        "run_id": run_id,
        "version": version,
        "prompt_version": f"prompt-{version}",
        "model_version": "gpt-test",
        "evaluation": {
            "answer": "The policy applies to enterprise users.",
            "evaluator_id": f"evaluator-{version}",
            "evaluator_version": version,
            "rubric_id": "answer-quality",
            "rubric_version": "rubric-v1",
            "judge_model": "deterministic-rule-engine",
            "threshold_profile": "strict",
            "metrics": metrics,
        },
    }


def test_compare_regression_flags_candidate_regression(make_client) -> None:
    client = make_client()

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
    assert report["id"]
    assert report["project_id"] == "demo-project"
    assert report["created_at"]
    assert report["baseline_version"] == "v1"
    assert report["candidate_version"] == "v2"
    assert report["baseline_evaluator_id"] == "evaluator-v1"
    assert report["candidate_evaluator_id"] == "evaluator-v2"
    assert report["baseline_rubric_id"] == "answer-quality"
    assert report["candidate_rubric_version"] == "rubric-v1"
    assert report["baseline_judge_model"] == "deterministic-rule-engine"
    assert report["candidate_threshold_profile"] == "strict"
    assert [metric["regressed"] for metric in report["metrics"]] == [True, True]

    persisted_response = client.get(f"/v1/regressions/reports/{report['id']}")
    assert persisted_response.status_code == 200
    assert persisted_response.json() == report


def test_compare_regression_flags_candidate_improvement(make_client) -> None:
    client = make_client()

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


def test_compare_regression_rejects_metric_mismatch(make_client) -> None:
    client = make_client()

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


def test_get_unknown_regression_report_returns_404(make_client) -> None:
    client = make_client()

    response = client.get("/v1/regressions/reports/missing-report")

    assert response.status_code == 404
    assert response.json()["detail"] == "Regression report not found"


def test_get_regression_report_rejects_cross_project_access(make_client) -> None:
    owner_client = make_client(project_id="demo-project")
    other_client = make_client(project_id="other-project")

    created = owner_client.post(
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
    ).json()

    response = other_client.get(f"/v1/regressions/reports/{created['id']}")

    assert response.status_code == 403
    assert response.json()["detail"] == "API key cannot access this project"
