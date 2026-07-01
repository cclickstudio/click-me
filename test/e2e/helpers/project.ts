// 건도연 프로젝트 채팅 진입 헬퍼.
// /chat/<pid>로 직접 이동하면 프로젝트 게이트 클릭 없이 세션 게이트(또는 세션)로 들어간다.
// ProjectContext는 토큰 준비 후 1회 fetch라 약간 지연 → 진입 후 sign-in 리다이렉트가 없을 때까지 기다린다.
import { expect, type Page } from '@playwright/test';
import { injectToken, userToken, PROJECT_ID } from './auth';

/** 토큰 주입 후 건도연 프로젝트의 새 채팅(/chat/<pid>/new)으로 진입한다. */
export async function enterGundoyeonChat(page: Page): Promise<void> {
  await injectToken(page, userToken());
  await page.goto(`/chat/${PROJECT_ID}/new`);
  // 토큰이 무효면 (app) 레이아웃이 /sign-in으로 보낸다 — 그렇지 않음을 확인.
  await expect(page).not.toHaveURL(/\/sign-in/, { timeout: 15_000 });
}

/** 특정 세션 URL(/chat/<pid>/<sid>)로 직접 진입(새로고침 복원 검증용). */
export async function gotoSession(page: Page, sessionId: string): Promise<void> {
  await injectToken(page, userToken());
  await page.goto(`/chat/${PROJECT_ID}/${sessionId}`);
  await expect(page).not.toHaveURL(/\/sign-in/, { timeout: 15_000 });
}
