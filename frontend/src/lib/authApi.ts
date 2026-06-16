const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export type UserRole = 'ADMIN' | 'COMPANY' | 'USER';
export type UserStatus = 'ACTIVE' | 'PENDING' | 'REJECTED';

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
