'use client';

// 센터 최상단 필터 바 — 세그먼트[안읽음·읽음·전체] + 프로젝트 드롭다운(+ADMIN 기업 드롭다운).
// 스펙: docs/center/center-spec.md §4·§7. 채팅/알림 각 센터가 자기 필터바를 보유한다.

import { useEffect, useState } from 'react';
import { api, setAdminOrgId } from '@/lib/api';
import { Select } from '@/components/ui/Select';

export type CenterSegment = 'unread' | 'read' | 'all';

const SEGMENTS: { v: CenterSegment; l: string }[] = [
  { v: 'unread', l: '안읽음' },
  { v: 'read', l: '읽음' },
  { v: 'all', l: '전체' },
];

type ProjectOpt = { id: string; name: string };

export function CenterFilterBar({
  segment,
  onSegment,
  projectId,
  onProjectId,
  projects,
  isAdmin,
  orgId,
  onOrgId,
}: {
  segment: CenterSegment;
  onSegment: (s: CenterSegment) => void;
  projectId: string;
  onProjectId: (id: string) => void;
  projects: ProjectOpt[];
  isAdmin: boolean;
  orgId: string;
  onOrgId: (id: string) => void;
}) {
  const [orgs, setOrgs] = useState<ProjectOpt[]>([]);

  // ADMIN 기업 목록 — impersonation 드롭다운용(AdminOrgPicker와 동일 소스). 실패 시 전체만.
  useEffect(() => {
    if (!isAdmin) return;
    let alive = true;
    api.admin
      .organizations()
      .then((list) => {
        if (alive && Array.isArray(list)) setOrgs(list.map((o) => ({ id: o.id, name: o.name })));
      })
      .catch(() => {
        if (alive) setOrgs([]);
      });
    return () => {
      alive = false;
    };
  }, [isAdmin]);

  return (
    <div className="flex flex-col gap-2 border-b border-[#E5E8EB] px-3 py-2.5 dark:border-[#2D3748]">
      {/* ADMIN 전용 — 기업 선택(프로젝트 드롭다운 위/왼쪽, 스펙 §7). 선택 시 X-Org-Id 반영. */}
      {isAdmin && (
        <Select
          aria-label="기업 선택"
          className="w-full"
          value={orgId}
          onChange={(v) => {
            setAdminOrgId(v || null);
            onProjectId(''); // 기업 바뀌면 프로젝트 선택 초기화(전체)
            onOrgId(v);
          }}
          options={[
            { value: '', label: '기업 전체' },
            ...orgs.map((o) => ({ value: o.id, label: o.name })),
          ]}
        />
      )}
      {/* space-between — 좌: 세그먼트, 우: 프로젝트 드롭다운(기본 전체). */}
      <div className="flex items-center justify-between gap-2">
        <div className="inline-flex rounded-lg bg-[#F2F4F6] p-0.5 dark:bg-[#252D3D]">
          {SEGMENTS.map((s) => {
            const active = segment === s.v;
            return (
              <button
                key={s.v}
                type="button"
                onClick={() => onSegment(s.v)}
                className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                  active
                    ? 'bg-white text-[#191F28] shadow-sm dark:bg-[#1C2333] dark:text-[#F2F4F6]'
                    : 'text-[#8B95A1] hover:text-[#4E5968] dark:text-[#6B7280] dark:hover:text-[#9CA3AF]'
                }`}
              >
                {s.l}
              </button>
            );
          })}
        </div>
        <Select
          aria-label="프로젝트 선택"
          className="min-w-[120px] flex-1"
          value={projectId}
          onChange={onProjectId}
          options={[
            { value: '', label: '전체 프로젝트' },
            ...projects.map((p) => ({ value: p.id, label: p.name })),
          ]}
        />
      </div>
    </div>
  );
}

export default CenterFilterBar;
