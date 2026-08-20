import { useEffect, useRef, useState } from "react";
import { sendChat } from "./api.js";
import ResponseBlocks from "./components/ResponseBlocks.jsx";

const suggestions = [
  ["比較各類別成交率", "比較五個類別的成交率，告訴我最高的是哪一類？"],
  ["查看年度成交趨勢", "2020 到 2025 年的成交總額有什麼變化？"],
  ["找出作者排名", "找出作者成交表現最好的前十名。"],
];

function InlineAnswer({ value }) {
  const tokens = String(value || "目前沒有文字答案。").split(
    /(\*\*[^*]+\*\*|`[^`]+`)/g,
  );
  return (
    <>
      {tokens.map((token, index) => {
        if (token.startsWith("**") && token.endsWith("**"))
          return <strong key={index}>{token.slice(2, -2)}</strong>;
        if (token.startsWith("`") && token.endsWith("`"))
          return <code key={index}>{token.slice(1, -1)}</code>;
        return token;
      })}
    </>
  );
}

function Message({ message }) {
  if (message.role === "user")
    return (
      <article className="message user">
        <div className="avatar">你</div>
        <div className="message-body">
          <div className="bubble">
            <div className="answer-text">{message.text}</div>
          </div>
          <div className="message-meta">剛剛</div>
        </div>
      </article>
    );

  if (message.loading)
    return (
      <article className="message assistant">
        <div className="avatar">鑑</div>
        <div className="message-body">
          <div className="bubble">
            <div className="typing" aria-label="Agent 分析中">
              <i />
              <i />
              <i />
            </div>
            <div className="live-trace" aria-live="polite">
              {message.traces.map((step, index) => (
                <div
                  className={`live-step ${step.status || "done"}`}
                  key={index}
                >
                  <span className="live-icon">
                    {step.status === "blocked" ? "!" : "✓"}
                  </span>
                  <span>
                    <strong>{step.label}</strong>
                    {step.detail && <small>{step.detail}</small>}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </article>
    );

  const response = message.response;
  if (response.error)
    return (
      <article className="message assistant">
        <div className="avatar">鑑</div>
        <div className="message-body">
          <div className="bubble">
            <div className="notice">
              {response.error.message}（{response.error.code}）
            </div>
          </div>
          <div className="message-meta">Agent</div>
        </div>
      </article>
    );
  return (
    <article className="message assistant">
      <div className="avatar">鑑</div>
      <div className="message-body">
        <div className="bubble">
          <div className="answer-text">
            <InlineAnswer value={response.answer} />
          </div>
          <div className="attachments">
            <ResponseBlocks response={response} />
          </div>
        </div>
        <div className="message-meta">
          Agent · {response.metadata?.model || "資料研究助手"}
        </div>
      </div>
    </article>
  );
}

function Welcome({ onSuggestion }) {
  return (
    <div className="welcome">
      <div className="welcome-icon">鑑</div>
      <h2>今天想研究哪一批收藏品？</h2>
      <p>你可以直接用自然語言追問，像跟研究助理聊天一樣。</p>
      <div className="suggestions">
        {suggestions.map(([label, text]) => (
          <button type="button" key={label} onClick={() => onSuggestion(text)}>
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}

export default function App() {
  const [messages, setMessages] = useState([]);
  const [conversationId, setConversationId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [debugMode, setDebugMode] = useState(true);
  const [question, setQuestion] = useState("");
  const [health, setHealth] = useState({ label: "連線檢查中", ok: false });
  const messagesRef = useRef(null);
  const textareaRef = useRef(null);

  useEffect(() => {
    fetch("/health")
      .then((res) => res.json())
      .then((result) =>
        setHealth(
          result.status === "ok"
            ? { label: "服務已連線", ok: true }
            : { label: "服務異常", ok: false },
        ),
      )
      .catch(() => setHealth({ label: "服務未連線", ok: false }));
  }, []);

  useEffect(() => {
    if (messagesRef.current)
      messagesRef.current.scrollTop = messagesRef.current.scrollHeight;
  }, [messages]);
  useEffect(() => {
    if (!textareaRef.current) return;
    textareaRef.current.style.height = "auto";
    textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 150)}px`;
  }, [question]);

  const ask = async (rawText = question) => {
    const text = rawText.trim();
    if (!text || busy) return;
    const loadingId =
      globalThis.crypto?.randomUUID?.() || `loading-${Date.now()}`;
    setMessages((current) => [
      ...current,
      { id: `user-${loadingId}`, role: "user", text },
      { id: loadingId, role: "assistant", loading: true, traces: [] },
    ]);
    setQuestion("");
    setBusy(true);
    try {
      const response = await sendChat({
        message: text,
        conversationId,
        debugMode,
        onTrace: (trace) =>
          setMessages((current) =>
            current.map((message) =>
              message.id === loadingId
                ? { ...message, traces: [...message.traces, trace] }
                : message,
            ),
          ),
      });
      setConversationId(response.conversation_id || conversationId);
      setMessages((current) =>
        current.map((message) =>
          message.id === loadingId
            ? { id: loadingId, role: "assistant", response }
            : message,
        ),
      );
    } catch (error) {
      const response = {
        error: {
          code: "NETWORK_ERROR",
          message: `無法連線到 Agent：${error.message}`,
        },
      };
      setMessages((current) =>
        current.map((message) =>
          message.id === loadingId
            ? { id: loadingId, role: "assistant", response }
            : message,
        ),
      );
    } finally {
      setBusy(false);
      textareaRef.current?.focus();
    }
  };

  const resetChat = () => {
    setMessages([]);
    setConversationId(null);
    setQuestion("");
    textareaRef.current?.focus();
  };
  const conversationLabel = conversationId ? "研究中的對話" : "新的研究對話";
  const modelLabel =
    [...messages].reverse().find((message) => message.response?.metadata?.model)
      ?.response.metadata.model || "gpt-5.5";

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="對話側欄">
        <div className="brand">
          <div className="brand-mark">鑑</div>
          <div>
            <strong>AI 藝術品拍賣資料查詢 Agent</strong>
            <span>AI AUCTION DATA AGENT</span>
          </div>
        </div>
        <button className="new-chat" type="button" onClick={resetChat}>
          <span className="plus">＋</span> 開始新對話
        </button>
        <div className="sidebar-section">
          <p className="section-label">目前對話</p>
          <div className="conversation-label">
            <span className="conversation-dot" />
            <span>{conversationLabel}</span>
          </div>
        </div>
        <div className="sidebar-spacer" />
        <div className="sidebar-note">
          <span className="status-dot" />
          <div>
            <strong>本機 Agent</strong>
            <span>{modelLabel} · DuckDB</span>
          </div>
        </div>
      </aside>
      <main className="chat-main">
        <header className="chat-header">
          <div>
            <p className="eyebrow">COLLECTION RESEARCH</p>
            <h1>AI 藝術品拍賣資料查詢 Agent</h1>
            <p className="header-subtitle">
              直接提問，Agent 會依資料自行查詢與整理。
            </p>
          </div>
          <div className="header-actions">
            <label className="debug-control">
              <input
                type="checkbox"
                checked={debugMode}
                onChange={(event) => setDebugMode(event.target.checked)}
              />{" "}
              顯示分析步驟
            </label>
            <div className={`health-badge ${health.ok ? "ok" : ""}`}>
              <span />
              {health.label}
            </div>
          </div>
        </header>
        <section className="messages" ref={messagesRef} aria-live="polite">
          {messages.length ? (
            messages.map((message) => (
              <Message key={message.id} message={message} />
            ))
          ) : (
            <Welcome onSuggestion={ask} />
          )}
        </section>
        <div className="status" role="status" aria-live="polite">
          {busy ? "Agent 正在理解問題、查詢資料…" : ""}
        </div>
        <form
          className="composer"
          onSubmit={(event) => {
            event.preventDefault();
            ask();
          }}
        >
          <textarea
            ref={textareaRef}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                ask();
              }
            }}
            rows="1"
            autoComplete="off"
            disabled={busy}
            placeholder="輸入你的問題…（Enter 送出，Shift + Enter 換行）"
          />
          <button
            className="send-button"
            type="submit"
            disabled={busy}
            aria-label="送出問題"
          >
            <span>送出</span>
            <span className="send-arrow">↑</span>
          </button>
        </form>
        <p className="composer-note">
          回答會使用專案資料庫；拍賣公司、價格與成交狀態是模擬資料。
        </p>
      </main>
    </div>
  );
}
