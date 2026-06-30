const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export type UserRole = 'ADMIN' | 'COMPANY' | 'USER';
export type UserStatus = 'ACTIVE';

export type UserOut = {
  id: string;
  login_id: string;
  name: string;
  role: UserRole;
  status: UserStatus;
  must_change_password: boolean;
  phone_num: string | null;
  user_email: string | null;
  team_id: string | null;
  organization_id: string | null;
};

export type AuthResponse = {
  access_token: string;
  token_type: string;
  user: UserOut;
};

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options.headers },
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail ?? '요청 실패');
  return data as T;
}

export const authApi = {
  // 통합 로그인 진입점 — 화면은 이 함수만 호출. provider에 따라 cognito↔자체 JWT로 분기.
  // cognito: amazon-cognito-identity-js로 인증(ID 토큰) → me()로 우리 User 조회.
  // local(기본): 기존 POST /api/auth/login.
  signIn: async (login_id: string, password: string): Promise<AuthResponse> => {
    const provider = process.env.NEXT_PUBLIC_AUTH_PROVIDER ?? 'local';
    if (provider === 'cognito') {
      // 동적 import — local 모드 번들에 Cognito SDK를 포함하지 않는다.
      const { cognitoLogin } = await import('./cognito');
      const token = await cognitoLogin(login_id, password);
      const user = await authApi.me(token);
      return { access_token: token, token_type: 'bearer', user };
    }
    return authApi.login({ login_id, password });
  },

  login: (body: { login_id: string; password: string }) =>
    request<AuthResponse>('/api/auth/login', { method: 'POST', body: JSON.stringify(body) }),

  me: (token: string) =>
    request<UserOut>('/api/auth/me', { headers: { Authorization: `Bearer ${token}` } }),

  changePassword: (token: string, new_password: string) =>
    request<{ ok: boolean }>('/api/auth/change-password', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: JSON.stringify({ new_password }),
    }),

  updateProfile: (
    token: string,
    body: { name?: string; phone_num?: string | null; user_email?: string | null },
  ) =>
    request<UserOut>('/api/auth/me', {
      method: 'PATCH',
      headers: { Authorization: `Bearer ${token}` },
      body: JSON.stringify(body),
    }),
};

export const TOKEN_KEY = 'clickme_token';
export const saveToken = (t: string) => localStorage.setItem(TOKEN_KEY, t);
export const getToken = (): string | null =>
  typeof window === 'undefined' ? null : localStorage.getItem(TOKEN_KEY);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);
