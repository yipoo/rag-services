import { useEffect, useState } from "react";
import { Button, Card, Form, Input, Modal, Select, Table, Tag, message } from "antd";
import { api } from "../api/client";

export default function TenantsPage() {
  const [data, setData] = useState<any[]>([]);
  const [industries, setIndustries] = useState<any[]>([]);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();

  const load = async () => {
    const [t, i] = await Promise.all([api.get("/api/admin/tenants"), api.get("/api/industries")]);
    setData(t.data); setIndustries(i.data);
  };
  useEffect(() => { load(); }, []);

  const submit = async () => {
    const v = await form.validateFields();
    await api.post("/api/admin/tenants", v);
    message.success("已创建"); setOpen(false); form.resetFields(); load();
  };

  return (
    <Card title="租户管理" extra={<Button type="primary" onClick={() => setOpen(true)}>新建租户</Button>}>
      <Table
        rowKey="id"
        dataSource={data}
        columns={[
          { title: "ID", dataIndex: "id", width: 60 },
          { title: "Code", dataIndex: "code", width: 140 },
          { title: "名称", dataIndex: "name" },
          { title: "套餐", dataIndex: "plan", width: 100 },
          { title: "默认行业", dataIndex: "default_industry_code", width: 120 },
          { title: "订阅行业", dataIndex: "industries", render: (arr: string[]) => arr.map((c) => <Tag key={c}>{c}</Tag>) },
        ]}
      />
      <Modal title="新建租户" open={open} onOk={submit} onCancel={() => setOpen(false)} width={560}>
        <Form form={form} layout="vertical">
          <Form.Item label="租户Code" name="code" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item label="租户名称" name="name" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item label="套餐" name="plan" initialValue="basic"><Input /></Form.Item>
          <Form.Item label="订阅行业" name="industries" rules={[{ required: true }]}>
            <Select mode="multiple" options={industries.map((i) => ({ value: i.code, label: `${i.name} (${i.code})` }))} />
          </Form.Item>
          <Form.Item label="默认行业" name="default_industry_code"><Input /></Form.Item>
          <Form.Item label="管理员邮箱" name="admin_email" rules={[{ required: true, type: "email" }]}><Input /></Form.Item>
          <Form.Item label="管理员密码" name="admin_password" rules={[{ required: true, min: 8 }]}><Input.Password /></Form.Item>
          <Form.Item label="管理员姓名" name="admin_name"><Input /></Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
