import { useEffect } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuthStore } from "./store/auth";
import { api } from "./api/client";
import LoginPage from "./pages/Login";
import Layout from "./components/Layout";
import KnowledgeSetsPage from "./pages/KnowledgeSets";
import DocumentsPage from "./pages/Documents";
import DocumentDetailPage from "./pages/DocumentDetail";
import FAQsPage from "./pages/FAQs";
import UnansweredPage from "./pages/Unanswered";
import ChatPage from "./pages/Chat";
import IndustriesPage from "./pages/Industries";
import TenantsPage from "./pages/Tenants";

function Private({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token);
  return token ? <>{children}</> : <Navigate to="/login" replace />;
}

export default function App() {
  const { token, setTenants } = useAuthStore();

  useEffect(() => {
    if (token) {
      api.get("/api/auth/me").then((r) => setTenants(r.data.tenants));
    }
  }, [token]);

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/*"
        element={
          <Private>
            <Layout>
              <Routes>
                <Route path="/" element={<Navigate to="/knowledge/documents" replace />} />
                <Route path="/knowledge/sets" element={<KnowledgeSetsPage />} />
                <Route path="/knowledge/documents" element={<DocumentsPage />} />
                <Route path="/knowledge/documents/:id" element={<DocumentDetailPage />} />
                <Route path="/knowledge/faqs" element={<FAQsPage />} />
                <Route path="/unanswered" element={<UnansweredPage />} />
                <Route path="/chat" element={<ChatPage />} />
                <Route path="/admin/industries" element={<IndustriesPage />} />
                <Route path="/admin/tenants" element={<TenantsPage />} />
              </Routes>
            </Layout>
          </Private>
        }
      />
    </Routes>
  );
}
