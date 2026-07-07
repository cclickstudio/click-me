'use client';

// 채팅 /키워드 — 광고 맥락(제품·카테고리·타깃·카피)으로 SNS 해시태그·키워드를 추천받아 칩으로 표시(F10).
// 칩 클릭 시 개별 복사, "전체 복사"로 묶음 복사. 백엔드 POST /api/chat/keywords(gpt-4o-mini) 호출.
import { useState } from 'react';
import { api } from '@/lib/api';

const cardCls =
  'mt-1 w-full rounded-xl border border-line bg-card p-4';
const labelCls =
  'text-[11px] font-semibold text-ink-tertiary mb-1 block';
const inputCls =
  'w-full px-3 py-2 rounded-lg border border-line text-sm bg-surface-2 text-ink focus:outline-none focus:border-primary';

// 클립보드 복사(P10 패턴) — Clipboard API + execCommand 폴백.
async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    try {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand('copy');
      document.body.removeChild(ta);
      return ok;
    } catch {
      return false;
    }
  }
}

type Result = { hashtags: string[]; keywords: string[] };

export default function KeywordWidget({
  initial,
}: {
  initial?: { product?: string; category?: string; target?: string; copy?: string };
}) {
  const [product, setProduct] = useState(initial?.product ?? '');
  const [category, setCategory] = useState(initial?.category ?? '');
  const [target, setTarget] = useState(initial?.target ?? '');
  const [copy, setCopy] = useState(initial?.copy ?? '');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [copied, setCopied] = useState<string | null>(null); // 마지막 복사한 칩 텍스트
  const [allCopied, setAllCopied] = useState(false);

  const canSubmit =
    !loading &&
    (product.trim() || category.trim() || target.trim() || copy.trim()) !== '';

  const generate = async () => {
    if (!canSubmit) return;
    setLoading(true);
    setError(null);
    try {
      const r = await api.chat.keywords({
        product: product.trim() || undefined,
        category: category.trim() || undefined,
        target: target.trim() || undefined,
        copy_text: copy.trim() || undefined,
      });
      setResult(r);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : '키워드를 불러오지 못했어요. 다시 시도해 주세요.'
      );
    } finally {
      setLoading(false);
    }
  };

  const onChip = async (text: string) => {
    if (await copyText(text)) {
      setCopied(text);
      setTimeout(() => setCopied(c => (c === text ? null : c)), 1200);
    }
  };

  const copyAll = async () => {
    if (!result) return;
    const all = [...result.hashtags, ...result.keywords].join(' ');
    if (await copyText(all)) {
      setAllCopied(true);
      setTimeout(() => setAllCopied(false), 1500);
    }
  };

  const chip = (text: string, kind: 'tag' | 'kw') => (
    <button
      key={`${kind}-${text}`}
      type='button'
      onClick={() => onChip(text)}
      title='클릭하면 복사돼요'
      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[12px] transition-colors ${
        copied === text
          ? 'border-[#15803D] bg-[#EAFBF1] text-[#15803D] dark:bg-[#0F2A1C] dark:border-[#1B4D33] dark:text-[#4ADE80]'
          : kind === 'tag'
            ? 'border-line bg-[#EBF3FF] text-primary hover:border-primary dark:bg-[#1E3A5F] dark:text-[#9CC4FF]'
            : 'border-line bg-white text-ink-secondary hover:border-primary hover:text-primary dark:bg-[#252D3D]'
      }`}>
      {copied === text ? '복사됨 ✓' : text}
    </button>
  );

  return (
    <div className={cardCls}>
      <p className='text-sm font-semibold text-ink mb-3'>
        #️⃣ 해시태그·키워드 추천
      </p>

      <div className='space-y-3'>
        <div>
          <label className={labelCls}>제품·서비스</label>
          <input
            className={inputCls}
            value={product}
            onChange={e => setProduct(e.target.value)}
            placeholder='예: 클릭미 수분 크림'
          />
        </div>
        <div className='grid grid-cols-2 gap-2'>
          <div>
            <label className={labelCls}>업종·카테고리</label>
            <input
              className={inputCls}
              value={category}
              onChange={e => setCategory(e.target.value)}
              placeholder='예: 뷰티/스킨케어'
            />
          </div>
          <div>
            <label className={labelCls}>타깃 고객</label>
            <input
              className={inputCls}
              value={target}
              onChange={e => setTarget(e.target.value)}
              placeholder='예: 20대 여성'
            />
          </div>
        </div>
        <div>
          <label className={labelCls}>광고 카피 (선택)</label>
          <input
            className={inputCls}
            value={copy}
            onChange={e => setCopy(e.target.value)}
            placeholder='예: 하루 종일 촉촉함, 가벼운 수분 크림'
          />
        </div>
        <button
          onClick={generate}
          disabled={!canSubmit}
          className='w-full py-2 rounded-lg bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary-hover disabled:opacity-40 transition-colors'>
          {loading ? '추천 중…' : result ? '다시 추천받기' : '키워드 추천받기'}
        </button>
      </div>

      {error && (
        <p className='mt-3 text-[12px] text-[#F04452]'>{error}</p>
      )}

      {result && (result.hashtags.length > 0 || result.keywords.length > 0) && (
        <div className='mt-4 space-y-3'>
          {result.hashtags.length > 0 && (
            <div>
              <p className={labelCls}>해시태그</p>
              <div className='flex flex-wrap gap-1.5'>
                {result.hashtags.map(t => chip(t, 'tag'))}
              </div>
            </div>
          )}
          {result.keywords.length > 0 && (
            <div>
              <p className={labelCls}>키워드</p>
              <div className='flex flex-wrap gap-1.5'>
                {result.keywords.map(k => chip(k, 'kw'))}
              </div>
            </div>
          )}
          <button
            onClick={copyAll}
            className='w-full py-1.5 rounded-lg border border-line text-[12px] font-semibold text-ink-secondary hover:border-primary hover:text-primary transition-colors'>
            {allCopied ? '전체 복사됨 ✓' : '전체 복사'}
          </button>
        </div>
      )}
    </div>
  );
}
