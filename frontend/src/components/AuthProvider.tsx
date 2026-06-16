'use client';

import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { authApi, clearToken, getToken, saveToken, type UserOut } from '@/lib/authApi';

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
    setToken(null);
    setUser(null);
  }, []);

  return <Ctx.Provider value={{ user, token, loading, login, logout }}>{children}</Ctx.Provider>;
}

export const useAuth = () => useContext(Ctx);
