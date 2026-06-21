// 충전 후 자동 게재 재개용 — 게재할 캠페인·배정액을 sessionStorage에 잠시 보관
// (게재 시작 시 크레딧 부족 → /payment 이동 → 충전 성공 후 이 값으로 활성화를 이어간다)

const KEY = 'clickme_pending_activation';

export interface PendingActivation {
  campaignId: string;
  commit: number;
}

export function setPendingActivation(p: PendingActivation): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(p));
  } catch {
    /* sessionStorage 불가 환경 — 재개 생략 */
  }
}

/** 보관된 재개 정보를 꺼내고 즉시 비운다(1회성). */
export function popPendingActivation(): PendingActivation | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    sessionStorage.removeItem(KEY);
    return JSON.parse(raw) as PendingActivation;
  } catch {
    return null;
  }
}
