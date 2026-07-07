const usageCards = [
  { label: '이번 달 API 호출', value: '-', sub: 'OpenAI + Anthropic' },
  { label: '총 시뮬레이션', value: '-', sub: '이번 달' },
  { label: '활성 사용자', value: '-', sub: 'DAU 기준' },
  { label: '예상 비용', value: '-', sub: 'USD' },
];

export default function Page() {
  return (
    <>
      <header className="h-14 bg-card border-b border-line px-6 flex items-center justify-between shrink-0 transition-colors">
        <h1 className="text-sm font-semibold text-ink">사용량</h1>
        <div className="w-8 h-8 rounded-full bg-primary-subtle flex items-center justify-center text-xs font-medium text-primary">
          A
        </div>
      </header>

      <main className="flex-1 p-6">
        <div className="grid grid-cols-4 gap-4 mb-6">
          {usageCards.map((s) => (
            <div key={s.label} className="bg-card border border-line rounded-2xl p-5 transition-colors">
              <p className="text-xs text-ink-tertiary mb-1">{s.label}</p>
              <p className="text-3xl font-bold text-ink mb-1">{s.value}</p>
              <p className="text-xs text-ink-muted">{s.sub}</p>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-2 gap-5">
          <div className="bg-card border border-line rounded-2xl p-6 transition-colors">
            <h2 className="text-sm font-semibold text-ink mb-1">API 호출 추이</h2>
            <p className="text-xs text-ink-tertiary mb-5">일별 API 사용량</p>
            <div className="min-h-48 flex items-center justify-center border-2 border-dashed border-line rounded-xl">
              <p className="text-xs text-ink-muted">준비 중</p>
            </div>
          </div>

          <div className="bg-card border border-line rounded-2xl p-6 transition-colors">
            <h2 className="text-sm font-semibold text-ink mb-1">시뮬레이션 추이</h2>
            <p className="text-xs text-ink-tertiary mb-5">일별 시뮬레이션 실행 수</p>
            <div className="min-h-48 flex items-center justify-center border-2 border-dashed border-line rounded-xl">
              <p className="text-xs text-ink-muted">준비 중</p>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}
