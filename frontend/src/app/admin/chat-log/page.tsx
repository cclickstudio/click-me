export default function Page() {
  return (
    <>
      <header className="h-14 bg-white dark:bg-[#1C2333] border-b border-[#E5E8EB] dark:border-[#2D3748] px-6 flex items-center justify-between shrink-0 transition-colors">
        <h1 className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">채팅 기록</h1>
        <div className="w-8 h-8 rounded-full bg-[#EBF3FF] dark:bg-[#1E3A5F] flex items-center justify-center text-xs font-medium text-[#3182F6]">
          A
        </div>
      </header>

      <main className="flex-1 p-6">
        <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl overflow-hidden transition-colors">
          <div className="px-6 py-4 border-b border-[#E5E8EB] dark:border-[#2D3748] flex items-center justify-between">
            <h2 className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">전체 채팅 기록</h2>
            <div className="w-48 h-8 bg-[#F2F4F6] dark:bg-[#252D3D] rounded-lg" />
          </div>

          <div className="grid grid-cols-4 px-6 py-3 bg-[#F9FAFB] dark:bg-[#161B27] border-b border-[#E5E8EB] dark:border-[#2D3748]">
            {['사용자', '마지막 메시지', '메시지 수', '일시'].map((col) => (
              <span key={col} className="text-xs font-medium text-[#8B95A1] dark:text-[#6B7280]">{col}</span>
            ))}
          </div>

          <div className="divide-y divide-[#F2F4F6] dark:divide-[#1E2A3A]">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="grid grid-cols-4 px-6 py-4 items-center">
                <div className="flex items-center gap-3">
                  <div className="w-7 h-7 rounded-full bg-[#F2F4F6] dark:bg-[#252D3D]" />
                  <div className="h-3 w-16 bg-[#F2F4F6] dark:bg-[#252D3D] rounded" />
                </div>
                <div className="h-3 w-40 bg-[#F9FAFB] dark:bg-[#161B27] rounded" />
                <div className="h-3 w-8 bg-[#F9FAFB] dark:bg-[#161B27] rounded" />
                <div className="h-3 w-24 bg-[#F9FAFB] dark:bg-[#161B27] rounded" />
              </div>
            ))}
          </div>
        </div>
      </main>
    </>
  );
}
