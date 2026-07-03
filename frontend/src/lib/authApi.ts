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
      const tokens = await cognitoLogin(login_id, password);
      // refresh 토큰은 여기서 저장(재발급용), access 토큰 저장은 AuthProvider.login이 담당.
      saveRefreshToken(tokens.refreshToken);
      const user = await authApi.me(tokens.accessToken);
      return { access_token: tokens.accessToken, token_type: 'bearer', user };
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

// ── 토큰 저장: 쿠키 ──────────────────────────────────────────────
// localStorage → 쿠키로 이전. JS가 읽어 Authorization 헤더에 실어야 하므로 httpOnly는 불가하며,
// EventSource(SSE)는 same-origin 쿠키를 자동 전송하므로 쿠키 저장이 헤더 못 붙이는 스트림도 커버한다.
// SameSite=Lax + (https면) Secure. access는 Cognito 수명(1h), refresh는 장기(30d) 기준 max-age.
const ACCESS_KEY = 'access_token';
const REFRESH_KEY = 'refresh_token';
const ACCESS_MAX_AGE = 60 * 60; // 1시간
const REFRESH_MAX_AGE = 60 * 60 * 24 * 30; // 30일
export const TOKEN_KEY = ACCESS_KEY; // 하위호환 별칭

function setCookie(name: string, value: string, maxAge: number): void {
  if (typeof document === 'undefined') return;
  const secure = location.protocol === 'https:' ? '; Secure' : '';
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/; max-age=${maxAge}; SameSite=Lax${secure}`;
}

function getCookie(name: string): string | null {
  if (typeof document === 'undefined') return null;
  const m = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
  return m ? decodeURIComponent(m[1]) : null;
}

function delCookie(name: string): void {
  if (typeof document === 'undefined') return;
  document.cookie = `${name}=; path=/; max-age=0; SameSite=Lax`;
}

export const saveToken = (t: string) => setCookie(ACCESS_KEY, t, ACCESS_MAX_AGE);
export const getToken = (): string | null => getCookie(ACCESS_KEY);
export const saveRefreshToken = (t: string) => setCookie(REFRESH_KEY, t, REFRESH_MAX_AGE);
export const getRefreshToken = (): string | null => getCookie(REFRESH_KEY);
export const clearToken = () => {
  delCookie(ACCESS_KEY);
  delCookie(REFRESH_KEY);
};

// access 토큰의 username claim 추출(refresh 시 CognitoUser 지정용). 검증 없이 payload만 디코드.
function usernameFromToken(jwtToken: string): string | null {
  try {
    const seg = jwtToken.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    const payload = JSON.parse(atob(seg));
    return payload.username ?? payload['cognito:username'] ?? null;
  } catch {
    return null;
  }
}

// access 만료(401) 시 refresh 토큰으로 재발급. 성공 시 새 access 토큰 반환, 실패 시 토큰 정리 후 null.
export async function refreshAccessToken(): Promise<string | null> {
  const provider = process.env.NEXT_PUBLIC_AUTH_PROVIDER ?? 'local';
  if (provider !== 'cognito') return null;
  const refresh = getRefreshToken();
  const current = getToken();
  const username = current && usernameFromToken(current);
  if (!refresh || !username) return null;
  try {
    const { cognitoRefresh } = await import('./cognito');
    const tokens = await cognitoRefresh(username, refresh);
    saveToken(tokens.accessToken);
    saveRefreshToken(tokens.refreshToken);
    return tokens.accessToken;
  } catch {
    clearToken();
    return null;
  }
}
