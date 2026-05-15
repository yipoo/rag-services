import { useEffect, useState } from "react";
import {
  Alert, Button, Card, Col, Drawer, Form, Input, Modal, Row, Select, Space, Statistic,
  Table, Tag, message,
} from "antd";
import { api } from "../api/client";
import { useAuthStore } from "../store/auth";

interface Item {
  id: number;
  question: string;
  answer_given: string;
  confidence: number;
  source: string;
  category: string;
  status: string;
  handled_faq_id: number | null;
  retrieval: any;
  session_id: number | null;
  created_at: string;
}

const CATEGORY_TAG: Record<string, { color: string; label: string }> = {
  miss:    { color: "red",     label: "0 命中" },
  handoff: { color: "orange",  label: "极低分（建议转人工）" },
  low:     { color: "gold",    label: "低分回答" },
};
const STATUS_TAG: Record<string, { color: string; label: string }> = {
  pending:   { color: "blue",    label: "待处理" },
  handled:   { color: "green",   label: "已处理" },
  dismissed: { color: "default", label: "已忽略" },
};

export default function UnansweredPage() {
  const { tenantId, industry } = useAuthStore();
  const [data, setData] = useState<Item[]>([]);
  const [stats, setStats] = useState<any>({ total: 0, by_status: {}, by_category: {} });
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<{ status?: string; category?: string; q?: string }>({ status: "pending" });
  const [sets, setSets] = useState<{ id: number; name: string }[]>([]);
  const [drawer, setDrawer] = useState<Item | null>(null);
  const [convertOpen, setConvertOpen] = useState(false);
  const [convertItem, setConvertItem] = useState<Item | null>(null);
  const [form] = Form.useForm();

  const load = async () => {
    setLoading(true);
    try {
      const params: any = {};
      if (filter.status) params.status = filter.status;
      if (filter.category) params.category = filter.category;
      if (filter.q) params.q = filter.q;
      const [d, s, ks] = await Promise.all([
        api.get("/api/unanswered", { params }),
        api.get("/api/unanswered/stats"),
        api.get("/api/knowledge-sets"),
      ]);
      setData(d.data); setStats(s.data); setSets(ks.data);
    } finally { setLoading(false); }
  };

  useEffect(() => { if (tenantId && industry) load(); }, [tenantId, industry, filter.status, filter.category]);

  const updateStatus = async (id: number, st: string) => {
    await api.patch(`/api/unanswered/${id}`, { status: st });
    message.success("已更新"); load();
  };
  const del = async (id: number) => {
    await api.delete(`/api/unanswered/${id}`);
    message.success("已删除"); load();
  };

  const openConvert = (it: Item) => {
    setConvertItem(it);
    form.setFieldsValue({
      question: it.question,
      answer: it.answer_given && !it.answer_given.includes("再描述") ? it.answer_given : "",
      similar_questions: "",
      knowledge_set_id: undefined,
    });
    setConvertOpen(true);
  };

  const submitConvert = async () => {
    const v = await form.validateFields();
    await api.post(`/api/unanswered/${convertItem!.id}/convert-to-faq`, {
      question: v.question,
      answer: v.answer,
      similar_questions: (v.similar_questions || "").split("\n").map((s: string) => s.trim()).filter(Boolean),
      knowledge_set_id: v.knowledge_set_id || null,
      mark_handled: true,
    });
    message.success("已沉淀为 FAQ");
    setConvertOpen(false); setConvertItem(null); load();
  };

  return (
    <Card title={`待优化问题 (${industry})`}>
      <Alert
        showIcon
        type="info"
        style={{ marginBottom: 16 }}
        message="这里收集了所有低置信度或未命中的对话。把它们沉淀成 FAQ，机器人就会越来越聪明。"
      />

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card><Statistic title="待处理" value={stats.by_status?.pending || 0} valueStyle={{ color: "#1677ff" }} /></Card></Col>
        <Col span={6}><Card><Statistic title="已处理" value={stats.by_status?.handled || 0} valueStyle={{ color: "#52c41a" }} /></Card></Col>
        <Col span={6}><Card><Statistic title="0 命中" value={stats.by_category?.miss || 0} valueStyle={{ color: "#ff4d4f" }} /></Card></Col>
        <Col span={6}><Card><Statistic title="低分回答" value={stats.by_category?.low || 0} /></Card></Col>
      </Row>

      <Space style={{ marginBottom: 12 }} wrap>
        <Select
          placeholder="状态" value={filter.status} allowClear style={{ width: 140 }}
          onChange={(v) => setFilter({ ...filter, status: v })}
          options={["pending", "handled", "dismissed"].map((v) => ({ value: v, label: STATUS_TAG[v].label }))}
        />
        <Select
          placeholder="类别" value={filter.category} allowClear style={{ width: 200 }}
          onChange={(v) => setFilter({ ...filter, category: v })}
          options={["miss", "handoff", "low"].map((v) => ({ value: v, label: CATEGORY_TAG[v].label }))}
        />
        <Input.Search placeholder="搜索问题" allowClear style={{ width: 240 }}
          onSearch={(v) => { setFilter({ ...filter, q: v }); load(); }} />
        <Button onClick={load}>刷新</Button>
      </Space>

      <Table
        rowKey="id"
        dataSource={data}
        loading={loading}
        columns={[
          { title: "ID", dataIndex: "id", width: 60 },
          {
            title: "用户问题", dataIndex: "question", ellipsis: true,
            render: (t, r) => <a onClick={() => setDrawer(r)}>{t}</a>,
          },
          {
            title: "类别", dataIndex: "category", width: 180,
            render: (v) => <Tag color={CATEGORY_TAG[v]?.color}>{CATEGORY_TAG[v]?.label || v}</Tag>,
          },
          { title: "置信度", dataIndex: "confidence", width: 100, render: (v) => v.toFixed(3) },
          {
            title: "状态", dataIndex: "status", width: 100,
            render: (v) => <Tag color={STATUS_TAG[v]?.color}>{STATUS_TAG[v]?.label || v}</Tag>,
          },
          { title: "时间", dataIndex: "created_at", width: 180, render: (v) => new Date(v).toLocaleString() },
          {
            title: "操作", width: 220, render: (_, r) => (
              <Space>
                <a onClick={() => openConvert(r)}>沉淀为 FAQ</a>
                {r.status !== "handled" && <a onClick={() => updateStatus(r.id, "handled")}>已处理</a>}
                {r.status !== "dismissed" && <a onClick={() => updateStatus(r.id, "dismissed")}>忽略</a>}
                <a style={{ color: "#ff4d4f" }} onClick={() => del(r.id)}>删除</a>
              </Space>
            ),
          },
        ]}
      />

      <Drawer
        title={`问题详情 #${drawer?.id}`}
        open={!!drawer} onClose={() => setDrawer(null)} width={560}
      >
        {drawer && (
          <Space direction="vertical" style={{ width: "100%" }}>
            <div><b>用户问题：</b><br />{drawer.question}</div>
            <div><b>当时的回答：</b><br /><pre style={{ whiteSpace: "pre-wrap" }}>{drawer.answer_given || "（无）"}</pre></div>
            <div>
              <Tag color={CATEGORY_TAG[drawer.category]?.color}>{CATEGORY_TAG[drawer.category]?.label}</Tag>
              <Tag color={STATUS_TAG[drawer.status]?.color}>{STATUS_TAG[drawer.status]?.label}</Tag>
              <Tag>来源: {drawer.source}</Tag>
              <Tag>置信度: {drawer.confidence.toFixed(3)}</Tag>
            </div>
            <div>
              <b>检索到的片段：</b>
              {(drawer.retrieval?.chunks || []).length === 0 ? <div style={{ color: "#888" }}>无</div> : (
                <ul>
                  {drawer.retrieval.chunks.map((c: any, i: number) => (
                    <li key={i}>
                      <Tag color="blue">分数 {c.score?.toFixed(3)}</Tag>
                      {c.document_title} (chunk #{c.chunk_id})
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <Button type="primary" onClick={() => { setDrawer(null); openConvert(drawer); }}>沉淀为 FAQ</Button>
          </Space>
        )}
      </Drawer>

      <Modal
        title="沉淀为 FAQ"
        open={convertOpen}
        onOk={submitConvert}
        onCancel={() => { setConvertOpen(false); setConvertItem(null); }}
        width={680} okText="保存 FAQ"
      >
        <Alert
          showIcon type="info" style={{ marginBottom: 12 }}
          message="原问题会自动加为相似问，提升下次召回率"
        />
        <Form form={form} layout="vertical">
          <Form.Item label="标准问" name="question" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item label="答案" name="answer" rules={[{ required: true }]}><Input.TextArea rows={5} /></Form.Item>
          <Form.Item label="额外相似问（每行一条，可选）" name="similar_questions">
            <Input.TextArea rows={3} placeholder={"其他可能的问法"} />
          </Form.Item>
          <Form.Item label="所属知识集" name="knowledge_set_id">
            <Select
              placeholder={sets.length === 0 ? "暂无知识集（可留空）" : "选择"}
              options={sets.map((s) => ({ value: s.id, label: s.name }))} allowClear
            />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
