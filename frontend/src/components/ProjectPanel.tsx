'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useProjects, type SimRow } from './ProjectContext';
import { useAuth } from './AuthProvider';
import TrashSection from './TrashSection';
import ModeBadge from './ModeBadge';
import { authedFetch } from '@/lib/api';
import { formatKST } from '@/lib/datetime';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

const statusColor: Record<string, string> = {
  COMPLETED: 'bg-success', completed: 'bg-success',
  QUEUED: 'bg-warning', pending: 'bg-warning',
  RUNNING: 'bg-info', running: 'bg-info',
  FAILED: 'bg-danger', failed: 'bg-danger',
};

const fmt = (iso: string) => formatKST(iso);

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

// ── 시뮬레이션 1건 + 토론 펼침 ─────────────────────────────────
// 시뮬 행(상세 링크) 아래에 그 시뮬의 저장된 토론 목록을 lazy 로드해 펼친다(말풍선 토글).
function SimEntry({ sim, isActive }: { sim: SimRow; isActive: boolean }) {
  const { debates, loadDebates } = useProjects();
  const [open, setOpen] = useState(false);
  const list = debates[sim.id];

  const toggle = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const next = !open;
    setOpen(next);
    if (next && list === undefined) loadDebates(sim.id);
  };

  return (
    <div>
      <div className={`flex items-center gap-1 rounded-md transition-colors ${
        isActive ? 'bg-primary-subtle' : 'hover:bg-primary-subtle'
      }`}>
        <Link href={`/simulation/${sim.id}`} className="flex items-center gap-2 px-2 py-1.5 flex-1 min-w-0 group">
          <span className={`w-2 h-2 rounded-full shrink-0 ${statusColor[sim.status] ?? 'bg-ink-muted'}`} />
          <div className="flex-1 min-w-0">
            <p className={`text-xs truncate ${isActive ? 'text-primary font-medium' : 'text-ink-secondary group-hover:text-primary'}`}>
              {sim.ad_title || '제목 없음'}
            </p>
            <p className="text-[10px] text-ink-muted truncate">
              {sim.sample_size}명 · {sim.created_by_name ?? '—'} · {fmt(sim.created_at)}
            </p>
          </div>
          {isActive && <span className="shrink-0 w-1.5 h-1.5 rounded-full bg-primary" />}
        </Link>
        {/* 토론 펼침 토글(말풍선 + 건수) */}
        <button
          onClick={toggle}
          title="토론 내역"
          className="shrink-0 flex items-center gap-1 pr-2 pl-1 py-1.5 text-ink-tertiary hover:text-primary transition-colors"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
          {list && list.length > 0 && <span className="text-[10px] font-medium">{list.length}</span>}
          <ChevronIcon open={open} />
        </button>
      </div>

      {open && (
        <div className="ml-6 pl-2 border-l border-line space-y-0.5 my-0.5">
          {list === undefined ? (
            <p className="text-[10px] text-ink-muted px-2 py-1">불러오는 중...</p>
          ) : list.length === 0 ? (
            <p className="text-[10px] text-ink-muted px-2 py-1">토론 내역 없음</p>
          ) : (
            list.map(d => (
              <Link
                key={d.debate_id}
                href={`/simulation/${sim.id}`}
                className="flex items-start gap-2 px-2 py-1 rounded-md hover:bg-primary-subtle transition-colors group"
              >
                <span className={`mt-1 w-1.5 h-1.5 rounded-full shrink-0 ${statusColor[d.status] ?? 'bg-ink-muted'}`} />
                <div className="min-w-0 flex-1">
                  <p className="text-[11px] truncate text-ink-secondary group-hover:text-primary">
                    {d.headline ?? d.topic ?? '토론'}
                  </p>
                  <p className="text-[10px] text-ink-muted">
                    {d.rounds_run ? `${d.rounds_run}라운드` : '—'}{d.created_at ? ` · ${fmt(d.created_at)}` : ''}
                  </p>
                </div>
              </Link>
            ))
          )}
        </div>
      )}
    </div>
  );
}

// ── 프로젝트 생성 모달 ──────────────────────────────────────────
// defaultName으로 이름칸 프리필(캠페인명 등), onCreated는 생성된 프로젝트를 넘겨 호출측 자동선택 지원.
export function CreateProjectModal({
  onClose,
  onCreated,
  defaultName = '',
}: {
  onClose: () => void;
  onCreated: (created?: { id: string; name: string } | null) => void;
  defaultName?: string;
}) {
  const [name, setName] = useState(defaultName);
  const [description, setDescription] = useState('');
  const [creating, setCreating] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { inputRef.current?.focus(); inputRef.current?.select(); }, []);

  const handleCreate = async () => {
    if (!name.trim() || creating) return;
    setCreating(true);
    const res = await authedFetch(`${API_BASE}/api/projects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name.trim(), description: description.trim() || null }),
    });
    const created = res.ok ? ((await res.json()) as { id: string; name: string }) : null;
    setCreating(false);
    onCreated(created);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-card rounded-2xl shadow-xl w-full max-w-md mx-4 p-6">
        <h2 className="text-lg font-bold text-ink mb-4">새 프로젝트</h2>
        <div className="space-y-3">
          <div>
            <label className="text-xs font-medium text-ink-secondary block mb-1">프로젝트 이름 *</label>
            <input
              ref={inputRef}
              value={name}
              onChange={e => setName(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') handleCreate(); if (e.key === 'Escape') onClose(); }}
              placeholder="예: 2024 여름 캠페인"
              className="w-full px-3 py-2.5 text-sm border border-line rounded-xl bg-surface-2 text-ink placeholder:text-ink-muted focus:outline-none focus:border-primary transition-colors"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-ink-secondary block mb-1">설명 (선택)</label>
            <textarea
              value={description}
              onChange={e => setDescription(e.target.value)}
              onKeyDown={e => { if (e.key === 'Escape') onClose(); }}
              placeholder="프로젝트에 대한 간단한 설명"
              rows={3}
              className="w-full px-3 py-2.5 text-sm border border-line rounded-xl bg-surface-2 text-ink placeholder:text-ink-muted focus:outline-none focus:border-primary transition-colors resize-none"
            />
          </div>
        </div>
        <div className="flex gap-2 mt-5">
          <button
            onClick={onClose}
            className="flex-1 py-2.5 text-sm font-medium border border-line rounded-xl text-ink-secondary hover:bg-accent transition-colors"
          >
            취소
          </button>
          <button
            onClick={handleCreate}
            disabled={!name.trim() || creating}
            className="flex-1 py-2.5 text-sm font-medium bg-primary text-primary-foreground rounded-xl hover:bg-primary-hover transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {creating ? '생성 중...' : '만들기'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── 프로젝트 아이템 ─────────────────────────────────────────────
// CompanyPanel(조회 전용)에서도 재사용하므로 export.
export function ProjectItem({
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
  const { details, loadDetails, refreshDetails, selectedProjectId, selectProject, revealProjectId, revealNonce } = useProjects();
  const router = useRouter();
  const [simOpen, setSimOpen] = useState(false);
  const [genOpen, setGenOpen] = useState(false);
  const [trashOpen, setTrashOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

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

  // 외부(패널)에서 isOpen이 켜지면 상세를 로드한다(내역 클릭으로 펼쳐진 경우 포함).
  useEffect(() => {
    if (isOpen && !d?.loaded) loadDetails(project.id);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  // 내역 클릭 등으로 이 프로젝트가 reveal 대상이 되면 화면에 보이도록 스크롤.
  useEffect(() => {
    if (revealProjectId === project.id) rootRef.current?.scrollIntoView({ block: 'nearest' });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [revealNonce]);

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
    <div ref={rootRef}>
      <div
        className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg transition-colors text-left ${
          isSelected ? 'bg-primary-subtle' : 'hover:bg-accent'
        }`}
      >
        {/* 접기/펼치기 */}
        <button onClick={toggle} className="flex items-center gap-2 flex-1 min-w-0 text-left">
          <ChevronIcon open={isOpen} />
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
            className={isSelected ? 'text-primary shrink-0' : 'text-ink-tertiary shrink-0'}>
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
          </svg>
          <span className="flex-1 min-w-0">
            <span className={`block text-sm font-medium truncate ${isSelected ? 'text-primary' : 'text-ink'}`}>
              {project.name}
            </span>
            {isAdmin && project.organization_name && (
              <span className="block text-[10px] text-ink-muted truncate">{project.organization_name}</span>
            )}
          </span>
        </button>
        {/* 자세히 보기 */}
        <Link
          href={`/projects/${project.id}`}
          title="프로젝트 상세"
          className="shrink-0 p-1 rounded-md text-ink-muted hover:text-primary hover:bg-primary-subtle transition-colors"
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
        <div className="ml-5 border-l border-line pl-2 space-y-0.5 mt-0.5 mb-1">
          {isLoading ? (
            <p className="text-xs text-ink-muted px-2 py-1.5">불러오는 중...</p>
          ) : (
            <>
              {/* 시뮬레이션 섹션 */}
              <button
                onClick={() => setSimOpen(v => !v)}
                className="w-full flex items-center gap-2 px-2 py-1.5 hover:bg-accent rounded-md transition-colors"
              >
                <ChevronIcon open={simOpen} />
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-ink-tertiary shrink-0">
                  <circle cx="12" cy="12" r="10" /><polygon points="10 8 16 12 10 16 10 8" />
                </svg>
                <span className="text-xs font-semibold text-ink-secondary uppercase tracking-wide">
                  시뮬레이션{sims.length > 0 ? ` (${sims.length})` : ''}
                </span>
              </button>
              {simOpen && (
                <div className="ml-4 space-y-0.5">
                  {sims.length === 0 ? (
                    <p className="text-xs text-ink-muted px-2 py-1">
                      {filterNames ? '해당 내역 없음' : '내역 없음'}
                    </p>
                  ) : sims.map(s => (
                    <SimEntry key={s.id} sim={s} isActive={s.id === activeSimId} />
                  ))}
                  {canRun && (
                    <button
                      onClick={goToSim}
                      className="w-full flex items-center gap-1.5 px-2 py-1.5 rounded-md text-xs text-primary hover:bg-primary-subtle transition-colors"
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
                className="w-full flex items-center gap-2 px-2 py-1.5 hover:bg-accent rounded-md transition-colors"
              >
                <ChevronIcon open={genOpen} />
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-ink-tertiary shrink-0">
                  <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
                </svg>
                <span className="text-xs font-semibold text-ink-secondary uppercase tracking-wide">
                  제너레이터{gens.length > 0 ? ` (${gens.length})` : ''}
                </span>
              </button>
              {genOpen && (
                <div className="ml-4 space-y-0.5">
                  {gens.length === 0 ? (
                    <p className="text-xs text-ink-muted px-2 py-1">
                      {filterNames ? '해당 내역 없음' : '내역 없음'}
                    </p>
                  ) : gens.map(g => {
                    const isActive = g.id === activeGenId;
                    return (
                      <Link
                        key={g.id}
                        href={`/generations/${g.id}`}
                        className={`flex items-center gap-2 px-2 py-1.5 rounded-md transition-colors group ${
                          isActive ? 'bg-primary-subtle' : 'hover:bg-primary-subtle'
                        }`}
                      >
                        <span className={`w-2 h-2 rounded-full shrink-0 ${statusColor[g.status] ?? 'bg-ink-muted'}`} />
                        <div className="flex-1 min-w-0">
                          <p className={`text-xs truncate flex items-center gap-1.5 ${isActive ? 'text-primary font-medium' : 'text-ink-secondary group-hover:text-primary'}`}>
                            <ModeBadge mode={g.mode} format={g.format} />
                            <span className="truncate">{g.product_name ?? '—'} · {g.created_by_name ?? '—'}</span>
                          </p>
                          <p className="text-[10px] text-ink-muted">{fmt(g.created_at)}</p>
                        </div>
                        {isActive && <span className="shrink-0 w-1.5 h-1.5 rounded-full bg-primary" />}
                      </Link>
                    );
                  })}
                  {canRun && (
                    <button
                      onClick={goToGen}
                      className="w-full flex items-center gap-1.5 px-2 py-1.5 rounded-md text-xs text-primary hover:bg-primary-subtle transition-colors"
                    >
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
                      </svg>
                      제너레이터 추가
                    </button>
                  )}
                </div>
              )}

              {/* 휴지통 — 펼치면 삭제된 시뮬/제너, 클릭 시 상세 */}
              <button
                onClick={() => setTrashOpen(v => !v)}
                className="w-full flex items-center gap-2 px-2 py-1.5 hover:bg-accent rounded-md transition-colors"
              >
                <ChevronIcon open={trashOpen} />
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-ink-tertiary shrink-0">
                  <polyline points="3 6 5 6 21 6" />
                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                </svg>
                <span className="text-xs font-semibold text-ink-secondary uppercase tracking-wide">
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
  const { projects, loading, details, loadDetails, selectProject, refresh, refreshAll, revealProjectId, revealNonce } = useProjects();
  const { user } = useAuth();
  const [openProjectId, setOpenProjectId] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);

  // 내역 클릭 등으로 reveal 요청이 오면 그 프로젝트를 펼친다(플랫 목록이라 바로 열림).
  useEffect(() => {
    if (revealProjectId) setOpenProjectId(revealProjectId);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [revealNonce]);

  const simMatch = pathname.match(/^\/simulation\/([^/]+)/);
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

  // ── 접힌 상태 ──
  if (collapsed) {
    return (
      <aside className="fixed top-0 left-56 h-full w-[50px] bg-surface-1 border-r border-line flex flex-col items-center pt-3 z-30 transition-all duration-200">
        <button
          onClick={onToggle}
          title="패널 펼치기"
          className="w-8 h-8 flex items-center justify-center rounded-lg text-ink-tertiary hover:bg-accent hover:text-primary transition-colors"
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
      <aside className="fixed top-0 left-56 h-full w-72 bg-surface-1 border-r border-line flex flex-col z-30 transition-all duration-200">
        {/* 헤더 */}
        <div className="h-14 flex items-center justify-between px-3 border-b border-line shrink-0">
          {/* 접기 버튼 */}
          <button
            onClick={onToggle}
            title="패널 접기"
            className="w-7 h-7 flex items-center justify-center rounded-lg text-ink-tertiary hover:bg-accent hover:text-primary transition-colors"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="15 18 9 12 15 6" />
            </svg>
          </button>

          <p className="text-sm font-semibold text-ink-secondary">프로젝트</p>

          <div className="flex items-center gap-1">
            {/* 새로고침 */}
            <button
              onClick={refreshAll}
              title="새로고침"
              className="w-7 h-7 flex items-center justify-center rounded-lg text-ink-tertiary hover:bg-accent hover:text-primary transition-colors"
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="23 4 23 10 17 10" /><polyline points="1 20 1 14 7 14" />
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
              </svg>
            </button>

            {/* + 버튼 */}
            <button
              onClick={() => setShowModal(true)}
              title="새 프로젝트"
              className="w-7 h-7 flex items-center justify-center rounded-lg text-ink-tertiary hover:bg-primary-subtle hover:text-primary transition-colors"
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
            <p className="text-xs text-ink-muted px-3 py-2">불러오는 중...</p>
          ) : projects.length === 0 ? (
            <div className="px-3 py-6 text-center">
              <p className="text-xs text-ink-muted mb-3">프로젝트가 없습니다</p>
              <button
                onClick={() => setShowModal(true)}
                className="text-xs text-primary hover:underline font-medium"
              >
                첫 프로젝트 만들기
              </button>
            </div>
          ) : (
            <div className="space-y-0.5">
              {projects.map(p => (
                <ProjectItem
                  key={p.id}
                  project={p}
                  activeSimId={activeSimId}
                  activeGenId={activeGenId}
                  autoOpen={p.id === activeProjectId}
                  filterNames={null}
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
        <div className="border-t border-line shrink-0 p-2">
          <Link
            href="/trash"
            className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${
              pathname === '/trash'
                ? 'bg-primary-subtle text-primary font-medium'
                : 'text-ink-tertiary hover:bg-accent hover:text-primary'
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
