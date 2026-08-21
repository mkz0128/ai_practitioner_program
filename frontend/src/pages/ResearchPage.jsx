import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { sendChat } from "../api.js";
import ResponseBlocks from "../components/ResponseBlocks.jsx";

const suggestions = [
  "比較五個類別的成交率，告訴我最高的是哪一類？",
  "2020 到 2025 年的成交總額有什麼變化？",
  "找出作者成交表現最好的前十名。",
];

function InlineAnswer({ value }) {
  const tokens = String(value || "目前沒有文字答案。").split(
    /(\*\*[^*]+\*\*|`[^`]+`)/g,
  );
  return tokens.map((token, index) => {
    if (token.startsWith("**") && token.endsWith("**"))
      return <strong key={index}>{token.slice(2, -2)}</strong>;
    if (token.startsWith("`") && token.endsWith("`"))
      return <code key={index}>{token.slice(1, -1)}</code>;
    return token;
  });
}

function Message({ message }) {
  if (message.role === "user") {
    return (
      <article className="research-message user-message">
        <div className="research-avatar">你</div>
        <div className="research-message-body">
          <div className="research-bubble">{message.text}</div>
        </div>
      </article>
    );
  }

  if (message.loading) {
    return (
      <article className="research-message assistant-message">
        <div className="research-avatar">鑑</div>
        <div className="research-message-body">
          <div className="research-bubble">
            <div className="research-typing" aria-label="Agent 分析中">
              <i /><i /><i />
            </div>
            {!!message.traces.length && (
              <div className="research-live-trace" aria-live="polite">
                {message.traces.map((step, index) => (
                  <div className={`research-live-step ${step.status || "done"}`} key={index}>
                    <span>{step.status === "blocked" ? "!" : "✓"}</span>
                    <div>
                      <strong>{step.label}</strong>
                      {step.detail && <small>{step.detail}</small>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </article>
    );
  }

  const { response } = message;
  if (response.error) {
    return (
      <article className="research-message assistant-message">
        <div className="research-avatar">鑑</div>
        <div className="research-message-body">
          <div className="research-bubble research-error">
            {response.error.message}
            {response.error.code && <small>{response.error.code}</small>}
          </div>
        </div>
      </article>
    );
  }

  return (
    <article className="research-message assistant-message">
      <div className="research-avatar">鑑</div>
      <div className="research-message-body">
        <div className="research-bubble">
          <div className="research-answer"><InlineAnswer value={response.answer} /></div>
          <ResponseBlocks response={response} />
          {response.disclosure && <p className="research-disclosure">{response.disclosure}</p>}
        </div>
        <span className="research-message-meta">
          AI 研究助手 · {response.metadata?.model || "資料庫分析"}
        </span>
      </div>
    </article>
  );
}

export default function ResearchPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const [messages, setMessages] = useState([]);
  const [conversationId, setConversationId] = useState(null);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [debugMode, setDebugMode] = useState(false);
  const messagesRef = useRef(null);
  const textareaRef = useRef(null);
  const abortRef = useRef(null);
  const cleanupTimerRef = useRef(null);
  const initialQuestionRef = useRef(location.state?.initialQuestion || "");

  const ask = useCallback(async (rawText) => {
    const text = String(rawText ?? question).trim();
    if (!text || busy) return;
    const loadingId = globalThis.crypto?.randomUUID?.() || `loading-${Date.now()}`;
    const controller = new AbortController();
    abortRef.current = controller;
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
        signal: controller.signal,
        onTrace: (trace) => setMessages((current) => current.map((item) =>
          item.id === loadingId ? { ...item, traces: [...item.traces, trace] } : item,
        )),
      });
      setConversationId(response.conversation_id || conversationId);
      setMessages((current) => current.map((item) =>
        item.id === loadingId ? { id: loadingId, role: "assistant", response } : item,
      ));
    } catch (error) {
      if (error.name === "AbortError") return;
      setMessages((current) => current.map((item) => item.id === loadingId ? {
        id: loadingId,
        role: "assistant",
        response: { error: { code: "NETWORK_ERROR", message: `無法連線到 Agent：${error.message}` } },
      } : item));
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      setBusy(false);
      textareaRef.current?.focus();
    }
  }, [busy, conversationId, debugMode, question]);

  useEffect(() => {
    const initialQuestion = initialQuestionRef.current;
    if (!initialQuestion) return;
    initialQuestionRef.current = "";
    navigate(location.pathname, { replace: true, state: null });
    ask(initialQuestion);
  }, [ask, location.pathname, navigate]);

  useEffect(() => {
    const element = messagesRef.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [messages]);

  useEffect(() => {
    const element = textareaRef.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, 132)}px`;
  }, [question]);

  useEffect(() => {
    if (cleanupTimerRef.current) clearTimeout(cleanupTimerRef.current);
    return () => {
      const controller = abortRef.current;
      cleanupTimerRef.current = setTimeout(() => controller?.abort(), 0);
    };
  }, []);

  const resetChat = () => {
    abortRef.current?.abort();
    setMessages([]);
    setConversationId(null);
    setQuestion("");
    setBusy(false);
    textareaRef.current?.focus();
  };

  return (
    <main className="research-page">
      <header className="research-header">
        <div>
          <p className="kicker">AI COLLECTION RESEARCH</p>
          <h1>藝術市場研究助手</h1>
          <p>以自然語言查詢歷年拍賣資料，並繼續追問分析結果。</p>
        </div>
        <div className="research-actions">
          <label>
            <input type="checkbox" checked={debugMode} onChange={(event) => setDebugMode(event.target.checked)} />
            顯示分析步驟
          </label>
          <button type="button" onClick={resetChat}>＋ 新對話</button>
        </div>
      </header>

      <section className="research-messages" ref={messagesRef} aria-live="polite">
        {messages.length ? messages.map((message) => <Message message={message} key={message.id} />) : (
          <div className="research-welcome">
            <div className="research-welcome-mark">鑑</div>
            <h2>今天想研究什麼？</h2>
            <p>可詢問成交率、年度趨勢、作者排名、拍品圖片等資料。</p>
            <div className="research-suggestions">
              {suggestions.map((suggestion) => (
                <button type="button" onClick={() => ask(suggestion)} key={suggestion}>{suggestion}</button>
              ))}
            </div>
          </div>
        )}
      </section>

      <div className="research-status" role="status">{busy ? "Agent 正在理解問題並查詢資料…" : ""}</div>
      <form className="research-composer" onSubmit={(event) => { event.preventDefault(); ask(); }}>
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
          disabled={busy}
          placeholder="輸入問題…（Enter 送出，Shift + Enter 換行）"
          aria-label="輸入研究問題"
        />
        <button className="gold-button" type="submit" disabled={busy || !question.trim()}>送出 ↑</button>
      </form>
      <p className="research-note">回答使用專案資料庫；拍賣公司、價格與成交狀態為模擬資料。</p>
    </main>
  );
}
