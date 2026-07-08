'use client';

// 채팅 안 토론 요약 위젯 — run_id로 토론 결과(report)를 조회해 결론·합의·이견·권고를 정리해 보여준다.
// "토론 요약" 버튼으로 띄우며, 별도 메시지로 영속화돼 새로고침에도 남는다. 모델 칩은 표시하지 않는다.
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { DebateReport } from '@/lib/types';

const cardCls =
  'mt-1 w-full rounded-xl border border-line bg-card p-4';

export default function DebateSummaryWidget({ runId }: { runId: string }) {
  const [rep, setRep] = useState<DebateReport | null>(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await api.debate.result(runId);
        if (!cancelled) setRep(r.report);
      } catch {
        if (!cancelled) setErr(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [runId]);

  return (
    <div className={cardCls}>
      <p className="text-sm font-semibold text-ink mb-2">📝 토론 요약</p>
      {err ? (
        <p className="text-[12px] text-ink-muted">요약을 불러오지 못했어요.</p>
      ) : !rep ? (
        <p className="text-[12px] text-ink-muted">요약을 정리하는 중...</p>
      ) : (
        <div className="space-y-3">
          {rep.topic && (
            <p className="text-[12px] text-ink-secondary">
              <span className="font-semibold text-primary">주제 </span>
              {rep.topic}
            </p>
          )}
          {rep.plain_summary && (
            <div className="rounded-xl bg-[#EEF4FF] dark:bg-[#162844] border border-[#D5E3FB] dark:border-[#1E3A5F] p-3">
              <p className="text-[11px] font-semibold text-primary mb-1">한눈에 보는 결론</p>
              <p className="text-[13px] leading-relaxed text-ink">
                {rep.plain_summary}
              </p>
            </div>
          )}
          {rep.consensus?.length > 0 && (
            <div>
              <p className="text-[11px] font-semibold text-[#00A36C] mb-1">합의</p>
              <ul className="space-y-0.5">
                {rep.consensus.map((c, i) => (
                  <li key={i} className="text-[12px] text-ink">
                    · {c}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {rep.dissent?.length > 0 && (
            <div>
              <p className="text-[11px] font-semibold text-[#F04452] mb-1">이견</p>
              <ul className="space-y-0.5">
                {rep.dissent.map((c, i) => (
                  <li key={i} className="text-[12px] text-ink">
                    · {c}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {rep.ranked_actions?.length > 0 && (
            <div>
              <p className="text-[11px] font-semibold text-ink-secondary mb-1">개선 권고</p>
              <div className="space-y-1">
                {rep.ranked_actions.map((a) => (
                  <div key={a.rank} className="flex gap-2 text-[12px]">
                    <span className="shrink-0 font-bold text-primary">{a.rank}.</span>
                    <span className="text-ink">
                      {a.action}
                      {a.expected_effect && (
                        <span className="text-ink-tertiary"> — {a.expected_effect}</span>
                      )}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
