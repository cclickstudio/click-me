// P5 E2E③ — N4 세션 누수.
// A 세션에서 시뮬을 완료하면 그 sim_id가 chat_proactive_seen_<pid>에 등록되고,
// 다른 세션 B를 열어 폴링을 강제(가드 해제)해도 "아직 확인하지 않은 시뮬 결과" 선제 알림이
// 뜨지 않아야 한다(누수 없음). 대조로 seen에서 그 id를 빼면 알림이 떠야 한다.
//
// 주의: 브라우저 컨텍스트는 매 테스트 새로 시작돼 localStorage가 비어 있어,
// DB에 남아있는 과거 테스트 시뮬(최근 48h)이 전부 unseen으로 잡힌다.
// → 시작 시 현재 recent COMPLETED 시뮬을 seen에 사전 채워 베이스라인을 깨끗이 만든다.
import { test, expect } from '@playwright/test';
import { enterGundoyeonChat, gotoSession } from './helpers/project';
import { runSimulation } from './helpers/sim';
import { recentSimIds, createSession, deleteSession } from './helpers/db';
import { PROJECT_ID } from './helpers/auth';

test.setTimeout(240_000);

const ALERT = /🔔 아직 확인하지 않은 시뮬레이션 결과가 있어요/;
const seenKey = `chat_proactive_seen_${PROJECT_ID}`;
const lastKey = `chat_proactive_last_${PROJECT_ID}`;

test('A 시뮬 완료가 seen에 등록되어 B 세션 선제 알림으로 누수되지 않는다', async ({ page }) => {
  const adTitle = `E2E누수-${Date.now()}`;
  const preSeed = recentSimIds(PROJECT_ID); // A 실행 전 recent 시뮬(베이스라인)
  let sessionB: string | null = null;

  try {
    // ── A 세션: seen을 베이스라인으로 채우고 가드를 걸어 둔 뒤 시뮬 실행 ──
    await enterGundoyeonChat(page);
    await page.evaluate(
      ([sk, lk, seed]) => {
        localStorage.setItem(sk, JSON.stringify(seed));
        localStorage.setItem(lk, String(Date.now())); // A는 폴링 가드(20분)로 잠금
      },
      [seenKey, lastKey, preSeed] as const,
    );

    await runSimulation(page, {
      adTitle,
      adContent: '하루 종일 무너지지 않는 매트 쿠션. 첫 구매 사은품 증정.',
    });
    await expect(page.getByText('✅ 시뮬레이션 결과').first()).toBeVisible({ timeout: 90_000 });
    await expect(page.getByText('AI 소비자 토론을 시작했어요').first()).toBeVisible({
      timeout: 60_000,
    });

    // 완료 시 seen에 새 sim_id가 등록됐는지 — 폴링으로 확인(localStorage 쓰기 비동기 여유).
    let newSimId = '';
    for (let i = 0; i < 20; i++) {
      const seen: string[] = await page.evaluate(
        (sk) => JSON.parse(localStorage.getItem(sk) || '[]'),
        seenKey,
      );
      const added = seen.filter((x) => !preSeed.includes(x));
      if (added.length > 0) {
        newSimId = added[added.length - 1];
        break;
      }
      await page.waitForTimeout(1000);
    }
    expect(newSimId, 'A 시뮬 완료 후 seen에 새 sim_id가 등록되지 않음').not.toBe('');

    // ── B 세션 열기 + 가드 해제로 폴링 강제 → 선제 알림이 뜨면 안 된다 ──
    sessionB = createSession(PROJECT_ID);
    await gotoSession(page, sessionB);
    await page.evaluate((lk) => localStorage.removeItem(lk), lastKey); // 가드 해제
    await page.reload();

    // 폴링(api.projects.simulations)이 실제로 한 번 돌 때까지 기다린 뒤 알림 부재를 단언.
    await page.waitForResponse(
      (r) => /\/projects\/.*\/simulations/.test(r.url()) && r.status() === 200,
      { timeout: 30_000 },
    );
    await page.waitForTimeout(3000);
    await expect(page.getByText(ALERT), 'seen에 있는데도 B에 선제 알림이 누수됨').toHaveCount(0);

    // ── 대조: seen에서 새 sim_id를 빼면(다시 미열람) 알림이 떠야 한다 ──
    await page.evaluate(
      ([sk, lk, seed]) => {
        localStorage.setItem(sk, JSON.stringify(seed)); // preSeed만 — 새 sim_id 제외
        localStorage.removeItem(lk);
      },
      [seenKey, lastKey, preSeed] as const,
    );
    await page.reload();
    await expect(page.getByText(ALERT).first(), '대조: seen에서 빼면 선제 알림이 떠야 함').toBeVisible({
      timeout: 30_000,
    });
    // 알림이 바로 그 시뮬(A의 제품명)에 관한 것인지 확인.
    await expect(page.getByText(adTitle).first()).toBeVisible({ timeout: 10_000 });
  } finally {
    if (sessionB) deleteSession(sessionB);
  }
});
