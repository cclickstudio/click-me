// 시뮬 실행 직후 결과(SimRunResult)를 결과 라우트로 넘기는 sessionStorage 브리지.
// 백엔드가 simulation_id로 SimRunResult 전체를 돌려주지 않으므로, 실행 흐름에서만 전체 데이터를 전달한다.

import type { AnalysisMode, SimComparisonResult, SimRunResult } from './types';

export interface StoredSimResult {
  result: SimRunResult;
  adTitle?: string;
  adDescription?: string;
  mode?: AnalysisMode; // individual이면 [id] 라우트가 심층 뷰로 렌더(콜드 폴백엔 없음).
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

/* ─── Persona Set 비교 결과 브리지 — compare는 단일 SimRunResult가 아니라 세그먼트 배열이라 별도 키로 저장. ─── */

export interface StoredSimComparison {
  comparison: SimComparisonResult;
  adTitle?: string;
  adDescription?: string;
}

const compareKey = (runId: string) => `sim-compare:${runId}`;

export function saveSimComparison(runId: string, data: StoredSimComparison): void {
  try {
    sessionStorage.setItem(compareKey(runId), JSON.stringify(data));
  } catch {
    // 무시 — compare는 콜드 복원 경로가 없으므로 저장 실패 시 결과 화면도 없음.
  }
}

export function loadSimComparison(runId: string): StoredSimComparison | null {
  try {
    const raw = sessionStorage.getItem(compareKey(runId));
    return raw ? (JSON.parse(raw) as StoredSimComparison) : null;
  } catch {
    return null;
  }
}

export function clearSimComparison(runId: string): void {
  try {
    sessionStorage.removeItem(compareKey(runId));
  } catch {
    // 무시
  }
}
