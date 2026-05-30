from agentops_api.security import ApiScope


def _case(case_id: str, *, with_context: bool = True) -> dict:
    return {
        "case_id": case_id,
        "user_input": "Who does the policy apply to?",
        "reference_context": ["The policy applies to enterprise users."] if with_context else [],
        "expected_answer": "The policy applies to enterprise users.",
        "judge_rubric": "Answer must be grounded in retrieved policy text.",
        "pass_criteria": "All requested metrics must pass.",
    }


def _dataset_run_payload(*, project_id: str = "demo-project", cases: list[dict] | None = None) -> dict:
    return {
        "project_id": project_id,
        "dataset": {
            "dataset_id": "rag-trust-suite",
            "version": "2026.05.30",
            "cases": cases or [_case("case-001")],
        },
        "rubric_id": "rag-answer-quality",
        "rubric_version": "v1",
        "threshold_profile": "strict",
    }


def _compare_payload(baseline_run_id: str, candidate_run_id: str, *, project_id: str = "demo-project") -> dict:
    return {
        "project_id": project_id,
        "baseline_run_id": baseline_run_id,
        "candidate_run_id": candidate_run_id,
        "baseline_version": "baseline-v1",
        "candidate_version": "candidate-v2",
        "baseline_prompt_version": "prompt-v1",
        "candidate_prompt_version": "prompt-v2",
        "regression_tolerance": 0.05,
        "metadata": {"suite": "nightly"},
    }


def _create_dataset_run(client, *, cases: list[dict] | None = None, project_id: str = "demo-project") -> dict:
    response = client.post(
        "/v1/golden-datasets/runs",
        json=_dataset_run_payload(project_id=project_id, cases=cases),
    )
    assert response.status_code == 201
    return response.json()


def test_compare_golden_dataset_regression_requires_api_key(make_client) -> None:
    client = make_client(include_auth_header=False)

    response = client.post(
        "/v1/golden-datasets/regressions/compare",
        json=_compare_payload("baseline-run", "candidate-run"),
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing API key"


def test_compare_golden_dataset_regression_requires_evaluate_scope(make_client) -> None:
    client = make_client(scopes=[ApiScope.READ])

    response = client.post(
        "/v1/golden-datasets/regressions/compare",
        json=_compare_payload("baseline-run", "candidate-run"),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "API key does not have the required scope"


def test_compare_golden_dataset_regression_detects_unchanged_runs(make_client) -> None:
    client = make_client()
    baseline = _create_dataset_run(client)
    candidate = _create_dataset_run(client)

    response = client.post(
        "/v1/golden-datasets/regressions/compare",
        json=_compare_payload(baseline["run_id"], candidate["run_id"]),
    )

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "unchanged"
    assert result["total_cases"] == 1
    assert result["unchanged_cases"] == 1
    assert result["case_reports"][0]["case_id"] == "case-001"

    report_response = client.get(
        f"/v1/regressions/reports/{result['case_reports'][0]['report_id']}"
    )
    assert report_response.status_code == 200
    persisted_report = report_response.json()
    assert persisted_report["metadata"]["agentops_kind"] == "golden_dataset_case_regression"
    assert persisted_report["metadata"]["case_id"] == "case-001"


def test_compare_golden_dataset_regression_detects_regressed_candidate(make_client) -> None:
    client = make_client()
    baseline = _create_dataset_run(client, cases=[_case("case-001", with_context=True)])
    candidate = _create_dataset_run(client, cases=[_case("case-001", with_context=False)])

    response = client.post(
        "/v1/golden-datasets/regressions/compare",
        json=_compare_payload(baseline["run_id"], candidate["run_id"]),
    )

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "regressed"
    assert result["regressed_cases"] == 1
    assert result["case_reports"][0]["status"] == "regressed"
    assert any(metric["regressed"] for metric in result["case_reports"][0]["metrics"])


def test_compare_golden_dataset_regression_rejects_mismatched_cases(make_client) -> None:
    client = make_client()
    baseline = _create_dataset_run(client, cases=[_case("case-001")])
    candidate = _create_dataset_run(client, cases=[_case("case-002")])

    response = client.post(
        "/v1/golden-datasets/regressions/compare",
        json=_compare_payload(baseline["run_id"], candidate["run_id"]),
    )

    assert response.status_code == 422
    assert "missing candidate cases" in response.json()["detail"]


def test_compare_golden_dataset_regression_rejects_cross_project_runs(make_client) -> None:
    project_a_client = make_client(project_id="project-a")
    baseline = _create_dataset_run(project_a_client, project_id="project-a")
    candidate = _create_dataset_run(project_a_client, project_id="project-a")
    project_b_client = make_client(project_id="project-b")

    response = project_b_client.post(
        "/v1/golden-datasets/regressions/compare",
        json=_compare_payload(
            baseline["run_id"],
            candidate["run_id"],
            project_id="project-b",
        ),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "API key cannot access this project"


def test_compare_golden_dataset_regression_rejects_running_runs(make_client) -> None:
    client = make_client()
    running_run = client.post(
        "/v1/runs",
        json={
            "project_id": "demo-project",
            "metadata": {
                "agentops_kind": "golden_dataset_run",
                "dataset_id": "rag-trust-suite",
                "dataset_version": "2026.05.30",
            },
        },
    ).json()
    candidate = _create_dataset_run(client)

    response = client.post(
        "/v1/golden-datasets/regressions/compare",
        json=_compare_payload(running_run["id"], candidate["run_id"]),
    )

    assert response.status_code == 409
    assert "must be complete" in response.json()["detail"]


def test_compare_golden_dataset_regression_rejects_non_dataset_runs(make_client) -> None:
    client = make_client()
    regular_run = client.post("/v1/runs", json={"project_id": "demo-project"}).json()
    client.post(f"/v1/runs/{regular_run['id']}/complete")
    candidate = _create_dataset_run(client)

    response = client.post(
        "/v1/golden-datasets/regressions/compare",
        json=_compare_payload(regular_run["id"], candidate["run_id"]),
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "baseline_run_id must reference a golden dataset run"
