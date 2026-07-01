// P3 E2E① — 시뮬 영속 + 새로고침 복원 (가장 중요).
// 실제 LLM 시뮬을 1회 돌려 ① DB에 sim_input·sim_result·debate_stream 위젯이 남는지,
// ② 그 세션 URL로 직접 재진입(새로고침 복원) 시 결과·토론 위젯이 다시 보이는지 검증한다.
import { test, expect } from '@playwright/test';
import { enterGundoyeonChat, gotoSession } from './helpers/project';
import { runSimulation } from './helpers/sim';
import { latestSession, type LatestSession } from './helpers/db';
import { PROJECT_ID } from './helpers/auth';

// 시뮬은 실제 호출이라 오래 걸린다 — 결과 90s·토론 포함 전체 4분 여유.
test.setTimeout(240_000);

test('시뮬 결과·토론이 DB에 영속되고 세션 URL 재진입으로 복원된다', async ({ page }) => {
  const adTitle = `E2E시뮬-${Date.now()}`;

  await enterGundoyeonChat(page);
  await runSimulation(page, {
    adTitle,
    adContent: '촉촉함이 24시간 지속되는 저자극 수분 크림. 첫 구매 30% 할인.',
  });

  // 결과 위젯(텍스트 "시뮬레이션 결과")이 뜰 때까지 — 실행~결과 최대 90s.
  await expect(page.getByText('시뮬레이션 결과', { exact: false }).first()).toBeVisible({
    timeout: 90_000,
  });
  // 토론 stream 메시지도 떠야 한다 — 토론 시작까지 최대 60s 추가.
  await expect(page.getByText('AI 소비자 토론을 시작했어요').first()).toBeVisible({
    timeout: 60_000,
  });

  // ── ① DB 영속 검증 — 위젯 시퀀스를 폴링으로 확인(영속은 비동기라 약간 지연될 수 있음). ──
  let latest: LatestSession = { session_id: null, widget_types: [], ad_titles: [], message_count: 0 };
  const want = ['sim_input', 'sim_result', 'debate_stream'];
  for (let i = 0; i < 20; i++) {
    latest = latestSession(PROJECT_ID);
    if (want.every((t) => latest.widget_types.includes(t))) break;
    await page.waitForTimeout(1500);
  }
  expect(latest.session_id, '건도연 프로젝트의 최신 세션을 찾지 못함').not.toBeNull();
  for (const t of want) {
    expect(latest.widget_types, `위젯 시퀀스에 ${t}가 없음`).toContain(t);
  }
  // 제품명은 content가 아니라 sim_input 위젯 data.ad_title에 남는다.
  expect(latest.ad_titles, 'sim_input의 ad_title에 제품명이 없음').toContain(adTitle);

  // ── ② 새로고침 복원 — 세션 URL로 직접 재진입 시 결과·토론 위젯이 다시 보인다. ──
  const sessionId = latest.session_id!;
  await gotoSession(page, sessionId);
  await expect(page).toHaveURL(new RegExp(`/chat/${PROJECT_ID}/${sessionId}`));
  // 결과 요약·토론 위젯이 복원돼야 한다(재구독 시 토론 스트림은 처음부터 replay).
  await expect(page.getByText('시뮬레이션 결과', { exact: false }).first()).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByText('AI 소비자 토론을 시작했어요').first()).toBeVisible({
    timeout: 30_000,
  });
});
