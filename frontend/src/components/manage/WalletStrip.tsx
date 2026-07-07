// 계정 지갑 스트립 — 선불 잔액·누적 지출·충전 한도를 스탯 블록으로, 소진율은 게이지로. 설명은 접이식(ⓘ).
// 캠페인·모니터링 페이지의 중복 지갑 카드를 이 한 컴포넌트로 통일한다.
'use client';

import { useState, type ReactNode } from 'react';
import type { AccountWallet } from '@/components/manage/campaigns/types';

// 라벨 위·값 아래 스탯 블록 — KPI 타일과 같은 위계(12px 회색 라벨 + 굵은 tabular 숫자)
function Stat({ label, value, valueClass }: { label: string; value: string; valueClass?: string }) {
  return (
    <div>
      <p className="text-[12px] text-ink-tertiary">{label}</p>
      <p
        className={`mt-0.5 text-[16px] font-bold tabular-nums ${valueClass ?? 'text-ink'}`}
      >
        {value}
      </p>
    </div>
  );
}

function Divider() {
  return <div className="hidden h-8 w-px shrink-0 bg-[#F2F4F6] dark:bg-[#2D3748] sm:block" />;
}

// 반원 게이지 — 한도 소진율. 반지름 26 반원(호 길이 πr), stroke-dasharray로 채움. 홈 타일에서도 재사용.
export function ArcGauge({ pct, strokeClass }: { pct: number; strokeClass: string }) {
  const C = Math.PI * 26;
  const filled = (Math.min(pct, 100) / 100) * C;
  return (
    <svg width="64" height="38" viewBox="0 0 64 38" className="overflow-visible">
      <path
        d="M6 34 A26 26 0 0 1 58 34"
        fill="none"
        strokeWidth="7"
        strokeLinecap="round"
        className="stroke-[#F2F4F6] dark:stroke-[#2D3748]"
      />
      <path
        d="M6 34 A26 26 0 0 1 58 34"
        fill="none"
        strokeWidth="7"
        strokeLinecap="round"
        strokeDasharray={`${filled} ${C}`}
        className={strokeClass}
      />
    </svg>
  );
}

export function WalletStrip({
  account,
  extra,
  explain,
}: {
  account: AccountWallet;
  extra?: ReactNode; // 잔액 런웨이 등 페이지별 추가 항목
  explain?: ReactNode; // 접이식 설명(지갑 개념·지표 정의 등) — 기본 접힘
}) {
  const [open, setOpen] = useState(false);
  const spent = account.amount_spent_krw ?? 0;
  const cap = account.spend_cap_krw;
  const pct = cap != null && cap > 0 ? Math.min(100, Math.round((spent / cap) * 100)) : null;
  // 게이지 임계색 — 캠페인 카드 소진율과 동일 규칙(95% 빨강 / 80% 주황 / 그 외 파랑)
  const meterStroke =
    pct == null
      ? ''
      : pct >= 95
        ? 'stroke-red-500'
        : pct >= 80
          ? 'stroke-amber-500'
          : 'stroke-[#3182F6]';
  const pctText =
    pct == null
      ? ''
      : pct >= 95
        ? 'text-red-600 dark:text-red-400'
        : pct >= 80
          ? 'text-amber-600 dark:text-amber-400'
          : 'text-ink';
  return (
    <div className="mb-4 rounded-xl border border-line bg-white px-4 py-3.5 dark:bg-[#1A1F28]">
      <div className="flex items-center justify-between">
        <span className="text-[13px] font-semibold text-ink-secondary">
          계정 지갑
        </span>
        {explain && (
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            className="shrink-0 text-[12px] text-ink-tertiary transition-colors hover:text-primary"
          >
            ⓘ 지갑·지표 설명 {open ? '▲' : '▾'}
          </button>
        )}
      </div>
      <div className="mt-2.5 flex flex-wrap items-center gap-x-5 gap-y-3">
        <Stat
          label="선불 잔액"
          value={`₩${(account.available_balance_krw ?? 0).toLocaleString()}`}
        />
        <Divider />
        <Stat label="누적 지출" value={`₩${spent.toLocaleString()}`} />
        {cap != null && cap > 0 && (
          <>
            <Divider />
            <Stat label="충전 한도" value={`₩${cap.toLocaleString()}`} />
            <Divider />
            <div className="flex items-center gap-2.5">
              <div className="relative">
                <ArcGauge pct={pct ?? 0} strokeClass={meterStroke} />
                <span
                  className={`absolute inset-x-0 bottom-0 text-center text-[12px] font-bold tabular-nums ${pctText}`}
                >
                  {pct}%
                </span>
              </div>
              <div>
                <p className="text-[12px] text-ink-tertiary">한도 소진율</p>
                {pct != null && pct >= 95 && (
                  <p className={`text-[11px] font-semibold ${pctText}`}>거의 소진</p>
                )}
              </div>
            </div>
          </>
        )}
        {extra && (
          <>
            <Divider />
            {extra}
          </>
        )}
      </div>
      {open && explain && (
        <div className="mt-3 space-y-1 rounded-lg bg-[#F9FAFB] px-3.5 py-2.5 text-[13px] leading-relaxed text-[#6B7684] dark:bg-[#232A36]">
          {explain}
        </div>
      )}
    </div>
  );
}
