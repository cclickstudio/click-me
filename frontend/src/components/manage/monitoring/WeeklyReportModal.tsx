// 주간 리포트 모달 — 최근 7일 실측 요약(총합·캠페인별 표·하이라이트·다음 액션)
'use client';

import { useEffect, useState } from 'react';
import { api, type WeeklyReport } from '@/lib/api';

export function WeeklyReportModal({ onClose }: { onClose: () => void }) {
  const [report, setReport] = useState<WeeklyReport | null>(null);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    api.management
      .weeklyReport()
      .then((r) => {
        setReport(r.report);
        setNote(r.note);
      })
      .catch((e) => setNote(e instanceof Error ? e.message : '리포트를 불러오지 못했어요.'));
  }, []);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white p-6 shadow-2xl dark:bg-[#1C2333]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-bold text-[#191F28] dark:text-[#F2F4F6]">주간 리포트</h3>
          <button
            onClick={onClose}
            className="text-sm text-[#8B95A1] hover:text-[#191F28] dark:hover:text-[#F2F4F6]"
          >
            닫기 ✕
          </button>
        </div>

        {!report && (
          <p className="mt-4 text-sm text-[#8B95A1]">{note ?? '불러오는 중…'}</p>
        )}

        {report && (
          <>
            <p className="mt-1 text-xs text-[#8B95A1]">
              {report.period.since} ~ {report.period.until} · 실측(Meta) 기준
            </p>

            <div className="mt-4 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
              {(
                [
                  ['지출', `₩${report.totals.spend_krw.toLocaleString()}`],
                  ['노출', report.totals.impressions.toLocaleString()],
                  ['클릭', report.totals.clicks.toLocaleString()],
                  [
                    'CTR / CPC',
                    `${(report.totals.ctr * 100).toFixed(1)}% / ₩${report.totals.cpc_krw.toLocaleString()}`,
                  ],
                ] as [string, string][]
              ).map(([label, value]) => (
                <div
                  key={label}
                  className="rounded-xl border border-[#E5E8EB] px-3 py-2.5 dark:border-[#2D3748]"
                >
                  <p className="text-[11px] text-[#8B95A1]">{label}</p>
                  <p className="mt-0.5 text-[15px] font-bold tabular-nums text-[#191F28] dark:text-[#F2F4F6]">
                    {value}
                  </p>
                </div>
              ))}
            </div>

            {report.campaigns.length > 0 && (
              <div className="mt-4 overflow-x-auto rounded-xl border border-[#E5E8EB] dark:border-[#2D3748]">
                <table className="w-full text-[12px] [&_td]:whitespace-nowrap [&_th]:whitespace-nowrap">
                  <thead className="border-b border-[#E5E8EB] text-[#8B95A1] dark:border-[#2D3748]">
                    <tr>
                      <th className="px-3 py-2 text-left font-semibold">캠페인</th>
                      <th className="px-3 py-2 text-right font-semibold">지출</th>
                      <th className="px-3 py-2 text-right font-semibold">노출</th>
                      <th className="px-3 py-2 text-right font-semibold">클릭</th>
                      <th className="px-3 py-2 text-right font-semibold">CTR</th>
                      <th className="px-3 py-2 text-right font-semibold">CPC</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.campaigns.map((c) => (
                      <tr
                        key={c.campaign_id}
                        className="border-b border-[#F2F4F6] last:border-0 dark:border-[#2D3748]"
                      >
                        <td className="px-3 py-2 text-[#191F28] dark:text-[#F2F4F6]">{c.name}</td>
                        <td className="px-3 py-2 text-right tabular-nums">
                          ₩{c.spend_krw.toLocaleString()}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">
                          {c.impressions.toLocaleString()}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">
                          {c.clicks.toLocaleString()}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">
                          {(c.ctr * 100).toFixed(1)}%
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">
                          ₩{c.cpc_krw.toLocaleString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {report.highlights.length > 0 && (
              <div className="mt-4">
                <p className="text-[12px] font-semibold text-[#4E5968] dark:text-[#9CA3AF]">
                  하이라이트
                </p>
                <ul className="mt-1 space-y-1 text-[13px] text-[#191F28] dark:text-[#F2F4F6]">
                  {report.highlights.map((h) => (
                    <li key={h}>· {h}</li>
                  ))}
                </ul>
              </div>
            )}

            {report.next_actions.length > 0 && (
              <div className="mt-3 rounded-xl bg-[#F9FAFB] px-4 py-3 dark:bg-[#232A36]">
                <p className="text-[12px] font-semibold text-[#4E5968] dark:text-[#9CA3AF]">
                  다음 액션 제안
                </p>
                <ul className="mt-1 space-y-1 text-[13px] text-[#191F28] dark:text-[#F2F4F6]">
                  {report.next_actions.map((a) => (
                    <li key={a}>· {a}</li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
