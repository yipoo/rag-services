import { useEffect, useState } from "react";
import { Button, Card, Form, Input, InputNumber, Modal, Popconfirm, Space, Switch, Table, message } from "antd";
import { api } from "../api/client";
import { useAuthStore } from "../store/auth";

interface KSet {
  id: number;
  name: string;
  description: string;
  is_active: boolean;
  weight: number;
  scope: string;
}

export default function KnowledgeSetsPage() {
  const { tenantId, industry } = useAuthStore();
  const [data, setData] = useState<KSet[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<KSet | null>(null);
  const [form] = Form.useForm();

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get("/api/knowledge-sets");
      setData(r.data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { if (tenantId && industry) load(); }, [tenantId, industry]);

  const submit = async () => {
    const v = await form.validateFields();
    if (editing) {
      await api.patch(`/api/knowledge-sets/${editing.id}`, v);
      message.success("已更新");
    } else {
      await api.post("/api/knowledge-sets", v);
      message.success("已创建");
    }
    setOpen(false); setEditing(null); form.resetFields(); load();
  };

  const del = async (id: number) => {
    await api.delete(`/api/knowledge-sets/${id}`);
    message.success("已删除"); load();
  };

  return (
    <Card
      title={`知识集 (${industry})`}
      extra={<Button type="primary" onClick={() => { setEditing(null); form.resetFields(); setOpen(true); }}>新建知识集</Button>}
    >
      <Table
        rowKey="id"
        dataSource={data}
        loading={loading}
        columns={[
          { title: "ID", dataIndex: "id", width: 60 },
          { title: "名称", dataIndex: "name" },
          { title: "描述", dataIndex: "description" },
          { title: "范围", dataIndex: "scope", width: 90 },
          { title: "权重", dataIndex: "weight", width: 80 },
          { title: "启用", dataIndex: "is_active", width: 80, render: (v) => (v ? "✓" : "✗") },
          {
            title: "操作", width: 160, render: (_, r) => (
              <Space>
                <a onClick={() => { setEditing(r); form.setFieldsValue(r); setOpen(true); }}>编辑</a>
                <Popconfirm title="确定删除?" onConfirm={() => del(r.id)}><a>删除</a></Popconfirm>
              </Space>
            ),
          },
        ]}
      />
      <Modal title={editing ? "编辑知识集" : "新建知识集"} open={open} onOk={submit} onCancel={() => setOpen(false)}>
        <Form form={form} layout="vertical">
          <Form.Item label="名称" name="name" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item label="描述" name="description"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item label="权重" name="weight" initialValue={1.0}><InputNumber step={0.1} min={0} /></Form.Item>
          {editing && <Form.Item label="启用" name="is_active" valuePropName="checked"><Switch /></Form.Item>}
        </Form>
      </Modal>
    </Card>
  );
}
