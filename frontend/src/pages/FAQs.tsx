import { useEffect, useState } from "react";
import {
  Button, Card, Form, Input, Modal, Popconfirm, Select, Space, Switch, Table, Tag, Upload, message,
} from "antd";
import { UploadOutlined, DownloadOutlined } from "@ant-design/icons";
import { api } from "../api/client";
import { useAuthStore } from "../store/auth";

interface FAQ {
  id: number;
  question: string;
  answer: string;
  similar_questions: string[];
  is_active: boolean;
  hit_count: number;
  knowledge_set_id: number | null;
}

export default function FAQsPage() {
  const { tenantId, industry, token } = useAuthStore();
  const tid = tenantId;
  const [data, setData] = useState<FAQ[]>([]);
  const [sets, setSets] = useState<{ id: number; name: string }[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<FAQ | null>(null);
  const [search, setSearch] = useState("");
  const [form] = Form.useForm();

  const load = async () => {
    setLoading(true);
    try {
      const [d, s] = await Promise.all([
        api.get("/api/faqs", { params: search ? { q: search } : undefined }),
        api.get("/api/knowledge-sets"),
      ]);
      setData(d.data);
      setSets(s.data);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { if (tenantId && industry) load(); }, [tenantId, industry]);

  const submit = async () => {
    const v = await form.validateFields();
    const payload = {
      question: v.question,
      answer: v.answer,
      similar_questions: (v.similar_questions || "")
        .split("\n").map((s: string) => s.trim()).filter(Boolean),
      knowledge_set_id: v.knowledge_set_id || null,
    };
    if (editing) {
      await api.patch(`/api/faqs/${editing.id}`, { ...payload, is_active: v.is_active });
      message.success("已更新");
    } else {
      await api.post("/api/faqs", payload);
      message.success("已创建");
    }
    setOpen(false); setEditing(null); form.resetFields(); load();
  };

  const del = async (id: number) => {
    await api.delete(`/api/faqs/${id}`);
    message.success("已删除"); load();
  };

  const exportCsv = () => {
    const url = `/api/faqs/export.csv`;
    fetch(url, {
      headers: {
        Authorization: `Bearer ${token}`,
        "X-Tenant-Id": String(tid),
        "X-Industry": industry || "",
      },
    }).then(r => r.blob()).then(b => {
      const a = document.createElement("a");
      a.href = URL.createObjectURL(b);
      a.download = `faqs_${industry}.csv`;
      a.click();
    });
  };

  return (
    <Card
      title={`FAQ (${industry})`}
      extra={
        <Space>
          <Input.Search placeholder="搜索问题" allowClear onSearch={(v) => { setSearch(v); load(); }} style={{ width: 200 }} />
          <Upload
            beforeUpload={async (file) => {
              const fd = new FormData();
              fd.append("file", file);
              await api.post("/api/faqs/import", fd, { headers: { "Content-Type": "multipart/form-data" } });
              message.success("导入完成"); load();
              return false;
            }}
          >
            <Button icon={<UploadOutlined />}>导入 CSV</Button>
          </Upload>
          <Button icon={<DownloadOutlined />} onClick={exportCsv}>导出 CSV</Button>
          <Button type="primary" onClick={() => { setEditing(null); form.resetFields(); setOpen(true); }}>新建 FAQ</Button>
        </Space>
      }
    >
      <Table
        rowKey="id"
        dataSource={data}
        loading={loading}
        columns={[
          { title: "ID", dataIndex: "id", width: 60 },
          { title: "标准问", dataIndex: "question", ellipsis: true },
          {
            title: "相似问", dataIndex: "similar_questions", width: 200,
            render: (arr: string[]) => arr?.length ? <Tag color="blue">{arr.length} 条</Tag> : "-",
          },
          { title: "命中", dataIndex: "hit_count", width: 80 },
          {
            title: "状态", dataIndex: "is_active", width: 80,
            render: (v) => v ? <Tag color="green">启用</Tag> : <Tag>禁用</Tag>,
          },
          {
            title: "操作", width: 140, render: (_, r) => (
              <Space>
                <a onClick={() => {
                  setEditing(r);
                  form.setFieldsValue({
                    ...r,
                    similar_questions: (r.similar_questions || []).join("\n"),
                  });
                  setOpen(true);
                }}>编辑</a>
                <Popconfirm title="确定删除?" onConfirm={() => del(r.id)}><a>删除</a></Popconfirm>
              </Space>
            ),
          },
        ]}
      />

      <Modal
        title={editing ? "编辑 FAQ" : "新建 FAQ"}
        open={open} onOk={submit} onCancel={() => setOpen(false)} width={720}
      >
        <Form form={form} layout="vertical">
          <Form.Item label="标准问题" name="question" rules={[{ required: true }]}>
            <Input placeholder="例如：如何申请退款？" />
          </Form.Item>
          <Form.Item label="答案" name="answer" rules={[{ required: true }]}>
            <Input.TextArea rows={5} />
          </Form.Item>
          <Form.Item
            label="相似问（每行一条，提升召回）"
            name="similar_questions"
            tooltip="多写几条相似的问法，能显著提高被召回的概率"
          >
            <Input.TextArea
              rows={4}
              placeholder={"退款怎么操作？\n我想退钱\n如何退费"}
            />
          </Form.Item>
          <Form.Item
            label="所属知识集（可选）"
            name="knowledge_set_id"
            extra={sets.length === 0
              ? <span style={{ color: "#fa8c16" }}>当前行业还没有知识集，可先到"知识库 → 知识集"创建，或留空</span>
              : null}
          >
            <Select
              placeholder={sets.length === 0 ? "暂无知识集（可留空）" : "选择一个知识集"}
              options={sets.map((s) => ({ value: s.id, label: s.name }))}
              disabled={sets.length === 0}
              allowClear
            />
          </Form.Item>
          {editing && (
            <Form.Item label="启用" name="is_active" valuePropName="checked">
              <Switch />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </Card>
  );
}
