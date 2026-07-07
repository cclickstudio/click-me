'use client';

// 리포트 다운로드 카드 — 채팅에서 만든 프로젝트 리포트를 PDF/HTML로 내려받는다(T13)
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export default function ReportWidget({
  projectId,
  period,
}: {
  projectId?: string;
  period?: string;
}) {
  const params = new URLSearchParams();
  if (projectId) params.set('project_id', projectId);
  params.set('period', period ?? 'month');
  const href = `${API_BASE}/api/chat/report?${params.toString()}`;

  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="mt-1 inline-flex items-center gap-2 px-4 py-2.5 rounded-xl border border-primary/30 bg-[#F5F9FF] dark:bg-[#16243C] text-primary text-sm font-semibold hover:bg-primary-subtle transition-colors"
    >
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
        <polyline points="7 10 12 15 17 10" />
        <line x1="12" y1="15" x2="12" y2="3" />
      </svg>
      리포트 다운로드
    </a>
  );
}
