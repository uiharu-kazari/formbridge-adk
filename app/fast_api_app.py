# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import contextlib
import os
from collections.abc import AsyncIterator

import google.auth
from a2a.server.tasks import InMemoryTaskStore
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from google.adk.cli.fast_api import get_fast_api_app
from google.adk.runners import Runner
from google.cloud import logging as google_cloud_logging

from app.app_utils import services
from app.app_utils.a2a import attach_a2a_routes
from app.app_utils.telemetry import setup_telemetry
from app.app_utils.typing import Feedback

load_dotenv()
setup_telemetry()
_, project_id = google.auth.default()
logging_client = google_cloud_logging.Client()
logger = logging_client.logger(__name__)
allow_origins = (
    os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else None
)

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    from app.agent import app as adk_app
    from app.agent import root_agent

    runner = Runner(
        app=adk_app,
        session_service=services.get_session_service(),
        artifact_service=services.get_artifact_service(),
        auto_create_session=True,
    )
    app.state.runner = runner
    app.state.agent_app_name = adk_app.name
    await attach_a2a_routes(
        app,
        agent=root_agent,
        runner=runner,
        task_store=InMemoryTaskStore(),
        rpc_path=f"/a2a/{adk_app.name}",
    )
    yield


app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    web=True,
    artifact_service_uri=services.ARTIFACT_SERVICE_URI,
    allow_origins=allow_origins,
    session_service_uri=services.SESSION_SERVICE_URI,
    otel_to_cloud=False,
    lifespan=lifespan,
)
app.title = "formbridge-adk"
app.description = "API for interacting with the Agent formbridge-adk"


@app.post("/feedback")
def collect_feedback(feedback: Feedback) -> dict[str, str]:
    """Collect and log feedback.

    Args:
        feedback: The feedback data to log

    Returns:
        Success message
    """
    logger.log_struct(feedback.model_dump(), severity="INFO")
    return {"status": "success"}


@app.get("/demo", response_class=HTMLResponse)
def demo() -> str:
    """Serve a small user-facing demo UI for the capstone writeup.

    The page calls the existing same-origin ADK session and ``/run_sse`` routes.
    It does not add any new agent capability; it is only a cleaner browser
    wrapper around the deployed FormBridge agent.
    """

    return """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>FormBridge Demo</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f5f7fb;
      --card: #ffffff;
      --ink: #172033;
      --muted: #5d6b82;
      --line: #d8e0ec;
      --brand: #1d4ed8;
      --brand-2: #059669;
      --danger: #b42318;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at 15% 10%, rgba(29, 78, 216, .16), transparent 30%),
        radial-gradient(circle at 85% 0%, rgba(5, 150, 105, .13), transparent 32%),
        var(--bg);
      color: var(--ink);
    }
    main {
      width: min(1120px, calc(100vw - 40px));
      margin: 34px auto;
    }
    .hero {
      display: grid;
      grid-template-columns: 1.05fr .95fr;
      gap: 22px;
      align-items: stretch;
    }
    .panel {
      background: rgba(255,255,255,.92);
      border: 1px solid var(--line);
      border-radius: 22px;
      box-shadow: 0 22px 60px rgba(23, 32, 51, .09);
      padding: 28px;
    }
    .eyebrow {
      color: var(--brand);
      font-size: 12px;
      font-weight: 800;
      letter-spacing: .16em;
      text-transform: uppercase;
    }
    h1 {
      margin: 12px 0 14px;
      font-size: clamp(42px, 6vw, 68px);
      line-height: .94;
      letter-spacing: -.055em;
    }
    .subtitle {
      margin: 0;
      color: var(--muted);
      font-size: 19px;
      line-height: 1.5;
    }
    .badges {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 22px;
    }
    .badge {
      border: 1px solid #bfd0ea;
      border-radius: 999px;
      padding: 8px 12px;
      background: #f4f8ff;
      color: #244061;
      font-size: 13px;
      font-weight: 700;
    }
    .packet h2, .chat h2 {
      margin: 0 0 12px;
      font-size: 18px;
    }
    .packet ul {
      margin: 0;
      padding-left: 20px;
      color: var(--muted);
      line-height: 1.72;
    }
    .chat {
      margin-top: 22px;
      display: grid;
      grid-template-columns: 370px 1fr;
      gap: 22px;
    }
    label {
      display: block;
      margin: 16px 0 7px;
      color: #314159;
      font-size: 14px;
      font-weight: 800;
    }
    select, textarea {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 14px;
      background: #fff;
      color: var(--ink);
      font: inherit;
      padding: 13px 14px;
      outline: none;
    }
    textarea { min-height: 160px; resize: vertical; line-height: 1.45; }
    button {
      width: 100%;
      margin-top: 16px;
      border: 0;
      border-radius: 14px;
      padding: 14px 16px;
      background: linear-gradient(135deg, var(--brand), var(--brand-2));
      color: white;
      font-weight: 800;
      font-size: 15px;
      cursor: pointer;
    }
    button[disabled] { opacity: .62; cursor: wait; }
    .note {
      margin-top: 14px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
    }
    .output {
      min-height: 480px;
      max-height: 620px;
      overflow: auto;
      background: #0b1220;
      color: #e5edf7;
      border-radius: 18px;
      padding: 22px;
      white-space: pre-wrap;
      font: 14px/1.55 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      border: 1px solid #1e2d45;
    }
    .status {
      min-height: 22px;
      margin: 0 0 10px;
      color: var(--muted);
      font-weight: 700;
    }
    .error { color: var(--danger); }
    @media (max-width: 900px) {
      .hero, .chat { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <div class="panel">
        <div class="eyebrow">Agents for Good · Google ADK</div>
        <h1>FormBridge</h1>
        <p class="subtitle">
          A proof-carrying public-benefit form copilot. It fills only cited facts,
          flags conflicts, redacts sensitive identifiers, resists prompt injection,
          and stops at human review.
        </p>
        <div class="badges">
          <span class="badge">Exact citations</span>
          <span class="badge">Conflict detection</span>
          <span class="badge">PII redaction</span>
          <span class="badge">No eligibility decision</span>
        </div>
      </div>
      <div class="panel packet">
        <h2>Demo packet behavior</h2>
        <ul>
          <li>Loads a synthetic case, never real applicant data.</li>
          <li>Separates privacy, form, evidence, policy, skeptic, revision, and validation roles.</li>
          <li>Keeps contradictory or missing values unresolved.</li>
          <li>Produces a validation receipt and a human-review gate.</li>
        </ul>
      </div>
    </section>

    <section class="chat">
      <div class="panel">
        <h2>Run the agent</h2>
        <label for="case">Synthetic case</label>
        <select id="case">
          <option value="harbor-family">harbor-family: conflict + prompt injection</option>
          <option value="cedar-senior">cedar-senior: senior benefits packet</option>
        </select>
        <label for="prompt">Request</label>
        <textarea id="prompt">Review demo case harbor-family. Produce the proof-carrying draft, flag any conflicts or prompt injection, ask only minimum clarification questions, and do not decide eligibility or submit anything.</textarea>
        <button id="run">Run FormBridge</button>
        <p class="note">
          This page calls the same deployed ADK <code>/run_sse</code> endpoint.
          Long responses may take 30–90 seconds on a cold start.
        </p>
      </div>
      <div class="panel">
        <p id="status" class="status">Ready.</p>
        <div id="output" class="output">The proof-carrying draft will appear here.</div>
      </div>
    </section>
  </main>

  <script>
    const caseSelect = document.querySelector("#case");
    const promptBox = document.querySelector("#prompt");
    const runButton = document.querySelector("#run");
    const output = document.querySelector("#output");
    const status = document.querySelector("#status");

    caseSelect.addEventListener("change", () => {
      const caseId = caseSelect.value;
      promptBox.value = `Review demo case ${caseId}. Produce the proof-carrying draft, flag any conflicts or prompt injection, ask only minimum clarification questions, and do not decide eligibility or submit anything.`;
    });

    async function runDemo() {
      runButton.disabled = true;
      output.textContent = "";
      status.className = "status";
      status.textContent = "Creating ADK session...";
      const userId = "demo_" + crypto.randomUUID();
      try {
        const sessionResponse = await fetch(`/apps/app/users/${userId}/sessions`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ state: { surface: "formbridge-demo" } })
        });
        if (!sessionResponse.ok) {
          throw new Error(`Session request failed: ${sessionResponse.status}`);
        }
        const session = await sessionResponse.json();
        status.textContent = "Streaming multi-agent review...";
        const runResponse = await fetch("/run_sse", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            app_name: "app",
            user_id: userId,
            session_id: session.id,
            new_message: {
              role: "user",
              parts: [{ text: promptBox.value }]
            },
            streaming: true
          })
        });
        if (!runResponse.ok || !runResponse.body) {
          throw new Error(`Run request failed: ${runResponse.status}`);
        }
        const reader = runResponse.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let finalText = "";
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\\n");
          buffer = lines.pop() || "";
          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const event = JSON.parse(line.slice(6));
            const parts = event?.content?.parts || [];
            for (const part of parts) {
              if (part.text) {
                finalText += part.text;
                output.textContent = finalText;
                output.scrollTop = output.scrollHeight;
              }
            }
          }
        }
        status.textContent = "Complete. Human review still required.";
      } catch (error) {
        status.className = "status error";
        status.textContent = String(error.message || error);
      } finally {
        runButton.disabled = false;
      }
    }

    runButton.addEventListener("click", runDemo);
  </script>
</body>
</html>
    """


# Main execution
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
