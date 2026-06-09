export default function Page() {
  return (
    <>
      <header className="h-14 bg-white border-b border-[#E5E8EB] px-6 flex items-center justify-between shrink-0">
        <h1 className="text-sm font-semibold text-[#191F28]">고객 문의</h1>
        <div className="w-8 h-8 rounded-full bg-[#EBF3FF] flex items-center justify-center text-xs font-medium text-[#3182F6]">
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
                  ? 'bg-[#191F28] text-white'
                  : 'bg-white border border-[#E5E8EB] text-[#8B95A1] hover:text-[#191F28]'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>

        <div className="bg-white border border-[#E5E8EB] rounded-2xl overflow-hidden">
          <div className="grid grid-cols-5 px-6 py-3 bg-[#F9FAFB] border-b border-[#E5E8EB]">
            {['제목', '작성자', '카테고리', '상태', '접수일'].map((col) => (
              <span key={col} className="text-xs font-medium text-[#8B95A1]">{col}</span>
            ))}
          </div>

          <div className="px-6 py-16 flex flex-col items-center justify-center">
            <div className="w-10 h-10 rounded-2xl bg-[#F2F4F6] flex items-center justify-center mb-3">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#B0B8C1" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
            </div>
            <p className="text-sm text-[#B0B8C1]">접수된 문의가 없습니다</p>
          </div>
        </div>
      </main>
    </>
  );
}
