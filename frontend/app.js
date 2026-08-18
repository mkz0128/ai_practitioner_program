const state = { conversationId: null, busy: false };

const $ = (selector) => document.querySelector(selector);
const messages = $("#messages");
const question = $("#question");
const sendButton = $("#send");
const status = $("#status");
const welcomeMarkup = $("#welcome").outerHTML;

function esc(value) {
  return String(value ?? "").replace(/[&<>\"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[char]));
}

function formatValue(value) {
  if (typeof value === "number") return new Intl.NumberFormat("zh-TW").format(value);
  return value ?? "—";
}

function formatAnswer(value) {
  return esc(value)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\n/g, "<br>");
}

function scrollToBottom() { messages.scrollTop = messages.scrollHeight; }

function anonymousId() {
  const key = "auction_anonymous_id";
  let value = localStorage.getItem(key);
  if (!value) {
    value = (globalThis.crypto?.randomUUID?.() || `anon_${Date.now()}_${Math.random().toString(36).slice(2)}`);
    localStorage.setItem(key, value);
  }
  return value;
}

function removeWelcome() {
  const welcome = $("#welcome");
  if (welcome) welcome.remove();
}

function renderTable(table) {
  if (!table?.columns?.length) return "";
  const rows = (table.rows || []).slice(0, 20);
  const headers = table.columns.map((column) => `<th>${esc(column.label)}</th>`).join("");
  const body = rows.map((row) => `<tr>${table.columns.map((column) => `<td>${esc(formatValue(row[column.key]))}</td>`).join("")}</tr>`).join("");
  const more = (table.rows || []).length > rows.length
    ? `<p class="more-rows">僅顯示前 ${rows.length} 筆，完整結果共 ${table.row_count} 筆。</p>` : "";
  return `<details class="attachment" open><summary>${esc(table.title || "資料結果")}（${table.row_count ?? rows.length} 筆）</summary><div class="attachment-content"><div class="table-wrap"><table><thead><tr>${headers}</tr></thead><tbody>${body}</tbody></table></div>${more}</div></details>`;
}

// Chart blocks use a stable spec. The frontend owns the visual adapter, so this can be replaced by ECharts later.
function renderChart(chart, table) {
  if (!chart || !chart.encoding?.x || !chart.encoding?.y) return "";
  const rows = chart.data?.length ? chart.data : (table?.rows || []);
  if (!rows.length) return "";
  const values = rows.map((row) => Number(row[chart.encoding.y]) || 0);
  const max = Math.max(...values, 1);
  const bars = rows.slice(0, 20).map((row) => {
    const value = Number(row[chart.encoding.y]) || 0;
    const label = row[chart.encoding.x];
    const display = chart.encoding.y_format === "0.00%" ? `${value.toFixed(2)}%` : formatValue(value);
    return `<div class="bar-row"><span>${esc(label)}</span><span class="bar-track"><span class="bar-fill" style="width:${Math.max(2, value / max * 100)}%"></span></span><strong>${esc(display)}</strong></div>`;
  }).join("");
  return `<details class="attachment" open><summary>圖表：${esc(chart.title)}</summary><div class="attachment-content"><div class="chart">${bars}</div></div></details>`;
}

function renderImages(items) {
  if (!items?.length) return "";
  const cards = items.map((image) => `<figure><img src="${esc(image.url)}" alt="${esc(image.caption)}" loading="lazy" /><figcaption>${esc(image.caption)}</figcaption></figure>`).join("");
  return `<details class="attachment" open><summary>拍品圖片（${items.length} 張）</summary><div class="attachment-content"><div class="images">${cards}</div></div></details>`;
}

function renderDebug(debug) {
  if (!debug) return "";
  const skills = (debug.skills || []).map((skill) => `<li><strong>${esc(skill.name || skill.id)}</strong><span>${esc(skill.purpose || "")}</span></li>`).join("");
  const trace = (debug.trace || []).map((step) => `<li class="trace-${esc(step.status || "done")}"><strong>${esc(step.label)}</strong><span>${esc(step.detail || "")}</span></li>`).join("");
  const sql = (debug.sql || []).map((query) => `<pre>${esc(query)}</pre>`).join("");
  return `<details class="attachment debug-panel" open><summary>分析流程（可審計）</summary><div class="attachment-content"><h4>Skills</h4><ul class="trace-list">${skills || "<li>未使用額外 Skill</li>"}</ul><h4>執行步驟</h4><ol class="trace-list">${trace || "<li>沒有可顯示的步驟</li>"}</ol>${sql ? `<h4>唯讀 SQL</h4><div class="technical">${sql}</div>` : ""}</div></details>`;
}

function renderBlocks(response) {
  const blocks = response.blocks || [];
  const tables = new Map();
  blocks.filter((block) => block.type === "table").forEach((block) => tables.set(block.id, block.data));
  return blocks.map((block) => {
    if (block.type === "table") return renderTable(block.data);
    if (block.type === "chart") return renderChart(block.data, tables.get(block.data?.data_table_id));
    if (block.type === "image") return renderImages(block.data?.items || []);
    if (block.type === "kpi") return `<div class="kpi"><strong>${esc(block.title)}</strong><span>${esc(block.data?.value ?? "—")}</span></div>`;
    return "";
  }).filter(Boolean).join("");
}

function appendUserMessage(text) {
  const node = document.createElement("article");
  node.className = "message user";
  node.innerHTML = `<div class="avatar">你</div><div class="message-body"><div class="bubble"><div class="answer-text">${esc(text).replace(/\n/g, "<br>")}</div></div><div class="message-meta">剛剛</div></div>`;
  messages.appendChild(node);
  scrollToBottom();
}

function appendTypingMessage() {
  const node = document.createElement("article");
  node.className = "message assistant";
  node.id = "typing-message";
  node.innerHTML = `<div class="avatar">鑑</div><div class="message-body"><div class="bubble"><div class="typing" aria-label="Agent 分析中"><i></i><i></i><i></i></div><div class="live-trace" aria-live="polite"></div></div></div>`;
  messages.appendChild(node);
  scrollToBottom();
  return node;
}

function appendLiveTrace(node, step) {
  const trace = node?.querySelector(".live-trace");
  if (!trace) return;
  const item = document.createElement("div");
  item.className = `live-step ${step.status || "done"}`;
  item.innerHTML = `<span class="live-icon">${step.status === "blocked" ? "!" : "✓"}</span><span><strong>${esc(step.label)}</strong>${step.detail ? `<small>${esc(step.detail)}</small>` : ""}</span>`;
  trace.appendChild(item);
  scrollToBottom();
}

function appendAssistantMessage(response) {
  const node = document.createElement("article");
  node.className = "message assistant";
  if (response.error) {
    const debug = renderDebug(response.debug);
    node.innerHTML = `<div class="avatar">鑑</div><div class="message-body"><div class="bubble"><div class="notice">${esc(response.error.message)}（${esc(response.error.code)}）</div>${debug ? `<div class="attachments">${debug}</div>` : ""}</div><div class="message-meta">Agent</div></div>`;
  } else {
    const attachments = [
      renderBlocks(response),
      renderDebug(response.debug),
      ...(response.warnings || []).map((warning) => `<div class="notice">${esc(warning)}</div>`),
    ].filter(Boolean).join("");
    node.innerHTML = `<div class="avatar">鑑</div><div class="message-body"><div class="bubble"><div class="answer-text">${formatAnswer(response.answer || "目前沒有文字答案。")}</div>${attachments ? `<div class="attachments">${attachments}</div>` : ""}</div><div class="message-meta">Agent · ${esc(response.metadata?.model || "資料研究助手")}</div></div>`;
    if (response.metadata?.model) $("#model-label").textContent = `${response.metadata.model} · DuckDB`;
  }
  messages.appendChild(node);
  scrollToBottom();
}

function setBusy(isBusy) {
  state.busy = isBusy;
  sendButton.disabled = isBusy;
  question.disabled = isBusy;
  status.textContent = isBusy ? "Agent 正在理解問題、查詢資料…" : "";
}

function resizeComposer() {
  question.style.height = "auto";
  question.style.height = `${Math.min(question.scrollHeight, 150)}px`;
}

async function readSse(response, typing) {
  if (!response.body) throw new Error("服務沒有回傳串流內容");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result = null;
  const consume = (chunk) => {
    buffer += chunk;
    const packets = buffer.split("\n\n");
    buffer = packets.pop() || "";
    for (const raw of packets) {
      let event = "message";
      let data = "";
      raw.split(/\r?\n/).forEach((line) => {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        if (line.startsWith("data:")) data += line.slice(5).trim();
      });
      if (!data) continue;
      const payload = JSON.parse(data);
      if (event === "trace") appendLiveTrace(typing, payload);
      if (event === "result") result = payload;
    }
  };
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    consume(decoder.decode(value, { stream: true }));
  }
  consume(decoder.decode());
  if (!result) throw new Error("Agent 沒有回傳結果");
  return result;
}

async function ask(text = question.value.trim()) {
  if (!text || state.busy) return;
  removeWelcome();
  appendUserMessage(text);
  question.value = "";
  resizeComposer();
  const typing = appendTypingMessage();
  setBusy(true);
  try {
    const result = await fetch("../api/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "X-Anonymous-Id": anonymousId(),
      },
      body: JSON.stringify({ message: text, conversation_id: state.conversationId, mode: $("#debug-mode").checked ? "debug" : "normal", stream: true })
    });
    if (!result.ok) throw new Error(`HTTP ${result.status}`);
    const response = await readSse(result, typing);
    typing.remove();
    state.conversationId = response.conversation_id || state.conversationId;
    if (response.conversation_id) $("#conversation-label span:last-child").textContent = "研究中的對話";
    appendAssistantMessage(response);
  } catch (error) {
    typing.remove();
    appendAssistantMessage({ error: { code: "NETWORK_ERROR", message: `無法連線到 Agent：${error.message}` } });
  } finally {
    setBusy(false);
    question.focus();
  }
}

function resetChat() {
  state.conversationId = null;
  messages.innerHTML = welcomeMarkup;
  $("#conversation-label span:last-child").textContent = "新的研究對話";
  status.textContent = "";
  bindSuggestions();
  question.value = "";
  resizeComposer();
  question.focus();
}

function bindSuggestions() {
  document.querySelectorAll("[data-suggestion]").forEach((button) => button.addEventListener("click", () => ask(button.dataset.suggestion)));
}

$("#composer").addEventListener("submit", (event) => { event.preventDefault(); ask(); });
question.addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); ask(); } });
question.addEventListener("input", resizeComposer);
$("#new-chat").addEventListener("click", resetChat);
bindSuggestions();
resizeComposer();

fetch("../health").then((res) => res.json()).then((health) => {
  const badge = $("#health-badge");
  if (health.status === "ok") { badge.innerHTML = "<span></span>服務已連線"; badge.classList.add("ok"); }
  else badge.innerHTML = "<span></span>服務異常";
}).catch(() => { $("#health-badge").innerHTML = "<span></span>服務未連線"; });
