def test_trace_viewer_shell_is_served_without_embedding_credentials(make_client) -> None:
    client = make_client(include_auth_header=False)

    response = client.get("/viewer")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    html = response.text
    assert "AgentOps Trace Viewer" in html
    assert "sessionStorage" in html
    assert "X-AgentOps-API-Key" in html
    assert "/v1/runs" in html
    assert "test-agentops-key" not in html
    assert ("t" + "p-") not in html
