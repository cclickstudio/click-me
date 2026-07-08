// 내역(시뮬·제너·채팅) 정렬·필터·검색 컨트롤 — width 100%, 왼쪽 정렬·필터 / 오른쪽 검색.
'use client';

import { useMemo } from 'react';
import { Select } from '@/components/ui/Select';

// 백엔드 목록 계약과 1:1 대응하는 쿼리 모델.
export type HistoryQuery = {
  sort: 'created_at' | 'title' | 'org_name';
  order: 'asc' | 'desc';
  status?: 'completed' | 'in_progress' | 'failed'; // 상태순=필터(그 상태만 보기)
  orgStatus?: 'ACTIVE' | 'INACTIVE'; // 조직 상태 필터(활성/비활성 조직 데이터만 보기)
  searchField: 'title' | 'org_name';
  search: string;
};

export const DEFAULT_HISTORY_QUERY: HistoryQuery = {
  sort: 'created_at',
  order: 'desc',
  status: undefined,
  orgStatus: undefined,
  searchField: 'title',
  search: '',
};

// 왼쪽 Category: 날짜순/가나다순/조직명순/상태순. 오른쪽 Kind는 왼쪽 값에 종속.
type Category = 'date' | 'name' | 'org' | 'status';

function categoryOf(q: HistoryQuery): Category {
  if (q.status) return 'status';
  if (q.sort === 'title') return 'name';
  if (q.sort === 'org_name') return 'org';
  return 'date';
}

export function HistoryControls({
  value,
  onChange,
  hasStatus = true,
  titleLabel = '제목',
}: {
  value: HistoryQuery;
  onChange: (next: HistoryQuery) => void;
  hasStatus?: boolean; // 채팅은 상태 개념이 없어 false
  titleLabel?: string; // 가나다순/검색 라벨(광고명·상품명·제목 등)
}) {
  const category = categoryOf(value);

  // 왼쪽 Category 변경 시 오른쪽 Kind를 그 카테고리의 기본값으로 초기화.
  const onCategory = (c: Category) => {
    if (c === 'date') onChange({ ...value, sort: 'created_at', order: 'desc', status: undefined });
    else if (c === 'name') onChange({ ...value, sort: 'title', order: 'asc', status: undefined });
    else if (c === 'org') onChange({ ...value, sort: 'org_name', order: 'asc', status: undefined });
    else onChange({ ...value, sort: 'created_at', order: 'desc', status: 'completed' });
  };

  const onKind = (kind: string) => {
    if (category === 'status') onChange({ ...value, status: kind as HistoryQuery['status'] });
    else onChange({ ...value, order: kind as 'asc' | 'desc' });
  };

  const categoryOptions = useMemo(
    () => [
      { value: 'date', label: '날짜순' },
      { value: 'name', label: `가나다순 (${titleLabel})` },
      { value: 'org', label: '조직명순' },
      ...(hasStatus ? [{ value: 'status', label: '상태순' }] : []),
    ],
    [hasStatus, titleLabel],
  );

  const kindOptions = useMemo(() => {
    if (category === 'date') {
      return [
        { value: 'desc', label: '최근순' },
        { value: 'asc', label: '오래된순' },
      ];
    }
    if (category === 'name' || category === 'org') {
      return [
        { value: 'asc', label: 'A→Z' },
        { value: 'desc', label: 'Z→A' },
      ];
    }
    return [
      { value: 'completed', label: '완료' },
      { value: 'in_progress', label: '진행중' },
      { value: 'failed', label: '실패' },
    ];
  }, [category]);

  const kindValue = category === 'status' ? (value.status ?? 'completed') : value.order;

  return (
    <div className="flex w-full flex-wrap items-center justify-between gap-3">
      {/* 왼쪽 — 정렬(2단 캐스케이딩) + 조직 상태 필터 */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold text-[#8B95A1]">정렬</span>
        <Select
          value={category}
          onChange={(v) => onCategory(v as Category)}
          options={categoryOptions}
          aria-label="정렬 기준"
          className="w-44"
        />
        <Select
          value={kindValue}
          onChange={onKind}
          options={kindOptions}
          aria-label="정렬 방향"
          className="w-28"
        />
      </div>

      {/* 오른쪽 — 검색(필드 + 입력) */}
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-[#8B95A1]">검색</span>
        <Select
          value={value.searchField}
          onChange={(v) => onChange({ ...value, searchField: v as 'title' | 'org_name' })}
          options={[
            { value: 'title', label: titleLabel },
            { value: 'org_name', label: '조직명' },
          ]}
          aria-label="검색 필드"
          className="w-28"
        />
        <div className="relative">
          <svg
            width="12"
            height="12"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#B0B8C1]"
          >
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            value={value.search}
            onChange={(e) => onChange({ ...value, search: e.target.value })}
            placeholder={`${value.searchField === 'org_name' ? '조직명' : titleLabel} 검색`}
            className="w-52 rounded-xl border border-line bg-transparent pl-7 pr-3 py-2.5 text-sm text-ink placeholder-[#B0B8C1] focus:border-primary outline-none"
          />
        </div>
      </div>
    </div>
  );
}

// 내역 실행자 표기 — ADMIN이 실행했으면 '관리자', 그 외엔 이름(없으면 —).
export function executorLabel(row: {
  created_by_role?: string | null;
  created_by_name?: string | null;
}): string {
  if (row.created_by_role === 'ADMIN') return '관리자';
  return row.created_by_name ?? '—';
}

// 조직 상태(활성/비활성) 필터 — 헤더의 AdminOrgPicker 옆에 배치(정렬 영역과 분리).
export function OrgStatusFilter({
  value,
  onChange,
}: {
  value?: 'ACTIVE' | 'INACTIVE';
  onChange: (v: 'ACTIVE' | 'INACTIVE' | undefined) => void;
}) {
  return (
    <label className="flex items-center gap-2 text-sm text-ink-secondary">
      <span className="font-medium">상태</span>
      <Select
        value={value ?? ''}
        onChange={(v) => onChange((v || undefined) as 'ACTIVE' | 'INACTIVE' | undefined)}
        options={[
          { value: '', label: '전체 조직' },
          { value: 'ACTIVE', label: '활성 조직' },
          { value: 'INACTIVE', label: '비활성 조직' },
        ]}
        aria-label="조직 상태 필터"
        className="min-w-[130px]"
      />
    </label>
  );
}

// 조직 상태 표시 점 — ACTIVE=초록, INACTIVE=빨강, 그 외=회색.
export function OrgStatusDot({ status }: { status?: string | null }) {
  const active = status === 'ACTIVE';
  const inactive = status === 'INACTIVE';
  const color = active ? 'bg-emerald-500' : inactive ? 'bg-red-500' : 'bg-[#B0B8C1]';
  const label = active ? '활성 조직' : inactive ? '비활성 조직' : '알 수 없음';
  return (
    <span className="inline-flex items-center" title={label}>
      <span className={`inline-block h-2.5 w-2.5 rounded-full ${color}`} aria-hidden="true" />
      <span className="sr-only">{label}</span>
    </span>
  );
}

// 쿼리 → URLSearchParams 조각(공용). limit/offset은 훅이 붙인다.
export function historyQueryString(q: HistoryQuery): string {
  const p = new URLSearchParams();
  if (q.sort !== 'created_at') p.set('sort', q.sort);
  if (q.order !== 'desc') p.set('order', q.order);
  if (q.status) p.set('status', q.status);
  if (q.orgStatus) p.set('org_status', q.orgStatus);
  if (q.search.trim()) {
    p.set('search', q.search.trim());
    p.set('search_field', q.searchField);
  }
  return p.toString();
}
