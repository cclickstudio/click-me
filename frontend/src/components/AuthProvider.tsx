'use client';

import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { authApi, clearToken, getToken, saveToken, type UserOut } from '@/lib/authApi';
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
      .catch(() => clearToken())
      .finally(() => setLoading(false));
  }, []);

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
