"""Browser trace viewer for local AgentOps debugging."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

TRACE_VIEWER_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgentOps Trace Viewer</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --surface: #ffffff;
      --surface-2: #eef2f5;
      --line: #d9e0e7;
      --line-strong: #b7c2cc;
      --text: #19212a;
      --muted: #627083;
      --accent: #0f766e;
      --accent-soft: #d8f0ed;
      --warn: #a16207;
      --danger: #b42318;
      --ok: #146c43;
      --mono: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
      --sans: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: var(--sans);
      font-size: 14px;
      line-height: 1.4;
    }

    button,
    input,
    select {
      font: inherit;
    }

    .shell {
      min-height: 100svh;
      display: grid;
      grid-template-rows: auto 1fr;
    }

    .topbar {
      display: grid;
      grid-template-columns: minmax(190px, 260px) 1fr auto auto;
      gap: 12px;
      align-items: center;
      padding: 14px 18px;
      border-bottom: 1px solid var(--line);
      background: var(--surface);
    }

    .brand {
      display: flex;
      flex-direction: column;
      gap: 2px;
      min-width: 0;
    }

    .brand strong {
      font-size: 16px;
      font-weight: 700;
      letter-spacing: 0;
    }

    .brand span,
    .status-line {
      color: var(--muted);
      font-size: 12px;
    }

    .auth {
      display: grid;
      grid-template-columns: minmax(190px, 360px) auto;
      gap: 8px;
      justify-content: end;
      align-items: center;
    }

    input,
    select {
      height: 34px;
      border: 1px solid var(--line-strong);
      border-radius: 6px;
      background: var(--surface);
      color: var(--text);
      padding: 0 10px;
      outline: none;
      min-width: 0;
    }

    input:focus,
    select:focus,
    button:focus-visible {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px var(--accent-soft);
    }

    button {
      height: 34px;
      border: 1px solid var(--line-strong);
      border-radius: 6px;
      background: var(--surface);
      color: var(--text);
      padding: 0 11px;
      cursor: pointer;
      transition: background 120ms ease, border-color 120ms ease, color 120ms ease;
    }

    button:hover {
      background: var(--surface-2);
    }

    .primary {
      background: var(--accent);
      border-color: var(--accent);
      color: white;
    }

    .primary:hover {
      background: #0b5f59;
    }

    .workspace {
      display: grid;
      grid-template-columns: minmax(260px, 320px) minmax(0, 1fr) minmax(260px, 340px);
      min-height: 0;
    }

    .pane {
      min-width: 0;
      min-height: 0;
      overflow: auto;
      border-right: 1px solid var(--line);
      background: var(--surface);
    }

    .pane:last-child {
      border-right: 0;
    }

    .pane-header {
      position: sticky;
      top: 0;
      z-index: 1;
      display: grid;
      gap: 10px;
      padding: 14px;
      border-bottom: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.96);
      backdrop-filter: blur(8px);
    }

    .pane-header h1,
    .pane-header h2 {
      margin: 0;
      font-size: 14px;
      font-weight: 700;
      letter-spacing: 0;
    }

    .filters {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 8px;
      align-items: center;
    }

    .run-list,
    .timeline,
    .stack {
      display: grid;
      gap: 0;
    }

    .run-row,
    .event-row,
    .summary-row,
    .empty {
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
    }

    .run-row {
      display: grid;
      width: 100%;
      height: auto;
      text-align: left;
      border-width: 0 0 1px;
      border-radius: 0;
      gap: 5px;
      background: transparent;
      justify-items: stretch;
    }

    .run-row:hover,
    .run-row[aria-current="true"] {
      background: var(--surface-2);
    }

    .run-title,
    .event-title,
    .detail-title {
      display: flex;
      gap: 8px;
      align-items: center;
      min-width: 0;
    }

    .truncate {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .meta {
      color: var(--muted);
      font-size: 12px;
      font-family: var(--mono);
    }

    .badge {
      display: inline-flex;
      align-items: center;
      min-height: 21px;
      padding: 2px 7px;
      border-radius: 999px;
      border: 1px solid var(--line-strong);
      color: var(--muted);
      background: var(--surface);
      font-size: 12px;
      font-weight: 600;
      white-space: nowrap;
    }

    .badge.running,
    .badge.pass,
    .badge.succeeded {
      color: var(--ok);
      border-color: #95d5b2;
      background: #ebf8f1;
    }

    .badge.warn,
    .badge.canceled {
      color: var(--warn);
      border-color: #f3d27a;
      background: #fff8e6;
    }

    .badge.fail,
    .badge.failed,
    .badge.error {
      color: var(--danger);
      border-color: #f3b7b2;
      background: #fff1f0;
    }

    .detail {
      background: #fbfcfd;
    }

    .detail-header {
      display: grid;
      gap: 12px;
      padding: 16px 18px;
      border-bottom: 1px solid var(--line);
      background: var(--surface);
    }

    .detail-title h2 {
      margin: 0;
      min-width: 0;
      font-size: 18px;
      letter-spacing: 0;
    }

    .metrics {
      display: grid;
      grid-template-columns: repeat(4, minmax(110px, 1fr));
      border-top: 1px solid var(--line);
      border-left: 1px solid var(--line);
    }

    .metric {
      padding: 10px;
      border-right: 1px solid var(--line);
      border-bottom: 1px solid var(--line);
      background: var(--surface);
    }

    .metric span {
      display: block;
      color: var(--muted);
      font-size: 12px;
    }

    .metric strong {
      display: block;
      margin-top: 3px;
      font-size: 18px;
      letter-spacing: 0;
    }

    .timeline-toolbar {
      position: sticky;
      top: 0;
      z-index: 1;
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      align-items: center;
      padding: 10px 14px;
      border-bottom: 1px solid var(--line);
      background: rgba(251, 252, 253, 0.96);
      backdrop-filter: blur(8px);
    }

    .tab[aria-pressed="true"] {
      background: var(--accent-soft);
      border-color: #8fcac3;
      color: #064e49;
    }

    .event-row {
      display: grid;
      grid-template-columns: 72px minmax(0, 1fr);
      gap: 12px;
      background: var(--surface);
    }

    .seq {
      color: var(--muted);
      font-family: var(--mono);
      font-size: 12px;
    }

    pre {
      margin: 8px 0 0;
      padding: 9px 10px;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #f8fafc;
      color: #25313f;
      font-family: var(--mono);
      font-size: 12px;
      line-height: 1.45;
      white-space: pre-wrap;
      word-break: break-word;
    }

    .summary-row {
      display: grid;
      gap: 6px;
      background: var(--surface);
    }

    .summary-row h3 {
      margin: 0;
      font-size: 13px;
      letter-spacing: 0;
    }

    .summary-row p {
      margin: 0;
      color: var(--muted);
      font-size: 12px;
    }

    .empty {
      color: var(--muted);
      background: var(--surface);
    }

    .error-text {
      color: var(--danger);
    }

    @media (max-width: 1080px) {
      .workspace {
        grid-template-columns: minmax(240px, 300px) minmax(0, 1fr);
      }

      .inspector {
        display: none;
      }
    }

    @media (max-width: 760px) {
      .topbar {
        grid-template-columns: 1fr;
      }

      .auth {
        grid-template-columns: 1fr auto;
        justify-content: stretch;
      }

      .workspace {
        grid-template-columns: 1fr;
      }

      .runs {
        max-height: 42svh;
      }

      .metrics {
        grid-template-columns: repeat(2, minmax(100px, 1fr));
      }
    }
  </style>
</head>
<body>
  <div class="shell">
    <header class="topbar">
      <div class="brand" aria-label="AgentOps Trace Viewer">
        <strong>AgentOps Trace Viewer</strong>
        <span>Run timeline, RAG evidence, evaluations, and errors</span>
      </div>
      <div id="status" class="status-line" role="status">Enter an API key to load project runs.</div>
      <div class="auth">
        <input id="apiKey" type="password" autocomplete="off" placeholder="X-AgentOps-API-Key" aria-label="API key">
        <button id="connect" class="primary" type="button">Load</button>
      </div>
      <button id="reload" type="button">Refresh</button>
    </header>
    <main class="workspace">
      <section class="pane runs" aria-label="Runs">
        <div class="pane-header">
          <h1>Runs</h1>
          <div class="filters">
            <select id="statusFilter" aria-label="Run status filter">
              <option value="">All statuses</option>
              <option value="running">Running</option>
              <option value="succeeded">Succeeded</option>
              <option value="failed">Failed</option>
              <option value="canceled">Canceled</option>
            </select>
            <button id="clearKey" type="button">Clear key</button>
          </div>
        </div>
        <div id="runList" class="run-list">
          <div class="empty">No runs loaded.</div>
        </div>
      </section>
      <section class="pane detail" aria-label="Run detail">
        <div id="detailHeader" class="detail-header">
          <div class="detail-title">
            <h2>Select a run</h2>
          </div>
          <div class="meta">The viewer calls authenticated /v1 APIs from this browser session.</div>
        </div>
        <div id="metrics" class="metrics" aria-label="Run summary"></div>
        <div class="timeline-toolbar" aria-label="Timeline filters">
          <button class="tab" type="button" data-filter="all" aria-pressed="true">All</button>
          <button class="tab" type="button" data-filter="message" aria-pressed="false">Messages</button>
          <button class="tab" type="button" data-filter="model_call" aria-pressed="false">Models</button>
          <button class="tab" type="button" data-filter="tool_call" aria-pressed="false">Tools</button>
          <button class="tab" type="button" data-filter="rag_retrieval" aria-pressed="false">RAG</button>
          <button class="tab" type="button" data-filter="evaluation" aria-pressed="false">Evaluations</button>
          <button class="tab" type="button" data-filter="error" aria-pressed="false">Errors</button>
        </div>
        <div id="timeline" class="timeline">
          <div class="empty">Timeline appears after selecting a run.</div>
        </div>
      </section>
      <aside class="pane inspector" aria-label="Evidence inspector">
        <div class="pane-header">
          <h2>Evidence</h2>
          <div class="meta">Recent page from run detail</div>
        </div>
        <div id="inspector" class="stack">
          <div class="empty">RAG, evaluation, and error evidence appears here.</div>
        </div>
      </aside>
    </main>
  </div>

  <script>
    const state = {
      runs: [],
      selectedRunId: null,
      detail: null,
      filter: "all",
    };

    const nodes = {
      apiKey: document.querySelector("#apiKey"),
      clearKey: document.querySelector("#clearKey"),
      connect: document.querySelector("#connect"),
      detailHeader: document.querySelector("#detailHeader"),
      inspector: document.querySelector("#inspector"),
      metrics: document.querySelector("#metrics"),
      reload: document.querySelector("#reload"),
      runList: document.querySelector("#runList"),
      status: document.querySelector("#status"),
      statusFilter: document.querySelector("#statusFilter"),
      tabs: Array.from(document.querySelectorAll(".tab")),
      timeline: document.querySelector("#timeline"),
    };

    nodes.apiKey.value = sessionStorage.getItem("agentops_api_key") || "";

    function setStatus(message, isError = false) {
      nodes.status.textContent = message;
      nodes.status.classList.toggle("error-text", isError);
    }

    function getApiKey() {
      return nodes.apiKey.value.trim();
    }

    async function apiGet(path) {
      const apiKey = getApiKey();
      if (!apiKey) {
        throw new Error("Missing API key");
      }
      const response = await fetch(path, {
        headers: {
          "X-AgentOps-API-Key": apiKey,
          "Accept": "application/json",
        },
      });
      if (!response.ok) {
        let detail = response.statusText;
        try {
          const errorBody = await response.json();
          detail = errorBody.detail || detail;
        } catch {
          detail = response.statusText;
        }
        throw new Error(`${response.status} ${detail}`);
      }
      return response.json();
    }

    async function loadRuns() {
      try {
        sessionStorage.setItem("agentops_api_key", getApiKey());
        setStatus("Loading runs...");
        const status = nodes.statusFilter.value;
        const query = new URLSearchParams({ limit: "50" });
        if (status) {
          query.set("status", status);
        }
        state.runs = await apiGet(`/v1/runs?${query.toString()}`);
        renderRuns();
        if (state.runs.length > 0) {
          const nextRun = state.runs.find((run) => run.id === state.selectedRunId) || state.runs[0];
          await selectRun(nextRun.id);
        } else {
          state.selectedRunId = null;
          state.detail = null;
          renderEmptyDetail();
        }
        setStatus(`Loaded ${state.runs.length} runs.`);
      } catch (error) {
        setStatus(error.message, true);
      }
    }

    async function selectRun(runId) {
      state.selectedRunId = runId;
      renderRuns();
      setStatus("Loading run detail...");
      state.detail = await apiGet(`/v1/runs/${encodeURIComponent(runId)}/detail`);
      renderDetail();
      setStatus(`Loaded run ${runId}.`);
    }

    function renderRuns() {
      nodes.runList.replaceChildren();
      if (state.runs.length === 0) {
        nodes.runList.append(empty("No runs found for this project."));
        return;
      }
      for (const run of state.runs) {
        const row = document.createElement("button");
        row.type = "button";
        row.className = "run-row";
        row.setAttribute("aria-current", String(run.id === state.selectedRunId));
        row.addEventListener("click", () => selectRun(run.id).catch((error) => {
          setStatus(error.message, true);
        }));

        const title = document.createElement("div");
        title.className = "run-title";
        title.append(badge(run.status), span(run.name || "Untitled run", "truncate"));

        const meta = document.createElement("div");
        meta.className = "meta truncate";
        meta.textContent = `${formatTime(run.started_at)} ${run.session_id || run.project_id}`;

        row.append(title, meta);
        nodes.runList.append(row);
      }
    }

    function renderDetail() {
      if (!state.detail) {
        renderEmptyDetail();
        return;
      }

      const run = state.detail.run;
      const summary = state.detail.summary;
      nodes.detailHeader.replaceChildren(
        div("detail-title", [badge(run.status), heading(run.name || "Untitled run")]),
        div("meta", [`${run.id} ${formatTime(run.started_at)}`]),
      );

      nodes.metrics.replaceChildren(
        metric("Events", summary.event_count),
        metric("Tokens", summary.total_tokens),
        metric("Latency", `${summary.total_latency_ms} ms`),
        metric("Errors", summary.error_count),
        metric("Tool calls", summary.tool_call_count),
        metric("RAG events", summary.rag_retrieval_count),
        metric("Evaluations", summary.evaluation_count),
        metric("Models", summary.model_call_count),
      );

      renderTimeline();
      renderInspector();
    }

    function renderEmptyDetail() {
      nodes.detailHeader.replaceChildren(
        div("detail-title", [heading("Select a run")]),
        div("meta", ["The viewer calls authenticated /v1 APIs from this browser session."]),
      );
      nodes.metrics.replaceChildren();
      nodes.timeline.replaceChildren(empty("Timeline appears after selecting a run."));
      nodes.inspector.replaceChildren(empty("RAG, evaluation, and error evidence appears here."));
    }

    function renderTimeline() {
      nodes.timeline.replaceChildren();
      const events = state.detail.timeline.filter((event) => {
        return state.filter === "all" || event.type === state.filter;
      });
      if (events.length === 0) {
        nodes.timeline.append(empty("No events match this filter."));
        return;
      }
      for (const event of events) {
        const row = document.createElement("article");
        row.className = "event-row";
        row.append(div("seq", [`#${event.sequence}`]), eventBody(event));
        nodes.timeline.append(row);
      }
    }

    function renderInspector() {
      nodes.inspector.replaceChildren();
      const groups = [
        ["RAG evidence", state.detail.rag_evidence],
        ["Evaluations", state.detail.evaluations],
        ["Errors", state.detail.errors],
      ];
      let count = 0;
      for (const [title, events] of groups) {
        for (const event of events) {
          count += 1;
          const row = document.createElement("section");
          row.className = "summary-row";
          row.append(heading3(title), paragraph(event.name || event.type), payloadBlock(event.payload));
          nodes.inspector.append(row);
        }
      }
      if (count === 0) {
        nodes.inspector.append(empty("No RAG, evaluation, or error evidence in the recent page."));
      }
    }

    function eventBody(event) {
      const body = document.createElement("div");
      const title = document.createElement("div");
      title.className = "event-title";
      title.append(badge(event.type), span(event.name || event.type, "truncate"));
      body.append(title, div("meta", [formatTime(event.timestamp)]), payloadBlock(event.payload));
      return body;
    }

    function badge(value) {
      const item = document.createElement("span");
      item.className = `badge ${String(value).replaceAll("_", "-")}`;
      item.textContent = value;
      return item;
    }

    function metric(label, value) {
      const item = document.createElement("div");
      item.className = "metric";
      const labelNode = document.createElement("span");
      labelNode.textContent = label;
      const valueNode = document.createElement("strong");
      valueNode.textContent = value;
      item.append(labelNode, valueNode);
      return item;
    }

    function payloadBlock(payload) {
      const block = document.createElement("pre");
      block.textContent = JSON.stringify(payload, null, 2);
      return block;
    }

    function empty(message) {
      return div("empty", [message]);
    }

    function heading(text) {
      const node = document.createElement("h2");
      node.className = "truncate";
      node.textContent = text;
      return node;
    }

    function heading3(text) {
      const node = document.createElement("h3");
      node.textContent = text;
      return node;
    }

    function paragraph(text) {
      const node = document.createElement("p");
      node.textContent = text;
      return node;
    }

    function span(text, className = "") {
      const node = document.createElement("span");
      node.className = className;
      node.textContent = text;
      return node;
    }

    function div(className, children) {
      const node = document.createElement("div");
      node.className = className;
      for (const child of children) {
        if (typeof child === "string") {
          node.append(document.createTextNode(child));
        } else {
          node.append(child);
        }
      }
      return node;
    }

    function formatTime(value) {
      if (!value) {
        return "no timestamp";
      }
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) {
        return value;
      }
      return date.toLocaleString();
    }

    nodes.connect.addEventListener("click", () => {
      loadRuns();
    });
    nodes.reload.addEventListener("click", () => {
      loadRuns();
    });
    nodes.statusFilter.addEventListener("change", () => {
      loadRuns();
    });
    nodes.clearKey.addEventListener("click", () => {
      nodes.apiKey.value = "";
      sessionStorage.removeItem("agentops_api_key");
      setStatus("API key cleared for this browser session.");
    });
    for (const tab of nodes.tabs) {
      tab.addEventListener("click", () => {
        state.filter = tab.dataset.filter;
        for (const item of nodes.tabs) {
          item.setAttribute("aria-pressed", String(item === tab));
        }
        renderTimeline();
      });
    }
  </script>
</body>
</html>
"""


@router.get("/viewer", response_class=HTMLResponse)
def trace_viewer() -> HTMLResponse:
    return HTMLResponse(TRACE_VIEWER_HTML)
