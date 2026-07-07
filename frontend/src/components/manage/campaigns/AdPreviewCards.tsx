// 대표 광고 시안 — 같은 크리에이티브를 페북/인스타 스타일 카드 각 1개로 미리보기
'use client';

import type { CreativePreview } from './types';

// 이미지 없을 때(데모·미수집) placeholder — 광고명 + 그라데이션
function Placeholder({ name }: { name: string }) {
  return (
    <div className="flex aspect-square w-full items-center justify-center bg-gradient-to-br from-[#E8F3FF] to-[#F2E8FF] dark:from-[#1E3A5F] dark:to-[#3A2D5F]">
      <span className="px-3 text-center text-[12px] font-medium text-ink-secondary">
        {name || '광고 시안'}
      </span>
    </div>
  );
}

// 원본 해상도 이미지 — 자연 비율(크롭 없음). 차트가 이 카드 높이에 맞춰 늘어난다.
function AdImage({ c }: { c: CreativePreview }) {
  const src = c.image_url || c.thumbnail_url;
  if (!src) return <Placeholder name={c.ad_name} />;
  return (
    // 외부(Meta CDN) 이미지 — next/image 도메인 화이트리스트 회피용 일반 img
    // eslint-disable-next-line @next/next/no-img-element
    <img src={src} alt={c.ad_name} loading="lazy" className="block h-auto w-full" />
  );
}

const cardBase =
  'overflow-hidden rounded-xl border border-line bg-white dark:bg-[#1A1F28]';

// 페이스북 피드 스타일 — 광고주·문구·이미지·헤드라인+CTA·소셜바
function FacebookCard({ c }: { c: CreativePreview }) {
  return (
    <figure className={cardBase}>
      <div className="flex items-center gap-2 px-3 py-2">
        <div className="h-7 w-7 shrink-0 rounded-full bg-gradient-to-br from-[#1877F2] to-[#3182F6]" />
        <div className="min-w-0 flex-1 leading-tight">
          <p className="truncate text-[12px] font-semibold text-ink">광고주</p>
          <p className="text-[10px] text-ink-tertiary">광고 · clickme.co.kr</p>
        </div>
        <span className="text-ink-tertiary">···</span>
      </div>
      {c.primary_text && (
        <p className="px-3 pb-2 text-[12px] leading-snug text-[#333D4B] dark:text-[#D1D6DB]">
          {c.primary_text}
        </p>
      )}
      <div className="w-full bg-surface-1">
        <AdImage c={c} />
      </div>
      <div className="flex items-center justify-between gap-2 bg-[#F7F8FA] px-3 py-2 dark:bg-[#22272F]">
        <div className="min-w-0">
          <p className="text-[10px] uppercase text-ink-tertiary">clickme.co.kr</p>
          <p className="truncate text-[12px] font-semibold text-ink">
            {c.headline || c.ad_name}
          </p>
        </div>
        <span className="shrink-0 rounded-md bg-[#E5E8EB] px-2 py-1 text-[10px] font-semibold text-ink-secondary dark:bg-[#2D3748] dark:text-[#D1D6DB]">
          자세히 보기
        </span>
      </div>
      <div className="flex items-center gap-4 border-t border-[#F2F4F6] px-3 py-1.5 text-[11px] text-ink-tertiary">
        <span>👍 좋아요</span>
        <span>💬 댓글</span>
        <span>↪ 공유</span>
      </div>
    </figure>
  );
}

// 인스타그램 스타일 — 사용자명·이미지·액션아이콘·캡션
function InstagramCard({ c }: { c: CreativePreview }) {
  return (
    <figure className={cardBase}>
      <div className="flex items-center gap-2 px-3 py-2">
        <div className="h-7 w-7 shrink-0 rounded-full bg-gradient-to-br from-[#F58529] via-[#DD2A7B] to-[#8134AF]" />
        <div className="min-w-0 flex-1 leading-tight">
          <p className="truncate text-[12px] font-semibold text-ink">clickme.co.kr</p>
          <p className="text-[10px] text-ink-tertiary">광고</p>
        </div>
        <span className="text-ink-tertiary">···</span>
      </div>
      <div className="w-full bg-surface-1">
        <AdImage c={c} />
      </div>
      <div className="flex items-center justify-between px-3 pt-2 text-[15px]">
        <div className="flex gap-3">
          <span>♡</span>
          <span>💬</span>
          <span>↪</span>
        </div>
        <span>🔖</span>
      </div>
      <p className="px-3 pt-1.5 text-[12px] leading-snug text-[#333D4B] dark:text-[#D1D6DB]">
        <span className="font-semibold text-ink">clickme.co.kr</span>{' '}
        {c.primary_text || c.headline || c.ad_name}
      </p>
      <p className="px-3 pb-2 pt-1 text-[12px] font-semibold text-primary">자세히 보기 ›</p>
    </figure>
  );
}

export default function AdPreviewCards({ items }: { items: CreativePreview[] }) {
  // 대표 1개를 페북/인스타 두 스타일로 좌우 배치 — placement≠크리에이티브라 동일 시안을 양 채널 형태로
  const c = items[0];
  if (!c) return null;
  return (
    <div className="grid grid-cols-2 gap-3">
      <div>
        <p className="mb-1 text-[11px] font-medium text-ink-tertiary">Facebook</p>
        <FacebookCard c={c} />
      </div>
      <div>
        <p className="mb-1 text-[11px] font-medium text-ink-tertiary">Instagram</p>
        <InstagramCard c={c} />
      </div>
    </div>
  );
}
