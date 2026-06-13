const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export type UserRole = 'ADMIN' | 'COMPANY' | 'USER';
export type UserStatus = 'ACTIVE' | 'PENDING' | 'REJECTED';

export type UserOut = {
  id: string;
  email: string;
  name: string;
  role: UserRole;
  status: UserStatus;
  organization_id: string | null;
};

export type AuthResponse = {
  access_token: string;
  token_type: string;
  user: UserOut;
};

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail ?? '요청 실패');
  return data as T;
}

export const authApi = {
  signupCompany: (body: { name: string; email: string; password: string; company_name: string }) =>
    request<AuthResponse>('/api/auth/signup/company', { method: 'POST', body: JSON.stringify(body) }),

  signupUser: (body: { name: string; email: string; password: string; organization_id: string }) =>
    request<AuthResponse>('/api/auth/signup/user', { method: 'POST', body: JSON.stringify(body) }),

  login: (body: { email: string; password: string }) =>
    request<AuthResponse>('/api/auth/login', { method: 'POST', body: JSON.stringify(body) }),

  me: (token: string) =>
    request<UserOut>('/api/auth/me', { headers: { Authorization: `Bearer ${token}` } }),
};

export const TOKEN_KEY = 'clickme_token';
export const saveToken = (t: string) => localStorage.setItem(TOKEN_KEY, t);
export const getToken = (): string | null =>
  typeof window === 'undefined' ? null : localStorage.getItem(TOKEN_KEY);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);
