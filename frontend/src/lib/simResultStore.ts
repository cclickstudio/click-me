// 시뮬 실행 직후 결과(SimRunResult)를 결과 라우트로 넘기는 sessionStorage 브리지.
// 백엔드가 simulation_id로 SimRunResult 전체를 돌려주지 않으므로, 실행 흐름에서만 전체 데이터를 전달한다.

import type { SimRunResult } from './types';

export interface StoredSimResult {
  result: SimRunResult;
  adTitle?: string;
  adDescription?: string;
}

const key = (simulationId: string) => `sim-result:${simulationId}`;

export function saveSimResult(simulationId: string, data: StoredSimResult): void {
  try {
    sessionStorage.setItem(key(simulationId), JSON.stringify(data));
  } catch {
    // 저장 실패(용량·비활성)는 무시 — 결과 라우트가 콜드 폴백으로 처리.
  }
}

export function loadSimResult(simulationId: string): StoredSimResult | null {
  try {
    const raw = sessionStorage.getItem(key(simulationId));
    return raw ? (JSON.parse(raw) as StoredSimResult) : null;
  } catch {
    return null;
  }
}

export function clearSimResult(simulationId: string): void {
  try {
    sessionStorage.removeItem(key(simulationId));
  } catch {
    // 무시
  }
}
