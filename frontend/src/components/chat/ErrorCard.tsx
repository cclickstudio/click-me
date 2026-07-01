'use client';

// 공통 에러 카드(X1) — 시뮬·생성·채팅의 에러를 동일한 카드 + 재시도로 통일.
// 원본 메시지를 사용자 친화 문구(키 없음/한도/네트워크/기타)로 분류해 보여준다.

type Props = {
  message?: string | null;
  onRetry?: () => void;
  retrying?: boolean;
  className?: string;
};

// 원본 에러 문자열 → 사용자 친화 카테고리 문구.
export function friendlyError(raw?: string | null): string {
  const m = (raw ?? '').toLowerCase();
  if (/한도|limit|quota|429|rate.?limit|exceed/.test(m))
    return '사용량 한도에 도달했어요. 잠시 후 다시 시도해주세요.';
  if (/api.?key|unauthor|401|403|인증|권한|verif/.test(m))
    return '인증·권한에 문제가 있어요. 관리자에게 문의하거나 잠시 후 다시 시도해주세요.';
  if (/network|fetch|연결|끊|timeout|시간 초과|econn|네트워크/.test(m))
    return '네트워크 연결이 불안정해요. 연결을 확인하고 다시 시도해주세요.';
  // 그 외엔 원본을 그대로(있으면), 없으면 일반 안내.
  return (raw && raw.trim()) || '문제가 발생했어요. 잠시 후 다시 시도해주세요.';
}

export default function ErrorCard({ message, onRetry, retrying, className }: Props) {
  return (
    <div
      className={`flex items-start gap-2.5 px-4 py-3 rounded-xl border bg-[#FEF2F2] dark:bg-[#3B0D0D] border-[#FECACA] dark:border-[#7F1D1D] ${className ?? ''}`}
    >
      <svg
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="mt-0.5 shrink-0 text-[#DC2626] dark:text-[#FCA5A5]"
      >
        <circle cx="12" cy="12" r="10" />
        <line x1="12" y1="8" x2="12" y2="12" />
        <line x1="12" y1="16" x2="12.01" y2="16" />
      </svg>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-[#DC2626] dark:text-[#FCA5A5] leading-snug">
          {friendlyError(message)}
        </p>
        {onRetry && (
          <button
            onClick={onRetry}
            disabled={retrying}
            className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-[#DC2626] dark:text-[#FCA5A5] hover:underline disabled:opacity-50"
          >
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className={retrying ? 'animate-spin' : ''}
            >
              <path d="M23 4v6h-6" />
              <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
            </svg>
            {retrying ? '다시 시도 중…' : '다시 시도'}
          </button>
        )}
      </div>
    </div>
  );
}
