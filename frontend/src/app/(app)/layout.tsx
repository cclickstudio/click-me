// 앱 셸(사이드바+좌측 패널) Route Group 레이아웃 — AppLayout을 한 번만 마운트해 라우트 이동 간 패널을 persist.
import AppLayout from '@/components/AppLayout';

export default function AppGroupLayout({ children }: { children: React.ReactNode }) {
  return <AppLayout>{children}</AppLayout>;
}
