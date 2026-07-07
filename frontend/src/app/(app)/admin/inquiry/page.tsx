export default function Page() {
  return (
    <>
      <header className="h-14 bg-card border-b border-line px-6 flex items-center justify-between shrink-0 transition-colors">
        <h1 className="text-sm font-semibold text-ink">고객 문의</h1>
        <div className="w-8 h-8 rounded-full bg-primary-subtle flex items-center justify-center text-xs font-medium text-primary">
          A
        </div>
      </header>

      <main className="flex-1 p-6">
        <div className="flex items-center gap-3 mb-5">
          {['전체', '미해결', '해결됨'].map((tab, i) => (
            <button
              key={tab}
              className={`px-4 py-1.5 rounded-full text-sm font-medium transition-colors ${
                i === 0
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-card border border-line text-ink-tertiary hover:text-ink dark:hover:text-[#F2F4F6]'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>

        <div className="bg-card border border-line rounded-2xl overflow-hidden transition-colors">
          <div className="grid grid-cols-5 px-6 py-3 bg-surface-1 border-b border-line">
            {['제목', '작성자', '카테고리', '상태', '접수일'].map((col) => (
              <span key={col} className="text-xs font-medium text-ink-tertiary">{col}</span>
            ))}
          </div>

          <div className="px-6 py-16 flex flex-col items-center justify-center">
            <div className="w-10 h-10 rounded-2xl bg-surface-1 flex items-center justify-center mb-3">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#B0B8C1" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
            </div>
            <p className="text-sm text-ink-muted">접수된 문의가 없습니다</p>
          </div>
        </div>
      </main>
    </>
  );
}
