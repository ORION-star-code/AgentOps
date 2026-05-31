def test_trace_viewer_shell_is_served_without_embedding_credentials(make_client) -> None:
    client = make_client(include_auth_header=False)

    response = client.get("/viewer")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    html = response.text
    assert "<title>AgentOps Trace Observatory</title>" in html
    assert "AgentOps Trace Observatory" in html
    assert 'aria-label="AgentOps Trace Observatory"' in html
    assert 'data-visual-system="observatory-dark"' in html
    assert "Observatory Command Bar" in html
    assert "Trace Spine filters" in html
    assert "No Trace Spine selected" in html
    assert "event-node" in html
    assert "event-summary" in html
    assert "event-signal" in html
    assert "kv-grid" in html
    assert "Payload" in html
    assert "Metrics" in html
    assert "Raw JSON" in html
    assert "Copy JSON" in html
    assert "ragEvidenceSection" in html
    assert "evaluationMetricsSection" in html
    assert "metric-bar" in html
    assert "extractLatency" in html
    assert "extractTokens" in html
    assert "retrieval:" in html
    assert "color-scheme: dark" in html
    assert "--app-bg: #060b10" in html
    assert "--message: #22d3ee" in html
    assert "--model: #a78bfa" in html
    assert "--tool: #f59e0b" in html
    assert "--evaluation: #22c55e" in html
    assert "Evidence Inspector" in html
    assert "Search runs" in html
    assert "Copy run ID" in html
    assert "prefers-reduced-motion" in html
    assert "sessionStorage" in html
    assert "X-AgentOps-API-Key" in html
    assert "/v1/runs" in html
    assert "test-agentops-key" not in html
    assert ("t" + "p-") not in html
