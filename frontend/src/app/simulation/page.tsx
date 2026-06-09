import AppLayout from '@/components/AppLayout';

function EmptyCard({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="bg-white border border-[#E5E8EB] rounded-2xl p-6 flex flex-col">
      <h2 className="text-sm font-semibold text-[#191F28] mb-1">{title}</h2>
      <p className="text-xs text-[#8B95A1] mb-5">{desc}</p>
      <div className="flex-1 min-h-48 flex items-center justify-center border-2 border-dashed border-[#E5E8EB] rounded-xl">
        <p className="text-xs text-[#B0B8C1]">준비 중</p>
      </div>
    </div>
  );
}

export default function Page() {
  return (
    <AppLayout>
      <div className="max-w-screen-xl mx-auto px-6 py-8">
        {/* Page header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-[#191F28]">광고 시뮬레이터</h1>
            <p className="text-sm text-[#8B95A1] mt-1">
              AI 가상 소비자 20명에게 광고를 테스트하고 성과를 예측합니다
            </p>
          </div>
          <button className="px-4 py-2 bg-[#3182F6] text-white text-sm font-medium rounded-lg hover:bg-[#1B6EEB] transition-colors opacity-40 cursor-not-allowed">
            시뮬레이션 시작
          </button>
        </div>

        {/* Top row */}
        <div className="grid grid-cols-3 gap-5 mb-5">
          <EmptyCard
            title="광고 입력"
            desc="이미지 또는 텍스트 광고를 업로드하세요"
          />
          <EmptyCard
            title="시뮬레이션 설정"
            desc="페르소나 수, 캠페인 목표를 설정하세요"
          />
          <EmptyCard
            title="결과 미리보기"
            desc="시뮬레이션 결과가 여기에 표시됩니다"
          />
        </div>

        {/* Bottom row */}
        <div className="grid grid-cols-2 gap-5">
          <EmptyCard
            title="구매의향 분포"
            desc="5단계 Likert 구매의향 분포 차트"
          />
          <EmptyCard
            title="KPI 요약"
            desc="CTR · CVR · Net Sentiment 예측값"
          />
        </div>
      </div>
    </AppLayout>
  );
}
