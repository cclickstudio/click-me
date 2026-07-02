'use client';

import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { getToken } from '@/lib/authApi';
import { useAuth } from '@/components/AuthProvider';
import { api, authedFetch } from '@/lib/api';
import type { DebateSessionMeta } from '@/lib/types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export type Project = { id: string; name: string; status: string; description?: string | null; created_at?: string; created_by_name: string | null; organization_name: string | null; team_id: string | null; team_name: string | null };
export type SimRow = { id: string; status: string; sample_size: number; ad_title: string | null; created_by_name: string | null; created_at: string };
export type GenRow = { id: string; status: string; product_name: string | null; mode: string; format: string; created_by_name: string | null; created_at: string };

export type TrashRow = { id: string; kind: 'sim' | 'gen'; label: string; deleted_at: string };
type ProjectDetails = { sims: SimRow[]; gens: GenRow[]; trashed: TrashRow[]; loaded: boolean };

type ProjectContextValue = {
  projects: Project[];
  loading: boolean;
  details: Record<string, ProjectDetails>;
  loadDetails: (projectId: string) => Promise<void>;
  loadAll: () => Promise<void>;
  refreshDetails: (projectId: string) => Promise<void>;
  refresh: () => Promise<void>;
  // 프로젝트 목록 + 로드된 프로젝트들의 시뮬/제너/휴지통 + 채팅까지 싹 다시 불러온다(새로고침 버튼).
  refreshAll: () => Promise<void>;
  // 채팅 세션 목록 갱신 신호 — refreshAll 시 증가, ProjectChatSection이 구독해 재조회.
  chatRefreshKey: number;
  selectedProjectId: string | null;
  selectedProject: Project | null;
  selectProject: (id: string | null) => void;
  // 시뮬레이션별 토론 목록(DB 영속화) — 패널에서 lazy 로드. 키 = simulation_id.
  debates: Record<string, DebateSessionMeta[]>;
  loadDebates: (simulationId: string) => Promise<void>;
};

const ProjectContext = createContext<ProjectContextValue>({
  projects: [],
  loading: true,
  details: {},
  loadDetails: async () => {},
  loadAll: async () => {},
  refreshDetails: async () => {},
  refresh: async () => {},
  refreshAll: async () => {},
  chatRefreshKey: 0,
  selectedProjectId: null,
  selectedProject: null,
  selectProject: () => {},
  debates: {},
  loadDebates: async () => {},
});

export function ProjectProvider({ children }: { children: React.ReactNode }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(false);
  const [details, setDetails] = useState<Record<string, ProjectDetails>>({});
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [debates, setDebates] = useState<Record<string, DebateSessionMeta[]>>({});
  const [chatRefreshKey, setChatRefreshKey] = useState(0);
  const { token } = useAuth();
  const fetchedTokenRef = useRef<string | null>(null);

  const fetchProjects = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    setLoading(true);
    try {
      const res = await authedFetch(`${API_BASE}/api/projects`, {
        cache: 'no-store',
      });
      const data = await res.json();
      if (Array.isArray(data)) setProjects(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  // 토큰이 준비된 시점에 프로젝트를 1회 로드 — 로그인/세션 복원 후 패널 데이터를 채운다.
  // (앱 마운트 1회로 묶으면 로그인 전 토큰 부재로 스킵돼, 이후 페이지마다 강제 refresh가 필요해진다.)
  useEffect(() => {
    if (!token) { fetchedTokenRef.current = null; return; }
    if (fetchedTokenRef.current === token) return;
    fetchedTokenRef.current = token;
    fetchProjects();
  }, [token, fetchProjects]);

  // 활성 프로젝트를 localStorage에 고정 — 페이지 이동·새로고침 후에도 유지(생성 내역 누락 방지).
  useEffect(() => {
    const stored = localStorage.getItem('selectedProjectId');
    if (stored) setSelectedProjectId(stored);
  }, []);

  const selectProject = useCallback((id: string | null) => {
    setSelectedProjectId(id);
    if (id) localStorage.setItem('selectedProjectId', id);
    else localStorage.removeItem('selectedProjectId');
  }, []);

  const fetchDetailsForProject = async (projectId: string) => {
    const token = getToken();
    if (!token) return;
    const [s, g, t] = await Promise.all([
      authedFetch(`${API_BASE}/api/projects/${projectId}/simulations`).then(r => r.json()).catch(() => []),
      authedFetch(`${API_BASE}/api/projects/${projectId}/generations`).then(r => r.json()).catch(() => []),
      authedFetch(`${API_BASE}/api/projects/trash?project_id=${projectId}`).then(r => r.json()).catch(() => null),
    ]);
    const trashed: TrashRow[] = t
      ? [
          ...(Array.isArray(t.simulations) ? t.simulations : []).map((x: { id: string; ad_title: string | null; deleted_at: string }) => ({
            id: x.id, kind: 'sim' as const, label: x.ad_title ?? '시뮬레이션', deleted_at: x.deleted_at,
          })),
          ...(Array.isArray(t.generations) ? t.generations : []).map((x: { id: string; product_name: string | null; deleted_at: string }) => ({
            id: x.id, kind: 'gen' as const, label: x.product_name ?? '제너레이터', deleted_at: x.deleted_at,
          })),
        ]
      : [];
    setDetails(prev => ({
      ...prev,
      [projectId]: {
        sims: Array.isArray(s) ? s : [],
        gens: Array.isArray(g) ? g : [],
        trashed,
        loaded: true,
      },
    }));
  };

  const loadDetails = async (projectId: string) => {
    if (details[projectId]?.loaded) return;
    await fetchDetailsForProject(projectId);
  };

  const refreshDetails = async (projectId: string) => {
    await fetchDetailsForProject(projectId);
  };

  // 새로고침 버튼 — 프로젝트 목록 + 로드된 프로젝트들의 시뮬/제너/휴지통을 재조회하고,
  // 채팅 세션도 갱신 신호를 올린다. (아직 안 펼친 프로젝트는 펼칠 때 로드되므로 제외)
  const refreshAll = async () => {
    await fetchProjects();
    const loadedIds = Object.keys(details).filter(id => details[id]?.loaded);
    await Promise.all(loadedIds.map(id => fetchDetailsForProject(id)));
    setChatRefreshKey(k => k + 1);
  };

  // 아직 로드 안 된 프로젝트 details를 일괄 로드 — MY 필터링에 사용
  const loadAll = async () => {
    const unloaded = projects.filter(p => !details[p.id]?.loaded);
    await Promise.all(unloaded.map(p => fetchDetailsForProject(p.id)));
  };

  // 시뮬레이션별 토론 목록 lazy 로드(중복 호출 무해 — 갱신 시 덮어씀).
  const loadDebates = useCallback(async (simulationId: string) => {
    try {
      const { debates: sessions } = await api.debate.bySimulation(simulationId);
      setDebates(prev => ({ ...prev, [simulationId]: sessions }));
    } catch {
      // ignore — DB 미연동·네트워크 오류 시 빈 상태 유지
    }
  }, []);

  const selectedProject = projects.find(p => p.id === selectedProjectId) ?? null;

  return (
    <ProjectContext.Provider value={{
      projects, loading, details, loadDetails, loadAll, refreshDetails, refresh: fetchProjects,
      refreshAll, chatRefreshKey,
      selectedProjectId, selectedProject, selectProject,
      debates, loadDebates,
    }}>
      {children}
    </ProjectContext.Provider>
  );
}

export function useProjects() {
  return useContext(ProjectContext);
}
