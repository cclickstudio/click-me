'use client';

import { createContext, useContext, useEffect, useRef, useState } from 'react';
import { getToken } from '@/lib/authApi';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export type Project = { id: string; name: string; status: string };
export type SimRow = { id: string; status: string; sample_size: number; created_by_name: string | null; created_at: string };
export type GenRow = { id: string; status: string; product_name: string | null; created_by_name: string | null; created_at: string };

type ProjectDetails = { sims: SimRow[]; gens: GenRow[]; loaded: boolean };

type ProjectContextValue = {
  projects: Project[];
  loading: boolean;
  details: Record<string, ProjectDetails>;
  loadDetails: (projectId: string) => Promise<void>;
  refreshDetails: (projectId: string) => Promise<void>;
  refresh: () => Promise<void>;
  selectedProjectId: string | null;
  selectedProject: Project | null;
  selectProject: (id: string | null) => void;
};

const ProjectContext = createContext<ProjectContextValue>({
  projects: [],
  loading: true,
  details: {},
  loadDetails: async () => {},
  refreshDetails: async () => {},
  refresh: async () => {},
  selectedProjectId: null,
  selectedProject: null,
  selectProject: () => {},
});

export function ProjectProvider({ children }: { children: React.ReactNode }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(false);
  const [details, setDetails] = useState<Record<string, ProjectDetails>>({});
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const fetchedRef = useRef(false);

  const fetchProjects = async () => {
    const token = getToken();
    if (!token) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/projects`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (Array.isArray(data)) setProjects(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (fetchedRef.current) return;
    fetchedRef.current = true;
    fetchProjects();
  }, []);

  const fetchDetailsForProject = async (projectId: string) => {
    const token = getToken();
    if (!token) return;
    const headers = { Authorization: `Bearer ${token}` };
    const [s, g] = await Promise.all([
      fetch(`${API_BASE}/api/projects/${projectId}/simulations`, { headers }).then(r => r.json()).catch(() => []),
      fetch(`${API_BASE}/api/projects/${projectId}/generations`, { headers }).then(r => r.json()).catch(() => []),
    ]);
    setDetails(prev => ({
      ...prev,
      [projectId]: {
        sims: Array.isArray(s) ? s : [],
        gens: Array.isArray(g) ? g : [],
        loaded: true,
      },
    }));
  };

  const loadDetails = async (projectId: string) => {
    if (details[projectId]?.loaded) return;
    await fetchDetailsForProject(projectId);
  };

  // 캐시 무시하고 강제 재조회 — 시뮬/제너 완료 후 패널 갱신에 사용
  const refreshDetails = async (projectId: string) => {
    await fetchDetailsForProject(projectId);
  };

  const selectedProject = projects.find(p => p.id === selectedProjectId) ?? null;

  return (
    <ProjectContext.Provider value={{
      projects, loading, details, loadDetails, refreshDetails, refresh: fetchProjects,
      selectedProjectId, selectedProject, selectProject: setSelectedProjectId,
    }}>
      {children}
    </ProjectContext.Provider>
  );
}

export function useProjects() {
  return useContext(ProjectContext);
}
