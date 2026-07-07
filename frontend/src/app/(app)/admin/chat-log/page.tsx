export default function Page() {
  return (
    <>
      <header className="h-14 bg-card border-b border-line px-6 flex items-center justify-between shrink-0 transition-colors">
        <h1 className="text-sm font-semibold text-ink">채팅 기록</h1>
        <div className="w-8 h-8 rounded-full bg-primary-subtle flex items-center justify-center text-xs font-medium text-primary">
          A
        </div>
      </header>

      <main className="flex-1 p-6">
        <div className="bg-card border border-line rounded-2xl overflow-hidden transition-colors">
          <div className="px-6 py-4 border-b border-line flex items-center justify-between">
            <h2 className="text-sm font-semibold text-ink">전체 채팅 기록</h2>
            <div className="w-48 h-8 bg-surface-1 rounded-lg" />
          </div>

          <div className="grid grid-cols-4 px-6 py-3 bg-surface-1 border-b border-line">
            {['사용자', '마지막 메시지', '메시지 수', '일시'].map((col) => (
              <span key={col} className="text-xs font-medium text-ink-tertiary">{col}</span>
            ))}
          </div>

          <div className="divide-y divide-line">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="grid grid-cols-4 px-6 py-4 items-center">
                <div className="flex items-center gap-3">
                  <div className="w-7 h-7 rounded-full bg-surface-1" />
                  <div className="h-3 w-16 bg-surface-1 rounded" />
                </div>
                <div className="h-3 w-40 bg-surface-1 rounded" />
                <div className="h-3 w-8 bg-surface-1 rounded" />
                <div className="h-3 w-24 bg-surface-1 rounded" />
              </div>
            ))}
          </div>
        </div>
      </main>
    </>
  );
}
