// 알림 SSE 구독 훅 — "changed" 신호 수신 시 onChange 호출, 지수 백오프 재연결
'use client';

import { useEffect, useRef } from 'react';
import { authedFetch } from '@/lib/api';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export function useNotificationStream(enabled: boolean, onChange: () => void) {
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useEffect(() => {
    if (!enabled) return;
    let stopped = false;
    let ctrl: AbortController | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const run = async (attempt: number) => {
      ctrl = new AbortController();
      try {
        const res = await authedFetch(`${API_BASE}/api/management/notifications/stream`, {
          signal: ctrl.signal,
        });
        if (!res.ok || !res.body) throw new Error(String(res.status));
        const reader = res.body.getReader();
        const dec = new TextDecoder();
        let buf = '';
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          const lines = buf.split('\n');
          buf = lines.pop() ?? '';
          for (const line of lines) {
            if (line.includes('"changed"')) onChangeRef.current();
          }
          attempt = 0; // 정상 수신 중 — 백오프 리셋
        }
      } catch {
        /* 재연결로 폴스루 — SSE 실패 시 라우트 전환 폴링이 폴백(스펙 §6) */
      }
      if (!stopped) {
        const delay = Math.min(30_000, 1000 * 2 ** attempt);
        timer = setTimeout(() => run(attempt + 1), delay);
      }
    };
    run(0);
    return () => {
      stopped = true;
      ctrl?.abort();
      if (timer) clearTimeout(timer);
    };
  }, [enabled]);
}
