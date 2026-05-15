import { Layout as AntLayout, Menu, Select, Space, Dropdown, Avatar, theme } from "antd";
import {
  DatabaseOutlined,
  FileTextOutlined,
  MessageOutlined,
  AppstoreOutlined,
  TeamOutlined,
  UserOutlined,
  AlertOutlined,
} from "@ant-design/icons";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuthStore } from "../store/auth";

const { Header, Sider, Content } = AntLayout;

export default function Layout({ children }: { children: React.ReactNode }) {
  const { tenants, tenantId, industry, setTenant, setIndustry, isPlatformAdmin, email, logout } =
    useAuthStore();
  const navigate = useNavigate();
  const loc = useLocation();
  const { token } = theme.useToken();

  const currentTenant = tenants.find((t) => t.id === tenantId);
  const industryOptions = currentTenant?.industries.map((c) => ({ value: c, label: c })) || [];

  const menuItems: any[] = [
    {
      key: "knowledge",
      icon: <DatabaseOutlined />,
      label: "知识库",
      children: [
        { key: "/knowledge/sets", label: <Link to="/knowledge/sets">知识集</Link> },
        { key: "/knowledge/documents", label: <Link to="/knowledge/documents">文档</Link>, icon: <FileTextOutlined /> },
        { key: "/knowledge/faqs", label: <Link to="/knowledge/faqs">FAQ</Link> },
      ],
    },
    { key: "/chat", icon: <MessageOutlined />, label: <Link to="/chat">对话调试</Link> },
    { key: "/unanswered", icon: <AlertOutlined />, label: <Link to="/unanswered">待优化问题</Link> },
  ];
  if (isPlatformAdmin) {
    menuItems.push({
      key: "admin",
      icon: <AppstoreOutlined />,
      label: "平台运营",
      children: [
        { key: "/admin/industries", label: <Link to="/admin/industries">行业管理</Link> },
        { key: "/admin/tenants", icon: <TeamOutlined />, label: <Link to="/admin/tenants">租户管理</Link> },
      ],
    });
  }

  return (
    <AntLayout style={{ minHeight: "100vh" }}>
      <Header style={{ display: "flex", alignItems: "center", padding: "0 24px", background: token.colorBgContainer, borderBottom: `1px solid ${token.colorBorderSecondary}` }}>
        <div style={{ fontSize: 18, fontWeight: 600, marginRight: 32 }}>🤖 RAG 客服后台</div>
        <Space size="middle" style={{ flex: 1 }}>
          <span style={{ color: "#888" }}>租户:</span>
          <Select
            value={tenantId || undefined}
            style={{ minWidth: 180 }}
            options={tenants.map((t) => ({ value: t.id, label: `${t.name} (${t.code})` }))}
            onChange={(v) => {
              const t = tenants.find((x) => x.id === v);
              setTenant(v, t?.default_industry_code || t?.industries[0] || "general");
            }}
            placeholder="选择租户"
          />
          <span style={{ color: "#888" }}>行业:</span>
          <Select
            value={industry || undefined}
            style={{ minWidth: 140 }}
            options={industryOptions}
            onChange={setIndustry}
            placeholder="选择行业"
          />
        </Space>
        <Dropdown
          menu={{
            items: [{ key: "logout", label: "退出登录", onClick: () => { logout(); navigate("/login"); } }],
          }}
        >
          <Space style={{ cursor: "pointer" }}>
            <Avatar icon={<UserOutlined />} />
            <span>{email}</span>
          </Space>
        </Dropdown>
      </Header>
      <AntLayout>
        <Sider width={220} style={{ background: token.colorBgContainer }}>
          <Menu
            mode="inline"
            selectedKeys={[loc.pathname]}
            defaultOpenKeys={["knowledge", "admin"]}
            items={menuItems}
            style={{ height: "100%", borderRight: 0 }}
          />
        </Sider>
        <Content style={{ padding: 24, background: "#f5f5f5" }}>{children}</Content>
      </AntLayout>
    </AntLayout>
  );
}
