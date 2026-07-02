'use client';

import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import {
  authApi,
  clearToken,
  getToken,
  refreshAccessToken,
  saveToken,
  type UserOut,
} from '@/lib/authApi';
import { setAdminOrgId } from '@/lib/api';

type AuthCtx = {
  user: UserOut | null;
  token: string | null;
  loading: boolean;
  login: (token: string, user: UserOut) => void;
  logout: () => void;
};

const Ctx = createContext<AuthCtx>({
  user: null, token: null, loading: true,
  login: () => {}, logout: () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserOut | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const t = getToken();
    if (!t) { setLoading(false); return; }
    authApi.me(t)
      .then((u) => { setUser(u); setToken(t); })
      .catch(async () => {
        // access 만료 가능성 — refresh 토큰으로 1회 재발급 후 재조회(새로고침 시 로그인 유지).
        const nt = await refreshAccessToken();
        if (nt) {
          try {
            const u = await authApi.me(nt);
            setUser(u);
            setToken(nt);
            return;
          } catch {
            /* 재발급했지만 조회 실패 → 아래에서 정리 */
          }
        }
        clearToken();
      })
      .finally(() => setLoading(false));
  }, []);

  // 비-admin이 impersonation 힌트(adminOrgId)를 들고 다니지 않게 정리 — 로그인/계정 전환/me() 실패 반영.
  // loading 중(user 미해석)에는 지우지 않는다 → 새로고침 시 admin의 선택이 날아가지 않도록.
  useEffect(() => {
    if (!loading && (!user || user.role !== 'ADMIN')) setAdminOrgId(null);
  }, [loading, user]);

  const login = useCallback((t: string, u: UserOut) => {
    saveToken(t);
    setToken(t);
    setUser(u);
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setAdminOrgId(null); // admin impersonation 선택도 함께 소멸 — 비-admin 재로그인 시 누출 방지.
    setToken(null);
    setUser(null);
    // cognito 모드면 Cognito 로컬 세션도 정리(fire-and-forget, local 모드는 no-op).
    import('@/lib/cognito').then((m) => m.cognitoSignOut()).catch(() => {});
  }, []);

  return <Ctx.Provider value={{ user, token, loading, login, logout }}>{children}</Ctx.Provider>;
}

export const useAuth = () => useContext(Ctx);
