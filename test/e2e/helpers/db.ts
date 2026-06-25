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

export function latestSession(projectId: string): LatestSession {
  const out = execFileSync('uv', ['run', 'python', DB_QUERY, 'latest-session', projectId], {
    cwd: BACKEND_DIR,
    encoding: 'utf-8',
  });
  return JSON.parse(out.trim().split(/\r?\n/).pop()!) as LatestSession;
}
