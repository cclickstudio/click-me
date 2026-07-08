'use client';
// 시뮬 결과 → Meta 캠페인 집행 — from-simulation 제안 생성 후 승인·실행(simulation_id 연결).
// 집행하면 created_campaigns.simulation_id가 채워져 매니지먼트 성과비교(before-after)에서 예측이 붙는다.

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';

// 집행 권장 게이트 — 정본은 백엔드(GET /management/exec-gate). 아래는 조회 실패 시 폴백.
const DEFAULT_GATE = { min_click_intent_rate: 0.01, max_rejection_rate: 0.2 };

export function ExecuteFromSimulation({
  simulationId,
  defaultName,
  clickIntentRate,
  rejectionRate,
}: {
  simulationId: string;
  defaultName?: string;
  clickIntentRate: number;
  rejectionRate: number;
}) {
  const [gate, setGate] = useState(DEFAULT_GATE);
  useEffect(() => {
    let alive = true;
    api.management
      .execGate()
      .then((g) => {
        if (alive) setGate(g);
      })
      .catch(() => {}); // 실패 시 DEFAULT_GATE 폴백
    return () => {
      alive = false;
    };
  }, []);
  const executable =
    clickIntentRate >= gate.min_click_intent_rate && rejectionRate < gate.max_rejection_rate;
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(defaultName ?? '');
  const [linkUrl, setLinkUrl] = useState('');
  const [budget, setBudget] = useState(10000);
  const [startDate, setStartDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [endDate, setEndDate] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  // AI 이름 추천 — 폼 열릴 때 1회 조회(부가 기능, 실패해도 무시)
  const [suggestions, setSuggestions] = useState<string[]>([]);
  useEffect(() => {
    if (!open) return;
    let alive = true;
    api.management
      .nameSuggestions(simulationId)
      .then((r) => {
        if (alive) setSuggestions(r.names ?? []);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [open, simulationId]);

  async function handleExecute() {
    if (!linkUrl.trim()) {
      setError('목적지 URL(link_url)을 입력하세요.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      // from-simulation → approve → execute (generator from-candidate와 동일 단일 경로).
      const { proposal } = await api.management.fromSimulation({
        simulation_id: simulationId,
        link_url: linkUrl.trim(),
        name: name.trim() || defaultName || '시뮬 기반 캠페인',
        daily_budget_krw: budget,
        start_date: startDate,
        end_date: endDate || null,
        country: 'KR',
        age_min: 18,
        age_max: 65,
        gender: 'all',
      });
      const a = (await api.management.approve(proposal, true)) as { approved_action: unknown };
      const resp = (await api.management.execute(a.approved_action, proposal)) as {
        error_message?: string;
      };
      if (resp.error_message) {
        setError(resp.error_message);
        return;
      }
      setDone(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Meta 광고 집행에 실패했습니다.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="px-3 py-1.5 rounded-full text-sm font-semibold bg-primary text-primary-foreground hover:bg-primary-hover transition-colors"
      >
        이 광고로 캠페인 집행
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
          onClick={() => !busy && setOpen(false)}
        >
          <div
            className="bg-card rounded-2xl w-full max-w-md p-6 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-lg font-bold text-ink">
              시뮬 광고로 캠페인 집행
            </h3>
            <p className="mt-1 text-[12px] text-ink-tertiary">
              이 시뮬 결과의 광고로 Meta 캠페인을 만듭니다(일시정지 상태로 생성 — 게재는
              매니지먼트에서 시작). 집행 후 성과비교에 예측이 자동 연결됩니다.
            </p>

            {!executable && (
              <div className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-[12px] text-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
                집행 권장 기준 미달 — 클릭 의향률 {(clickIntentRate * 100).toFixed(1)}%(≥
                {(gate.min_click_intent_rate * 100).toFixed(0)}% 필요)· 거부율{' '}
                {(rejectionRate * 100).toFixed(1)}%(&lt;
                {(gate.max_rejection_rate * 100).toFixed(0)}% 필요). 기준을 충족해야 집행할 수
                있어요.
              </div>
            )}

            {done ? (
              <div className="mt-4">
                <p className="rounded-lg bg-green-50 px-3 py-2 text-[13px] text-green-700 dark:bg-green-900/20 dark:text-green-400">
                  ✓ 캠페인을 만들었어요(일시정지). 매니지먼트에서 게재를 시작하세요.
                </p>
                <div className="mt-4 flex justify-end gap-2">
                  <Link
                    href="/manage/campaigns"
                    className="px-3 py-1.5 rounded-lg text-sm font-medium bg-primary text-primary-foreground hover:bg-primary-hover"
                  >
                    캠페인 관리로 →
                  </Link>
                  <button
                    onClick={() => setOpen(false)}
                    className="px-3 py-1.5 rounded-lg text-sm font-medium text-ink-secondary"
                  >
                    닫기
                  </button>
                </div>
              </div>
            ) : (
              <div className="mt-4 space-y-3">
                <Field label="캠페인 이름">
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="캠페인 이름"
                    className={inputCls}
                  />
                </Field>
                {suggestions.length > 0 && (
                  <div className="-mt-1 flex flex-wrap items-center gap-1.5">
                    <span className="text-[11px] text-ink-tertiary">AI 추천</span>
                    {suggestions.map((s) => (
                      <button
                        key={s}
                        type="button"
                        onClick={() => setName(s)}
                        className="rounded-full border border-line px-2.5 py-1 text-[11px] text-ink-secondary hover:border-primary hover:text-primary transition-colors"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                )}
                <Field label="목적지 URL (link_url)">
                  <input
                    value={linkUrl}
                    onChange={(e) => setLinkUrl(e.target.value)}
                    placeholder="https://example.com/landing"
                    className={inputCls}
                  />
                </Field>
                <Field label="일예산 (₩, 하루 상한)">
                  <input
                    type="number"
                    min={1}
                    value={budget}
                    onChange={(e) => setBudget(Number(e.target.value))}
                    className={inputCls}
                  />
                </Field>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="시작일">
                    <input
                      type="date"
                      value={startDate}
                      onChange={(e) => setStartDate(e.target.value)}
                      className={inputCls}
                    />
                  </Field>
                  <Field label="종료일 (선택)">
                    <input
                      type="date"
                      value={endDate}
                      onChange={(e) => setEndDate(e.target.value)}
                      className={inputCls}
                    />
                  </Field>
                </div>

                {error && (
                  <p className="rounded-lg bg-red-50 px-3 py-2 text-[12px] text-red-600 dark:bg-red-900/20 dark:text-red-400">
                    {error}
                  </p>
                )}

                <div className="flex justify-end gap-2 pt-1">
                  <button
                    onClick={() => setOpen(false)}
                    disabled={busy}
                    className="px-3 py-1.5 rounded-lg text-sm font-medium text-ink-secondary disabled:opacity-40"
                  >
                    취소
                  </button>
                  <button
                    onClick={handleExecute}
                    disabled={busy || !executable}
                    className="px-4 py-1.5 rounded-lg text-sm font-semibold bg-primary text-primary-foreground hover:bg-primary-hover disabled:opacity-40"
                  >
                    {busy ? '집행 중…' : '집행하기'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}

const inputCls =
  'w-full rounded-lg border border-line bg-white dark:bg-[#161B26] px-3 py-2 text-sm text-ink outline-none focus:border-primary';

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[12px] font-medium text-ink-secondary">
        {label}
      </span>
      {children}
    </label>
  );
}
