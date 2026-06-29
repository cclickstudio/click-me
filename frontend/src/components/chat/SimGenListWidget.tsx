'use client';

// 채팅 공통 목록 위젯 — 시뮬/제너 과거 실행 목록. 읽기용(보기·요약)과 선택용(개선·이어가기) 두 모드.
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { formatKST } from '@/lib/datetime';
import ComparisonWidget from './ComparisonWidget';

type ListItem = {
  id: string;
  title: string;
  status?: string;
  created_at?: string | null;
  sample_size?: number;
  mode?: string;
};
type Domain = 'sim' | 'gen';

const cardCls =
  'mt-1 w-full rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#1C2333] p-3';

const fmtDate = formatKST;

const pct = (n: unknown) => (typeof n === 'number' ? `${(n * 100).toFixed(0)}%` : '—');
const sc = (n: unknown) => (typeof n === 'number' ? n.toFixed(2) : '—');

// 읽기용 1행 — 클릭 시 요약 토글(결과 요약 API), 상세 페이지 링크 제공.
function ReadRow({ domain, item }: { domain: Domain; item: ListItem }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [summary, setSummary] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);

  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (next && summary === null) {
      setLoading(true);
      try {
        setSummary((await api.chat.resultSummary(domain, item.id)) as Record<string, unknown>);
      } catch {
        setSummary({ error: 'load_failed' });
      } finally {
        setLoading(false);
      }
    }
  };

  const detailHref = domain === 'sim' ? `/simulation/${item.id}` : `/generations/${item.id}`;

  return (
    <div className="rounded-lg border border-[#E5E8EB] dark:border-[#2D3748]">
      <button
        onClick={toggle}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-[#F9FAFB] dark:hover:bg-[#252D3D] transition-colors rounded-lg"
      >
        <div className="flex-1 min-w-0">
          <p className="text-sm text-[#191F28] dark:text-[#F2F4F6] truncate">{item.title}</p>
          <p className="text-[10px] text-[#B0B8C1]">
            {item.status ?? ''}
            {item.sample_size ? ` · ${item.sample_size}명` : ''}
            {item.created_at ? ` · ${fmtDate(item.created_at)}` : ''}
          </p>
        </div>
        <span className="text-[10px] text-[#8B95A1] shrink-0">{open ? '접기' : '요약'}</span>
      </button>
      {open && (
        <div className="px-3 pb-3 pt-1 border-t border-[#E5E8EB] dark:border-[#2D3748]">
          {loading ? (
            <p className="text-xs text-[#B0B8C1] py-1">불러오는 중...</p>
          ) : summary?.error ? (
            <p className="text-xs text-[#B0B8C1] py-1">요약을 불러오지 못했어요.</p>
          ) : domain === 'sim' ? (
            <div className="grid grid-cols-2 gap-1.5 text-xs py-1">
              <span className="text-[#8B95A1]">클릭 의향률 <b className="text-[#191F28] dark:text-[#F2F4F6]">{pct(summary?.click_intent_rate)}</b></span>
              <span className="text-[#8B95A1]">구매의도 <b className="text-[#191F28] dark:text-[#F2F4F6]">{sc(summary?.purchase_intent)}/5</b></span>
              <span className="text-[#8B95A1]">신뢰도 <b className="text-[#191F28] dark:text-[#F2F4F6]">{sc(summary?.trust_avg)}/5</b></span>
              <span className="text-[#8B95A1]">거부율 <b className="text-[#191F28] dark:text-[#F2F4F6]">{pct(summary?.rejection_rate)}</b></span>
            </div>
          ) : (
            <p className="text-xs text-[#4E5968] dark:text-[#9CA3AF] py-1">
              시안 {String((summary?.candidate_count as number) ?? 0)}개
              {summary?.status ? ` · ${String(summary.status)}` : ''}
            </p>
          )}
          <button
            onClick={() => router.push(detailHref)}
            className="mt-1 text-xs text-[#3182F6] font-semibold hover:underline"
          >
            상세 보기 →
          </button>
        </div>
      )}
    </div>
  );
}

// 비교(compare) 모드 — 시뮬 2개를 체크 선택 → 비교 표 렌더.
function CompareList({ items }: { items: ListItem[] }) {
  const [picked, setPicked] = useState<string[]>([]);
  const [confirmed, setConfirmed] = useState<{ id: string; title: string }[] | null>(null);

  const toggle = (id: string) => {
    setPicked((prev) =>
      prev.includes(id) ? prev.filter((p) => p !== id) : prev.length < 2 ? [...prev, id] : prev,
    );
  };

  if (confirmed) {
    return <ComparisonWidget items={confirmed} />;
  }

  return (
    <>
      <div className="space-y-1.5">
        {items.map((it) => {
          const on = picked.includes(it.id);
          return (
            <button
              key={it.id}
              onClick={() => toggle(it.id)}
              className={`w-full flex items-center gap-2 px-3 py-2 text-left rounded-lg border transition-colors ${
                on
                  ? 'border-[#3182F6] bg-[#EBF3FF] dark:bg-[#1E3A5F]'
                  : 'border-[#E5E8EB] dark:border-[#2D3748] hover:border-[#3182F6]'
              }`}
            >
              <span
                className={`w-4 h-4 rounded border shrink-0 flex items-center justify-center text-[10px] ${
                  on ? 'bg-[#3182F6] border-[#3182F6] text-white' : 'border-[#B0B8C1]'
                }`}
              >
                {on ? '✓' : ''}
              </span>
              <span className="flex-1 min-w-0 text-sm text-[#191F28] dark:text-[#F2F4F6] truncate">
                {it.title}
              </span>
            </button>
          );
        })}
      </div>
      <button
        disabled={picked.length !== 2}
        onClick={() =>
          setConfirmed(
            picked.map((id) => ({ id, title: items.find((x) => x.id === id)?.title ?? id })),
          )
        }
        className="mt-2 w-full py-2 rounded-lg bg-[#3182F6] text-white text-sm font-semibold hover:bg-[#1B6EEB] disabled:opacity-40 transition-colors"
      >
        비교하기 {picked.length}/2
      </button>
    </>
  );
}

export default function SimGenListWidget({
  domain,
  mode,
  items,
  onResult,
}: {
  domain: Domain;
  mode: 'read' | 'select' | 'compare';
  items: ListItem[];
  onResult?: (message: string) => void; // 선택 시 후속 메시지를 채팅으로 보냄
}) {
  if (!items || items.length === 0) {
    return (
      <div className={cardCls}>
        <p className="text-sm text-[#8B95A1]">아직 {domain === 'sim' ? '시뮬레이션' : '광고 생성'} 내역이 없어요.</p>
      </div>
    );
  }

  // 선택 시 보낼 후속 메시지(개선·이어가기 흐름으로 라우팅).
  const selectMessage = (item: ListItem) =>
    domain === 'sim'
      ? `'${item.title}' 시뮬레이션 결과를 바탕으로 광고 시안을 개선해줘`
      : `'${item.title}' 시안으로 시뮬레이션을 돌려줘`;

  return (
    <div className={cardCls}>
      <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-2">
        {domain === 'sim' ? '🧪' : '🎨'}{' '}
        {mode === 'select'
          ? `${domain === 'sim' ? '시뮬레이션' : '광고 생성'} 선택`
          : mode === 'compare'
            ? '시뮬레이션 비교'
            : `최근 ${domain === 'sim' ? '시뮬레이션' : '광고 생성'}`}
        <span className="text-[11px] font-normal text-[#8B95A1]"> ({items.length})</span>
      </p>
      {mode === 'compare' ? (
        <CompareList items={items} />
      ) : (
      <div className="space-y-1.5">
        {mode === 'read'
          ? items.map((it) => <ReadRow key={it.id} domain={domain} item={it} />)
          : items.map((it) => (
              <button
                key={it.id}
                onClick={() => onResult?.(selectMessage(it))}
                className="w-full flex items-center gap-2 px-3 py-2 text-left rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] hover:border-[#3182F6] hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F] transition-colors"
              >
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-[#191F28] dark:text-[#F2F4F6] truncate">{it.title}</p>
                  <p className="text-[10px] text-[#B0B8C1]">
                    {it.status ?? ''}
                    {it.created_at ? ` · ${fmtDate(it.created_at)}` : ''}
                  </p>
                </div>
                <span className="text-xs text-[#3182F6] font-semibold shrink-0">선택 →</span>
              </button>
            ))}
      </div>
      )}
    </div>
  );
}
