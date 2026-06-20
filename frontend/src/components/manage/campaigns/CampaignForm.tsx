// 신규 캠페인 생성 폼 — 목표·예산·기간·소재 입력 → 제안 생성
import { useState } from 'react';

export type CampaignFormValues = {
  name: string;
  daily_budget_krw: number;
  run_days: number;
  creative_ad_id?: string;
};

function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-[#191F28] dark:text-[#F2F4F6]">{label}</span>
      {children}
      {hint && <span className="block text-[11px] text-[#8B95A1] mt-1">{hint}</span>}
    </label>
  );
}

const inputCls =
  'mt-1.5 w-full rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] bg-transparent px-3 py-2 text-sm text-[#191F28] dark:text-[#F2F4F6] focus:border-[#3182F6] outline-none';

export function CampaignForm({
  onSubmit,
  busy,
}: {
  onSubmit: (v: CampaignFormValues) => void;
  busy: boolean;
}) {
  const [name, setName] = useState('');
  const [budget, setBudget] = useState(50_000);
  const [runDays, setRunDays] = useState(7);
  const [creativeId, setCreativeId] = useState('');

  const valid = name.trim().length > 0 && budget >= 1_000 && runDays >= 1;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (valid && !busy)
          onSubmit({
            name: name.trim(),
            daily_budget_krw: budget,
            run_days: runDays,
            creative_ad_id: creativeId.trim() || undefined,
          });
      }}
      className="rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] p-5 space-y-4 max-w-xl"
    >
      <Field label="캠페인 이름">
        <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="예: 가을 신상 런칭" />
      </Field>
      <div className="grid grid-cols-2 gap-4">
        <Field label="일 예산 (KRW)" hint="최소 ₩1,000">
          <input
            type="number"
            min={1000}
            step={1000}
            className={inputCls}
            value={budget}
            onChange={(e) => setBudget(Number(e.target.value))}
          />
        </Field>
        <Field label="집행 기간 (일)" hint="1~90일">
          <input
            type="number"
            min={1}
            max={90}
            className={inputCls}
            value={runDays}
            onChange={(e) => setRunDays(Number(e.target.value))}
          />
        </Field>
      </div>
      <Field label="목표">
        <div className={`${inputCls} text-[#8B95A1] cursor-not-allowed`}>트래픽 (클릭) · v1 고정</div>
      </Field>
      <Field label="소재 ID (선택)" hint="기존 광고 소재를 연결할 경우">
        <input className={inputCls} value={creativeId} onChange={(e) => setCreativeId(e.target.value)} placeholder="ad_xxxxx" />
      </Field>

      <div className="flex items-center justify-between pt-1">
        <p className="text-[11px] text-[#8B95A1]">예상 총지출 ₩{(budget * runDays).toLocaleString()}</p>
        <button
          type="submit"
          disabled={!valid || busy}
          className="px-4 py-2 bg-[#3182F6] text-white text-sm font-medium rounded-lg hover:bg-[#1B6EEB] disabled:opacity-40"
        >
          {busy ? '생성 중…' : '제안 생성 →'}
        </button>
      </div>
    </form>
  );
}
