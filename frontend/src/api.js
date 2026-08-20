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
      const payload = JSON.parse(data);
      if (event === "trace") onTrace(payload);
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
}) {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      "X-Anonymous-Id": anonymousId(),
    },
    body: JSON.stringify({
      message,
      conversation_id: conversationId,
      mode: debugMode ? "debug" : "normal",
      stream: true,
    }),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return readSse(response, onTrace);
}
