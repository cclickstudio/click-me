// DB 조회 헬퍼 — backend(uv)로 db_query.py를 돌려 채팅 세션의 위젯 시퀀스를 가져온다.
import { execFileSync } from 'node:child_process';
import path from 'node:path';

const BACKEND_DIR = path.resolve(__dirname, '../../../backend');
const DB_QUERY = path.resolve(__dirname, '..', 'db_query.py');

export type LatestSession = {
  session_id: string | null;
  widget_types: string[];
  ad_titles: string[];
  message_count: number;
};

function run<T>(args: string[]): T {
  const out = execFileSync('uv', ['run', 'python', DB_QUERY, ...args], {
    cwd: BACKEND_DIR,
    encoding: 'utf-8',
  });
  return JSON.parse(out.trim().split(/\r?\n/).pop()!) as T;
}

export function latestSession(projectId: string): LatestSession {
  return run<LatestSession>(['latest-session', projectId]);
}

/** 최근 48시간 내 COMPLETED 시뮬 id 목록 — 선제 알림 seen 사전 채움용. */
export function recentSimIds(projectId: string): string[] {
  return run<{ sim_ids: string[] }>(['recent-sim-ids', projectId]).sim_ids;
}

/** 대조용 빈 세션 B 생성 → session_id 반환. */
export function createSession(projectId: string): string {
  return run<{ session_id: string }>(['create-session', projectId]).session_id;
}

export function deleteSession(sessionId: string): void {
  run<{ ok: boolean }>(['delete-session', sessionId]);
}
