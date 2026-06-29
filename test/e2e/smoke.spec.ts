// P2 스모크 — 토큰 주입 로그인 + 건도연 채팅 진입이 동작하는지(셋업 자체 검증).
// 시뮬을 돌리지 않으므로 빠르고, P3~P5의 토대가 되는 헬퍼가 살아있음을 보장한다.
import { test, expect } from '@playwright/test';
import { enterGundoyeonChat } from './helpers/project';

test('토큰 주입으로 건도연 채팅에 진입하면 sign-in으로 안 튕기고 컴포저가 보인다', async ({
  page,
}) => {
  await enterGundoyeonChat(page);

  // 빈 채팅 화면의 안내문과 입력 컴포저가 떠야 한다.
  await expect(page.getByText('광고에 대해 무엇이든 물어보세요')).toBeVisible({
    timeout: 20_000,
  });
  await expect(
    page.getByPlaceholder('메시지를 입력하세요... (/로 명령어, Shift+Enter로 줄바꿈)'),
  ).toBeVisible();
  // 빈화면 시뮬 칩도 존재(P3에서 사용) — 빈화면 그리드·하단 칩 두 곳에 있어 first()로 한정.
  await expect(page.getByRole('button', { name: '🧪 시뮬 돌리기' }).first()).toBeVisible();
});
