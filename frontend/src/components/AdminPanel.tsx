'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useProjects, type SimRow } from './ProjectContext';
import TrashSection from './TrashSection';
import { getToken } from '@/lib/authApi';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

const statusColor: Record<string, string> = {
  COMPLETED: 'bg-emerald-400', completed: 'bg-emerald-400',
  QUEUED: 'bg-yellow-400', pending: 'bg-yellow-400',
  RUNNING: 'bg-blue-400', running: 'bg-blue-400',
  FAILED: 'bg-red-400', failed: 'bg-red-400',
};

const fmt = (iso: string) => {
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
};

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      width="12" height="12" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
      className={`transition-transform duration-150 shrink-0 ${open ? 'rotate-90' : ''}`}
    >
      <polyline points="9 18 15 12 9 6" />
    </svg>
  );
}

type GenRow = { id: string; status: string; product_name: string | null; created_by_name: string | null; created_at: string };

// ── 프로젝트 아이템 ──────────────────────────────────────────────
function ProjectItem({
  project,
  activeSimId,
  activeGenId,
}: {
  project: { id: string; name: string };
  activeSimId: string | null;
  activeGenId: string | null;
}) {
  const router = useRouter();
  const { details, loadDetails, refreshDetails } = useProjects();
  const [open, setOpen] = useState(false);
  const [simOpen, setSimOpen] = useState(false);
  const [genOpen, setGenOpen] = useState(false);
  const [trashOpen, setTrashOpen] = useState(false);

  const d = details[project.id];
  const isLoading = open && !d?.loaded;
  const sims: SimRow[] = d?.sims ?? [];
  const gens: GenRow[] = d?.gens ?? [];
  const trashed = d?.trashed ?? [];

  const toggle = async () => {
    setOpen(v => !v);
    if (!open) await loadDetails(project.id);
  };

  return (
    <div>
      <div className="flex items-center gap-1.5 px-2 py-1.5 rounded-lg hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D] transition-colors group">
        <button onClick={toggle} className="flex items-center gap-1.5 flex-1 min-w-0 text-left">
          <ChevronIcon open={open} />
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="text-[#8B95A1] shrink-0">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
          </svg>
          <span className="text-sm font-medium text-[#191F28] dark:text-[#F2F4F6] truncate flex-1">{project.name}</span>
        </button>
        <Link
          href={`/projects/${project.id}`}
          title="상세 보기"
          onClick={e => e.stopPropagation()}
          className="opacity-0 group-hover:opacity-100 shrink-0 p-0.5 rounded text-[#B0B8C1] hover:text-[#3182F6] transition-all"
        >
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
            <polyline points="15 3 21 3 21 9" />
            <line x1="10" y1="14" x2="21" y2="3" />
          </svg>
        </Link>
      </div>

      {open && (
        <div className="ml-4 border-l border-[#E5E8EB] dark:border-[#2D3748] pl-2 space-y-0.5 mt-0.5 mb-1">
          {isLoading ? (
            <p className="text-[10px] text-[#B0B8C1] px-2 py-1">불러오는 중...</p>
          ) : (
            <>
              {/* 시뮬레이션 */}
              <button
                onClick={() => setSimOpen(v => !v)}
                className="w-full flex items-center gap-1.5 px-2 py-1 hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D] rounded-md transition-colors"
              >
                <ChevronIcon open={simOpen} />
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-[#8B95A1] shrink-0">
                  <circle cx="12" cy="12" r="10" /><polygon points="10 8 16 12 10 16 10 8" />
                </svg>
                <span className="text-xs font-semibold text-[#4E5968] dark:text-[#9CA3AF] uppercase tracking-wide">
                  시뮬레이션{sims.length > 0 ? ` (${sims.length})` : ''}
                </span>
              </button>
              {simOpen && (
                <div className="ml-3 space-y-0.5">
                  {sims.length === 0 ? (
                    <p className="text-xs text-[#B0B8C1] px-2 py-1">내역 없음</p>
                  ) : sims.map(s => {
                    const isActive = s.id === activeSimId;
                    return (
                      <Link
                        key={s.id}
                        href={`/simulation/${s.id}`}
                        className={`flex items-center gap-1.5 px-2 py-1 rounded-md transition-colors group ${
                          isActive ? 'bg-[#EBF3FF] dark:bg-[#1E3A5F]' : 'hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F]'
                        }`}
                      >
                        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${statusColor[s.status] ?? 'bg-[#B0B8C1]'}`} />
                        <div className="flex-1 min-w-0">
                          <p className={`text-xs truncate ${isActive ? 'text-[#3182F6] font-medium' : 'text-[#4E5968] dark:text-[#9CA3AF]'}`}>
                            {s.ad_title || '제목 없음'}
                          </p>
                          <p className="text-[11px] text-[#B0B8C1] truncate">{s.sample_size}명 · {s.created_by_name ?? '—'} · {fmt(s.created_at)}</p>
                        </div>
                      </Link>
                    );
                  })}
                  <button
                    onClick={() => router.push('/simulation')}
                    className="w-full flex items-center gap-1 px-2 py-1 rounded-md text-xs text-[#3182F6] hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F] transition-colors"
                  >
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
                    </svg>
                    시뮬레이션 추가
                  </button>
                </div>
              )}

              {/* 제너레이터 */}
              <button
                onClick={() => setGenOpen(v => !v)}
                className="w-full flex items-center gap-1.5 px-2 py-1 hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D] rounded-md transition-colors"
              >
                <ChevronIcon open={genOpen} />
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-[#8B95A1] shrink-0">
                  <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
                </svg>
                <span className="text-xs font-semibold text-[#4E5968] dark:text-[#9CA3AF] uppercase tracking-wide">
                  제너레이터{gens.length > 0 ? ` (${gens.length})` : ''}
                </span>
              </button>
              {genOpen && (
                <div className="ml-3 space-y-0.5">
                  {gens.length === 0 ? (
                    <p className="text-xs text-[#B0B8C1] px-2 py-1">내역 없음</p>
                  ) : gens.map(g => {
                    const isActive = g.id === activeGenId;
                    return (
                      <Link
                        key={g.id}
                        href={`/generations/${g.id}`}
                        className={`flex items-center gap-1.5 px-2 py-1 rounded-md transition-colors group ${
                          isActive ? 'bg-[#EBF3FF] dark:bg-[#1E3A5F]' : 'hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F]'
                        }`}
                      >
                        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${statusColor[g.status] ?? 'bg-[#B0B8C1]'}`} />
                        <div className="flex-1 min-w-0">
                          <p className={`text-xs truncate ${isActive ? 'text-[#3182F6] font-medium' : 'text-[#4E5968] dark:text-[#9CA3AF]'}`}>
                            {g.product_name ?? '—'} · {g.created_by_name ?? '—'}
                          </p>
                          <p className="text-[11px] text-[#B0B8C1]">{fmt(g.created_at)}</p>
                        </div>
                      </Link>
                    );
                  })}
                </div>
              )}

              {/* 채팅 — 후순위(데이터 미연동, 칸만) */}
              <div className="w-full flex items-center gap-1.5 px-2 py-1">
                <span className="w-3 shrink-0" />
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-[#8B95A1] shrink-0">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                </svg>
                <span className="text-xs font-semibold text-[#4E5968] dark:text-[#9CA3AF] uppercase tracking-wide">채팅 (0)</span>
              </div>

              {/* 휴지통 — 펼치면 삭제된 시뮬/제너, 클릭 시 상세 */}
              <button
                onClick={() => setTrashOpen(v => !v)}
                className="w-full flex items-center gap-1.5 px-2 py-1 hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D] rounded-md transition-colors"
              >
                <ChevronIcon open={trashOpen} />
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-[#8B95A1] shrink-0">
                  <polyline points="3 6 5 6 21 6" />
                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                </svg>
                <span className="text-xs font-semibold text-[#4E5968] dark:text-[#9CA3AF] uppercase tracking-wide">
                  휴지통{trashed.length > 0 ? ` (${trashed.length})` : ''}
                </span>
              </button>
              {trashOpen && (
                <TrashSection projectId={project.id} trashed={trashed} onChanged={() => refreshDetails(project.id)} />
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

// 패널에서 다루는 프로젝트(팀 그룹핑용 메타 포함)
type PanelProject = { id: string; name: string; team_id: string | null; team_name: string | null };

const NO_TEAM = '(팀 미지정)';

// 팀 단위 그룹 — 회사 아래에서 팀별로 프로젝트를 묶는다.
function TeamGroup({
  name,
  projects,
  activeSimId,
  activeGenId,
}: {
  name: string;
  projects: PanelProject[];
  activeSimId: string | null;
  activeGenId: string | null;
}) {
  const [open, setOpen] = useState(true);

  return (
    <div>
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center gap-1.5 px-2 py-1 hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D] rounded-md transition-colors"
      >
        <ChevronIcon open={open} />
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-[#8B95A1] shrink-0">
          <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
          <circle cx="9" cy="7" r="4" />
          <path d="M23 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" />
        </svg>
        <span className="flex-1 min-w-0 text-left text-xs font-semibold text-[#4E5968] dark:text-[#9CA3AF] truncate">
          {name}
        </span>
        <span className="text-[10px] text-[#B0B8C1] shrink-0">{projects.length}</span>
      </button>

      {open && (
        <div className="ml-3 border-l border-[#E5E8EB] dark:border-[#2D3748] pl-2 space-y-0.5 mt-0.5 mb-1">
          {projects.length === 0 ? (
            <p className="text-[10px] text-[#B0B8C1] px-2 py-1">프로젝트 없음</p>
          ) : projects.map(p => (
            <ProjectItem key={p.id} project={p} activeSimId={activeSimId} activeGenId={activeGenId} />
          ))}
        </div>
      )}
    </div>
  );
}

// ── 회사 아이템 ─────────────────────────────────────────────────
// 회사(조직) → 팀 → 프로젝트 순으로 두 단계 그룹핑한다.
function CompanyItem({
  name,
  projects,
  activeSimId,
  activeGenId,
}: {
  name: string;
  projects: PanelProject[];
  activeSimId: string | null;
  activeGenId: string | null;
}) {
  const [open, setOpen] = useState(true);

  // 팀별 그룹핑 — 팀 미지정은 마지막
  const byTeam = projects.reduce<Record<string, PanelProject[]>>((acc, p) => {
    const key = p.team_name ?? NO_TEAM;
    (acc[key] ??= []).push(p);
    return acc;
  }, {});
  const teamNames = Object.keys(byTeam).sort((a, b) =>
    a === NO_TEAM ? 1 : b === NO_TEAM ? -1 : a.localeCompare(b)
  );

  return (
    <div>
      <div className="w-full flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D] transition-colors group">
        <button
          onClick={() => setOpen(v => !v)}
          className="flex items-center gap-2 flex-1 min-w-0 text-left"
        >
          <ChevronIcon open={open} />
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="text-[#3182F6] shrink-0">
            <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
            <polyline points="9 22 9 12 15 12 15 22" />
          </svg>
          <span className="flex-1 min-w-0 text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] truncate">{name}</span>
        </button>
        <span className="text-[10px] text-[#B0B8C1] shrink-0">{projects.length}</span>
      </div>

      {open && (
        <div className="ml-4 border-l border-[#E5E8EB] dark:border-[#2D3748] pl-2 space-y-0.5 mt-0.5 mb-1">
          {projects.length === 0 ? (
            <p className="text-[10px] text-[#B0B8C1] px-2 py-1">프로젝트 없음</p>
          ) : teamNames.map(tn => (
            <TeamGroup
              key={tn}
              name={tn}
              projects={byTeam[tn]}
              activeSimId={activeSimId}
              activeGenId={activeGenId}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── 메인 패널 ───────────────────────────────────────────────────
// ADMIN 전용 — 전체 회사를 보고, 회사 안에서 다시 팀별로 프로젝트를 나눠 본다.
export default function AdminPanel({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const pathname = usePathname();
  const { projects, loading, refresh } = useProjects();
  const [search, setSearch] = useState('');
  const [orgs, setOrgs] = useState<{ id: string; name: string }[]>([]);

  // 전체 조직 목록 — 프로젝트가 0개인 회사도 패널에 표시하기 위함
  useEffect(() => {
    fetch(`${API_BASE}/api/admin/organizations`, { headers: { Authorization: `Bearer ${getToken()}` } })
      .then(r => (r.ok ? r.json() : []))
      .then(d => { if (Array.isArray(d)) setOrgs(d); })
      .catch(() => {});
  }, []);

  const simMatch = pathname.match(/^\/simulation\/([^/]+)/);
  const genMatch = pathname.match(/^\/generations\/([^/]+)/);
  const activeSimId = simMatch?.[1] ?? null;
  const activeGenId = genMatch?.[1] ?? null;

  // 회사별 그룹핑 (팀 메타 포함)
  const grouped = projects.reduce<Record<string, PanelProject[]>>((acc, p) => {
    const key = p.organization_name ?? '(회사 미지정)';
    if (!acc[key]) acc[key] = [];
    acc[key].push({ id: p.id, name: p.name, team_id: p.team_id, team_name: p.team_name });
    return acc;
  }, {});

  // 프로젝트가 0개인 회사도 빈 채로 포함 (전체 조직 목록 머지)
  for (const o of orgs) {
    if (!grouped[o.name]) grouped[o.name] = [];
  }

  const filteredGrouped = search.trim()
    ? Object.fromEntries(
        Object.entries(grouped)
          .map(([company, projs]) => [
            company,
            projs.filter(p =>
              p.name.toLowerCase().includes(search.toLowerCase()) ||
              company.toLowerCase().includes(search.toLowerCase()) ||
              (p.team_name?.toLowerCase().includes(search.toLowerCase()) ?? false)
            ),
          ])
          .filter(([, projs]) => (projs as PanelProject[]).length > 0)
      )
    : grouped;

  const companyNames = Object.keys(filteredGrouped).sort();

  // ── 접힌 상태 ──
  if (collapsed) {
    return (
      <aside className="fixed top-0 left-56 h-full w-[50px] bg-[#FAFBFC] dark:bg-[#161B27] border-r border-[#E5E8EB] dark:border-[#2D3748] flex flex-col items-center pt-3 z-30 transition-all duration-200">
        <button
          onClick={onToggle}
          title="패널 펼치기"
          className="w-8 h-8 flex items-center justify-center rounded-lg text-[#8B95A1] hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D] hover:text-[#3182F6] transition-colors"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="9 18 15 12 9 6" />
          </svg>
        </button>
      </aside>
    );
  }

  // ── 펼친 상태 ──
  return (
    <aside className="fixed top-0 left-56 h-full w-72 bg-[#FAFBFC] dark:bg-[#161B27] border-r border-[#E5E8EB] dark:border-[#2D3748] flex flex-col z-30 transition-all duration-200">
      {/* 헤더 */}
      <div className="h-14 flex items-center justify-between px-3 border-b border-[#E5E8EB] dark:border-[#2D3748] shrink-0">
        <button
          onClick={onToggle}
          title="패널 접기"
          className="w-7 h-7 flex items-center justify-center rounded-lg text-[#8B95A1] hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D] hover:text-[#3182F6] transition-colors"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>
        <p className="text-sm font-semibold text-[#4E5968] dark:text-[#9CA3AF]">기업 현황</p>
        <button
          onClick={refresh}
          title="새로고침"
          className="w-7 h-7 flex items-center justify-center rounded-lg text-[#8B95A1] hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D] hover:text-[#3182F6] transition-colors"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="23 4 23 10 17 10" /><polyline points="1 20 1 14 7 14" />
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
          </svg>
        </button>
      </div>

      {/* 검색 */}
      <div className="px-3 py-2 border-b border-[#E5E8EB] dark:border-[#2D3748] shrink-0">
        <div className="relative">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
            className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#B0B8C1]">
            <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="회사·프로젝트 검색"
            className="w-full pl-7 pr-3 py-1.5 text-xs bg-[#F2F4F6] dark:bg-[#252D3D] border border-transparent rounded-lg text-[#191F28] dark:text-[#F2F4F6] placeholder-[#B0B8C1] focus:outline-none focus:border-[#3182F6] transition-colors"
          />
        </div>
      </div>

      {/* 목록 */}
      <div className="flex-1 overflow-y-auto py-2 px-2 space-y-0.5">
        {loading ? (
          <p className="text-xs text-[#B0B8C1] px-3 py-2">불러오는 중...</p>
        ) : companyNames.length === 0 ? (
          <p className="text-xs text-[#B0B8C1] px-3 py-6 text-center">
            {search ? '검색 결과 없음' : '데이터가 없습니다'}
          </p>
        ) : companyNames.map(name => (
          <CompanyItem
            key={name}
            name={name}
            projects={filteredGrouped[name] as PanelProject[]}
            activeSimId={activeSimId}
            activeGenId={activeGenId}
          />
        ))}
      </div>

      {/* 푸터 통계 */}
      {!loading && companyNames.length > 0 && (
        <div className="px-3 py-2 border-t border-[#E5E8EB] dark:border-[#2D3748] shrink-0">
          <p className="text-[10px] text-[#B0B8C1] dark:text-[#4B5563]">
            {companyNames.length}개 기업 · {projects.length}개 프로젝트
          </p>
        </div>
      )}
    </aside>
  );
}
