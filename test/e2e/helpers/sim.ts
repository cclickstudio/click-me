// 시뮬 위저드 구동 헬퍼 — 빈화면 칩으로 sim_form을 띄우고 5단계를 채워 실행한다.
// 칩 반영 전에 '다음'을 누르면 안 넘어가므로(비활성), 매 단계 '다음'이 활성일 때만 누른다.
import { expect, type Page } from '@playwright/test';

const NEXT = '다음';

async function clickNextWhenEnabled(page: Page): Promise<void> {
  const next = page.getByRole('button', { name: NEXT });
  await expect(next).toBeEnabled({ timeout: 10_000 });
  await next.click();
}

/**
 * sim_form을 띄우고 5단계를 채워 '시뮬레이션 실행'까지 누른다.
 * 표본 수는 슬라이더 최소(1명)로 낮춰 LLM 비용·시간을 줄인다.
 */
export async function runSimulation(
  page: Page,
  opts: { adTitle: string; adContent: string },
): Promise<void> {
  // 빈화면 시뮬 칩 → /시뮬레이션 → sim_form 위젯 등장.
  await page.getByRole('button', { name: '🧪 시뮬 돌리기' }).first().click();

  // step0 제품명
  await page.getByPlaceholder('예: 클릭미 신상 크림').fill(opts.adTitle);
  await clickNextWhenEnabled(page);

  // step1 광고 설명
  await page.getByPlaceholder('광고 카피·내용').fill(opts.adContent);
  await clickNextWhenEnabled(page);

  // step2 카테고리(대분류 → 세부 류)
  const selects = page.locator('select');
  await selects.nth(0).selectOption({ label: '뷰티/미용/화장품' });
  await selects.nth(1).selectOption('3'); // 3류
  await clickNextWhenEnabled(page);

  // step3 광고 목표 칩 '구매 전환' → '다음' 활성 후 클릭
  await page.getByRole('button', { name: '구매 전환' }).click();
  await clickNextWhenEnabled(page);

  // step4 표본 수를 최소(1)로 — 슬라이더 포커스 후 Home.
  const slider = page.locator('input[type="range"]').first();
  await slider.focus();
  await page.keyboard.press('Home');

  // 실행
  await page.getByRole('button', { name: '시뮬레이션 실행' }).click();
}
