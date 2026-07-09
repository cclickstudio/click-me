// 조직/회원 목록 정렬·role 필터 컨트롤 — 공용 Select 사용(다크 테마 일관).
'use client';

import Select from '@/components/ui/Select';

// 정렬 값은 `${sort}:${order}` 한 문자열로 인코딩(백엔드 sort/order 쿼리와 1:1 대응).
export type SortValue = string;

export const ORG_SORT_OPTIONS = [
  { value: 'created_at:desc', label: '최근순' },
  { value: 'created_at:asc', label: '오래된순' },
  { value: 'name:asc', label: '이름 A → Z' },
  { value: 'name:desc', label: '이름 Z → A' },
  { value: 'status:asc', label: '상태순' },
];

// 회원은 백엔드 기본값(역할순 ADMIN→USER)을 첫 옵션으로 노출 + 나머지는 조직과 동일.
export const USER_SORT_OPTIONS = [
  { value: 'role:desc', label: '<기본>' },
  ...ORG_SORT_OPTIONS,
];

// 회원 관리는 ADMIN/USER만 다룬다 — COMPANY는 조직 관리에서 조직째로 관리.
export const ROLE_FILTER_OPTIONS = [
  { value: '', label: '전체 역할' },
  { value: 'ADMIN', label: 'ADMIN' },
  { value: 'USER', label: 'USER' },
];

// 정렬 값(`sort:order`)을 백엔드 쿼리 파라미터로 분해.
export function sortToParams(v: SortValue): { sort: string; order: string } {
  const [sort, order] = v.split(':');
  return { sort: sort || 'created_at', order: order || 'desc' };
}

export function OrgUserControls({
  sort,
  onSort,
  sortOptions,
  role,
  onRole,
}: {
  sort: SortValue;
  onSort: (v: SortValue) => void;
  sortOptions: { value: string; label: string }[];
  role?: string; // 있으면 role 필터 Select 노출(회원 관리 전용)
  onRole?: (v: string) => void;
}) {
  return (
    <div className="flex w-full flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-[#8B95A1]">정렬</span>
        <Select
          value={sort}
          onChange={onSort}
          options={sortOptions}
          aria-label="정렬 기준"
          className="w-48"
        />
      </div>
      {onRole && (
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-[#8B95A1]">역할</span>
          <Select
            value={role ?? ''}
            onChange={onRole}
            options={ROLE_FILTER_OPTIONS}
            aria-label="역할 필터"
            className="w-40"
          />
        </div>
      )}
    </div>
  );
}
