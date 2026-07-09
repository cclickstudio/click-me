// 클라이언트 페이지네이션 — 이전/다음 + 현재 주변 페이지 번호. 무한스크롤과 별개.
'use client';

export function Pagination({
  page,
  totalPages,
  onChange,
}: {
  page: number;
  totalPages: number;
  onChange: (page: number) => void;
}) {
  if (totalPages <= 1) return null;

  // 현재 페이지 주변 최대 5개 번호만 노출(양끝에서 창을 밀어 5개 유지).
  const start = Math.max(1, Math.min(page - 2, totalPages - 4));
  const end = Math.min(totalPages, start + 4);
  const nums: number[] = [];
  for (let i = start; i <= end; i++) nums.push(i);

  const base =
    'min-w-8 h-8 px-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed';
  const idle = 'text-ink-secondary hover:bg-surface-1';

  return (
    <div className="flex items-center justify-center gap-1 pt-4">
      <button
        type="button"
        disabled={page === 1}
        onClick={() => onChange(page - 1)}
        className={`${base} ${idle}`}
        aria-label="이전 페이지"
      >
        이전
      </button>
      {nums.map((n) => (
        <button
          key={n}
          type="button"
          onClick={() => onChange(n)}
          aria-current={n === page ? 'page' : undefined}
          className={`${base} ${
            n === page ? 'bg-primary text-primary-foreground' : idle
          }`}
        >
          {n}
        </button>
      ))}
      <button
        type="button"
        disabled={page === totalPages}
        onClick={() => onChange(page + 1)}
        className={`${base} ${idle}`}
        aria-label="다음 페이지"
      >
        다음
      </button>
    </div>
  );
}

export default Pagination;
