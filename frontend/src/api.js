export function anonymousId() {
  const key = "auction_anonymous_id";
  let value = localStorage.getItem(key);
  if (!value) {
    value =
      globalThis.crypto?.randomUUID?.() ||
      `anon_${Date.now()}_${Math.random().toString(36).slice(2)}`;
    localStorage.setItem(key, value);
  }
  return value;
}

export async function readSse(response, onTrace) {
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
      let payload;
      try {
        payload = JSON.parse(data);
      } catch {
        throw new Error("Agent 回傳了無法解析的串流資料");
      }
      if (event === "trace") onTrace?.(payload);
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

export async function sendChat({
  message,
  conversationId,
  debugMode,
  onTrace,
  signal,
}) {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      "X-Anonymous-Id": anonymousId(),
      "X-Client-Request-Id":
        globalThis.crypto?.randomUUID?.() || `request_${Date.now()}`,
    },
    signal,
    body: JSON.stringify({
      message,
      conversation_id: conversationId,
      mode: debugMode ? "debug" : "normal",
      stream: true,
    }),
  });
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const payload = await response.json();
      message =
        payload?.detail?.message ||
        payload?.detail ||
        payload?.error?.message ||
        message;
    } catch {
      // The status code remains useful when the server does not return JSON.
    }
    throw new Error(message);
  }
  return readSse(response, onTrace);
}
