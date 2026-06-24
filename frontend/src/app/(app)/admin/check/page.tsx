const usageCards = [
  { label: '이번 달 API 호출', value: '-', sub: 'OpenAI + Anthropic' },
  { label: '총 시뮬레이션', value: '-', sub: '이번 달' },
  { label: '활성 사용자', value: '-', sub: 'DAU 기준' },
  { label: '예상 비용', value: '-', sub: 'USD' },
];

export default function Page() {
  return (
    <>
      <header className="h-14 bg-white dark:bg-[#1C2333] border-b border-[#E5E8EB] dark:border-[#2D3748] px-6 flex items-center justify-between shrink-0 transition-colors">
        <h1 className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">사용량</h1>
        <div className="w-8 h-8 rounded-full bg-[#EBF3FF] dark:bg-[#1E3A5F] flex items-center justify-center text-xs font-medium text-[#3182F6]">
          A
        </div>
      </header>

      <main className="flex-1 p-6">
        <div className="grid grid-cols-4 gap-4 mb-6">
          {usageCards.map((s) => (
            <div key={s.label} className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-5 transition-colors">
              <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mb-1">{s.label}</p>
              <p className="text-3xl font-bold text-[#191F28] dark:text-[#F2F4F6] mb-1">{s.value}</p>
              <p className="text-xs text-[#B0B8C1] dark:text-[#4B5563]">{s.sub}</p>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-2 gap-5">
          <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-6 transition-colors">
            <h2 className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-1">API 호출 추이</h2>
            <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mb-5">일별 API 사용량</p>
            <div className="min-h-48 flex items-center justify-center border-2 border-dashed border-[#E5E8EB] dark:border-[#2D3748] rounded-xl">
              <p className="text-xs text-[#B0B8C1] dark:text-[#4B5563]">준비 중</p>
            </div>
          </div>

          <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-6 transition-colors">
            <h2 className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-1">시뮬레이션 추이</h2>
            <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mb-5">일별 시뮬레이션 실행 수</p>
            <div className="min-h-48 flex items-center justify-center border-2 border-dashed border-[#E5E8EB] dark:border-[#2D3748] rounded-xl">
              <p className="text-xs text-[#B0B8C1] dark:text-[#4B5563]">준비 중</p>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}
