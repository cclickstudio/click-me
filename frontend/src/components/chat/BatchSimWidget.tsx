'use client';

// 배치 시뮬 위젯 — 광고 2개를 입력해 한 번에(순차) 비교 시뮬, KPI를 나란히 표로 보여준다(T11)
import { useState } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

type AdInput = { ad_title: string; ad_content: string; product_category: string };
type SimKpi = {
  ad_title?: string;
  purchase_intent?: number | null;
  click_intent_rate?: number | null;
  rejection_rate?: number | null;
  error?: string;
};

const EMPTY: AdInput = { ad_title: '', ad_content: '', product_category: '' };

function pct(v?: number | null) {
  return v == null ? '—' : `${(v * 100).toFixed(0)}%`;
}
function score(v?: number | null) {
  return v == null ? '—' : `${v.toFixed(2)}/5`;
}

export default function BatchSimWidget({ projectId }: { projectId?: string }) {
  const [ads, setAds] = useState<AdInput[]>([{ ...EMPTY }, { ...EMPTY }]);
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState<SimKpi[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const update = (i: number, key: keyof AdInput, value: string) => {
    setAds((prev) => prev.map((a, idx) => (idx === i ? { ...a, [key]: value } : a)));
  };

  const canRun = ads.every((a) => a.ad_content.trim()) && !running;

  const run = async () => {
    setRunning(true);
    setError(null);
    setResults(null);
    try {
      const res = await fetch(`${API_BASE}/api/chat/sim-batch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectId, ads }),
      });
      if (!res.ok) {
        setError('배치 시뮬 실행에 실패했어요. 잠시 후 다시 시도해주세요.');
        return;
      }
      const data = (await res.json()) as { results: SimKpi[] };
      setResults(data.results);
    } catch {
      setError('서버에 연결할 수 없어요.');
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="mt-1 w-full rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#1C2333] p-3">
      {!results ? (
        <>
          <div className="space-y-3">
            {ads.map((a, i) => (
              <div key={i} className="rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] p-2.5">
                <div className="text-xs font-bold text-[#4E5968] dark:text-[#9CA3AF] mb-1.5">
                  광고 {String.fromCharCode(65 + i)}
                </div>
                <input
                  value={a.ad_title}
                  onChange={(e) => update(i, 'ad_title', e.target.value)}
                  placeholder="제목 (선택)"
                  className="w-full mb-1.5 px-2.5 py-1.5 rounded-md border border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#252D3D] text-sm text-[#191F28] dark:text-[#F2F4F6]"
                />
                <textarea
                  value={a.ad_content}
                  onChange={(e) => update(i, 'ad_content', e.target.value)}
                  placeholder="광고 카피·문구"
                  rows={2}
                  className="w-full px-2.5 py-1.5 rounded-md border border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#252D3D] text-sm text-[#191F28] dark:text-[#F2F4F6] resize-none"
                />
              </div>
            ))}
          </div>
          {error && <p className="mt-2 text-xs text-[#F04452]">{error}</p>}
          <button
            disabled={!canRun}
            onClick={run}
            className="mt-3 w-full py-2 rounded-lg bg-[#3182F6] text-white text-sm font-semibold hover:bg-[#1B6EEB] disabled:opacity-40 transition-colors"
          >
            {running ? '비교 시뮬 실행 중…' : '비교 시뮬 실행'}
          </button>
        </>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[#8B95A1] dark:text-[#6B7280] text-xs">
                <th className="text-left py-1.5 pr-2">지표</th>
                {results.map((r, i) => (
                  <th key={i} className="text-right py-1.5 px-2 text-[#191F28] dark:text-[#F2F4F6]">
                    {r.ad_title || `광고 ${String.fromCharCode(65 + i)}`}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="text-[#4E5968] dark:text-[#9CA3AF]">
              {[
                { label: '구매의도', fmt: score, key: 'purchase_intent' as const },
                { label: '클릭 의향률', fmt: pct, key: 'click_intent_rate' as const },
                { label: '거부율', fmt: pct, key: 'rejection_rate' as const },
              ].map((row) => (
                <tr key={row.label} className="border-t border-[#F2F4F6] dark:border-[#252D3D]">
                  <td className="py-1.5 pr-2">{row.label}</td>
                  {results.map((r, i) => (
                    <td key={i} className="text-right py-1.5 px-2 tabular-nums">
                      {r.error ? '실패' : row.fmt(r[row.key])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <button
            onClick={() => {
              setResults(null);
              setAds([{ ...EMPTY }, { ...EMPTY }]);
            }}
            className="mt-3 text-xs text-[#3182F6] font-semibold hover:underline"
          >
            새 비교 시작
          </button>
        </div>
      )}
    </div>
  );
}
