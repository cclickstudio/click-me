// 토큰 주입 로그인 헬퍼 — /sign-in 폼 합성입력은 onSubmit이 잘 안 걸려 신뢰 못 한다.
// 대신 globalSetup이 발급한 토큰을 localStorage('clickme_token')에 addInitScript로 심는다.
import { readFileSync } from 'node:fs';
import path from 'node:path';
import type { Page } from '@playwright/test';

const TOKENS_PATH = path.resolve(__dirname, '..', '.auth-tokens.json');

export const USER_ID = '73859b11-03bf-4b1c-80c3-7d7895ed5725';
export const ADMIN_ID = '2fb541e2-8abb-48ad-99f8-e2f1054d3d9d';
export const PROJECT_ID = '8b33546d-e763-44fb-a222-6f02ba9a6707'; // 건도연

type Tokens = { user: string; admin: string };

let cached: Tokens | null = null;

export function tokens(): Tokens {
  if (!cached) {
    cached = JSON.parse(readFileSync(TOKENS_PATH, 'utf-8')) as Tokens;
  }
  return cached;
}

export function userToken(): string {
  return tokens().user;
}

export function adminToken(): string {
  return tokens().admin;
}

/** 페이지 첫 스크립트로 토큰을 심어, 이후 어떤 페이지로 이동해도 로그인 상태가 되게 한다. */
export async function injectToken(page: Page, token: string): Promise<void> {
  await page.addInitScript((t) => {
    window.localStorage.setItem('clickme_token', t);
  }, token);
}
