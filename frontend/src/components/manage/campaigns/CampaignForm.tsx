// 신규 캠페인 생성 폼 — 목표·예산·기간·소재 입력 → 제안 생성
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';

export type CampaignFormValues = {
  name: string;
  objective: 'traffic' | 'leads'; // 트래픽(클릭) / 리드(잠재고객 폼) — 리드라야 전환·ROAS 측정
  daily_budget_krw: number;
  run_days: number;
  creative_ad_id?: string;
  image_hash?: string; // 업로드한 광고 소재 이미지
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
  // 기본(자동): 총 예산만 받고 일 예산=Meta 최소·일수=최대한 길게로 폼이 자동 최적화(전략).
  // 기본값은 최소 금액(Meta floor) — 사용자가 직접 만지기 전까진 minBudget을 따라간다.
  const [total, setTotal] = useState(1_521);
  const [totalTouched, setTotalTouched] = useState(false); // 사용자가 총예산을 직접 만졌는가
  const [advanced, setAdvanced] = useState(false); // 고급 — 일예산·일수 직접 설정
  // 고급 모드 전용(자동 모드에선 floor·계산값을 씀).
  const [budget, setBudget] = useState(0);
  const [budgetTouched, setBudgetTouched] = useState(false); // 사용자가 예산을 직접 만졌는가
  const [runDays, setRunDays] = useState(1);
  const [creativeId, setCreativeId] = useState('');
  const [specialCat, setSpecialCat] = useState('NONE');
  const [country, setCountry] = useState('KR');
  const [ageMin, setAgeMin] = useState(18);
  const [ageMax, setAgeMax] = useState(65);
  const [gender, setGender] = useState<'all' | 'male' | 'female'>('all');
  // 광고 소재 이미지 — 업로드 시 Meta image_hash 받아 보관 + 샘플 시안 미리보기.
  const [imageHash, setImageHash] = useState<string | null>(null);
  const [imageName, setImageName] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [previews, setPreviews] = useState<{ format: string; html: string }[]>([]);
  const [previewing, setPreviewing] = useState(false);
  const [imgError, setImgError] = useState<string | null>(null);

  const onPickImage = async (file: File | undefined) => {
    if (!file) return;
    setUploading(true);
    setImgError(null);
    setPreviews([]);
    try {
      const r = await api.management.uploadAdImage(file);
      if (!r.image_hash) throw new Error('업로드 실패 (실모드에서만 가능)');
      setImageHash(r.image_hash);
      setImageName(file.name);
    } catch (e) {
      setImgError(e instanceof Error ? e.message : '이미지 업로드 실패');
    } finally {
      setUploading(false);
    }
  };

  const onPreview = async () => {
    if (!imageHash) return;
    setPreviewing(true);
    setImgError(null);
    try {
      const r = await api.management.adPreview(imageHash, name.trim() || undefined);
      setPreviews(r.previews ?? []);
    } catch (e) {
      setImgError(e instanceof Error ? e.message : '시안 생성 실패');
    } finally {
      setPreviewing(false);
    }
  };
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
  // 고급 모드에서 사용자가 안 만졌으면 최소로 따라간다(자동 모드는 floor 고정이라 무관).
  useEffect(() => {
    if (!budgetTouched) setBudget(minBudget);
  }, [minBudget, budgetTouched]);
  // 간편 모드 총 예산도 안 만졌으면 최소(minBudget)로 — 기본을 5만원이 아닌 최소로 픽스.
  useEffect(() => {
    if (!totalTouched) setTotal(minBudget);
  }, [minBudget, totalTouched]);

  // 자동 전략 — 일 예산 = floor(최소), 일수 = 최대(총÷floor, ≤90). 총<floor면 1일도 불가.
  const autoDays = total >= minBudget ? Math.min(Math.floor(total / minBudget), 90) : 0;
  const autoTotal = minBudget * autoDays; // 실제 집행될 총액(일예산×일수)
  // 실제 전송될 값 — 자동이면 floor·autoDays, 고급이면 사용자 입력.
  const sendDaily = advanced ? budget : minBudget;
  const sendDays = advanced ? runDays : autoDays;
  const valid =
    name.trim().length > 0 && sendDaily >= minBudget && sendDays >= 1 && sendDays <= 90;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (valid && !busy)
          onSubmit({
            name: name.trim(),
            objective,
            daily_budget_krw: sendDaily,
            run_days: sendDays,
            creative_ad_id: creativeId.trim() || undefined,
            image_hash: imageHash || undefined,
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
      {/* 예산 — 기본은 '총 예산만' 받고 일별은 자동 최적화(최소 일예산 × 최대 일수) */}
      <div>
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-[#191F28] dark:text-[#F2F4F6]">예산</span>
          <button
            type="button"
            onClick={() => setAdvanced((v) => !v)}
            className="text-[11px] font-medium text-[#8B95A1] hover:text-[#3182F6]"
          >
            {advanced ? '간편 설정으로' : '직접 설정(고급)'}
          </button>
        </div>

        {!advanced ? (
          <>
            <input
              type="number"
              min={minBudget}
              step={1000}
              className={inputCls}
              value={total}
              onChange={(e) => {
                setTotal(Number(e.target.value));
                setTotalTouched(true);
              }}
              placeholder={`총 예산 (최소 ₩${minBudget.toLocaleString()})`}
            />
            {autoDays > 0 ? (
              <div className="mt-2 rounded-xl bg-[#F2F9FF] dark:bg-[#16263A] px-3 py-2.5">
                <p className="text-sm font-semibold text-[#3182F6]">
                  일 ₩{minBudget.toLocaleString()} × {autoDays}일 = ₩{autoTotal.toLocaleString()}
                </p>
                <p className="mt-0.5 text-[11px] text-[#4E5968] dark:text-[#9CA3AF]">
                  최소 비용으로 최대한 길게 노출 — Meta 최소 일예산으로 가장 오래 집행해 노출·클릭에 유리.
                </p>
                <p className="mt-0.5 text-[11px] text-[#8B95A1]">
                  너무 낮은 일예산은 초반 게재가 느릴 수 있어요. 빠른 게재가 필요하면 ‘직접 설정’.
                </p>
              </div>
            ) : (
              <p className="mt-1.5 text-[11px] text-red-500">
                총 예산이 Meta 최소 일예산(₩{minBudget.toLocaleString()})보다 커야 해요.
              </p>
            )}
          </>
        ) : (
          <div className="mt-1.5 grid grid-cols-2 gap-4">
            <Field
              label="일 예산 (KRW)"
              hint={`Meta 최소 ₩${minBudget.toLocaleString()} (${objective === 'leads' ? '리드' : '트래픽'})`}
            >
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
        )}
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

      {/* ── 광고 소재 이미지 (업로드 → Meta 해시 → 샘플 시안) ── */}
      <Field label="광고 이미지" hint="업로드하면 Meta가 FB·인스타에 자동 배치 게재 · 시안 미리보기 가능">
        <div className="mt-1.5 flex flex-wrap items-center gap-2">
          <label className="cursor-pointer rounded-xl border border-dashed border-[#C9CED6] dark:border-[#3A4452] px-3 py-2 text-sm text-[#4E5968] dark:text-[#9CA3AF] hover:border-[#3182F6]">
            {uploading ? '업로드 중…' : imageName ? '이미지 변경' : '이미지 선택'}
            <input
              type="file"
              accept="image/*"
              className="hidden"
              disabled={uploading}
              onChange={(e) => onPickImage(e.target.files?.[0])}
            />
          </label>
          {imageHash && (
            <>
              <span className="text-[12px] text-green-600">✓ {imageName}</span>
              <button
                type="button"
                onClick={onPreview}
                disabled={previewing}
                className="rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] px-2.5 py-1.5 text-[12px] font-medium text-[#3182F6] disabled:opacity-40"
              >
                {previewing ? '시안 생성 중…' : '샘플 시안 보기'}
              </button>
            </>
          )}
        </div>
        {imgError && <span className="mt-1 block text-[11px] text-red-500">{imgError}</span>}
      </Field>

      {previews.length > 0 && (
        <div className="rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] p-3">
          <p className="mb-2 text-[12px] font-semibold text-[#4E5968] dark:text-[#9CA3AF]">
            샘플 시안 (페이스북 · 인스타그램)
          </p>
          <div className="flex flex-wrap gap-3">
            {previews.map((p) => (
              <div
                key={p.format}
                className="overflow-hidden rounded-lg border border-[#E5E8EB] dark:border-[#2D3748]"
                // Meta 호스팅 iframe — 샌드박스된 미리보기
                dangerouslySetInnerHTML={{ __html: p.html }}
              />
            ))}
          </div>
        </div>
      )}

      <Field label="기존 광고 재사용 (선택)" hint="보통 비워두세요 — 위에 올린 이미지로 새 소재를 만듭니다. Ads Manager의 기존 광고를 그대로 쓸 때만 그 광고 ID 입력(.env 값 아님)">
        <input className={inputCls} value={creativeId} onChange={(e) => setCreativeId(e.target.value)} placeholder="비워두기 (또는 Ads Manager 광고 ID)" />
      </Field>

      <div className="flex items-center justify-between pt-1">
        <p className="text-[11px] text-[#8B95A1]">
          예상 총지출 ₩{(advanced ? budget * runDays : autoTotal).toLocaleString()}
        </p>
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
