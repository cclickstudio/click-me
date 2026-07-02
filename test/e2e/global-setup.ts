// E2E 전역 셋업 — backend에서 USER·ADMIN JWT를 즉석 발급해 .auth-tokens.json에 기록한다.
// 토큰을 코드에 하드코딩하지 않는 이유: 7일 만료라 시간이 지나면 깨지고, jwt_secret 변경에도 약하다.
import { execFileSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';
import path from 'node:path';

const BACKEND_DIR = path.resolve(__dirname, '../../backend');
const TOKENS_PATH = path.resolve(__dirname, '.auth-tokens.json');

export const USER_ID = '73859b11-03bf-4b1c-80c3-7d7895ed5725';
export const ADMIN_ID = '2fb541e2-8abb-48ad-99f8-e2f1054d3d9d';
export const PROJECT_ID = '8b33546d-e763-44fb-a222-6f02ba9a6707';

function mint(userId: string, role: string): string {
  const code = `from core.auth import create_access_token; print(create_access_token('${userId}','${role}'))`;
  const out = execFileSync('uv', ['run', 'python', '-c', code], {
    cwd: BACKEND_DIR,
    encoding: 'utf-8',
  });
  return out.trim().split(/\r?\n/).pop()!.trim();
}

export default function globalSetup() {
  const tokens = {
    user: mint(USER_ID, 'USER'),
    admin: mint(ADMIN_ID, 'ADMIN'),
  };
  if (!tokens.user || !tokens.admin) {
    throw new Error('토큰 발급 실패 — backend(uv) 환경을 확인하세요.');
  }
  writeFileSync(TOKENS_PATH, JSON.stringify(tokens, null, 2));
}
