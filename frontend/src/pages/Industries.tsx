import { useEffect, useState } from "react";
import { Button, Card, Form, Input, InputNumber, Modal, Table, message } from "antd";
import { api } from "../api/client";

export default function IndustriesPage() {
  const [data, setData] = useState<any[]>([]);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();

  const load = async () => setData((await api.get("/api/industries")).data);
  useEffect(() => { load(); }, []);

  const submit = async () => {
    const v = await form.validateFields();
    await api.post("/api/industries", v);
    message.success("已创建"); setOpen(false); form.resetFields(); load();
  };

  return (
    <Card title="行业管理" extra={<Button type="primary" onClick={() => setOpen(true)}>新建行业</Button>}>
      <Table
        rowKey="id"
        dataSource={data}
        columns={[
          { title: "Code", dataIndex: "code", width: 140 },
          { title: "名称", dataIndex: "name", width: 140 },
          { title: "描述", dataIndex: "description" },
          { title: "转人工阈值", dataIndex: "handoff_threshold", width: 110 },
          { title: "启用", dataIndex: "is_active", width: 80, render: (v) => (v ? "✓" : "✗") },
        ]}
      />
      <Modal title="新建行业" open={open} onOk={submit} onCancel={() => setOpen(false)}>
        <Form form={form} layout="vertical">
          <Form.Item label="Code(英文,创建后不可改)" name="code" rules={[{ required: true, pattern: /^[a-z0-9_]+$/ }]}><Input /></Form.Item>
          <Form.Item label="名称" name="name" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item label="描述" name="description"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item label="默认 Prompt" name="default_prompt"><Input.TextArea rows={4} /></Form.Item>
          <Form.Item label="转人工阈值" name="handoff_threshold" initialValue={0.6}><InputNumber min={0} max={1} step={0.05} /></Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
