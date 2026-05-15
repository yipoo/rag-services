import { useEffect, useState } from "react";
import { Button, Card, Form, Input, Modal, Popconfirm, Select, Space, Table, Tag, Upload, message } from "antd";
import { UploadOutlined } from "@ant-design/icons";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useAuthStore } from "../store/auth";

interface Doc {
  id: number; title: string; source_type: string; status: string;
  chunk_count: number; size_bytes: number; error_message: string;
  knowledge_set_id: number | null; created_at: string;
}

const STATUS_COLOR: Record<string, string> = {
  pending: "default", parsing: "processing", parsed: "blue",
  published: "green", failed: "red", archived: "default",
};

export default function DocumentsPage() {
  const { tenantId, industry } = useAuthStore();
  const [data, setData] = useState<Doc[]>([]);
  const [sets, setSets] = useState<{ id: number; name: string }[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [manualOpen, setManualOpen] = useState(false);
  const [urlOpen, setUrlOpen] = useState(false);
  const [form] = Form.useForm();

  const load = async () => {
    setLoading(true);
    try {
      const [d, s] = await Promise.all([
        api.get("/api/documents"),
        api.get("/api/knowledge-sets"),
      ]);
      setData(d.data); setSets(s.data);
    } finally { setLoading(false); }
  };
  useEffect(() => { if (tenantId && industry) load(); }, [tenantId, industry]);

  // poll while there are processing documents
  useEffect(() => {
    const hasProcessing = data.some((d) => ["pending", "parsing"].includes(d.status));
    if (!hasProcessing) return;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [data]);

  const setOptions = sets.map((s) => ({ value: s.id, label: s.name }));

  return (
    <Card
      title={`文档 (${industry})`}
      extra={
        <Space>
          <Button onClick={() => { form.resetFields(); setManualOpen(true); }}>手动录入</Button>
          <Button onClick={() => { form.resetFields(); setUrlOpen(true); }}>抓取 URL</Button>
          <Button type="primary" icon={<UploadOutlined />} onClick={() => { form.resetFields(); setUploadOpen(true); }}>上传文件</Button>
        </Space>
      }
    >
      <Table
        rowKey="id"
        dataSource={data}
        loading={loading}
        columns={[
          { title: "ID", dataIndex: "id", width: 60 },
          { title: "标题", dataIndex: "title", render: (v, r) => <Link to={`/knowledge/documents/${r.id}`}>{v}</Link> },
          { title: "来源", dataIndex: "source_type", width: 90 },
          {
            title: "状态", dataIndex: "status", width: 100,
            render: (v, r) => (
              <Space direction="vertical" size={0}>
                <Tag color={STATUS_COLOR[v] || "default"}>{v}</Tag>
                {r.error_message && <span style={{ color: "red", fontSize: 11 }}>{r.error_message}</span>}
              </Space>
            ),
          },
          { title: "切片数", dataIndex: "chunk_count", width: 90 },
          { title: "大小", dataIndex: "size_bytes", width: 100, render: (v) => `${(v / 1024).toFixed(1)} KB` },
          {
            title: "操作", width: 200, render: (_, r) => (
              <Space>
                <a onClick={async () => { await api.post(`/api/documents/${r.id}/reprocess`); message.success("已触发重新处理"); load(); }}>重新处理</a>
                <Popconfirm title="确定删除?" onConfirm={async () => { await api.delete(`/api/documents/${r.id}`); message.success("已删除"); load(); }}>
                  <a>删除</a>
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />

      <Modal title="上传文件" open={uploadOpen} onCancel={() => setUploadOpen(false)} footer={null}>
        <Form form={form} layout="vertical">
          <Form.Item label="所属知识集" name="knowledge_set_id"><Select options={setOptions} allowClear /></Form.Item>
          <Form.Item label="标题(可选)" name="title"><Input placeholder="留空则用文件名" /></Form.Item>
          <Upload
            beforeUpload={async (file) => {
              const v = form.getFieldsValue();
              const fd = new FormData();
              fd.append("file", file);
              if (v.title) fd.append("title", v.title);
              if (v.knowledge_set_id) fd.append("knowledge_set_id", String(v.knowledge_set_id));
              try {
                await api.post("/api/documents/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
                message.success("已上传，正在解析");
                setUploadOpen(false); load();
              } catch (e: any) {
                message.error(e?.response?.data?.detail || "上传失败");
              }
              return false;
            }}
          >
            <Button icon={<UploadOutlined />}>选择文件 (PDF/Word/TXT/MD)</Button>
          </Upload>
        </Form>
      </Modal>

      <Modal title="手动录入" open={manualOpen} onOk={async () => {
        const v = await form.validateFields();
        await api.post("/api/documents/manual", v);
        message.success("已创建，正在处理"); setManualOpen(false); load();
      }} onCancel={() => setManualOpen(false)} width={720}>
        <Form form={form} layout="vertical">
          <Form.Item label="标题" name="title" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item label="所属知识集" name="knowledge_set_id"><Select options={setOptions} allowClear /></Form.Item>
          <Form.Item label="内容" name="content" rules={[{ required: true }]}><Input.TextArea rows={10} /></Form.Item>
        </Form>
      </Modal>

      <Modal title="抓取 URL" open={urlOpen} onOk={async () => {
        const v = await form.validateFields();
        await api.post("/api/documents/url", v);
        message.success("已创建，正在抓取"); setUrlOpen(false); load();
      }} onCancel={() => setUrlOpen(false)}>
        <Form form={form} layout="vertical">
          <Form.Item label="URL" name="url" rules={[{ required: true, type: "url" }]}><Input /></Form.Item>
          <Form.Item label="标题(可选)" name="title"><Input /></Form.Item>
          <Form.Item label="所属知识集" name="knowledge_set_id"><Select options={setOptions} allowClear /></Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
