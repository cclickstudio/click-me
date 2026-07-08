'use client';

// 패널 휴지통 펼침 내용 — 체크박스 선택 복원/영구삭제 + 전체 복원/비우기. (프로젝트·기업 패널 공용)

import { useState } from 'react';
import Link from 'next/link';
import { authedFetch } from '@/lib/api';
import { formatKSTDate } from '@/lib/datetime';
import type { TrashRow } from './ProjectContext';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

const fmt = (iso: string) => formatKSTDate(iso);

const keyOf = (t: TrashRow) => `${t.kind}-${t.id}`;

export default function TrashSection({
  projectId,
  trashed,
  onChanged,
}: {
  projectId: string;
  trashed: TrashRow[];
  onChanged: () => void;
}) {
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);

  const toggle = (k: string) =>
    setSel((s) => {
      const n = new Set(s);
      if (n.has(k)) n.delete(k);
      else n.add(k);
      return n;
    });

  const split = (items: TrashRow[]) => ({
    sim_ids: items.filter((t) => t.kind === 'sim').map((t) => t.id),
    gen_ids: items.filter((t) => t.kind === 'gen').map((t) => t.id),
  });

  const post = async (action: 'restore' | 'purge', body: object) => {
    setBusy(true);
    const res = await authedFetch(`${API_BASE}/api/projects/${projectId}/trash/${action}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    setBusy(false);
    if (!res.ok) { alert('처리에 실패했습니다.'); return; }
    setSel(new Set());
    onChanged();
  };

  const selectedItems = trashed.filter((t) => sel.has(keyOf(t)));

  const restoreAll = () => post('restore', {});
  const purgeAll = () => {
    if (!confirm('휴지통을 비울까요?\n모든 항목이 영구 삭제되며 되돌릴 수 없습니다.')) return;
    post('purge', {});
  };
  const restoreSel = () => post('restore', split(selectedItems));
  const purgeSel = () => {
    if (!confirm('선택한 항목을 영구 삭제할까요?\n되돌릴 수 없습니다.')) return;
    post('purge', split(selectedItems));
  };

  return (
    <div className="ml-4 space-y-0.5 mt-0.5">
      {/* 전체 액션 */}
      <div className="flex items-center gap-1.5 px-2 py-1">
        <button disabled={busy || trashed.length === 0} onClick={restoreAll}
          className="text-[10px] font-medium text-[#2563EB] hover:underline disabled:opacity-40 disabled:no-underline">전체 복원</button>
        <span className="text-[10px] text-[#D1D6DB]">|</span>
        <button disabled={busy || trashed.length === 0} onClick={purgeAll}
          className="text-[10px] font-medium text-red-500 hover:underline disabled:opacity-40 disabled:no-underline">비우기</button>
      </div>

      {trashed.length === 0 ? (
        <p className="text-xs text-[#B0B8C1] px-2 py-1">비어 있음</p>
      ) : (
        <>
          {trashed.map((t) => (
            <div key={keyOf(t)} className="flex items-center gap-2 px-2 py-1 rounded-md hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D] transition-colors">
              <label className="relative shrink-0 w-4 h-4 cursor-pointer">
                <input
                  type="checkbox"
                  checked={sel.has(keyOf(t))}
                  onChange={() => toggle(keyOf(t))}
                  className="peer sr-only"
                />
                <span className="block w-4 h-4 rounded-[5px] border border-[#D1D6DB] dark:border-[#3A4150] bg-white dark:bg-[#252D3D] peer-checked:bg-[#2563EB] peer-checked:border-[#2563EB] transition-colors" />
                <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" className="absolute inset-0 m-auto w-2.5 h-2.5 opacity-0 peer-checked:opacity-100 pointer-events-none">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              </label>
              <Link
                href={t.kind === 'sim' ? `/simulation/${t.id}` : `/generations/${t.id}`}
                className="flex-1 min-w-0 group"
              >
                <p className="text-xs truncate text-ink-secondary group-hover:text-[#2563EB]">{t.label}</p>
                <p className="text-[10px] text-ink-muted">{t.kind === 'sim' ? '시뮬레이션' : '제너레이터'} · {fmt(t.deleted_at)} 삭제</p>
              </Link>
            </div>
          ))}
          {sel.size > 0 && (
            <div className="flex items-center gap-1.5 px-2 py-1 border-t border-line mt-1">
              <button disabled={busy} onClick={restoreSel}
                className="text-[10px] font-medium text-[#2563EB] hover:underline disabled:opacity-40">선택 복원 ({sel.size})</button>
              <span className="text-[10px] text-[#D1D6DB]">|</span>
              <button disabled={busy} onClick={purgeSel}
                className="text-[10px] font-medium text-red-500 hover:underline disabled:opacity-40">선택 삭제</button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
