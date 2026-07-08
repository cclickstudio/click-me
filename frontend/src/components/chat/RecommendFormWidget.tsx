'use client';

// 채팅 /추천 — 광고 목표·예산·업종을 입력받아 CLIO(advise)에게 플랫폼·전략 추천을 요청하는 폼 위젯.
// 제출 시 자연어 추천 프롬프트를 구성해 onSubmit(=handleSend)으로 보내면 advise 노드가 답한다.
import { useState } from 'react';

const cardCls =
  'mt-1 w-full rounded-xl border border-line bg-card p-4';
const labelCls = 'text-[11px] font-semibold text-ink-tertiary mb-1 block';
const inputCls =
  'w-full px-3 py-2 rounded-lg border border-line text-sm bg-surface-2 text-ink focus:outline-none focus:border-primary';
const chipBase = 'px-2.5 py-1.5 rounded-lg border text-[11px] font-medium transition-colors';
const chipActive = 'border-primary bg-primary-subtle text-primary';
const chipIdle =
  'border-line text-ink-tertiary hover:border-primary';

const GOALS = ['관심 유도', '클릭 유도', '가입·문의 유도', '구매 전환', '재구매·단골'];

export default function RecommendFormWidget({
  onSubmit,
}: {
  onSubmit?: (prompt: string) => void;
}) {
  const [goal, setGoal] = useState('');
  const [budget, setBudget] = useState('');
  const [industry, setIndustry] = useState('');
  const [sent, setSent] = useState(false);

  const canSubmit = goal !== '' && budget.trim() !== '' && !sent;

  const submit = () => {
    if (!canSubmit) return;
    const parts = [
      `광고 목표는 '${goal}'`,
      `월 예산은 약 ${budget.trim()}만원`,
      industry.trim() ? `업종·제품은 '${industry.trim()}'` : '',
    ].filter(Boolean);
    const prompt =
      `광고 전략 추천을 받고 싶어요. ${parts.join(', ')}입니다. ` +
      '이 조건에 맞는 추천 광고 플랫폼(메타·인스타그램·유튜브·네이버 등)과 핵심 집행 전략을 알려주세요.';
    setSent(true);
    onSubmit?.(prompt);
  };

  if (sent) {
    return (
      <div className={cardCls}>
        <p className="text-sm text-ink-tertiary">전략 추천을 요청했어요. 잠시만요...</p>
      </div>
    );
  }

  return (
    <div className={cardCls}>
      <p className="text-sm font-semibold text-ink mb-3">
        💡 전략 추천 받기
      </p>
      <div className="space-y-3">
        <div>
          <label className={labelCls}>광고 목표 *</label>
          <div className="flex flex-wrap gap-1.5">
            {GOALS.map(g => (
              <button
                key={g}
                type="button"
                onClick={() => setGoal(g)}
                className={`${chipBase} ${goal === g ? chipActive : chipIdle}`}
              >
                {g}
              </button>
            ))}
          </div>
        </div>
        <div>
          <label className={labelCls}>월 예산 (만원) *</label>
          <input
            className={inputCls}
            type="number"
            inputMode="numeric"
            value={budget}
            onChange={e => setBudget(e.target.value)}
            placeholder="예: 300"
          />
        </div>
        <div>
          <label className={labelCls}>업종·제품 (선택)</label>
          <input
            className={inputCls}
            value={industry}
            onChange={e => setIndustry(e.target.value)}
            placeholder="예: 20대 여성 타깃 수분 크림"
          />
        </div>
        <button
          onClick={submit}
          disabled={!canSubmit}
          className="w-full py-2 rounded-lg bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary-hover disabled:opacity-40 transition-colors"
        >
          전략 추천 받기
        </button>
      </div>
    </div>
  );
}
