'use client';

// COMPANY 전용 좌측 패널 — 소속 조직 전체 프로젝트를 ALL/TEAM 토글로 조회(생성 불가).
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useProjects } from './ProjectContext';
import { ProjectItem } from './ProjectPanel';
import { authedFetch } from '@/lib/api';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

const NO_TEAM = '(팀 미지정)';

type Team = { id: string; name: string };

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

// 팀 단위 그룹 — TEAM 토글에서 팀별로 프로젝트를 묶는다(프로젝트 0개 팀도 표시).
function TeamSection({
  name,
  projects,
  activeSimId,
  activeGenId,
  activeProjectId,
  openProjectId,
  onToggleOpen,
}: {
  name: string;
  projects: { id: string; name: string; status: string; organization_name: string | null }[];
  activeSimId: string | null;
  activeGenId: string | null;
  activeProjectId: string | null;
  openProjectId: string | null;
  onToggleOpen: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div>
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center gap-1.5 px-2 py-1.5 hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D] rounded-md transition-colors"
      >
        <ChevronIcon open={open} />
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-[#8B95A1] shrink-0">
          <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
          <circle cx="9" cy="7" r="4" />
          <path d="M23 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" />
        </svg>
        <span className="flex-1 min-w-0 text-left text-xs font-semibold text-[#4E5968] dark:text-[#9CA3AF] uppercase tracking-wide truncate">
          {name}
        </span>
        <span className="text-[10px] text-[#B0B8C1] shrink-0">{projects.length}</span>
      </button>

      {open && (
        <div className="ml-3 border-l border-[#E5E8EB] dark:border-[#2D3748] pl-2 space-y-0.5 mt-0.5 mb-1">
          {projects.length === 0 ? (
            <p className="text-[10px] text-[#B0B8C1] px-2 py-1">프로젝트 없음</p>
          ) : projects.map(p => (
            <ProjectItem
              key={p.id}
              project={p}
              activeSimId={activeSimId}
              activeGenId={activeGenId}
              autoOpen={p.id === activeProjectId}
              filterNames={null}
              isAdmin={false}
              canRun={false}
              isOpen={openProjectId === p.id}
              onToggleOpen={onToggleOpen}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── 메인 패널 ───────────────────────────────────────────────────
export default function CompanyPanel({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const pathname = usePathname();
  const { projects, loading, details, loadDetails, selectProject, refreshAll } = useProjects();
  const [teams, setTeams] = useState<Team[]>([]);
  const [openProjectId, setOpenProjectId] = useState<string | null>(null);

  const simMatch = pathname.match(/^\/simulation\/([^/]+)/);
  const genMatch = pathname.match(/^\/generations\/([^/]+)/);
  const activeSimId = simMatch?.[1] ?? null;
  const activeGenId = genMatch?.[1] ?? null;
  const activeItemId = activeSimId ?? activeGenId;

  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);

  // 활성 시뮬/제너가 속한 프로젝트를 찾아 자동 펼침 (ProjectPanel과 동일 로직)
  useEffect(() => {
    if (!activeItemId) { setActiveProjectId(null); return; }

    for (const [pid, d] of Object.entries(details)) {
      if (activeSimId && d.sims.some(s => s.id === activeSimId)) { setActiveProjectId(pid); selectProject(pid); return; }
      if (activeGenId && d.gens.some(g => g.id === activeGenId)) { setActiveProjectId(pid); selectProject(pid); return; }
    }

    (async () => {
      for (const p of projects) {
        if (details[p.id]?.loaded) continue;
        await loadDetails(p.id);
        const d = details[p.id];
        if (!d) continue;
        if (activeSimId && d.sims.some(s => s.id === activeSimId)) { setActiveProjectId(p.id); selectProject(p.id); return; }
        if (activeGenId && d.gens.some(g => g.id === activeGenId)) { setActiveProjectId(p.id); selectProject(p.id); return; }
      }
    })();
  }, [activeItemId, details, projects]);

  // 전체 팀 목록 — TEAM 토글에서 프로젝트 0개 팀까지 표시하기 위함(팀 관리와 동일 목록)
  useEffect(() => {
    authedFetch(`${API_BASE}/api/company/teams`)
      .then(r => (r.ok ? r.json() : []))
      .then(d => { if (Array.isArray(d)) setTeams(d); })
      .catch(() => {});
  }, []);

  const toggleOpen = (id: string) => setOpenProjectId(prev => (prev === id ? null : id));

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

  // TEAM 토글 — 팀별 프로젝트 매칭(팀 목록 순서 + 미지정 마지막)
  const teamSections = teams.map(t => ({
    key: t.id,
    name: t.name,
    projects: projects.filter(p => p.team_id === t.id),
  }));
  const noTeamProjects = projects.filter(p => !p.team_id);
  if (noTeamProjects.length > 0) {
    teamSections.push({ key: '__none__', name: NO_TEAM, projects: noTeamProjects });
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

        <p className="text-sm font-semibold text-[#4E5968] dark:text-[#9CA3AF]">프로젝트</p>

        <div className="flex items-center gap-1">
          {/* 새로고침 */}
          <button
            onClick={refreshAll}
            title="새로고침"
            className="w-7 h-7 flex items-center justify-center rounded-lg text-[#8B95A1] hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D] hover:text-[#3182F6] transition-colors"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="23 4 23 10 17 10" /><polyline points="1 20 1 14 7 14" />
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
            </svg>
          </button>
        </div>
      </div>

      {/* 프로젝트 목록 */}
      <div className="flex-1 overflow-y-auto py-2 px-2">
        {loading ? (
          <p className="text-xs text-[#B0B8C1] px-3 py-2">불러오는 중...</p>
        ) : projects.length === 0 ? (
          <p className="text-xs text-[#B0B8C1] px-3 py-6 text-center">프로젝트가 없습니다</p>
        ) : (
          <div className="space-y-0.5">
            {teamSections.map(s => (
              <TeamSection
                key={s.key}
                name={s.name}
                projects={s.projects}
                activeSimId={activeSimId}
                activeGenId={activeGenId}
                activeProjectId={activeProjectId}
                openProjectId={openProjectId}
                onToggleOpen={toggleOpen}
              />
            ))}
          </div>
        )}
      </div>

      {/* 휴지통 */}
      <div className="border-t border-[#E5E8EB] dark:border-[#2D3748] shrink-0 p-2">
        <Link
          href="/trash"
          className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${
            pathname === '/trash'
              ? 'bg-[#EBF3FF] dark:bg-[#1E3A5F] text-[#3182F6] font-medium'
              : 'text-[#8B95A1] dark:text-[#6B7280] hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D] hover:text-[#3182F6]'
          }`}
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="shrink-0">
            <polyline points="3 6 5 6 21 6" />
            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
          </svg>
          휴지통
        </Link>
      </div>
    </aside>
  );
}
