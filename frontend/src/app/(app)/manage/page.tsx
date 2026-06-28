// 광고 매니지먼트는 카테고리(사이드바 토글) — 자체 페이지 없음. 캠페인 대시보드로 보낸다.
import { redirect } from 'next/navigation';

export default function Page() {
  redirect('/manage/campaigns');
}
