import { useAuthStore } from "../store/auth";

export interface SSEHandlers {
  onEvent: (event: string, data: any) => void;
  onError?: (err: any) => void;
  signal?: AbortSignal;
}

/**
 * POST + Bearer token + tenant headers, parse SSE stream manually.
 * Works around EventSource's inability to set headers / use POST.
 */
export async function postSSE(url: string, body: any, h: SSEHandlers) {
  const { token, tenantId, industry } = useAuthStore.getState();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "text/event-stream",
  };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (tenantId) headers["X-Tenant-Id"] = String(tenantId);
  if (industry) headers["X-Industry"] = industry;

  const res = await fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    signal: h.signal,
  });
  if (!res.ok || !res.body) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${text}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buf = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });

      // SSE events separated by blank line
      let idx;
      while ((idx = buf.indexOf("\n\n")) !== -1) {
        const raw = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        let event = "message";
        let data = "";
        for (const line of raw.split("\n")) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          else if (line.startsWith("data:")) data += line.slice(5).trim();
        }
        if (data) {
          try {
            h.onEvent(event, JSON.parse(data));
          } catch {
            h.onEvent(event, data);
          }
        }
      }
    }
  } catch (e) {
    h.onError?.(e);
  }
}
