'use client';

// 고객 문의 관리 — 목록 조회·상태 필터(전체/미해결/해결됨)·해결 처리(ADMIN 전용)

import { useEffect, useState } from 'react';
import { Check, RotateCcw, Mail, Inbox } from 'lucide-react';
import { api } from '@/lib/api';
import { formatKST } from '@/lib/datetime';

type Inquiry = {
  id: string;
  title: string;
  content: string;
  contact_email: string | null;
  is_resolved: boolean;
  created_at: string;
  resolved_at: string | null;
};

type TabKey = 'all' | 'open' | 'resolved';
const TABS: { key: TabKey; label: string }[] = [
  { key: 'all', label: '전체' },
  { key: 'open', label: '미해결' },
  { key: 'resolved', label: '해결됨' },
];

export default function Page() {
  const [items, setItems] = useState<Inquiry[]>([]);
  const [tab, setTab] = useState<TabKey>('all');
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  const load = () =>
    api.admin
      .inquiries()
      .then((r) => setItems(r.inquiries))
      .catch(() => setItems([]))
      .finally(() => setLoaded(true));

  useEffect(() => {
    load();
  }, []);

  const openCount = items.filter((i) => !i.is_resolved).length;
  const resolvedCount = items.length - openCount;
  const counts: Record<TabKey, number> = { all: items.length, open: openCount, resolved: resolvedCount };
  const filtered = items.filter((i) =>
    tab === 'all' ? true : tab === 'open' ? !i.is_resolved : i.is_resolved,
  );

  const toggle = async (i: Inquiry) => {
    setBusy(i.id);
    try {
      await api.admin.resolveInquiry(i.id, !i.is_resolved);
      await load();
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <header className="h-14 bg-card border-b border-line px-6 flex items-center justify-between shrink-0 transition-colors">
        <h1 className="text-sm font-semibold text-ink">고객 문의</h1>
        <div className="w-8 h-8 rounded-full bg-primary-subtle flex items-center justify-center text-xs font-medium text-primary">
          A
        </div>
      </header>

      <main className="flex-1 p-6">
        {/* 상태 탭 */}
        <div className="flex items-center gap-2 mb-5">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-4 py-1.5 rounded-full text-sm font-medium transition-colors ${
                tab === t.key
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-card border border-line text-ink-tertiary hover:text-ink'
              }`}
            >
              {t.label}
              <span className={`ml-1.5 ${tab === t.key ? 'text-primary-foreground/80' : 'text-ink-muted'}`}>
                {counts[t.key]}
              </span>
            </button>
          ))}
        </div>

        <div className="bg-card border border-line rounded-2xl overflow-hidden transition-colors">
          <div className="grid grid-cols-[1fr_180px_120px_110px] px-6 py-3 bg-surface-1 border-b border-line">
            {['제목·내용', '연락처', '상태', '접수일'].map((col) => (
              <span key={col} className="text-xs font-medium text-ink-tertiary">
                {col}
              </span>
            ))}
          </div>

          {!loaded ? (
            <div className="divide-y divide-line">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="px-6 py-4">
                  <div className="h-3 w-40 bg-surface-1 rounded animate-pulse" />
                </div>
              ))}
            </div>
          ) : filtered.length === 0 ? (
            <div className="px-6 py-16 flex flex-col items-center justify-center">
              <div className="w-10 h-10 rounded-2xl bg-surface-1 flex items-center justify-center mb-3 text-ink-muted">
                <Inbox size={18} />
              </div>
              <p className="text-sm text-ink-muted">
                {tab === 'resolved' ? '해결된 문의가 없습니다' : tab === 'open' ? '미해결 문의가 없습니다' : '접수된 문의가 없습니다'}
              </p>
            </div>
          ) : (
            <div className="divide-y divide-line">
              {filtered.map((i) => (
                <div key={i.id} className="grid grid-cols-[1fr_180px_120px_110px] px-6 py-4 items-center gap-2">
                  <div className="min-w-0 pr-4">
                    <p className="text-sm font-medium text-ink truncate">{i.title}</p>
                    <p className="text-xs text-ink-tertiary truncate mt-0.5">{i.content}</p>
                  </div>
                  <div className="min-w-0 flex items-center gap-1.5 text-xs text-ink-secondary">
                    {i.contact_email ? (
                      <>
                        <Mail size={13} className="shrink-0 text-ink-tertiary" />
                        <span className="truncate">{i.contact_email}</span>
                      </>
                    ) : (
                      <span className="text-ink-muted">—</span>
                    )}
                  </div>
                  <div>
                    {i.is_resolved ? (
                      <span className="inline-block px-2 py-0.5 rounded-full text-[10px] font-medium text-success bg-success-subtle">
                        해결됨
                      </span>
                    ) : (
                      <span className="inline-block px-2 py-0.5 rounded-full text-[10px] font-medium text-warning bg-warning-subtle">
                        미해결
                      </span>
                    )}
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs text-ink-muted">{formatKST(i.created_at)}</span>
                    <button
                      onClick={() => toggle(i)}
                      disabled={busy === i.id}
                      title={i.is_resolved ? '미해결로 되돌리기' : '해결 처리'}
                      className={`shrink-0 inline-flex items-center justify-center w-7 h-7 rounded-lg border transition-colors disabled:opacity-40 ${
                        i.is_resolved
                          ? 'border-line text-ink-tertiary hover:bg-surface-1'
                          : 'border-success-border text-success hover:bg-success-subtle'
                      }`}
                    >
                      {i.is_resolved ? <RotateCcw size={13} /> : <Check size={14} />}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
    </>
  );
}
