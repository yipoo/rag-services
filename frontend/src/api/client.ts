import axios from "axios";
import { useAuthStore } from "../store/auth";

export const api = axios.create({ baseURL: "" });

api.interceptors.request.use((config) => {
  const { token, tenantId, industry } = useAuthStore.getState();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  if (tenantId) config.headers["X-Tenant-Id"] = String(tenantId);
  if (industry) config.headers["X-Industry"] = industry;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err?.response?.status === 401) {
      useAuthStore.getState().logout();
    }
    return Promise.reject(err);
  }
);
