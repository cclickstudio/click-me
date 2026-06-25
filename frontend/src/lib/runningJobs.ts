// 동시 실행 제한 — 시뮬/제너 각 1개만. 채팅 위젯과 실행 페이지가 공유하는 전역 store.
// 시뮬 두 개·제너 두 개 동시 실행을 막되, 시뮬+제너 동시는 허용한다.
// 슬롯 누수 방지(X3): 위젯이 언마운트된 채 런이 끝나 해제 콜백을 못 받으면 슬롯이 영구 점유될 수
// 있으므로, 점유 시각을 기록하고 STALE_MS를 넘긴 슬롯은 자동 회수한다(실제 시뮬보다 충분히 긴 상한).
import { useSyncExternalStore } from 'react';

type Jobs = { sim: string | null; gen: string | null };
type Slot = { id: string; at: number } | null;

// 30분 — 이 데모 규모 시뮬/생성은 이보다 훨씬 짧으므로, 넘긴 슬롯은 누수로 보고 회수한다.
const STALE_MS = 30 * 60 * 1000;

let simSlot: Slot = null;
let genSlot: Slot = null;
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach(l => l());
}

// STALE 초과 슬롯은 null로 본다(자동 회수). now 주입 가능(테스트용).
function freshId(slot: Slot, now = Date.now()): string | null {
  if (!slot) return null;
  if (now - slot.at > STALE_MS) return null;
  return slot.id;
}

// useSyncExternalStore는 getSnapshot이 안정 참조를 반환해야 하므로, 값이 바뀔 때만 새 객체를 만든다.
let snapshot: Jobs = { sim: null, gen: null };
export function getJobs(): Jobs {
  const sim = freshId(simSlot);
  const gen = freshId(genSlot);
  if (snapshot.sim !== sim || snapshot.gen !== gen) {
    snapshot = { sim, gen };
  }
  return snapshot;
}

export function setSimJob(id: string | null) {
  simSlot = id ? { id, at: Date.now() } : null;
  emit();
}

export function setGenJob(id: string | null) {
  genSlot = id ? { id, at: Date.now() } : null;
  emit();
}

export function useRunningJobs(): Jobs {
  return useSyncExternalStore(
    l => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    getJobs,
    getJobs,
  );
}

// 테스트·점검용 — STALE 회수 로직 단독 검증.
export const __test = { freshId, STALE_MS };
