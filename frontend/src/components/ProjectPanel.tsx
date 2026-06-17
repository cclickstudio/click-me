'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useProjects } from './ProjectContext';
import { useAuth } from './AuthProvider';
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
      width="13" height="13" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
      className={`transition-transform duration-150 shrink-0 ${open ? 'rotate-90' : ''}`}
    >
      <polyline points="9 18 15 12 9 6" />
    </svg>
  );
}

// ── 프로젝트 생성 모달 ──────────────────────────────────────────
function CreateProjectModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [creating, setCreating] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { inputRef.current?.focus(); }, []);

  const handleCreate = async () => {
    if (!name.trim() || creating) return;
    setCreating(true);
    await fetch(`${API_BASE}/api/projects`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${getToken()}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name.trim(), description: description.trim() || null }),
    });
    setCreating(false);
    onCreated();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-white dark:bg-[#1C2333] rounded-2xl shadow-xl w-full max-w-md mx-4 p-6">
        <h2 className="text-lg font-bold text-[#191F28] dark:text-[#F2F4F6] mb-4">새 프로젝트</h2>
        <div className="space-y-3">
          <div>
            <label className="text-xs font-medium text-[#4E5968] dark:text-[#9CA3AF] block mb-1">프로젝트 이름 *</label>
            <input
              ref={inputRef}
              value={name}
              onChange={e => setName(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') handleCreate(); if (e.key === 'Escape') onClose(); }}
              placeholder="예: 2024 여름 캠페인"
              className="w-full px-3 py-2.5 text-sm border border-[#E5E8EB] dark:border-[#2D3748] rounded-xl bg-white dark:bg-[#252D3D] text-[#191F28] dark:text-[#F2F4F6] placeholder-[#B0B8C1] focus:outline-none focus:border-[#3182F6] transition-colors"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-[#4E5968] dark:text-[#9CA3AF] block mb-1">설명 (선택)</label>
            <textarea
              value={description}
              onChange={e => setDescription(e.target.value)}
              onKeyDown={e => { if (e.key === 'Escape') onClose(); }}
              placeholder="프로젝트에 대한 간단한 설명"
              rows={3}
              className="w-full px-3 py-2.5 text-sm border border-[#E5E8EB] dark:border-[#2D3748] rounded-xl bg-white dark:bg-[#252D3D] text-[#191F28] dark:text-[#F2F4F6] placeholder-[#B0B8C1] focus:outline-none focus:border-[#3182F6] transition-colors resize-none"
            />
          </div>
        </div>
        <div className="flex gap-2 mt-5">
          <button
            onClick={onClose}
            className="flex-1 py-2.5 text-sm font-medium border border-[#E5E8EB] dark:border-[#2D3748] rounded-xl text-[#4E5968] dark:text-[#9CA3AF] hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D] transition-colors"
          >
            취소
          </button>
          <button
            onClick={handleCreate}
            disabled={!name.trim() || creating}
            className="flex-1 py-2.5 text-sm font-medium bg-[#3182F6] text-white rounded-xl hover:bg-[#1B6EEB] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {creating ? '생성 중...' : '만들기'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── 프로젝트 아이템 ─────────────────────────────────────────────
function ProjectItem({
  project,
  activeSimId,
  activeGenId,
  autoOpen,
  filterNames,
  isAdmin,
  canRun,
  isOpen,
  onToggleOpen,
}: {
  project: { id: string; name: string; status: string; organization_name: string | null };
  isAdmin: boolean;
  canRun: boolean; // 시뮬/제너 실행 가능 여부 (COMPANY는 false)
  activeSimId: string | null;
  activeGenId: string | null;
  autoOpen: boolean;
  filterNames: string[] | null; // null=전체, 배열=해당 이름만(MY/TEAM)
  isOpen: boolean;
  onToggleOpen: (id: string) => void;
}) {
  const { details, loadDetails, refreshDetails, selectedProjectId, selectProject } = useProjects();
  const router = useRouter();
  const [simOpen, setSimOpen] = useState(false);
  const [genOpen, setGenOpen] = useState(false);
  const [trashOpen, setTrashOpen] = useState(false);

  const d = details[project.id];
  const isLoading = isOpen && !d?.loaded;
  const isSelected = selectedProjectId === project.id;

  const allSims = d?.sims ?? [];
  const allGens = d?.gens ?? [];
  const sims = filterNames ? allSims.filter(s => s.created_by_name != null && filterNames.includes(s.created_by_name)) : allSims;
  const gens = filterNames ? allGens.filter(g => g.created_by_name != null && filterNames.includes(g.created_by_name)) : allGens;
  const trashed = d?.trashed ?? [];

  useEffect(() => {
    if (!autoOpen) return;
    onToggleOpen(project.id);
    loadDetails(project.id).then(() => {
      if (activeSimId) setSimOpen(true);
      if (activeGenId) setGenOpen(true);
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoOpen]);

  const toggle = async () => {
    onToggleOpen(project.id);
    if (!isOpen) {
      selectProject(project.id);
      await loadDetails(project.id);
    }
  };

  const goToSim = (e: React.MouseEvent) => {
    e.stopPropagation();
    selectProject(project.id);
    router.push('/simulation');
  };

  const goToGen = (e: React.MouseEvent) => {
    e.stopPropagation();
    selectProject(project.id);
    router.push('/generator');
  };

  return (
    <div>
      <div
        className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg transition-colors text-left ${
          isSelected ? 'bg-[#EBF3FF] dark:bg-[#1E3A5F]' : 'hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D]'
        }`}
      >
        {/* 접기/펼치기 */}
        <button onClick={toggle} className="flex items-center gap-2 flex-1 min-w-0 text-left">
          <ChevronIcon open={isOpen} />
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
            className={isSelected ? 'text-[#3182F6] shrink-0' : 'text-[#8B95A1] shrink-0'}>
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
          </svg>
          <span className="flex-1 min-w-0">
            <span className={`block text-sm font-medium truncate ${isSelected ? 'text-[#3182F6]' : 'text-[#191F28] dark:text-[#F2F4F6]'}`}>
              {project.name}
            </span>
            {isAdmin && project.organization_name && (
              <span className="block text-[10px] text-[#B0B8C1] dark:text-[#4B5563] truncate">{project.organization_name}</span>
            )}
          </span>
        </button>
        {/* 자세히 보기 */}
        <Link
          href={`/projects/${project.id}`}
          title="프로젝트 상세"
          className="shrink-0 p-1 rounded-md text-[#B0B8C1] hover:text-[#3182F6] hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F] transition-colors"
          onClick={e => e.stopPropagation()}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
            <polyline points="15 3 21 3 21 9" />
            <line x1="10" y1="14" x2="21" y2="3" />
          </svg>
        </Link>
      </div>

      {isOpen && (
        <div className="ml-5 border-l border-[#E5E8EB] dark:border-[#2D3748] pl-2 space-y-0.5 mt-0.5 mb-1">
          {isLoading ? (
            <p className="text-xs text-[#B0B8C1] px-2 py-1.5">불러오는 중...</p>
          ) : (
            <>
              {/* 시뮬레이션 섹션 */}
              <button
                onClick={() => setSimOpen(v => !v)}
                className="w-full flex items-center gap-2 px-2 py-1.5 hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D] rounded-md transition-colors"
              >
                <ChevronIcon open={simOpen} />
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-[#8B95A1] shrink-0">
                  <circle cx="12" cy="12" r="10" /><polygon points="10 8 16 12 10 16 10 8" />
                </svg>
                <span className="text-xs font-semibold text-[#4E5968] dark:text-[#9CA3AF] uppercase tracking-wide">
                  시뮬레이션{sims.length > 0 ? ` (${sims.length})` : ''}
                </span>
              </button>
              {simOpen && (
                <div className="ml-4 space-y-0.5">
                  {sims.length === 0 ? (
                    <p className="text-xs text-[#B0B8C1] px-2 py-1">
                      {filterNames ? '해당 내역 없음' : '내역 없음'}
                    </p>
                  ) : sims.map(s => {
                    const isActive = s.id === activeSimId;
                    return (
                      <Link
                        key={s.id}
                        href={`/simulations/${s.id}`}
                        className={`flex items-center gap-2 px-2 py-1.5 rounded-md transition-colors group ${
                          isActive ? 'bg-[#EBF3FF] dark:bg-[#1E3A5F]' : 'hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F]'
                        }`}
                      >
                        <span className={`w-2 h-2 rounded-full shrink-0 ${statusColor[s.status] ?? 'bg-[#B0B8C1]'}`} />
                        <div className="flex-1 min-w-0">
                          <p className={`text-xs truncate ${isActive ? 'text-[#3182F6] font-medium' : 'text-[#4E5968] dark:text-[#9CA3AF] group-hover:text-[#3182F6]'}`}>
                            {s.sample_size}명 · {s.created_by_name ?? '—'}
                          </p>
                          <p className="text-[10px] text-[#B0B8C1] dark:text-[#4B5563]">{fmt(s.created_at)}</p>
                        </div>
                        {isActive && <span className="shrink-0 w-1.5 h-1.5 rounded-full bg-[#3182F6]" />}
                      </Link>
                    );
                  })}
                  {canRun && (
                    <button
                      onClick={goToSim}
                      className="w-full flex items-center gap-1.5 px-2 py-1.5 rounded-md text-xs text-[#3182F6] hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F] transition-colors"
                    >
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
                      </svg>
                      시뮬레이션 추가
                    </button>
                  )}
                </div>
              )}

              {/* 제너레이터 섹션 */}
              <button
                onClick={() => setGenOpen(v => !v)}
                className="w-full flex items-center gap-2 px-2 py-1.5 hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D] rounded-md transition-colors"
              >
                <ChevronIcon open={genOpen} />
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-[#8B95A1] shrink-0">
                  <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
                </svg>
                <span className="text-xs font-semibold text-[#4E5968] dark:text-[#9CA3AF] uppercase tracking-wide">
                  제너레이터{gens.length > 0 ? ` (${gens.length})` : ''}
                </span>
              </button>
              {genOpen && (
                <div className="ml-4 space-y-0.5">
                  {gens.length === 0 ? (
                    <p className="text-xs text-[#B0B8C1] px-2 py-1">
                      {filterNames ? '해당 내역 없음' : '내역 없음'}
                    </p>
                  ) : gens.map(g => {
                    const isActive = g.id === activeGenId;
                    return (
                      <Link
                        key={g.id}
                        href={`/generations/${g.id}`}
                        className={`flex items-center gap-2 px-2 py-1.5 rounded-md transition-colors group ${
                          isActive ? 'bg-[#EBF3FF] dark:bg-[#1E3A5F]' : 'hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F]'
                        }`}
                      >
                        <span className={`w-2 h-2 rounded-full shrink-0 ${statusColor[g.status] ?? 'bg-[#B0B8C1]'}`} />
                        <div className="flex-1 min-w-0">
                          <p className={`text-xs truncate ${isActive ? 'text-[#3182F6] font-medium' : 'text-[#4E5968] dark:text-[#9CA3AF] group-hover:text-[#3182F6]'}`}>
                            {g.product_name ?? '—'} · {g.created_by_name ?? '—'}
                          </p>
                          <p className="text-[10px] text-[#B0B8C1] dark:text-[#4B5563]">{fmt(g.created_at)}</p>
                        </div>
                        {isActive && <span className="shrink-0 w-1.5 h-1.5 rounded-full bg-[#3182F6]" />}
                      </Link>
                    );
                  })}
                  {canRun && (
                    <button
                      onClick={goToGen}
                      className="w-full flex items-center gap-1.5 px-2 py-1.5 rounded-md text-xs text-[#3182F6] hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F] transition-colors"
                    >
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
                      </svg>
                      제너레이터 추가
                    </button>
                  )}
                </div>
              )}

              {/* 채팅 — 후순위(데이터 미연동, 칸만) */}
              <div className="w-full flex items-center gap-2 px-2 py-1.5">
                <span className="w-[13px] shrink-0" />
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-[#8B95A1] shrink-0">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                </svg>
                <span className="text-xs font-semibold text-[#4E5968] dark:text-[#9CA3AF] uppercase tracking-wide">채팅 (0)</span>
              </div>

              {/* 휴지통 — 펼치면 삭제된 시뮬/제너, 클릭 시 상세 */}
              <button
                onClick={() => setTrashOpen(v => !v)}
                className="w-full flex items-center gap-2 px-2 py-1.5 hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D] rounded-md transition-colors"
              >
                <ChevronIcon open={trashOpen} />
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-[#8B95A1] shrink-0">
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

// ── 메인 패널 ───────────────────────────────────────────────────
export default function ProjectPanel({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const pathname = usePathname();
  const { projects, loading, details, loadDetails, loadAll, selectProject, refresh } = useProjects();
  const { user } = useAuth();
  const [view, setView] = useState<'ALL' | 'TEAM' | 'MY'>('ALL');
  const [teamNames, setTeamNames] = useState<string[]>([]);
  const [openProjectId, setOpenProjectId] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);

  const simMatch = pathname.match(/^\/simulations\/([^/]+)/);
  const genMatch = pathname.match(/^\/generations\/([^/]+)/);
  const activeSimId = simMatch?.[1] ?? null;
  const activeGenId = genMatch?.[1] ?? null;
  const activeItemId = activeSimId ?? activeGenId;

  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);

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

  const handleCreated = async () => {
    setShowModal(false);
    await refresh();
  };

  const myName = user?.name ?? null;

  // TEAM 토글용 — 내 팀 멤버 이름 목록 (팀 없으면 빈 배열)
  useEffect(() => {
    fetch(`${API_BASE}/api/company/my-team-members`, { headers: { Authorization: `Bearer ${getToken()}` } })
      .then(r => (r.ok ? r.json() : null))
      .then(d => { if (d && Array.isArray(d.member_names)) setTeamNames(d.member_names); })
      .catch(() => {});
  }, []);

  // null=전체(ALL), 배열=해당 이름만(MY/TEAM)
  const filterNames: string[] | null =
    view === 'ALL' ? null : view === 'MY' ? (myName ? [myName] : []) : teamNames;

  const changeView = (v: 'ALL' | 'TEAM' | 'MY') => {
    setView(v);
    if (v !== 'ALL') loadAll();
  };

  const projectMatches = (p: { id: string; created_by_name?: string | null }) => {
    if (!filterNames) return true;
    if (p.created_by_name && filterNames.includes(p.created_by_name)) return true;
    const d = details[p.id];
    if (!d?.loaded) return true;
    return d.sims.some(s => s.created_by_name != null && filterNames.includes(s.created_by_name))
      || d.gens.some(g => g.created_by_name != null && filterNames.includes(g.created_by_name));
  };

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
    <>
      <aside className="fixed top-0 left-56 h-full w-72 bg-[#FAFBFC] dark:bg-[#161B27] border-r border-[#E5E8EB] dark:border-[#2D3748] flex flex-col z-30 transition-all duration-200">
        {/* 헤더 */}
        <div className="h-14 flex items-center justify-between px-3 border-b border-[#E5E8EB] dark:border-[#2D3748] shrink-0">
          {/* 접기 버튼 */}
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
              onClick={refresh}
              title="새로고침"
              className="w-7 h-7 flex items-center justify-center rounded-lg text-[#8B95A1] hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D] hover:text-[#3182F6] transition-colors"
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="23 4 23 10 17 10" /><polyline points="1 20 1 14 7 14" />
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
              </svg>
            </button>
            {/* ALL / TEAM / MY 토글 */}
            <div className="flex items-center gap-0.5 bg-[#F2F4F6] dark:bg-[#252D3D] rounded-lg p-0.5">
              {(['ALL', 'TEAM', 'MY'] as const).map(v => (
                <button
                  key={v}
                  onClick={() => changeView(v)}
                  className={`px-1.5 py-0.5 rounded-md text-[10px] font-medium transition-colors ${
                    view === v
                      ? 'bg-white dark:bg-[#1C2333] text-[#191F28] dark:text-[#F2F4F6] shadow-sm'
                      : 'text-[#8B95A1] dark:text-[#6B7280]'
                  }`}
                >{v}</button>
              ))}
            </div>

            {/* + 버튼 */}
            <button
              onClick={() => setShowModal(true)}
              title="새 프로젝트"
              className="w-7 h-7 flex items-center justify-center rounded-lg text-[#8B95A1] hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F] hover:text-[#3182F6] transition-colors"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
              </svg>
            </button>
          </div>
        </div>

        {/* 프로젝트 목록 */}
        <div className="flex-1 overflow-y-auto py-2 px-2">
          {loading ? (
            <p className="text-xs text-[#B0B8C1] px-3 py-2">불러오는 중...</p>
          ) : projects.length === 0 ? (
            <div className="px-3 py-6 text-center">
              <p className="text-xs text-[#B0B8C1] dark:text-[#4B5563] mb-3">프로젝트가 없습니다</p>
              <button
                onClick={() => setShowModal(true)}
                className="text-xs text-[#3182F6] hover:underline font-medium"
              >
                첫 프로젝트 만들기
              </button>
            </div>
          ) : filterNames && projects.every(p => !projectMatches(p)) ? (
            <p className="text-xs text-[#B0B8C1] px-3 py-2">
              {view === 'TEAM' ? '우리 팀 작업 내역이 없습니다' : '참여한 프로젝트가 없습니다'}
            </p>
          ) : (
            <div className="space-y-0.5">
              {(filterNames ? projects.filter(projectMatches) : projects).map(p => (
                <ProjectItem
                  key={p.id}
                  project={p}
                  activeSimId={activeSimId}
                  activeGenId={activeGenId}
                  autoOpen={p.id === activeProjectId}
                  filterNames={filterNames}
                  isAdmin={user?.role === 'ADMIN'}
                  canRun={user?.role !== 'COMPANY'}
                  isOpen={openProjectId === p.id}
                  onToggleOpen={(id) => setOpenProjectId(prev => prev === id ? null : id)}
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

      {showModal && (
        <CreateProjectModal
          onClose={() => setShowModal(false)}
          onCreated={handleCreated}
        />
      )}
    </>
  );
}
