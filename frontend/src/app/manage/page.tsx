import AppLayout from '@/components/AppLayout';

const statCards = [
  { label: '전체 광고', value: '-' },
  { label: '진행 중', value: '-' },
  { label: '평균 CTR', value: '-' },
  { label: '총 시뮬레이션', value: '-' },
];

export default function Page() {
  return (
    <AppLayout>
      <div className="max-w-screen-xl mx-auto px-6 py-8">
        {/* Page header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-[#191F28]">광고 매니지먼트</h1>
            <p className="text-sm text-[#8B95A1] mt-1">
              광고 캠페인을 관리하고 성과를 추적합니다
            </p>
          </div>
          <button className="px-4 py-2 bg-[#3182F6] text-white text-sm font-medium rounded-lg hover:bg-[#1B6EEB] transition-colors opacity-40 cursor-not-allowed">
            + 새 광고 등록
          </button>
        </div>

        {/* Stat cards */}
        <div className="grid grid-cols-4 gap-4 mb-8">
          {statCards.map((s) => (
            <div key={s.label} className="bg-white border border-[#E5E8EB] rounded-2xl p-5">
              <p className="text-xs text-[#8B95A1] mb-1">{s.label}</p>
              <p className="text-2xl font-bold text-[#191F28]">{s.value}</p>
            </div>
          ))}
        </div>

        {/* Table area */}
        <div className="bg-white border border-[#E5E8EB] rounded-2xl overflow-hidden">
          <div className="px-6 py-4 border-b border-[#E5E8EB] flex items-center justify-between">
            <h2 className="text-sm font-semibold text-[#191F28]">광고 목록</h2>
            <div className="flex items-center gap-2">
              <div className="w-48 h-8 bg-[#F2F4F6] rounded-lg" />
              <div className="w-20 h-8 bg-[#F2F4F6] rounded-lg" />
            </div>
          </div>

          {/* Table header */}
          <div className="grid grid-cols-6 px-6 py-3 bg-[#F9FAFB] border-b border-[#E5E8EB]">
            {['광고명', '유형', '상태', '예상 CTR', '시뮬레이션', '등록일'].map((col) => (
              <span key={col} className="text-xs font-medium text-[#8B95A1]">
                {col}
              </span>
            ))}
          </div>

          {/* Empty state */}
          <div className="px-6 py-20 flex flex-col items-center justify-center">
            <div className="w-12 h-12 flex items-center justify-center rounded-2xl bg-[#F2F4F6] text-[#B0B8C1] mb-4">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <path d="M3 9h18" />
                <path d="M9 21V9" />
              </svg>
            </div>
            <p className="text-sm font-medium text-[#191F28] mb-1">등록된 광고가 없습니다</p>
            <p className="text-xs text-[#8B95A1]">새 광고를 등록하고 시뮬레이션을 시작하세요</p>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
