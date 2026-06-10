const statCards = [
  { label: '전체 사용자', value: '-', color: 'text-[#3182F6]' },
  { label: '월간 시뮬레이션', value: '-', color: 'text-[#10B981]' },
  { label: '미해결 문의', value: '-', color: 'text-[#F59E0B]' },
  { label: '이번 달 비용', value: '-', color: 'text-[#191F28] dark:text-[#F2F4F6]' },
];

export default function Page() {
  return (
    <>
      <header className="h-14 bg-white dark:bg-[#1C2333] border-b border-[#E5E8EB] dark:border-[#2D3748] px-6 flex items-center justify-between shrink-0 transition-colors">
        <h1 className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">관리자 대시보드</h1>
        <div className="w-8 h-8 rounded-full bg-[#EBF3FF] dark:bg-[#1E3A5F] flex items-center justify-center text-xs font-medium text-[#3182F6]">
          A
        </div>
      </header>

      <main className="flex-1 p-6">
        <div className="grid grid-cols-4 gap-4 mb-6">
          {statCards.map((s) => (
            <div key={s.label} className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-5 transition-colors">
              <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mb-2">{s.label}</p>
              <p className={`text-3xl font-bold ${s.color}`}>{s.value}</p>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-2 gap-5 mb-5">
          <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl overflow-hidden transition-colors">
            <div className="px-5 py-4 border-b border-[#E5E8EB] dark:border-[#2D3748] flex items-center justify-between">
              <h2 className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">최근 가입</h2>
              <a href="/admin/manage-user" className="text-xs text-[#3182F6] hover:underline">전체 보기</a>
            </div>
            <div className="divide-y divide-[#F2F4F6] dark:divide-[#1E2A3A]">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="px-5 py-3.5 flex items-center gap-3">
                  <div className="w-7 h-7 rounded-full bg-[#F2F4F6] dark:bg-[#252D3D]" />
                  <div className="flex-1">
                    <div className="h-3 w-24 bg-[#F2F4F6] dark:bg-[#252D3D] rounded mb-1.5" />
                    <div className="h-2.5 w-36 bg-[#F9FAFB] dark:bg-[#161B27] rounded" />
                  </div>
                  <div className="h-2.5 w-14 bg-[#F9FAFB] dark:bg-[#161B27] rounded" />
                </div>
              ))}
            </div>
          </div>

          <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl overflow-hidden transition-colors">
            <div className="px-5 py-4 border-b border-[#E5E8EB] dark:border-[#2D3748] flex items-center justify-between">
              <h2 className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">최근 시뮬레이션</h2>
              <span className="text-xs text-[#B0B8C1] dark:text-[#4B5563]">준비 중</span>
            </div>
            <div className="divide-y divide-[#F2F4F6] dark:divide-[#1E2A3A]">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="px-5 py-3.5 flex items-center gap-3">
                  <div className="flex-1">
                    <div className="h-3 w-32 bg-[#F2F4F6] dark:bg-[#252D3D] rounded mb-1.5" />
                    <div className="h-2.5 w-20 bg-[#F9FAFB] dark:bg-[#161B27] rounded" />
                  </div>
                  <div className="h-2.5 w-10 bg-[#F9FAFB] dark:bg-[#161B27] rounded" />
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl overflow-hidden transition-colors">
          <div className="px-5 py-4 border-b border-[#E5E8EB] dark:border-[#2D3748] flex items-center justify-between">
            <h2 className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">미해결 문의</h2>
            <a href="/admin/inquiry" className="text-xs text-[#3182F6] hover:underline">전체 보기</a>
          </div>
          <div className="px-5 py-12 flex flex-col items-center justify-center">
            <p className="text-sm text-[#B0B8C1] dark:text-[#4B5563]">미해결 문의가 없습니다</p>
          </div>
        </div>
      </main>
    </>
  );
}
