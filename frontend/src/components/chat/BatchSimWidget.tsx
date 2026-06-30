'use client';

// 배치 시뮬 위젯 — 광고 2개를 입력해 한 번에(순차) 비교 시뮬, KPI를 나란히 표로 보여준다(T11)
import { useState } from 'react';
import { getToken } from '@/lib/authApi';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

type AdInput = { ad_title: string; ad_content: string; product_category: string };
type SimKpi = {
  ad_title?: string;
  purchase_intent?: number | null;
  click_intent_rate?: number | null;
  ci_low?: number | null;
  ci_high?: number | null;
  trust_avg?: number | null;
  rejection_rate?: number | null;
  effective_n?: number | null;
  error?: string;
};

const EMPTY: AdInput = { ad_title: '', ad_content: '', product_category: '' };

function pct(v?: number | null) {
  return v == null ? '—' : `${(v * 100).toFixed(0)}%`;
}
function score(v?: number | null) {
  return v == null ? '—' : `${v.toFixed(2)}/5`;
}

function adName(r: SimKpi, i: number) {
  return r.ad_title || `광고 ${String.fromCharCode(65 + i)}`;
}

// A/B 승자 판정 — 클릭 의향률(유일한 신뢰구간 보유 KPI)의 CI 겹침으로 유의성을 가른다.
// 같은 페르소나 패널(결정적 seed)로 평가하므로 차이는 표본변동이 아닌 광고효과로 본다.
// CI가 겹치면 '유의차 없음'(점추정 단언 금지·기획서 통계 정직성), 분리되면 우세 시안.
type Verdict = { tone: 'win' | 'tie' | 'weak'; badge: string; detail: string };

function judgeWinner(results: SimKpi[]): Verdict | null {
  if (results.length !== 2) return null;
  const [a, b] = results;
  if (a.error || b.error) return null;
  const aM = a.click_intent_rate,
    bM = b.click_intent_rate;
  const nameA = adName(a, 0),
    nameB = adName(b, 1);
  if (aM == null || bM == null) return null;
  // 신뢰구간이 없으면 점추정만 — 유의성은 단정하지 않는다.
  if (a.ci_low == null || a.ci_high == null || b.ci_low == null || b.ci_high == null) {
    const lead = aM === bM ? null : aM > bM ? nameA : nameB;
    return {
      tone: 'weak',
      badge: '참고용 (유의성 판정 불가)',
      detail: lead
        ? `클릭 의향률 점추정은 ${lead}가 높지만, 신뢰구간이 없어 유의한 차이로 단정할 수 없어요.`
        : '두 시안의 클릭 의향률 점추정이 같아요.',
    };
  }
  // 두 신뢰구간이 겹치는지 — [aL,aH]와 [bL,bH]는 aL<=bH && bL<=aH 일 때 겹친다.
  const overlap = a.ci_low <= b.ci_high && b.ci_low <= a.ci_high;
  if (overlap) {
    return {
      tone: 'tie',
      badge: '유의차 없음',
      detail:
        '두 시안의 클릭 의향률 신뢰구간이 겹쳐, 통계적으로 의미 있는 차이로 보기 어려워요. 표본을 늘리거나 시안 차이를 키워보세요.',
    };
  }
  const winner = aM > bM ? nameA : nameB;
  return {
    tone: 'win',
    badge: `${winner} 우세 (유의)`,
    detail: `${winner}의 클릭 의향률 신뢰구간이 상대보다 높게 분리돼, 유의하게 우세해요 → ${winner} 권장.`,
  };
}

// 점추정 참고 — 4개 지표 중 각 시안이 앞선 개수(거부율은 낮을수록 우세). 유의성 아닌 참고용.
// 클릭 의향률 CI가 겹쳐도(특히 작은 표본) 다른 지표의 명확한 차이를 사용자가 놓치지 않게 보조.
function pointLead(results: SimKpi[]): string | null {
  if (results.length !== 2) return null;
  const [a, b] = results;
  if (a.error || b.error) return null;
  let aw = 0,
    bw = 0;
  const cmp = (x?: number | null, y?: number | null, higherBetter = true) => {
    if (x == null || y == null || x === y) return;
    if (higherBetter ? x > y : x < y) aw++;
    else bw++;
  };
  cmp(a.click_intent_rate, b.click_intent_rate, true);
  cmp(a.purchase_intent, b.purchase_intent, true);
  cmp(a.trust_avg, b.trust_avg, true);
  cmp(a.rejection_rate, b.rejection_rate, false); // 거부율은 낮을수록 우세
  const total = aw + bw;
  if (total === 0 || aw === bw) return null;
  const lead = aw > bw ? adName(a, 0) : adName(b, 1);
  return `참고(점추정): ${lead}가 4개 지표 중 ${Math.max(aw, bw)}개에서 앞서요 — 유의성은 클릭 의향률 기준이에요.`;
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
        headers: {
          'Content-Type': 'application/json',
          ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
        },
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
          {(() => {
            const v = judgeWinner(results);
            if (!v) return null;
            const lead = pointLead(results);
            const cls =
              v.tone === 'win'
                ? 'border-[#00C471]/30 bg-[#E7F9F1] dark:bg-[#10241C] text-[#00854D]'
                : v.tone === 'tie'
                  ? 'border-[#E5E8EB] dark:border-[#2D3748] bg-[#F9FAFB] dark:bg-[#252D3D] text-[#4E5968] dark:text-[#9CA3AF]'
                  : 'border-[#FFB020]/30 bg-[#FFF7E6] dark:bg-[#2A2310] text-[#B7791F]';
            return (
              <div className={`mb-3 rounded-lg border px-3 py-2.5 ${cls}`}>
                <div className="flex items-center gap-1.5 text-sm font-bold">
                  <span>🏆 A/B 판정</span>
                  <span className="text-[12px] font-semibold">· {v.badge}</span>
                </div>
                <p className="mt-1 text-[12px] leading-snug opacity-90">{v.detail}</p>
                {lead && v.tone !== 'win' && (
                  <p className="mt-1 text-[11px] leading-snug opacity-80">{lead}</p>
                )}
              </div>
            );
          })()}
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[#8B95A1] dark:text-[#6B7280] text-xs">
                <th className="text-left py-1.5 pr-2">지표</th>
                {results.map((r, i) => (
                  <th key={i} className="text-right py-1.5 px-2 text-[#191F28] dark:text-[#F2F4F6]">
                    {adName(r, i)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="text-[#4E5968] dark:text-[#9CA3AF]">
              {[
                { label: '클릭 의향률', fmt: pct, key: 'click_intent_rate' as const },
                { label: '구매의도', fmt: score, key: 'purchase_intent' as const },
                { label: '신뢰도', fmt: score, key: 'trust_avg' as const },
                { label: '거부율', fmt: pct, key: 'rejection_rate' as const },
              ].map((row) => (
                <tr key={row.label} className="border-t border-[#F2F4F6] dark:border-[#252D3D]">
                  <td className="py-1.5 pr-2">{row.label}</td>
                  {results.map((r, i) => (
                    <td key={i} className="text-right py-1.5 px-2 tabular-nums">
                      {r.error ? '실패' : row.fmt(r[row.key])}
                      {/* 클릭 의향률만 신뢰구간 동반 표기(유일한 CI 보유 KPI) */}
                      {row.key === 'click_intent_rate' &&
                        !r.error &&
                        r.ci_low != null &&
                        r.ci_high != null && (
                          <span className="block text-[10px] text-[#B0B8C1] dark:text-[#6B7280]">
                            CI {pct(r.ci_low)}–{pct(r.ci_high)}
                          </span>
                        )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-[10px] text-[#B0B8C1] dark:text-[#6B7280] leading-snug">
            * 두 시안을 같은 AI 소비자 패널로 평가했어요. 승자 판정은 클릭 의향률의 신뢰구간
            겹침 기준이며, 겹치면 차이 없음으로 봐요(점추정 단언 안 함).
          </p>
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
