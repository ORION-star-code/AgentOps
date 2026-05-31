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
      --bg: #f4f6f8;
      --surface: #ffffff;
      --surface-raised: #fbfcfd;
      --surface-quiet: #eef3f6;
      --ink: #17202a;
      --muted: #607083;
      --faint: #8493a3;
      --line: #d9e1e8;
      --line-strong: #b8c4ce;
      --accent: #0f766e;
      --accent-strong: #0a5e58;
      --accent-soft: #d9efec;
      --blue: #2563eb;
      --green: #13795b;
      --amber: #a16207;
      --red: #b42318;
      --violet: #6d5bd0;
      --shadow: 0 18px 50px rgba(21, 32, 43, 0.08);
      --mono: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
      --sans: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    * {
      box-sizing: border-box;
    }

    html {
      height: 100%;
    }

    body {
      min-height: 100%;
      margin: 0;
      background:
        linear-gradient(180deg, rgba(255, 255, 255, 0.82), rgba(244, 246, 248, 0.98)),
        var(--bg);
      color: var(--ink);
      font-family: var(--sans);
      font-size: 14px;
      line-height: 1.42;
    }

    button,
    input,
    select {
      font: inherit;
    }

    button {
      border: 1px solid var(--line-strong);
      background: var(--surface);
      color: var(--ink);
      cursor: pointer;
    }

    button,
    input,
    select {
      min-height: 34px;
      border-radius: 7px;
    }

    input,
    select {
      width: 100%;
      min-width: 0;
      border: 1px solid var(--line-strong);
      background: var(--surface);
      color: var(--ink);
      padding: 0 10px;
      outline: none;
    }

    button:disabled,
    input:disabled,
    select:disabled {
      cursor: not-allowed;
      opacity: 0.58;
    }

    input:focus,
    select:focus,
    button:focus-visible {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px var(--accent-soft);
      outline: none;
    }

    .app-shell {
      min-height: 100svh;
      display: grid;
      grid-template-rows: auto 1fr;
    }

    .topbar {
      position: sticky;
      top: 0;
      z-index: 20;
      display: grid;
      grid-template-columns: minmax(220px, 300px) minmax(160px, 1fr) minmax(360px, 560px);
      gap: 16px;
      align-items: center;
      min-height: 68px;
      padding: 12px 18px;
      border-bottom: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.92);
      backdrop-filter: blur(14px);
    }

    .brand {
      display: grid;
      grid-template-columns: 34px minmax(0, 1fr);
      gap: 10px;
      align-items: center;
      min-width: 0;
    }

    .brand-mark {
      display: grid;
      width: 34px;
      height: 34px;
      place-items: center;
      border: 1px solid #87c4bd;
      border-radius: 8px;
      background: #e4f5f2;
      color: #064e49;
      font-weight: 800;
    }

    .brand strong,
    .section-title strong {
      display: block;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 15px;
      font-weight: 750;
      letter-spacing: 0;
    }

    .brand span,
    .muted,
    .status-line,
    .meta {
      color: var(--muted);
    }

    .brand span,
    .status-line,
    .meta {
      font-size: 12px;
    }

    .status-chip {
      justify-self: start;
      display: inline-flex;
      align-items: center;
      max-width: 100%;
      min-height: 30px;
      gap: 8px;
      padding: 4px 10px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--surface-raised);
    }

    .status-dot {
      width: 7px;
      height: 7px;
      flex: 0 0 auto;
      border-radius: 999px;
      background: var(--faint);
    }

    .status-chip[data-state="ready"] .status-dot {
      background: var(--green);
    }

    .status-chip[data-state="busy"] .status-dot {
      background: var(--blue);
      animation: pulse 1.2s ease-in-out infinite;
    }

    .status-chip[data-state="error"] {
      border-color: #efb5ad;
      background: #fff4f2;
      color: var(--red);
    }

    .status-chip[data-state="error"] .status-dot {
      background: var(--red);
    }

    .command-bar {
      display: grid;
      grid-template-columns: minmax(150px, 1fr) auto auto auto;
      gap: 8px;
      align-items: center;
    }

    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 7px;
      min-width: 0;
      padding: 0 11px;
      font-weight: 650;
      transition:
        background 140ms ease,
        border-color 140ms ease,
        color 140ms ease,
        transform 140ms ease;
    }

    .btn:hover {
      background: var(--surface-quiet);
    }

    .btn:active {
      transform: translateY(1px);
    }

    .btn-primary {
      border-color: var(--accent);
      background: var(--accent);
      color: #ffffff;
    }

    .btn-primary:hover {
      background: var(--accent-strong);
    }

    .workspace {
      display: grid;
      grid-template-columns: minmax(280px, 340px) minmax(0, 1fr) minmax(320px, 390px);
      min-height: 0;
      padding: 14px;
      gap: 14px;
    }

    .pane {
      min-width: 0;
      min-height: 0;
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: rgba(255, 255, 255, 0.86);
      box-shadow: var(--shadow);
    }

    .pane-inner {
      display: grid;
      grid-template-rows: auto 1fr;
      height: 100%;
      min-height: 0;
    }

    .pane-header {
      display: grid;
      gap: 10px;
      padding: 14px;
      border-bottom: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.94);
    }

    .section-title {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: start;
      min-width: 0;
    }

    .section-title span {
      display: block;
      margin-top: 2px;
      color: var(--muted);
      font-size: 12px;
    }

    .sidebar-controls {
      display: grid;
      grid-template-columns: 1fr minmax(118px, 0.7fr);
      gap: 8px;
    }

    .scroll-area {
      min-height: 0;
      overflow: auto;
    }

    .run-list,
    .timeline-list,
    .evidence-list {
      display: grid;
    }

    .run-row {
      display: grid;
      width: 100%;
      height: auto;
      min-height: 82px;
      gap: 9px;
      padding: 13px 14px;
      border-width: 0 0 1px;
      border-color: var(--line);
      border-radius: 0;
      background: transparent;
      text-align: left;
    }

    .run-row:hover,
    .run-row[aria-current="true"] {
      background: #f3f8f7;
    }

    .run-row[aria-current="true"] {
      box-shadow: inset 3px 0 0 var(--accent);
    }

    .run-row-top,
    .event-row-top,
    .detail-title,
    .id-line,
    .split-line {
      display: flex;
      gap: 8px;
      align-items: center;
      min-width: 0;
    }

    .split-line {
      justify-content: space-between;
    }

    .truncate {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .mono,
    .meta,
    pre {
      font-family: var(--mono);
    }

    .badge {
      display: inline-flex;
      align-items: center;
      flex: 0 0 auto;
      min-height: 22px;
      padding: 2px 7px;
      border: 1px solid var(--line-strong);
      border-radius: 999px;
      background: var(--surface);
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
    }

    .badge.running,
    .badge.succeeded,
    .badge.pass {
      border-color: #8fd0bd;
      background: #eaf8f2;
      color: var(--green);
    }

    .badge.canceled,
    .badge.warn {
      border-color: #efd07a;
      background: #fff8e6;
      color: var(--amber);
    }

    .badge.failed,
    .badge.fail,
    .badge.error {
      border-color: #efb5ad;
      background: #fff4f2;
      color: var(--red);
    }

    .badge.model-call {
      border-color: #b9c7ff;
      background: #eef2ff;
      color: var(--blue);
    }

    .badge.tool-call,
    .badge.rag-retrieval {
      border-color: #b8c7ee;
      background: #f1f4ff;
      color: #4154a8;
    }

    .badge.evaluation {
      border-color: #cec3ff;
      background: #f4f1ff;
      color: var(--violet);
    }

    .detail {
      display: grid;
      grid-template-rows: auto auto auto 1fr;
      min-height: 0;
      overflow: hidden;
    }

    .detail-header {
      display: grid;
      gap: 12px;
      padding: 16px 18px;
      border-bottom: 1px solid var(--line);
      background:
        linear-gradient(135deg, rgba(15, 118, 110, 0.08), rgba(255, 255, 255, 0) 42%),
        var(--surface);
    }

    .detail-title h1 {
      margin: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 20px;
      letter-spacing: 0;
    }

    .header-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }

    .metrics {
      display: grid;
      grid-template-columns: repeat(8, minmax(86px, 1fr));
      border-bottom: 1px solid var(--line);
      background: var(--surface);
    }

    .metric {
      min-width: 0;
      padding: 11px 12px;
      border-right: 1px solid var(--line);
    }

    .metric:last-child {
      border-right: 0;
    }

    .metric span {
      display: block;
      overflow: hidden;
      color: var(--muted);
      font-size: 11px;
      font-weight: 650;
      text-overflow: ellipsis;
      text-transform: uppercase;
      white-space: nowrap;
    }

    .metric strong {
      display: block;
      margin-top: 3px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 19px;
      letter-spacing: 0;
    }

    .timeline-toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 7px;
      align-items: center;
      padding: 10px 14px;
      border-bottom: 1px solid var(--line);
      background: rgba(251, 252, 253, 0.96);
    }

    .tab {
      min-height: 30px;
      padding: 0 9px;
      border-radius: 999px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 750;
    }

    .tab[aria-pressed="true"] {
      border-color: #7fc4bc;
      background: var(--accent-soft);
      color: #064e49;
    }

    .timeline-list {
      min-height: 0;
      overflow: auto;
      background: var(--surface-raised);
    }

    .event-row {
      display: grid;
      grid-template-columns: 78px minmax(0, 1fr);
      width: 100%;
      min-height: 74px;
      gap: 12px;
      padding: 13px 15px;
      border-width: 0 0 1px;
      border-color: var(--line);
      border-radius: 0;
      background: var(--surface);
      text-align: left;
    }

    .event-row:hover,
    .event-row[aria-current="true"] {
      background: #f7fafc;
    }

    .event-row[aria-current="true"] {
      box-shadow: inset 3px 0 0 var(--accent);
    }

    .sequence {
      display: grid;
      gap: 3px;
      align-content: start;
      color: var(--muted);
      font-size: 12px;
    }

    .event-dot {
      width: 9px;
      height: 9px;
      border-radius: 999px;
      background: var(--line-strong);
    }

    .event-dot.message {
      background: var(--accent);
    }

    .event-dot.model_call {
      background: var(--blue);
    }

    .event-dot.tool_call,
    .event-dot.rag_retrieval {
      background: #4154a8;
    }

    .event-dot.evaluation {
      background: var(--violet);
    }

    .event-dot.error {
      background: var(--red);
    }

    .preview {
      display: -webkit-box;
      overflow: hidden;
      margin-top: 5px;
      color: #405063;
      font-family: var(--mono);
      font-size: 12px;
      -webkit-box-orient: vertical;
      -webkit-line-clamp: 2;
      word-break: break-word;
    }

    .inspector {
      display: grid;
      grid-template-rows: auto 1fr;
      min-height: 0;
    }

    .inspector-body {
      min-height: 0;
      overflow: auto;
    }

    .panel-section {
      display: grid;
      gap: 8px;
      padding: 14px;
      border-bottom: 1px solid var(--line);
      background: var(--surface);
    }

    .panel-section h3 {
      margin: 0;
      font-size: 13px;
      letter-spacing: 0;
    }

    .panel-section p {
      margin: 0;
      color: var(--muted);
      font-size: 12px;
    }

    pre {
      max-height: 360px;
      margin: 0;
      padding: 11px;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #f7f9fb;
      color: #223140;
      font-size: 12px;
      line-height: 1.45;
      white-space: pre-wrap;
      word-break: break-word;
    }

    .empty-state {
      display: grid;
      gap: 8px;
      padding: 24px 18px;
      color: var(--muted);
    }

    .empty-state strong {
      color: var(--ink);
      font-size: 14px;
    }

    .sr-only {
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    }

    @keyframes pulse {
      0%,
      100% {
        opacity: 0.45;
      }
      50% {
        opacity: 1;
      }
    }

    @media (prefers-reduced-motion: reduce) {
      *,
      *::before,
      *::after {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        scroll-behavior: auto !important;
        transition-duration: 0.01ms !important;
      }
    }

    @media (max-width: 1180px) {
      .workspace {
        grid-template-columns: minmax(260px, 320px) minmax(0, 1fr);
      }

      .inspector-pane {
        grid-column: 1 / -1;
        min-height: 360px;
      }

      .metrics {
        grid-template-columns: repeat(4, minmax(96px, 1fr));
      }
    }

    @media (max-width: 760px) {
      .topbar {
        position: static;
        grid-template-columns: 1fr;
      }

      .command-bar {
        grid-template-columns: 1fr auto;
      }

      .workspace {
        grid-template-columns: 1fr;
        padding: 10px;
      }

      .runs-pane {
        max-height: 42svh;
      }

      .metrics {
        grid-template-columns: repeat(2, minmax(110px, 1fr));
      }

      .event-row {
        grid-template-columns: 58px minmax(0, 1fr);
      }
    }
  </style>
</head>
<body>
  <div class="app-shell">
    <header class="topbar">
      <div class="brand" aria-label="AgentOps Trace Viewer">
        <div class="brand-mark" aria-hidden="true">A</div>
        <div>
          <strong>AgentOps Trace Viewer</strong>
          <span>Observe LangGraph and RAG agent runs</span>
        </div>
      </div>
      <div id="statusChip" class="status-chip" data-state="idle">
        <span class="status-dot" aria-hidden="true"></span>
        <span id="status" class="status-line" role="status">Enter an API key to load runs.</span>
      </div>
      <div class="command-bar" aria-label="Viewer commands">
        <label class="sr-only" for="apiKey">API key</label>
        <input id="apiKey" type="password" autocomplete="off" placeholder="X-AgentOps-API-Key">
        <button id="toggleKey" class="btn" type="button">Show</button>
        <button id="connect" class="btn btn-primary" type="button">Load</button>
        <button id="reload" class="btn" type="button">Refresh</button>
      </div>
    </header>
    <main class="workspace">
      <section class="pane runs-pane" aria-label="Runs">
        <div class="pane-inner">
          <div class="pane-header">
            <div class="section-title">
              <div>
                <strong>Runs</strong>
                <span id="runCount">No project loaded</span>
              </div>
              <button id="clearKey" class="btn" type="button">Clear key</button>
            </div>
            <div class="sidebar-controls">
              <input id="runSearch" type="search" placeholder="Search runs" aria-label="Search runs">
              <select id="statusFilter" aria-label="Run status filter">
                <option value="">All statuses</option>
                <option value="running">Running</option>
                <option value="succeeded">Succeeded</option>
                <option value="failed">Failed</option>
                <option value="canceled">Canceled</option>
              </select>
            </div>
          </div>
          <div class="scroll-area">
            <div id="runList" class="run-list">
              <div class="empty-state">
                <strong>No runs loaded</strong>
                <span>Load a project key to inspect recent agent traces.</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section class="pane" aria-label="Run detail">
        <div class="detail">
          <div id="detailHeader" class="detail-header">
            <div class="detail-title">
              <h1>Select a run</h1>
            </div>
            <div class="split-line">
              <span class="meta">Authenticated data is fetched through /v1 APIs.</span>
            </div>
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
          <div id="timeline" class="timeline-list">
            <div class="empty-state">
              <strong>No timeline selected</strong>
              <span>Select a run to inspect events, tokens, latency, and failures.</span>
            </div>
          </div>
        </div>
      </section>

      <aside class="pane inspector-pane" aria-label="Evidence Inspector">
        <div class="inspector">
          <div class="pane-header">
            <div class="section-title">
              <div>
                <strong>Evidence Inspector</strong>
                <span>Selected event and quality evidence</span>
              </div>
            </div>
          </div>
          <div id="inspector" class="inspector-body">
            <div class="empty-state">
              <strong>No event selected</strong>
              <span>Select a timeline row to inspect its full payload.</span>
            </div>
          </div>
        </div>
      </aside>
    </main>
  </div>

  <script>
    const EVENT_TYPES = [
      "message",
      "model_call",
      "tool_call",
      "rag_retrieval",
      "evaluation",
      "error",
      "custom",
    ];

    const state = {
      runs: [],
      selectedRunId: null,
      selectedEventId: null,
      detail: null,
      filter: "all",
      busy: false,
    };

    const nodes = {
      apiKey: document.querySelector("#apiKey"),
      clearKey: document.querySelector("#clearKey"),
      connect: document.querySelector("#connect"),
      detailHeader: document.querySelector("#detailHeader"),
      inspector: document.querySelector("#inspector"),
      metrics: document.querySelector("#metrics"),
      reload: document.querySelector("#reload"),
      runCount: document.querySelector("#runCount"),
      runList: document.querySelector("#runList"),
      runSearch: document.querySelector("#runSearch"),
      status: document.querySelector("#status"),
      statusChip: document.querySelector("#statusChip"),
      statusFilter: document.querySelector("#statusFilter"),
      tabs: Array.from(document.querySelectorAll(".tab")),
      timeline: document.querySelector("#timeline"),
      toggleKey: document.querySelector("#toggleKey"),
    };

    nodes.apiKey.value = sessionStorage.getItem("agentops_api_key") || "";

    function setBusy(isBusy) {
      state.busy = isBusy;
      nodes.connect.disabled = isBusy;
      nodes.reload.disabled = isBusy;
      nodes.statusFilter.disabled = isBusy;
    }

    function setStatus(message, mode = "idle") {
      nodes.status.textContent = message;
      nodes.statusChip.dataset.state = mode;
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
        setBusy(true);
        sessionStorage.setItem("agentops_api_key", getApiKey());
        setStatus("Loading runs...", "busy");
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
          state.selectedEventId = null;
          state.detail = null;
          renderEmptyDetail();
        }
        setStatus(`Loaded ${state.runs.length} runs.`, "ready");
      } catch (error) {
        setStatus(error.message, "error");
      } finally {
        setBusy(false);
      }
    }

    async function selectRun(runId) {
      state.selectedRunId = runId;
      state.selectedEventId = null;
      renderRuns();
      setStatus("Loading run detail...", "busy");
      state.detail = await apiGet(`/v1/runs/${encodeURIComponent(runId)}/detail`);
      renderDetail();
      setStatus(`Loaded run ${runId}.`, "ready");
    }

    function renderRuns() {
      nodes.runList.replaceChildren();
      const filtered = filteredRuns();
      nodes.runCount.textContent = `${filtered.length} visible of ${state.runs.length} loaded`;
      if (filtered.length === 0) {
        nodes.runList.append(emptyState("No matching runs", "Adjust search or status filters."));
        return;
      }
      for (const run of filtered) {
        const row = document.createElement("button");
        row.type = "button";
        row.className = "run-row";
        row.setAttribute("aria-current", String(run.id === state.selectedRunId));
        row.addEventListener("click", () => {
          selectRun(run.id).catch((error) => setStatus(error.message, "error"));
        });

        const top = div("run-row-top", [
          badge(run.status),
          span(run.name || "Untitled run", "truncate"),
        ]);
        const meta = div("meta truncate", [
          `${formatTime(run.started_at)} ${run.session_id || run.project_id}`,
        ]);
        const id = div("meta truncate", [run.id]);
        row.append(top, meta, id);
        nodes.runList.append(row);
      }
    }

    function filteredRuns() {
      const query = nodes.runSearch.value.trim().toLowerCase();
      if (!query) {
        return state.runs;
      }
      return state.runs.filter((run) => {
        const haystack = [
          run.id,
          run.name,
          run.session_id,
          run.project_id,
          run.status,
        ].filter(Boolean).join(" ").toLowerCase();
        return haystack.includes(query);
      });
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
        div("split-line", [
          div("id-line meta truncate", [run.id]),
          div("header-actions", [
            smallButton("Copy run ID", () => copyText(run.id)),
            smallButton("Refresh detail", () => selectRun(run.id)),
          ]),
        ]),
      );
      nodes.metrics.replaceChildren(
        metric("Events", summary.event_count),
        metric("Tokens", summary.total_tokens),
        metric("Latency", `${summary.total_latency_ms}ms`),
        metric("Errors", summary.error_count),
        metric("Tools", summary.tool_call_count),
        metric("RAG", summary.rag_retrieval_count),
        metric("Eval", summary.evaluation_count),
        metric("Models", summary.model_call_count),
      );
      updateTabCounts();
      renderTimeline();
      renderInspector();
    }

    function renderEmptyDetail() {
      nodes.detailHeader.replaceChildren(
        div("detail-title", [heading("Select a run")]),
        div("split-line", [span("Authenticated data is fetched through /v1 APIs.", "meta")]),
      );
      nodes.metrics.replaceChildren();
      nodes.timeline.replaceChildren(
        emptyState("No timeline selected", "Select a run to inspect events, tokens, latency, and failures."),
      );
      nodes.inspector.replaceChildren(
        emptyState("No event selected", "Select a timeline row to inspect its full payload."),
      );
      updateTabCounts();
    }

    function updateTabCounts() {
      const counts = Object.fromEntries(EVENT_TYPES.map((type) => [type, 0]));
      if (state.detail) {
        for (const event of state.detail.timeline) {
          counts[event.type] = (counts[event.type] || 0) + 1;
        }
      }
      for (const tab of nodes.tabs) {
        const filter = tab.dataset.filter;
        const label = tab.dataset.label || tab.textContent.split(" ")[0];
        tab.dataset.label = label;
        const count = filter === "all" && state.detail
          ? state.detail.timeline.length
          : (counts[filter] || 0);
        tab.textContent = `${label} ${count}`;
      }
    }

    function renderTimeline() {
      nodes.timeline.replaceChildren();
      const events = visibleEvents();
      if (events.length === 0) {
        nodes.timeline.append(emptyState("No events match this filter", "Try another event type."));
        return;
      }
      if (!state.selectedEventId || !events.some((event) => event.id === state.selectedEventId)) {
        state.selectedEventId = events[0].id;
      }
      for (const event of events) {
        const row = document.createElement("button");
        row.type = "button";
        row.className = "event-row";
        row.setAttribute("aria-current", String(event.id === state.selectedEventId));
        row.addEventListener("click", () => {
          state.selectedEventId = event.id;
          renderTimeline();
          renderInspector();
        });
        row.append(div("sequence mono", [eventDot(event.type), `#${event.sequence}`]), eventBody(event));
        nodes.timeline.append(row);
      }
    }

    function visibleEvents() {
      if (!state.detail) {
        return [];
      }
      return state.detail.timeline.filter((event) => {
        return state.filter === "all" || event.type === state.filter;
      });
    }

    function renderInspector() {
      nodes.inspector.replaceChildren();
      if (!state.detail) {
        nodes.inspector.append(emptyState("No event selected", "Select a timeline row to inspect its full payload."));
        return;
      }
      const selected = state.detail.timeline.find((event) => event.id === state.selectedEventId);
      if (selected) {
        nodes.inspector.append(inspectorSection(
          "Selected event",
          `${selected.type} / ${selected.name || "unnamed"} / #${selected.sequence}`,
          selected.payload,
        ));
      }
      addEvidenceGroup("RAG evidence", state.detail.rag_evidence);
      addEvidenceGroup("Evaluations", state.detail.evaluations);
      addEvidenceGroup("Errors", state.detail.errors);
      if (!selected && nodes.inspector.children.length === 0) {
        nodes.inspector.append(emptyState("No evidence in this page", "Recent timeline data has no RAG, evaluation, or error events."));
      }
    }

    function addEvidenceGroup(title, events) {
      for (const event of events) {
        nodes.inspector.append(inspectorSection(title, event.name || event.type, event.payload));
      }
    }

    function eventBody(event) {
      return div("", [
        div("event-row-top", [
          badge(event.type),
          span(event.name || event.type, "truncate"),
        ]),
        div("split-line", [
          span(formatTime(event.timestamp), "meta"),
          span(extractVerdict(event.payload), "meta"),
        ]),
        div("preview", [payloadPreview(event.payload)]),
      ]);
    }

    function inspectorSection(title, subtitle, payload) {
      const section = document.createElement("section");
      section.className = "panel-section";
      section.append(heading3(title), paragraph(subtitle), payloadBlock(payload));
      return section;
    }

    function badge(value) {
      const item = document.createElement("span");
      item.className = `badge ${String(value).replaceAll("_", "-")}`;
      item.textContent = value;
      return item;
    }

    function eventDot(type) {
      const dot = document.createElement("span");
      dot.className = `event-dot ${type}`;
      dot.setAttribute("aria-hidden", "true");
      return dot;
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

    function payloadPreview(payload) {
      const preferred = payload.message || payload.content || payload.answer || payload.query || payload.tool_name;
      if (typeof preferred === "string") {
        return preferred;
      }
      return JSON.stringify(payload);
    }

    function extractVerdict(payload) {
      if (payload.verdict) {
        return `verdict: ${payload.verdict}`;
      }
      if (payload.hit_status) {
        return `retrieval: ${payload.hit_status}`;
      }
      if (payload.latency_ms) {
        return `${payload.latency_ms}ms`;
      }
      return "";
    }

    function emptyState(title, message) {
      return div("empty-state", [strong(title), span(message)]);
    }

    function smallButton(text, action) {
      const button = document.createElement("button");
      button.className = "btn";
      button.type = "button";
      button.textContent = text;
      button.addEventListener("click", () => {
        Promise.resolve(action()).catch((error) => setStatus(error.message, "error"));
      });
      return button;
    }

    async function copyText(value) {
      await navigator.clipboard.writeText(value);
      setStatus("Copied run ID.", "ready");
    }

    function heading(text) {
      const node = document.createElement("h1");
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

    function strong(text) {
      const node = document.createElement("strong");
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
    nodes.runSearch.addEventListener("input", () => {
      renderRuns();
    });
    nodes.toggleKey.addEventListener("click", () => {
      const showing = nodes.apiKey.type === "text";
      nodes.apiKey.type = showing ? "password" : "text";
      nodes.toggleKey.textContent = showing ? "Show" : "Hide";
    });
    nodes.clearKey.addEventListener("click", () => {
      nodes.apiKey.value = "";
      sessionStorage.removeItem("agentops_api_key");
      state.runs = [];
      state.detail = null;
      state.selectedRunId = null;
      state.selectedEventId = null;
      renderRuns();
      renderEmptyDetail();
      setStatus("API key cleared for this browser session.", "idle");
    });
    for (const tab of nodes.tabs) {
      tab.dataset.label = tab.textContent;
      tab.addEventListener("click", () => {
        state.filter = tab.dataset.filter;
        for (const item of nodes.tabs) {
          item.setAttribute("aria-pressed", String(item === tab));
        }
        renderTimeline();
        renderInspector();
      });
    }
  </script>
</body>
</html>
"""


@router.get("/viewer", response_class=HTMLResponse)
def trace_viewer() -> HTMLResponse:
    return HTMLResponse(TRACE_VIEWER_HTML)
