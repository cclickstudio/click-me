export default function Page() {
  return (
    <>
      <header className="h-14 bg-white border-b border-[#E5E8EB] px-6 flex items-center justify-between shrink-0">
        <h1 className="text-sm font-semibold text-[#191F28]">채팅 기록</h1>
        <div className="w-8 h-8 rounded-full bg-[#EBF3FF] flex items-center justify-center text-xs font-medium text-[#3182F6]">
          A
        </div>
      </header>

      <main className="flex-1 p-6">
        <div className="bg-white border border-[#E5E8EB] rounded-2xl overflow-hidden">
          <div className="px-6 py-4 border-b border-[#E5E8EB] flex items-center justify-between">
            <h2 className="text-sm font-semibold text-[#191F28]">전체 채팅 기록</h2>
            <div className="w-48 h-8 bg-[#F2F4F6] rounded-lg" />
          </div>

          <div className="grid grid-cols-4 px-6 py-3 bg-[#F9FAFB] border-b border-[#E5E8EB]">
            {['사용자', '마지막 메시지', '메시지 수', '일시'].map((col) => (
              <span key={col} className="text-xs font-medium text-[#8B95A1]">{col}</span>
            ))}
          </div>

          <div className="divide-y divide-[#F2F4F6]">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="grid grid-cols-4 px-6 py-4 items-center">
                <div className="flex items-center gap-3">
                  <div className="w-7 h-7 rounded-full bg-[#F2F4F6]" />
                  <div className="h-3 w-16 bg-[#F2F4F6] rounded" />
                </div>
                <div className="h-3 w-40 bg-[#F9FAFB] rounded" />
                <div className="h-3 w-8 bg-[#F9FAFB] rounded" />
                <div className="h-3 w-24 bg-[#F9FAFB] rounded" />
              </div>
            ))}
          </div>
        </div>
      </main>
    </>
  );
}
