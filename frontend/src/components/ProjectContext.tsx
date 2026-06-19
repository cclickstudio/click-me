'use client';

import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { getToken } from '@/lib/authApi';
import { api } from '@/lib/api';
import type { DebateSessionMeta } from '@/lib/types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export type Project = { id: string; name: string; status: string; description?: string | null; created_at?: string; created_by_name: string | null; organization_name: string | null };
export type SimRow = { id: string; status: string; sample_size: number; ad_title: string | null; created_by_name: string | null; created_at: string };
export type GenRow = { id: string; status: string; product_name: string | null; created_by_name: string | null; created_at: string };

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
  const fetchedRef = useRef(false);

  const fetchProjects = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/projects`, {
        headers: { Authorization: `Bearer ${token}` },
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

  useEffect(() => {
    if (fetchedRef.current) return;
    fetchedRef.current = true;
    fetchProjects();
  }, []);

  const fetchDetailsForProject = async (projectId: string) => {
    const token = getToken();
    if (!token) return;
    const headers = { Authorization: `Bearer ${token}` };
    const [s, g, t] = await Promise.all([
      fetch(`${API_BASE}/api/projects/${projectId}/simulations`, { headers }).then(r => r.json()).catch(() => []),
      fetch(`${API_BASE}/api/projects/${projectId}/generations`, { headers }).then(r => r.json()).catch(() => []),
      fetch(`${API_BASE}/api/projects/trash?project_id=${projectId}`, { headers }).then(r => r.json()).catch(() => null),
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
      selectedProjectId, selectedProject, selectProject: setSelectedProjectId,
      debates, loadDebates,
    }}>
      {children}
    </ProjectContext.Provider>
  );
}

export function useProjects() {
  return useContext(ProjectContext);
}
