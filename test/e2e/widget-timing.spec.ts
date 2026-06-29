// P4 E2E② — 위젯 타이밍.
// 반응 완료(결과 위젯 "✅ 시뮬레이션 결과") 직후 토론 위젯("AI 소비자 토론을 시작했어요")이
// 둘 다 보이는지 검증한다. 결과만 뜨고 토론이 한참 뒤거나 안 뜨는 회귀를 잡는다.
import { test, expect } from '@playwright/test';
import { enterGundoyeonChat } from './helpers/project';
import { runSimulation } from './helpers/sim';

test.setTimeout(240_000);

test('반응 완료 직후 결과 위젯과 토론 위젯이 함께 보인다', async ({ page }) => {
  await enterGundoyeonChat(page);
  await runSimulation(page, {
    adTitle: `E2E타이밍-${Date.now()}`,
    adContent: '모공까지 채우는 고보습 에센스. 지금 첫 구매 시 사은품 증정.',
  });

  // 결과 위젯(헤더 + KPI 라벨)이 뜰 때까지 — 실행~결과 최대 90s.
  const resultHeader = page.getByText('✅ 시뮬레이션 결과').first();
  await expect(resultHeader).toBeVisible({ timeout: 90_000 });
  // 결과 위젯이 실제 KPI를 렌더했는지(메시지 텍스트가 아니라 위젯 내용).
  await expect(page.getByText('클릭 의향률').first()).toBeVisible({ timeout: 15_000 });

  // ★ 결과가 뜬 "직후" 토론 위젯도 떠야 한다 — 결과 시점 기준 60s 안.
  const debate = page.getByText('AI 소비자 토론을 시작했어요').first();
  await expect(debate).toBeVisible({ timeout: 60_000 });

  // 둘 다 동시에 화면에 있는지 최종 확인(결과가 토론 등장 후 사라지지 않음).
  await expect(resultHeader).toBeVisible();
  await expect(debate).toBeVisible();
});
