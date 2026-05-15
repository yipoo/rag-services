import { useState } from "react";
import {
  Alert, Button, Card, Col, Collapse, Descriptions, Input, List, Row, Space, Tag, Typography, message,
} from "antd";
import { useAuthStore } from "../store/auth";
import { postSSE } from "../api/sse";
import { api } from "../api/client";

interface Hit { chunk_id: number; document_id: number; document_title: string; score: number; text: string; }
interface Turn {
  role: "user" | "assistant";
  content: string;
  retrieval?: Hit[];
  confidence?: number;
  suggest_handoff?: boolean;
  source?: string;
  faq_hit?: any;
  cache_hit?: any;
  retrieval_debug?: any;
  timings?: Record<string, number>;
}

const SOURCE_TAG: Record<string, { color: string; label: string }> = {
  cache: { color: "purple", label: "缓存命中" },
  faq: { color: "cyan", label: "FAQ 命中" },
  llm: { color: "blue", label: "LLM 生成" },
  fallback: { color: "default", label: "兜底回复" },
};

export default function ChatPage() {
  const { industry } = useAuthStore();
  const [input, setInput] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [lastMeta, setLastMeta] = useState<Turn | null>(null);

  const send = async () => {
    if (!input.trim()) return;
    const q = input;
    setInput("");
    setTurns((p) => [...p, { role: "user", content: q }, { role: "assistant", content: "" }]);
    setLoading(true);

    let buf = "";
    try {
      await postSSE("/api/chat/stream",
        { question: q, session_id: sessionId, top_k: 5, debug: true },
        {
          onEvent: (event, data) => {
            if (event === "meta") {
              setSessionId(data.session_id);
              const metaTurn: Turn = {
                role: "assistant",
                content: "",
                retrieval: data.retrieval || [],
                confidence: data.confidence,
                suggest_handoff: data.suggest_handoff,
                source: data.source,
                faq_hit: data.faq_hit,
                cache_hit: data.cache_hit,
                retrieval_debug: data.retrieval_debug,
                timings: data.timings_ms,
              };
              setLastMeta(metaTurn);
              setTurns((p) => {
                const next = [...p];
                const last = next[next.length - 1];
                if (last?.role === "assistant") Object.assign(last, metaTurn);
                return next;
              });
            } else if (event === "delta") {
              buf += data.text || "";
              setTurns((p) => {
                const next = [...p];
                const last = next[next.length - 1];
                if (last?.role === "assistant") last.content = buf;
                return next;
              });
            } else if (event === "done") {
              setLoading(false);
            }
          },
          onError: (e) => { message.error(String(e)); setLoading(false); },
        }
      );
    } catch (e: any) {
      message.error(e?.message || "请求失败");
      setLoading(false);
    }
  };

  const clearCache = async () => {
    const r = await api.delete("/api/chat/cache");
    message.success(`已清空缓存 (${r.data.cleared} 条)`);
  };

  const debug = lastMeta?.retrieval_debug;

  return (
    <Row gutter={16}>
      <Col span={13}>
        <Card title={`对话调试 (${industry})`} extra={
          <Space>
            <Button size="small" onClick={clearCache}>清空缓存</Button>
            <Button size="small" onClick={() => { setTurns([]); setSessionId(null); setLastMeta(null); }}>新会话</Button>
          </Space>
        }>
          <div style={{ maxHeight: 480, overflow: "auto", marginBottom: 12, padding: 8, background: "#fafafa" }}>
            {turns.map((t, i) => (
              <div key={i} style={{ marginBottom: 12, textAlign: t.role === "user" ? "right" : "left" }}>
                <div style={{
                  display: "inline-block", maxWidth: "85%", padding: "8px 12px", borderRadius: 8,
                  background: t.role === "user" ? "#1677ff" : "#fff",
                  color: t.role === "user" ? "#fff" : "#000",
                  border: t.role === "user" ? "none" : "1px solid #eee",
                  whiteSpace: "pre-wrap",
                }}>
                  {t.content || (t.role === "assistant" && loading ? "…" : "")}
                </div>
                {t.role === "assistant" && t.source && (
                  <div style={{ marginTop: 4 }}>
                    <Space size={4} wrap>
                      <Tag color={SOURCE_TAG[t.source]?.color}>{SOURCE_TAG[t.source]?.label}</Tag>
                      {t.confidence !== undefined && (
                        <Tag color={t.confidence > 0.6 ? "green" : "orange"}>置信度 {t.confidence.toFixed(3)}</Tag>
                      )}
                      {t.suggest_handoff && <Tag color="red">建议转人工</Tag>}
                      {t.cache_hit && <Tag color="purple">缓存匹配 {t.cache_hit.score?.toFixed(3)}</Tag>}
                      {t.faq_hit && <Tag color="cyan">FAQ #{t.faq_hit.faq_id} 匹配 {t.faq_hit.score?.toFixed(3)}</Tag>}
                    </Space>
                  </div>
                )}
              </div>
            ))}
          </div>
          <Space.Compact style={{ width: "100%" }}>
            <Input value={input} onChange={(e) => setInput(e.target.value)} onPressEnter={send} placeholder="输入问题，回车发送" />
            <Button type="primary" onClick={send} loading={loading}>发送</Button>
          </Space.Compact>
        </Card>
      </Col>

      <Col span={11}>
        <Card title="检索详情" size="small">
          {!lastMeta && <Alert type="info" message="发送消息后会显示完整检索流水线" />}
          {lastMeta && (
            <Collapse
              defaultActiveKey={["final"]}
              size="small"
              items={[
                {
                  key: "summary",
                  label: "概要",
                  children: (
                    <Descriptions size="small" column={2} bordered>
                      <Descriptions.Item label="来源">{lastMeta.source}</Descriptions.Item>
                      <Descriptions.Item label="置信度">{lastMeta.confidence?.toFixed(3)}</Descriptions.Item>
                      <Descriptions.Item label="耗时(ms)" span={2}>
                        <pre style={{ margin: 0, fontSize: 11 }}>
                          {JSON.stringify({ ...lastMeta.timings, ...debug?.timings_ms }, null, 2)}
                        </pre>
                      </Descriptions.Item>
                    </Descriptions>
                  ),
                },
                debug?.stages?.faq?.length ? {
                  key: "faq",
                  label: `FAQ 召回 (${debug.stages.faq.length})`,
                  children: <StageList items={debug.stages.faq} field="text" />,
                } : null,
                debug?.stages?.vector?.length ? {
                  key: "vector",
                  label: `向量召回 (${debug.stages.vector.length})`,
                  children: <StageBrief items={debug.stages.vector} />,
                } : null,
                debug?.stages?.bm25?.length ? {
                  key: "bm25",
                  label: `BM25 召回 (${debug.stages.bm25.length})`,
                  children: <StageBrief items={debug.stages.bm25} />,
                } : null,
                debug?.stages?.fused?.length ? {
                  key: "fused",
                  label: `RRF 融合 (${debug.stages.fused.length})`,
                  children: <StageBrief items={debug.stages.fused} />,
                } : null,
                debug?.stages?.reranked?.length ? {
                  key: "reranked",
                  label: `Rerank (${debug.stages.reranked.length})`,
                  children: <StageBrief items={debug.stages.reranked} scoreKey="rerank_score" />,
                } : null,
                {
                  key: "final",
                  label: `送入 LLM 的 contexts (${lastMeta.retrieval?.length || 0})`,
                  children: (
                    <List
                      size="small"
                      dataSource={lastMeta.retrieval || []}
                      renderItem={(h) => (
                        <List.Item>
                          <List.Item.Meta
                            title={<Space><Tag color="blue">分数 {h.score.toFixed(3)}</Tag>{h.document_title}</Space>}
                            description={<pre style={{ whiteSpace: "pre-wrap", fontSize: 12, margin: 0 }}>{h.text}</pre>}
                          />
                        </List.Item>
                      )}
                    />
                  ),
                },
              ].filter(Boolean) as any}
            />
          )}
        </Card>
      </Col>
    </Row>
  );
}

function StageBrief({ items, scoreKey = "score" }: { items: any[]; scoreKey?: string }) {
  return (
    <List
      size="small"
      dataSource={items.slice(0, 10)}
      renderItem={(x) => (
        <List.Item>
          <Space>
            <Tag>chunk #{x.chunk_id ?? x.faq_id}</Tag>
            <span>{(x[scoreKey] ?? 0).toFixed(3)}</span>
          </Space>
        </List.Item>
      )}
    />
  );
}

function StageList({ items, field }: { items: any[]; field: string }) {
  return (
    <List
      size="small"
      dataSource={items}
      renderItem={(x) => (
        <List.Item>
          <List.Item.Meta
            title={<Space><Tag>FAQ #{x.faq_id}</Tag><span>分数 {x.score?.toFixed(3)}</span></Space>}
            description={<span style={{ fontSize: 12 }}>{x[field]}</span>}
          />
        </List.Item>
      )}
    />
  );
}
