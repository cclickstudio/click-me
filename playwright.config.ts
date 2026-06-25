// ClickMe E2E(Playwright) 설정 — frontend(3000)+backend(8000) 대상.
// 실행: cd frontend && pnpm test:e2e  (frontend dev 서버는 webServer가 자동 기동, backend는 별도로 떠 있어야 함)
// 시뮬은 실제 LLM 호출이라 1회 ~1분 → 테스트 타임아웃을 넉넉히(기본 3분) 잡는다.
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './test/e2e',
  globalSetup: './test/e2e/global-setup.ts',
  // 시뮬 E2E는 직렬로(LLM 비용·세션 간섭 방지). 재시도 1회로 일시적 흔들림 흡수.
  fullyParallel: false,
  workers: 1,
  retries: 1,
  timeout: 180_000,
  expect: { timeout: 15_000 },
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    actionTimeout: 15_000,
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'pnpm dev',
    cwd: 'frontend',
    url: 'http://localhost:3000',
    reuseExistingServer: true,
    timeout: 120_000,
    stdout: 'ignore',
    stderr: 'pipe',
  },
});
