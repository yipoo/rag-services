import { Button, Card, Form, Input, message } from "antd";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuthStore } from "../store/auth";

export default function LoginPage() {
  const navigate = useNavigate();
  const setLogin = useAuthStore((s) => s.setLogin);
  const setTenants = useAuthStore((s) => s.setTenants);

  const onFinish = async (values: { email: string; password: string }) => {
    try {
      const r = await api.post("/api/auth/login", values);
      setLogin({
        token: r.data.access_token,
        email: r.data.email,
        isPlatformAdmin: r.data.is_platform_admin,
      });
      const me = await api.get("/api/auth/me", {
        headers: { Authorization: `Bearer ${r.data.access_token}` },
      });
      setTenants(me.data.tenants);
      message.success("登录成功");
      navigate("/");
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "登录失败");
    }
  };

  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "#f0f2f5" }}>
      <Card title="RAG 客服管理后台" style={{ width: 380 }}>
        <Form layout="vertical" onFinish={onFinish} initialValues={{ email: "admin@example.com", password: "admin123456" }}>
          <Form.Item label="邮箱" name="email" rules={[{ required: true, type: "email" }]}>
            <Input />
          </Form.Item>
          <Form.Item label="密码" name="password" rules={[{ required: true }]}>
            <Input.Password />
          </Form.Item>
          <Button type="primary" htmlType="submit" block>登录</Button>
        </Form>
      </Card>
    </div>
  );
}
