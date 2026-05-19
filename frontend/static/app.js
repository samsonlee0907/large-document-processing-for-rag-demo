const state = {
  documents: [],
  selectedDocId: null,
  debugVisible: false,
  chatMessages: [],
  chatCorpusMode: "auto",
  selectedCorpusDocIds: [],
};

async function fetchJson(url, options = {}) {
  const timeoutMs = options.timeoutMs || 30000;
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  let response;
  try {
    response = await fetch(url, { ...options, signal: controller.signal });
  } finally {
    window.clearTimeout(timeoutId);
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || "Request failed");
  }
  return response.json();
}

function $(selector) {
  return document.querySelector(selector);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderInlineMarkdown(text) {
  return escapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
}

function renderMarkdown(text) {
  const lines = String(text || "").replace(/\r\n/g, "\n").split("\n");
  const blocks = [];
  let listMode = null;
  let listItems = [];
  let paragraph = [];
  let inCodeBlock = false;
  let codeLines = [];

  function flushParagraph() {
    if (!paragraph.length) return;
    blocks.push(`<p>${renderInlineMarkdown(paragraph.join(" "))}</p>`);
    paragraph = [];
  }

  function flushList() {
    if (!listMode || !listItems.length) return;
    const items = listItems.map((item) => `<li>${renderInlineMarkdown(item)}</li>`).join("");
    blocks.push(listMode === "ol" ? `<ol>${items}</ol>` : `<ul>${items}</ul>`);
    listMode = null;
    listItems = [];
  }

  function flushCodeBlock() {
    if (!codeLines.length) return;
    blocks.push(`<pre class="message-code"><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
    codeLines = [];
  }

  for (const rawLine of lines) {
    const line = rawLine.trim();
    const headingMatch = line.match(/^(#{1,6})\s+(.*)$/);
    const unorderedMatch = line.match(/^[-*]\s+(.*)$/);
    const orderedMatch = line.match(/^\d+\.\s+(.*)$/);
    const fenceMatch = line.match(/^```/);

    if (fenceMatch) {
      flushParagraph();
      flushList();
      if (inCodeBlock) {
        flushCodeBlock();
        inCodeBlock = false;
      } else {
        inCodeBlock = true;
      }
      continue;
    }

    if (inCodeBlock) {
      codeLines.push(rawLine);
      continue;
    }

    if (!line) {
      flushParagraph();
      flushList();
      continue;
    }

    if (headingMatch) {
      flushParagraph();
      flushList();
      const level = Math.min(6, headingMatch[1].length);
      blocks.push(`<h${level} class="message-heading">${renderInlineMarkdown(headingMatch[2])}</h${level}>`);
      continue;
    }

    if (unorderedMatch) {
      flushParagraph();
      if (listMode !== "ul") {
        flushList();
        listMode = "ul";
      }
      listItems.push(unorderedMatch[1]);
      continue;
    }

    if (orderedMatch) {
      flushParagraph();
      if (listMode !== "ol") {
        flushList();
        listMode = "ol";
      }
      listItems.push(orderedMatch[1]);
      continue;
    }

    flushList();
    paragraph.push(line);
  }

  flushParagraph();
  flushList();
  flushCodeBlock();
  return blocks.join("") || `<p>${renderInlineMarkdown(text)}</p>`;
}

function setActiveScreen(screen) {
  document.querySelectorAll(".screen").forEach((node) => node.classList.remove("active"));
  document.querySelectorAll(".nav-link").forEach((node) => node.classList.remove("active"));
  $(`#screen-${screen}`).classList.add("active");
  document.querySelector(`.nav-link[data-screen="${screen}"]`).classList.add("active");
}

function stageLabel(value) {
  return value.replaceAll("_", " ");
}

function statusClass(status) {
  if (status === "failed") return "failed";
  if (status === "processing") return "processing";
  return "";
}

function setGenerationStatus(kind, message) {
  const banner = $("#generation-status");
  if (!banner) return;
  const labels = {
    running: "Generation Running",
    success: "Generation Queued",
    error: "Generation Failed",
  };
  banner.className = "operation-status";
  banner.classList.add(kind);
  banner.classList.remove("hidden");
  banner.innerHTML = `<strong>${labels[kind] || "Generation Status"}</strong><div>${escapeHtml(message)}</div>`;
}

function clearGenerationStatus() {
  const banner = $("#generation-status");
  if (!banner) return;
  banner.className = "operation-status hidden";
  banner.innerHTML = "";
}

function getReadyDocuments() {
  return state.documents.filter((doc) => doc.status === "ready");
}

function syncSelectedCorpusDocIds() {
  const readyIds = new Set(getReadyDocuments().map((doc) => doc.doc_id));
  state.selectedCorpusDocIds = state.selectedCorpusDocIds.filter((docId) => readyIds.has(docId));
  if (state.chatCorpusMode === "custom" && state.selectedCorpusDocIds.length === 0) {
    if (state.selectedDocId && readyIds.has(state.selectedDocId)) {
      state.selectedCorpusDocIds = [state.selectedDocId];
    } else {
      const firstReady = getReadyDocuments()[0];
      if (firstReady) {
        state.selectedCorpusDocIds = [firstReady.doc_id];
      }
    }
  }
}

function renderMetrics(payload) {
  const metrics = [
    ["Total Documents", payload.total_documents],
    ["Processing Queue", payload.processing_queue],
    ["Ready for Chat", payload.ready_for_chat],
    ["Failed Jobs", payload.failed_jobs],
  ];
  $("#metrics-grid").innerHTML = metrics
    .map(
      ([label, value]) => `
      <article class="metric">
        <p class="eyebrow">${label}</p>
        <p class="metric-value">${value}</p>
      </article>
    `
    )
    .join("");
  $("#recent-activity").innerHTML =
    payload.recent_activity.length === 0
      ? `<div class="muted">No activity yet.</div>`
      : payload.recent_activity
          .map(
            (item) => `
      <div class="table-row">
        <div>${item.file_name}</div>
        <div>${stageLabel(item.stage)}</div>
        <div>${new Date(item.updated_at).toLocaleString()}</div>
        <div>${item.doc_id.slice(0, 8)}</div>
      </div>
    `
          )
          .join("");
}

function renderDocuments() {
  $("#documents-list").innerHTML =
    state.documents.length === 0
      ? `<div class="muted">No submitted documents yet.</div>`
      : state.documents
          .map(
            (doc) => `
      <article class="doc-card">
        <div class="panel-head">
          <h4>${doc.file_name}</h4>
          <span class="status-pill ${statusClass(doc.status)}">${doc.status}</span>
        </div>
        <p class="muted small">Format: ${doc.format} · Parser: ${doc.parser_path}</p>
        <p class="muted small">Stage: ${stageLabel(doc.stage)}</p>
        <div class="progress-track"><div class="progress-fill" style="width:${doc.progress}%"></div></div>
        <p class="muted small">Chunks: ${doc.chunk_count || 0} · Sections: ${doc.section_count || 0}</p>
        <div class="upload-form">
          <button class="ghost" data-doc-detail="${doc.doc_id}">Inspect</button>
          <button class="ghost" data-doc-retry="${doc.doc_id}">Retry</button>
          <button class="ghost danger-ghost" data-doc-delete="${doc.doc_id}">Delete</button>
        </div>
      </article>
    `
          )
          .join("");

  document.querySelectorAll("[data-doc-detail]").forEach((button) =>
    button.addEventListener("click", () => loadDocumentDetail(button.dataset.docDetail))
  );
  document.querySelectorAll("[data-doc-retry]").forEach((button) =>
    button.addEventListener("click", async () => {
      await fetchJson(`/api/documents/${button.dataset.docRetry}/retry`, { method: "POST" });
      await refreshDocuments();
    })
  );
  document.querySelectorAll("[data-doc-delete]").forEach((button) =>
    button.addEventListener("click", async () => {
      await handleDeleteDocument(button.dataset.docDelete);
    })
  );
}

function renderDetail(doc) {
  const warnings = (doc.warnings || []).map((item) => `<li>${item}</li>`).join("");
  const errors = (doc.errors || []).map((item) => `<li>${item}</li>`).join("");
  const metadata = doc.intermediate?.metadata || {};
  const segmentSummary = metadata.segment_count
    ? `${metadata.segment_count} segment(s) via ${metadata.segmentation_strategy || "segmentation"}`
    : "N/A";
  const figureSummary = metadata.figure_count ? `${metadata.figure_count} extracted figure artifact(s)` : "N/A";
  const activity = (doc.activity || [])
    .slice()
    .reverse()
    .slice(0, 8)
    .map((item) => `<div><strong>${item.level}</strong> ${item.message}</div>`)
    .join("");

  $("#document-detail").innerHTML = `
    <h4>${doc.file_name}</h4>
    <div class="detail-grid">
      <div><strong>Detected Format</strong>${doc.format}</div>
      <div><strong>Complexity</strong>${doc.complexity}</div>
      <div><strong>Parser Path</strong>${doc.parser_path}</div>
      <div><strong>Page Count</strong>${doc.page_count || "N/A"}</div>
      <div><strong>Chunk Count</strong>${doc.chunk_count}</div>
      <div><strong>Segmentation</strong>${segmentSummary}</div>
      <div><strong>Figure Artifacts</strong>${figureSummary}</div>
      <div><strong>Publish Status</strong>${doc.publish_status.message}</div>
      <div><strong>Last Sync</strong>${doc.publish_status.last_sync_time || "N/A"}</div>
      <div><strong>Stored Path</strong>${doc.stored_path}</div>
    </div>
    <div>
      <strong>Warnings</strong>
      ${warnings ? `<ul>${warnings}</ul>` : `<div class="muted">None</div>`}
    </div>
    <div>
      <strong>Errors</strong>
      ${errors ? `<ul>${errors}</ul>` : `<div class="muted">None</div>`}
    </div>
    <div>
      <strong>Recent Activity</strong>
      <div class="table-like">${activity || `<div class="muted">No activity.</div>`}</div>
    </div>
  `;
}

async function loadDocumentDetail(docId) {
  state.selectedDocId = docId;
  const doc = await fetchJson(`/api/documents/${docId}`);
  renderDetail(doc);
}

async function refreshDocuments() {
  state.documents = await fetchJson("/api/documents");
  syncSelectedCorpusDocIds();
  renderDocuments();
  renderChatScopeControls();
  if (state.selectedDocId) {
    const exists = state.documents.some((item) => item.doc_id === state.selectedDocId);
    if (exists) {
      await loadDocumentDetail(state.selectedDocId);
    } else {
      state.selectedDocId = null;
      $("#document-detail").innerHTML = `<div class="detail-card muted">Select a document card to inspect the full pipeline state.</div>`;
    }
  }
}

async function refreshDashboard() {
  const payload = await fetchJson("/api/dashboard");
  renderMetrics(payload);
}

async function refreshKnowledge() {
  const payload = await fetchJson("/api/knowledge/status");
  $("#knowledge-status").innerHTML = `
    <div class="detail-grid">
      <div><strong>Knowledge Base</strong>${payload.selected_knowledge_base}</div>
      <div><strong>Mode</strong>${payload.status.mode}</div>
      <div><strong>Ready</strong>${payload.status.ready}</div>
      <div><strong>Resource</strong>${payload.status.resource}</div>
      <div><strong>Last Sync</strong>${payload.status.last_sync_time || "N/A"}</div>
      <div><strong>Message</strong>${payload.status.message}</div>
    </div>
  `;
  $("#knowledge-documents").innerHTML =
    payload.documents.length === 0
      ? `<div class="muted">No ready documents have been published yet.</div>`
      : payload.documents
          .map(
            (item) => `
        <div class="table-row corpus-row">
          <div>${item.file_name}</div>
          <div>${item.chunk_count}</div>
          <div>${item.section_count}</div>
          <div>${item.last_sync_time || "N/A"}</div>
          <div><button class="ghost danger-ghost" data-knowledge-delete="${item.doc_id}">Delete</button></div>
        </div>
      `
          )
          .join("");
  document.querySelectorAll("[data-knowledge-delete]").forEach((button) =>
    button.addEventListener("click", async () => {
      await handleDeleteDocument(button.dataset.knowledgeDelete);
    })
  );
  renderChatScopeControls();
}

async function refreshConfig() {
  const payload = await fetchJson("/api/config");
  $("#config-summary").innerHTML = `
    <div>Search: ${payload.azure_search_enabled ? "configured" : "local preview"}</div>
    <div>Agentic retrieval: ${payload.azure_agentic_retrieval_enabled ? "enabled" : "off"}</div>
    <div>Planning model: ${
      payload.azure_agentic_planning_model_enabled
        ? escapeHtml(payload.azure_agentic_planning_model || "configured")
        : "off"
    }</div>
    <div>Doc Intelligence: ${payload.azure_document_intelligence_enabled ? "configured" : "off"}</div>
    <div>Content Understanding: ${payload.azure_content_understanding_enabled ? "configured" : "off"}</div>
    <div>Blob image store: ${payload.azure_blob_storage_enabled ? "configured" : "off"}</div>
  `;
}

function renderChatScopeControls() {
  const readyDocs = getReadyDocuments();
  const autoButton = $("#chat-scope-auto");
  const customButton = $("#chat-scope-custom");
  const picker = $("#chat-corpus-picker");
  const summary = $("#chat-scope-summary");

  autoButton.classList.toggle("active", state.chatCorpusMode === "auto");
  customButton.classList.toggle("active", state.chatCorpusMode === "custom");

  if (!readyDocs.length) {
    picker.classList.add("hidden");
    picker.innerHTML = "";
    summary.textContent = "No ready corpora are available yet.";
    return;
  }

  if (state.chatCorpusMode === "auto") {
    picker.classList.add("hidden");
    picker.innerHTML = "";
    summary.textContent = `Auto mode uses all ${readyDocs.length} ready corpora.`;
    return;
  }

  picker.classList.remove("hidden");
  summary.textContent =
    state.selectedCorpusDocIds.length > 0
      ? `Custom selection targets ${state.selectedCorpusDocIds.length} corpus${state.selectedCorpusDocIds.length === 1 ? "" : "a"}.`
      : "Select at least one ready corpus.";
  picker.innerHTML = readyDocs
    .map(
      (doc) => `
      <label class="corpus-option">
        <input type="checkbox" data-corpus-checkbox="${doc.doc_id}" ${state.selectedCorpusDocIds.includes(doc.doc_id) ? "checked" : ""} />
        <span>
          <strong>${escapeHtml(doc.file_name)}</strong>
          <span class="muted small">Chunks ${doc.chunk_count || 0} · Sections ${doc.section_count || 0}</span>
        </span>
      </label>
    `
    )
    .join("");
  document.querySelectorAll("[data-corpus-checkbox]").forEach((checkbox) =>
    checkbox.addEventListener("change", () => {
      const selected = Array.from(document.querySelectorAll("[data-corpus-checkbox]:checked")).map(
        (node) => node.dataset.corpusCheckbox
      );
      state.selectedCorpusDocIds = selected;
      renderChatScopeControls();
    })
  );
}

async function handleDeleteDocument(docId) {
  const documentRecord = state.documents.find((doc) => doc.doc_id === docId);
  const label = documentRecord?.file_name || docId;
  const confirmed = window.confirm(`Delete corpus "${label}" and remove its indexed chunks?`);
  if (!confirmed) return;

  await fetchJson(`/api/documents/${docId}`, { method: "DELETE", timeoutMs: 60000 });
  if (state.selectedDocId === docId) {
    state.selectedDocId = null;
  }
  state.selectedCorpusDocIds = state.selectedCorpusDocIds.filter((value) => value !== docId);
  await Promise.all([refreshDashboard(), refreshDocuments(), refreshKnowledge()]);
}

function collectImageEvidence(citations) {
  const seen = new Set();
  const images = [];
  for (const citation of citations || []) {
    for (const image of citation.image_evidence || []) {
      if (!image.artifact_id || !citation.doc_id) continue;
      const key = `${citation.doc_id}:${image.artifact_id}`;
      if (seen.has(key)) continue;
      seen.add(key);
      images.push({
        ...image,
        doc_id: citation.doc_id,
      });
    }
  }
  return images;
}

function renderChatThread() {
  const thread = $("#chat-thread");
  if (!state.chatMessages.length) {
    thread.innerHTML = `<div class="chat-empty">The corpus must be ready before chat returns grounded results.</div>`;
    return;
  }

  thread.innerHTML = state.chatMessages
    .map((message) => {
      const images = message.role === "assistant" ? collectImageEvidence(message.citations || []) : [];
      return `
        <div class="message-row ${message.role}">
          <article class="message-bubble ${message.pending ? "pending" : ""}">
            <div class="message-role">${message.role === "user" ? "You" : "Agent"}</div>
            <div class="message-body">${message.html}</div>
            ${
              images.length
                ? `<div class="message-images">
                    ${images
                      .slice(0, 4)
                      .map(
                        (image) => `
                      <figure class="image-evidence-card">
                        <img src="/api/documents/${image.doc_id}/figures/${image.artifact_id}" alt="${escapeHtml(
                          image.image_name || "Figure evidence"
                        )}" loading="lazy" />
                        <figcaption>${escapeHtml(image.description || image.image_name || "Figure evidence")}</figcaption>
                      </figure>
                    `
                      )
                      .join("")}
                  </div>`
                : ""
            }
          </article>
        </div>
      `;
    })
    .join("");

  thread.scrollTop = thread.scrollHeight;
}

function renderCitations(citations) {
  $("#chat-citations").innerHTML =
    !citations || citations.length === 0
      ? `<div class="muted">No citations returned.</div>`
      : citations
          .map((item) => `
        <article class="citation-card">
          <strong>${escapeHtml(item.title)}</strong>
          <div class="muted small">${escapeHtml(item.uri || item.chunk_id || "No URI available")}</div>
          <div class="muted small">${item.page_numbers?.length ? `Pages ${item.page_numbers.join(", ")}` : ""}</div>
          <div>${escapeHtml(item.snippet)}</div>
          ${
            item.image_evidence?.length
              ? `<div class="image-evidence-grid">
                  ${item.image_evidence
                    .filter((image) => image.artifact_id && item.doc_id)
                    .slice(0, 2)
                    .map(
                      (image) => `
                    <figure class="image-evidence-card">
                      <img src="/api/documents/${item.doc_id}/figures/${image.artifact_id}" alt="${escapeHtml(
                        image.image_name || "Figure evidence"
                      )}" loading="lazy" />
                      <figcaption>${escapeHtml(image.description || image.image_name || "Figure evidence")}</figcaption>
                    </figure>
                  `
                    )
                    .join("")}
                </div>`
              : ""
          }
        </article>
      `)
          .join("");
}

function renderSubqueries(diagnostics = {}) {
  const subqueries = diagnostics.subqueries || [];
  const activity = diagnostics.activity || [];
  const hasReasoning = activity.some((item) => item.type === "agenticReasoning");

  if (!subqueries.length) {
    $("#chat-subqueries").innerHTML = hasReasoning
      ? `<article class="subquery-note">Agentic reasoning ran, but Azure Search did not expose decomposed search steps in the response payload for this request.</article>`
      : `<div class="muted">No query plan yet.</div>`;
    return;
  }

  const note =
    subqueries.length === 1 && hasReasoning
      ? `<article class="subquery-note">This request used Azure Search agentic reasoning, but the service exposed only one concrete search step in the current payload. That is not just a UI collapse.</article>`
      : "";

  $("#chat-subqueries").innerHTML =
    note +
    subqueries
      .map(
        (item) => `
      <article class="subquery-card">
        <strong>Step ${item.step}</strong>
        <div>${escapeHtml(item.search || "No search text returned")}</div>
        <div class="muted small">${escapeHtml(item.knowledge_source || "Knowledge source unavailable")} · ${item.result_count ?? "?"} hits · ${item.elapsed_ms ?? "?"} ms</div>
      </article>
    `
      )
      .join("");
}

async function handleUpload(event) {
  event.preventDefault();
  const file = $("#upload-input").files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append("file", file);
  setGenerationStatus("running", `Uploading ${file.name} and queuing it for ingestion...`);
  try {
    await fetchJson("/api/documents/upload", { method: "POST", body: formData });
    $("#upload-form").reset();
    await refreshDashboard();
    await refreshDocuments();
    await refreshKnowledge();
    setGenerationStatus("success", `${file.name} was uploaded and queued for ingestion.`);
  } catch (error) {
    setGenerationStatus("error", error.message || "Document upload failed.");
  }
}

async function handleGenerateRandomResearch() {
  const button = $("#generate-random-research");
  button.disabled = true;
  button.textContent = "Generating…";
  setGenerationStatus(
    "running",
    "Generating a large research corpus. This can take a minute or two because the PDF is created before the ingestion job is queued."
  );
  try {
    const payload = await fetchJson("/api/samples/random-research-corpus", { method: "POST", timeoutMs: 120000 });
    state.selectedDocId = payload.job.doc_id;
    await Promise.all([refreshDashboard(), refreshDocuments(), refreshKnowledge()]);
    await loadDocumentDetail(payload.job.doc_id);
    const sampleLabel = payload.sample.report_title || payload.sample.topic_key || "Research corpus";
    setGenerationStatus(
      "success",
      `${sampleLabel} was generated (${payload.sample.page_count} pages) and queued for ingestion as ${payload.sample.file_name}.`
    );
  } catch (error) {
    setGenerationStatus("error", error.message || "Random research corpus generation failed.");
    $("#document-detail").innerHTML = `<div class="muted">${error.message}</div>`;
  } finally {
    button.disabled = false;
    button.textContent = "Generate Random Research Corpus";
  }
}

async function handleGenerateFuturesReport() {
  const button = $("#generate-futures-report");
  button.disabled = true;
  button.textContent = "Generating…";
  setGenerationStatus(
    "running",
    "Generating the AI futures report. This can take a minute or two before the ingestion job appears."
  );
  try {
    const payload = await fetchJson("/api/samples/generative-ai-futures-report", { method: "POST", timeoutMs: 120000 });
    state.selectedDocId = payload.job.doc_id;
    await Promise.all([refreshDashboard(), refreshDocuments(), refreshKnowledge()]);
    await loadDocumentDetail(payload.job.doc_id);
    setGenerationStatus(
      "success",
      `${payload.sample.file_name} was generated (${payload.sample.page_count} pages) and queued for ingestion.`
    );
  } catch (error) {
    setGenerationStatus("error", error.message || "AI futures report generation failed.");
    $("#document-detail").innerHTML = `<div class="muted">${error.message}</div>`;
  } finally {
    button.disabled = false;
    button.textContent = "Generate AI Futures Report";
  }
}

async function handleGenerateConstructionReport() {
  const button = $("#generate-construction-report");
  button.disabled = true;
  button.textContent = "Generating…";
  setGenerationStatus(
    "running",
    "Generating the construction report with blueprint-style diagrams. This can take a minute or two before the job is queued."
  );
  try {
    const payload = await fetchJson("/api/samples/construction-industry-report", {
      method: "POST",
      timeoutMs: 120000,
    });
    state.selectedDocId = payload.job.doc_id;
    await Promise.all([refreshDashboard(), refreshDocuments(), refreshKnowledge()]);
    await loadDocumentDetail(payload.job.doc_id);
    setGenerationStatus(
      "success",
      `${payload.sample.file_name} was generated (${payload.sample.page_count} pages) and queued for ingestion.`
    );
  } catch (error) {
    setGenerationStatus("error", error.message || "Construction report generation failed.");
    $("#document-detail").innerHTML = `<div class="muted">${error.message}</div>`;
  } finally {
    button.disabled = false;
    button.textContent = "Generate Construction Report";
  }
}

async function handleChat(event) {
  event.preventDefault();
  const question = $("#chat-input").value.trim();
  if (!question) return;
  const selectedDocIds = state.chatCorpusMode === "custom" ? state.selectedCorpusDocIds.slice() : [];
  if (state.chatCorpusMode === "custom" && selectedDocIds.length === 0) {
    $("#chat-subqueries").innerHTML = `<div class="muted">Select at least one ready corpus before sending a custom-scoped question.</div>`;
    return;
  }
  const submitButton = $('#chat-form button[type="submit"]');
  submitButton.disabled = true;
  submitButton.textContent = "Running…";
  $("#chat-citations").innerHTML = `<div class="muted">Waiting for grounded response…</div>`;
  $("#chat-subqueries").innerHTML = `<div class="muted">Waiting for query plan…</div>`;
  state.chatMessages.push({
    role: "user",
    html: renderMarkdown(question),
    pending: false,
    citations: [],
  });
  state.chatMessages.push({
    role: "assistant",
    html:
      state.chatCorpusMode === "custom"
        ? `<p>Running grounded retrieval over ${selectedDocIds.length} selected corpus${selectedDocIds.length === 1 ? "" : "a"}…</p>`
        : `<p>Running grounded retrieval over all ready corpora…</p>`,
    pending: true,
    citations: [],
  });
  renderChatThread();
  try {
    const payload = await fetchJson("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        include_debug: true,
        corpus_mode: state.chatCorpusMode,
        corpus_doc_ids: selectedDocIds,
      }),
      timeoutMs: 30000,
    });
    state.chatMessages[state.chatMessages.length - 1] = {
      role: "assistant",
      html: renderMarkdown(payload.answer),
      pending: false,
      citations: payload.citations || [],
      diagnostics: payload.diagnostics || {},
    };
    renderChatThread();
    renderCitations(payload.citations || []);
    renderSubqueries(payload.diagnostics || {});
    $("#chat-debug").textContent = JSON.stringify(payload.diagnostics, null, 2);
    $("#chat-input").value = "";
  } catch (error) {
    const message =
      error.name === "AbortError"
        ? "Grounded retrieval timed out after 30 seconds."
        : error.message || "Grounded retrieval failed.";
    state.chatMessages[state.chatMessages.length - 1] = {
      role: "assistant",
      html: renderMarkdown(message),
      pending: false,
      citations: [],
      diagnostics: { error: message },
    };
    renderChatThread();
    $("#chat-citations").innerHTML = `<div class="muted">${escapeHtml(message)}</div>`;
    $("#chat-subqueries").innerHTML = `<div class="muted">${escapeHtml(message)}</div>`;
    $("#chat-debug").textContent = JSON.stringify({ error: message }, null, 2);
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Send";
  }
}

async function bootstrap() {
  document.querySelectorAll(".nav-link").forEach((button) =>
    button.addEventListener("click", () => setActiveScreen(button.dataset.screen))
  );
  $("#refresh-dashboard").addEventListener("click", refreshDashboard);
  $("#refresh-documents").addEventListener("click", refreshDocuments);
  $("#sync-knowledge").addEventListener("click", async () => {
    await fetchJson("/api/knowledge/sync", { method: "POST" });
    await refreshKnowledge();
  });
  $("#toggle-debug").addEventListener("click", () => {
    state.debugVisible = !state.debugVisible;
    $("#chat-debug").classList.toggle("hidden", !state.debugVisible);
  });
  $("#chat-scope-auto").addEventListener("click", () => {
    state.chatCorpusMode = "auto";
    renderChatScopeControls();
  });
  $("#chat-scope-custom").addEventListener("click", () => {
    state.chatCorpusMode = "custom";
    syncSelectedCorpusDocIds();
    renderChatScopeControls();
  });
  $("#generate-random-research").addEventListener("click", handleGenerateRandomResearch);
  $("#generate-futures-report").addEventListener("click", handleGenerateFuturesReport);
  $("#generate-construction-report").addEventListener("click", handleGenerateConstructionReport);
  $("#upload-form").addEventListener("submit", handleUpload);
  $("#chat-form").addEventListener("submit", handleChat);

  await Promise.all([refreshConfig(), refreshDashboard(), refreshDocuments(), refreshKnowledge()]);
  renderChatScopeControls();
}

bootstrap().catch((error) => {
  console.error(error);
  $("#config-summary").textContent = error.message;
});
