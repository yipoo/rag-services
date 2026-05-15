import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface TenantBrief {
  id: number;
  code: string;
  name: string;
  role: string;
  default_industry_code: string | null;
  industries: string[];
}

interface AuthState {
  token: string | null;
  email: string | null;
  isPlatformAdmin: boolean;
  tenants: TenantBrief[];
  tenantId: number | null;
  industry: string | null;
  setLogin: (data: { token: string; email: string; isPlatformAdmin: boolean }) => void;
  setTenants: (tenants: TenantBrief[]) => void;
  setTenant: (tenantId: number, industry: string | null) => void;
  setIndustry: (industry: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      email: null,
      isPlatformAdmin: false,
      tenants: [],
      tenantId: null,
      industry: null,
      setLogin: ({ token, email, isPlatformAdmin }) =>
        set({ token, email, isPlatformAdmin }),
      setTenants: (tenants) => {
        const cur = get();
        if (!cur.tenantId && tenants.length > 0) {
          set({
            tenants,
            tenantId: tenants[0].id,
            industry:
              tenants[0].default_industry_code || tenants[0].industries[0] || "general",
          });
        } else {
          set({ tenants });
        }
      },
      setTenant: (tenantId, industry) => set({ tenantId, industry }),
      setIndustry: (industry) => set({ industry }),
      logout: () =>
        set({
          token: null,
          email: null,
          isPlatformAdmin: false,
          tenants: [],
          tenantId: null,
          industry: null,
        }),
    }),
    { name: "rag-auth" }
  )
);
