// 동시 실행 제한 — 시뮬/제너 각 1개만. 채팅 위젯과 실행 페이지가 공유하는 전역 store.
// 시뮬 두 개·제너 두 개 동시 실행을 막되, 시뮬+제너 동시는 허용한다.
import { useSyncExternalStore } from 'react';

type Jobs = { sim: string | null; gen: string | null };

let jobs: Jobs = { sim: null, gen: null };
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach(l => l());
}

export function getJobs(): Jobs {
  return jobs;
}

export function setSimJob(id: string | null) {
  jobs = { ...jobs, sim: id };
  emit();
}

export function setGenJob(id: string | null) {
  jobs = { ...jobs, gen: id };
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
