import AppLayout from '@/components/AppLayout';

const adTypes = [
  {
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="18" height="18" rx="2" />
        <circle cx="8.5" cy="8.5" r="1.5" />
        <polyline points="21 15 16 10 5 21" />
      </svg>
    ),
    label: '이미지 광고',
    desc: 'GPT Image 2',
    tag: '7.8 예정',
  },
  {
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" />
        <line x1="16" y1="13" x2="8" y2="13" />
        <line x1="16" y1="17" x2="8" y2="17" />
        <polyline points="10 9 9 9 8 9" />
      </svg>
    ),
    label: '텍스트 광고',
    desc: 'Gemini Flash 3.0',
    tag: '7.8 예정',
  },
  {
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <polygon points="23 7 16 12 23 17 23 7" />
        <rect x="1" y="5" width="15" height="14" rx="2" />
      </svg>
    ),
    label: '영상 광고',
    desc: 'Gemini Omni',
    tag: '7.8 예정',
  },
];

export default function Page() {
  return (
    <AppLayout>
      <div className="max-w-screen-xl mx-auto px-6 py-8">
        {/* Page header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">광고 제너레이터</h1>
          <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mt-1">
            시뮬레이션 결과를 기반으로 최적화된 광고 소재를 AI가 생성합니다
          </p>
        </div>

        {/* Ad type selector */}
        <div className="grid grid-cols-3 gap-4 mb-8">
          {adTypes.map((type) => (
            <div
              key={type.label}
              className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-5 opacity-60 cursor-not-allowed transition-colors"
            >
              <div className="flex items-start justify-between mb-3">
                <div className="w-9 h-9 flex items-center justify-center rounded-xl bg-[#F2F4F6] dark:bg-[#252D3D] text-[#8B95A1] dark:text-[#6B7280]">
                  {type.icon}
                </div>
                <span className="text-xs text-[#B0B8C1] dark:text-[#4B5563] bg-[#F2F4F6] dark:bg-[#252D3D] px-2 py-1 rounded-full">
                  {type.tag}
                </span>
              </div>
              <h3 className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-0.5">{type.label}</h3>
              <p className="text-xs text-[#8B95A1] dark:text-[#6B7280]">{type.desc}</p>
            </div>
          ))}
        </div>

        {/* Main area */}
        <div className="grid grid-cols-5 gap-5">
          {/* Input panel */}
          <div className="col-span-2 bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-6 transition-colors">
            <h2 className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-1">생성 설정</h2>
            <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mb-5">광고 생성 조건을 입력하세요</p>
            <div className="min-h-64 flex items-center justify-center border-2 border-dashed border-[#E5E8EB] dark:border-[#2D3748] rounded-xl">
              <p className="text-xs text-[#B0B8C1] dark:text-[#4B5563]">준비 중</p>
            </div>
          </div>

          {/* Result panel */}
          <div className="col-span-3 bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-6 transition-colors">
            <h2 className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-1">생성 결과</h2>
            <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mb-5">생성된 광고 소재가 여기에 표시됩니다</p>
            <div className="min-h-64 flex items-center justify-center border-2 border-dashed border-[#E5E8EB] dark:border-[#2D3748] rounded-xl">
              <p className="text-xs text-[#B0B8C1] dark:text-[#4B5563]">준비 중</p>
            </div>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
