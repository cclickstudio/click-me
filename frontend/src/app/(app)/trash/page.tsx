'use client';

// 휴지통 — soft delete된 프로젝트·시뮬·제너를 보고 복원한다. 삭제 30일 후 자동 영구삭제.

import { useEffect, useState, useCallback, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { authedFetch } from '@/lib/api';
import { formatKSTDate } from '@/lib/datetime';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

type Base = { id: string; deleted_at: string; days_left: number | null };
type TProject = Base & { name: string; org_name: string | null };
type TSim = Base & { ad_title: string | null };
type TGen = Base & { product_name: string | null };
type TrashData = { projects: TProject[]; simulations: TSim[]; generations: TGen[] };

const fmt = (iso: string) => formatKSTDate(iso);

function DaysLeft({ n }: { n: number | null }) {
  if (n === null) return null;
  const danger = n <= 3;
  return (
    <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${danger ? 'text-red-500 bg-red-50 dark:bg-red-900/20' : 'text-[#8B95A1] bg-[#F2F4F6] dark:bg-[#252D3D]'}`}>
      {n === 0 ? '오늘 만료' : `${n}일 남음`}
    </span>
  );
}

function TrashInner() {
  const params = useSearchParams();
  const org = params.get('org');
  const project = params.get('project');
  const [data, setData] = useState<TrashData>({ projects: [], simulations: [], generations: [] });
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    const q = project ? `?project_id=${project}` : org ? `?org_id=${org}` : '';
    authedFetch(`${API_BASE}/api/projects/trash${q}`)
      .then(r => (r.ok ? r.json() : { projects: [], simulations: [], generations: [] }))
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [org, project]);

  useEffect(() => { load(); }, [load]);

  const restore = async (kind: 'project' | 'sim' | 'gen', id: string) => {
    const path =
      kind === 'project' ? `/api/projects/${id}/restore`
      : kind === 'sim' ? `/api/projects/simulations/${id}/restore`
      : `/api/projects/generations/${id}/restore`;
    const res = await authedFetch(`${API_BASE}${path}`, { method: 'POST' });
    if (!res.ok) { alert('복원에 실패했습니다.'); return; }
    load();
  };

  const total = data.projects.length + data.simulations.length + data.generations.length;

  const Section = ({ title, children, count }: { title: string; count: number; children: React.ReactNode }) => (
    <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl overflow-hidden">
      <div className="px-6 py-4 border-b border-[#E5E8EB] dark:border-[#2D3748]">
        <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">{title} ({count})</p>
      </div>
      {count === 0 ? (
        <div className="py-10 text-center text-xs text-[#B0B8C1] dark:text-[#4B5563]">비어 있습니다</div>
      ) : children}
    </div>
  );

  const Row = ({ label, sub, daysLeft, onRestore }: { label: string; sub: string; daysLeft: number | null; onRestore: () => void }) => (
    <div className="flex items-center gap-3 px-6 py-3 border-b border-[#F9FAFB] dark:border-[#1C2333] last:border-0">
      <div className="flex-1 min-w-0">
        <p className="text-sm text-[#191F28] dark:text-[#F2F4F6] truncate">{label}</p>
        <p className="text-[11px] text-[#B0B8C1] dark:text-[#4B5563]">{sub}</p>
      </div>
      <DaysLeft n={daysLeft} />
      <button onClick={onRestore}
        className="px-3 py-1.5 text-xs font-medium text-[#3182F6] border border-[#3182F6]/30 rounded-lg hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F] transition-colors">복원</button>
    </div>
  );

  return (
      <div className="px-8 py-8 max-w-4xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">휴지통</h1>
          <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mt-1">
            삭제한 항목은 30일간 보관되며 그 안에 복원할 수 있습니다. 30일이 지나면 영구 삭제됩니다.
          </p>
        </div>

        {loading ? (
          <div className="py-20 text-center text-sm text-[#8B95A1]">불러오는 중...</div>
        ) : total === 0 ? (
          <div className="py-20 text-center text-sm text-[#8B95A1]">휴지통이 비어 있습니다</div>
        ) : (
          <>
            <Section title="프로젝트" count={data.projects.length}>
              {data.projects.map(p => (
                <Row key={p.id} label={p.name} sub={`${p.org_name ?? ''} · ${fmt(p.deleted_at)} 삭제`} daysLeft={p.days_left} onRestore={() => restore('project', p.id)} />
              ))}
            </Section>
            <Section title="시뮬레이션" count={data.simulations.length}>
              {data.simulations.map(s => (
                <Row key={s.id} label={s.ad_title ?? '제목 없음'} sub={`${fmt(s.deleted_at)} 삭제`} daysLeft={s.days_left} onRestore={() => restore('sim', s.id)} />
              ))}
            </Section>
            <Section title="제너레이터" count={data.generations.length}>
              {data.generations.map(g => (
                <Row key={g.id} label={g.product_name ?? '상품명 없음'} sub={`${fmt(g.deleted_at)} 삭제`} daysLeft={g.days_left} onRestore={() => restore('gen', g.id)} />
              ))}
            </Section>
          </>
        )}
      </div>
  );
}

export default function TrashPage() {
  return (
    <Suspense fallback={null}>
      <TrashInner />
    </Suspense>
  );
}
