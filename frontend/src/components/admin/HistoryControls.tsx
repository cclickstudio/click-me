// 내역(시뮬·제너·채팅) 정렬·검색 컨트롤 — width 100%, 왼쪽 정렬(2단 캐스케이딩) / 오른쪽 검색.
'use client';

import { useMemo } from 'react';

// 백엔드 목록 계약과 1:1 대응하는 쿼리 모델.
export type HistoryQuery = {
  sort: 'created_at' | 'title' | 'org_name';
  order: 'asc' | 'desc';
  status?: 'completed' | 'in_progress' | 'failed'; // 상태순=필터(그 상태만 보기)
  searchField: 'title' | 'org_name';
  search: string;
};

export const DEFAULT_HISTORY_QUERY: HistoryQuery = {
  sort: 'created_at',
  order: 'desc',
  status: undefined,
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

const selectCls =
  'rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] bg-transparent px-2.5 py-1.5 text-sm text-[#191F28] dark:text-[#F2F4F6] focus:border-[#3182F6] outline-none';

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
    if (category === 'date') onChange({ ...value, order: kind as 'asc' | 'desc' });
    else if (category === 'name' || category === 'org')
      onChange({ ...value, order: kind as 'asc' | 'desc' });
    else onChange({ ...value, status: kind as HistoryQuery['status'] });
  };

  const kindOptions = useMemo(() => {
    if (category === 'date') {
      return [
        { v: 'desc', label: '최근순' },
        { v: 'asc', label: '오래된순' },
      ];
    }
    if (category === 'name' || category === 'org') {
      return [
        { v: 'asc', label: 'A→Z' },
        { v: 'desc', label: 'Z→A' },
      ];
    }
    return [
      { v: 'completed', label: '완료' },
      { v: 'in_progress', label: '진행중' },
      { v: 'failed', label: '실패' },
    ];
  }, [category]);

  const kindValue = category === 'status' ? (value.status ?? 'completed') : value.order;

  return (
    <div className="flex w-full flex-wrap items-center justify-between gap-3">
      {/* 왼쪽 — 정렬(2단 캐스케이딩) */}
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-[#8B95A1]">정렬</span>
        <select
          value={category}
          onChange={(e) => onCategory(e.target.value as Category)}
          className={selectCls}
        >
          <option value="date">날짜순</option>
          <option value="name">가나다순 ({titleLabel})</option>
          <option value="org">조직명순</option>
          {hasStatus && <option value="status">상태순</option>}
        </select>
        <select value={kindValue} onChange={(e) => onKind(e.target.value)} className={selectCls}>
          {kindOptions.map((o) => (
            <option key={o.v} value={o.v}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      {/* 오른쪽 — 검색(필드 + 입력) */}
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-[#8B95A1]">검색</span>
        <select
          value={value.searchField}
          onChange={(e) =>
            onChange({ ...value, searchField: e.target.value as 'title' | 'org_name' })
          }
          className={selectCls}
        >
          <option value="title">{titleLabel}</option>
          <option value="org_name">조직명</option>
        </select>
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
            className="w-52 rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] bg-transparent pl-7 pr-3 py-1.5 text-sm text-[#191F28] dark:text-[#F2F4F6] placeholder-[#B0B8C1] focus:border-[#3182F6] outline-none"
          />
        </div>
      </div>
    </div>
  );
}

// 쿼리 → URLSearchParams 조각(공용). limit/offset은 훅이 붙인다.
export function historyQueryString(q: HistoryQuery): string {
  const p = new URLSearchParams();
  if (q.sort !== 'created_at') p.set('sort', q.sort);
  if (q.order !== 'desc') p.set('order', q.order);
  if (q.status) p.set('status', q.status);
  if (q.search.trim()) {
    p.set('search', q.search.trim());
    p.set('search_field', q.searchField);
  }
  return p.toString();
}
