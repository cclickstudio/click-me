// 신규 캠페인 생성 폼 — 목표·예산·기간·소재 입력 → 제안 생성
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';

export type CampaignFormValues = {
  name: string;
  objective: 'traffic' | 'leads'; // 트래픽(클릭) / 리드(잠재고객 폼) — 리드라야 전환·ROAS 측정
  daily_budget_krw: number;
  run_days: number;
  creative_ad_id?: string;
  special_ad_category: string; // NONE | HOUSING | EMPLOYMENT | CREDIT | ISSUES_ELECTIONS_POLITICS
  country: string; // ISO2
  age_min: number;
  age_max: number;
  gender: 'all' | 'male' | 'female';
};

// 특별 광고 카테고리 — 라벨은 백엔드 정책(/campaign-policy)에서 받아온다(정책 변경 시 자동 반영).
// 아래는 정책 도착 전 폴백일 뿐. 실제 표시는 서버 값 우선.
type Category = { value: string; label: string };
const DEFAULT_CATEGORIES: Category[] = [
  { value: 'NONE', label: '없음' },
  { value: 'HOUSING', label: '주택' },
  { value: 'EMPLOYMENT', label: '고용' },
  { value: 'CREDIT', label: '금융 상품·서비스' },
  { value: 'ISSUES_ELECTIONS_POLITICS', label: '사회·선거·정치' },
];
const COUNTRIES: { code: string; label: string }[] = [
  { code: 'KR', label: '대한민국' },
  { code: 'US', label: '미국' },
  { code: 'JP', label: '일본' },
];

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
  const [objective, setObjective] = useState<'traffic' | 'leads'>('traffic');
  // 기본값은 '최소 위주' — 예산은 정책의 목표별 최소(=Meta floor)를 따라가고, 기간은 최소 1일.
  const [budget, setBudget] = useState(0);
  const [budgetTouched, setBudgetTouched] = useState(false); // 사용자가 예산을 직접 만졌는가
  const [runDays, setRunDays] = useState(1);
  const [creativeId, setCreativeId] = useState('');
  const [specialCat, setSpecialCat] = useState('NONE');
  const [country, setCountry] = useState('KR');
  const [ageMin, setAgeMin] = useState(18);
  const [ageMax, setAgeMax] = useState(65);
  const [gender, setGender] = useState<'all' | 'male' | 'female'>('all');
  // Meta 정책(최소예산·특별카테고리 등)을 서버에서 받아온다 — 코드 하드코딩 대신 자동 최신화.
  // 폴백도 휴리스틱 금지 — 계정 floor 실측값(₩1,521)을 둘 다 동일하게(정책 도착 시 덮어씀).
  const [minByObjective, setMinByObjective] = useState<Record<string, number>>({
    traffic: 1_521,
    leads: 1_521,
  });
  const [categories, setCategories] = useState<Category[]>(DEFAULT_CATEGORIES);
  // 정책상 허용 연령 범위(인풋 min/max) — 백엔드 정책에서 받아 자동 반영.
  const [ageBounds, setAgeBounds] = useState({ min: 18, max: 65 });

  useEffect(() => {
    api.management
      .campaignPolicy()
      .then((p) => {
        setMinByObjective(p.min_by_objective_krw);
        if (p.special_ad_categories?.length) setCategories(p.special_ad_categories);
        if (p.age_min && p.age_max) setAgeBounds({ min: p.age_min, max: p.age_max });
      })
      .catch(() => {}); // 실패 시 폴백 기본값 유지
  }, []);

  // 목표별 최소 일예산 = Meta floor(정책에서 받음). 미달이면 Meta가 광고세트 생성을 거부한다.
  const minBudget = minByObjective[objective] ?? 1_521;
  // 사용자가 안 만졌으면 항상 최소(=floor)로 따라간다 — 기본 '최소 위주' + 정책 변경 자동 반영.
  useEffect(() => {
    if (!budgetTouched) setBudget(minBudget);
  }, [minBudget, budgetTouched]);
  const valid = name.trim().length > 0 && budget >= minBudget && runDays >= 1;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (valid && !busy)
          onSubmit({
            name: name.trim(),
            objective,
            daily_budget_krw: budget,
            run_days: runDays,
            creative_ad_id: creativeId.trim() || undefined,
            special_ad_category: specialCat,
            country,
            age_min: ageMin,
            age_max: ageMax,
            gender,
          });
      }}
      className="rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] p-5 space-y-4 max-w-xl"
    >
      <Field label="캠페인 이름">
        <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="예: 가을 신상 런칭" />
      </Field>
      <div className="grid grid-cols-2 gap-4">
        <Field label="일 예산 (KRW)" hint={`Meta 최소 ₩${minBudget.toLocaleString()} (${objective === 'leads' ? '리드' : '트래픽'})`}>
          <input
            type="number"
            min={minBudget}
            step={1000}
            className={inputCls}
            value={budget}
            onChange={(e) => {
              setBudgetTouched(true);
              setBudget(Number(e.target.value));
            }}
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
      <Field label="목표" hint="리드는 잠재고객 폼(즉석 양식)으로 전환·ROAS 측정이 가능">
        <select
          className={inputCls}
          value={objective}
          onChange={(e) => setObjective(e.target.value as 'traffic' | 'leads')}
        >
          <option value="traffic">트래픽 (클릭)</option>
          <option value="leads">리드 (잠재고객 폼)</option>
        </select>
      </Field>

      {/* ── 광고세트 타겟 (Meta) ── */}
      <p className="text-[11px] font-semibold text-[#8B95A1] pt-1 border-t border-[#F2F4F6] dark:border-[#2D3748]">
        타겟 · 정책
      </p>
      <div className="grid grid-cols-2 gap-4">
        <Field label="위치">
          <select className={inputCls} value={country} onChange={(e) => setCountry(e.target.value)}>
            {COUNTRIES.map((c) => (
              <option key={c.code} value={c.code}>
                {c.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="성별">
          <select
            className={inputCls}
            value={gender}
            onChange={(e) => setGender(e.target.value as 'all' | 'male' | 'female')}
          >
            <option value="all">전체</option>
            <option value="male">남성</option>
            <option value="female">여성</option>
          </select>
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Field label="연령 최소" hint={`특별 카테고리는 ${ageBounds.min}세 이상 강제`}>
          <input
            type="number"
            min={ageBounds.min}
            max={ageBounds.max}
            className={inputCls}
            value={ageMin}
            onChange={(e) => setAgeMin(Number(e.target.value))}
          />
        </Field>
        <Field label="연령 최대">
          <input
            type="number"
            min={ageBounds.min}
            max={ageBounds.max}
            className={inputCls}
            value={ageMax}
            onChange={(e) => setAgeMax(Number(e.target.value))}
          />
        </Field>
      </div>
      <Field label="특별 광고 카테고리" hint="주택·고용·금융·정치 광고는 Meta 정책상 신고 필수">
        <select
          className={inputCls}
          value={specialCat}
          onChange={(e) => setSpecialCat(e.target.value)}
        >
          {categories.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </select>
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
