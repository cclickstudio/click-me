'use client';

import Link from 'next/link';
import { useTheme } from '../components/ThemeProvider';

function SunIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="5" />
      <line x1="12" y1="1" x2="12" y2="3" /><line x1="12" y1="21" x2="12" y2="23" />
      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" /><line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
      <line x1="1" y1="12" x2="3" y2="12" /><line x1="21" y1="12" x2="23" y2="12" />
      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" /><line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  );
}

const features = [
  {
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
        <circle cx="9" cy="7" r="4" />
        <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
        <path d="M16 3.13a4 4 0 0 1 0 7.75" />
      </svg>
    ),
    title: '광고 시뮬레이션',
    desc: 'OCEAN 심리 모델 기반 AI 가상 소비자 20명에게 광고를 테스트하고 구매의향 분포를 사전에 예측합니다.',
    href: '/simulation',
    label: '시뮬레이션 시작',
  },
  {
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
      </svg>
    ),
    title: '광고 제너레이터',
    desc: '시뮬레이션 분석 결과를 기반으로 최적화된 광고 카피와 소재를 AI가 자동으로 생성합니다.',
    href: '/generator',
    label: '광고 생성하기',
  },
  {
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <line x1="18" y1="20" x2="18" y2="10" />
        <line x1="12" y1="20" x2="12" y2="4" />
        <line x1="6" y1="20" x2="6" y2="14" />
      </svg>
    ),
    title: '광고 매니지먼트',
    desc: '집행한 광고의 실제 성과를 시뮬레이션 예측치와 비교하고 캠페인을 한곳에서 관리합니다.',
    href: '/manage',
    label: '성과 확인하기',
  },
];

const steps = [
  { step: '01', title: '광고 업로드', desc: '이미지 또는 텍스트 광고 소재를 업로드합니다.' },
  { step: '02', title: 'AI 시뮬레이션', desc: '가상 소비자 20명이 광고를 분석하고 반응합니다.' },
  { step: '03', title: '성과 예측', desc: 'CTR·CVR 예측값과 구매의향 분포를 확인합니다.' },
];

export default function Page() {
  const { theme, toggle } = useTheme();

  return (
    <div className="min-h-screen bg-white dark:bg-[#0F1117] transition-colors">
      {/* Header */}
      <header className="border-b border-[#E5E8EB] dark:border-[#2D3748] sticky top-0 z-50 bg-white/80 dark:bg-[#0F1117]/80 backdrop-blur-sm transition-colors">
        <div className="max-w-screen-xl mx-auto px-6 h-14 flex items-center justify-between">
          <span className="text-[#3182F6] font-bold text-lg">ClickMe</span>
          <div className="flex items-center gap-3">
            <button
              onClick={toggle}
              className="p-2 rounded-lg text-[#8B95A1] dark:text-[#6B7280] hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D] transition-colors"
              aria-label="다크 모드 전환"
            >
              {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
            </button>
            <Link
              href="/sign-in"
              className="text-sm text-[#4E5968] dark:text-[#9CA3AF] hover:text-[#191F28] dark:hover:text-[#F2F4F6] font-medium transition-colors"
            >
              로그인
            </Link>
            <Link
              href="/dashboard"
              className="px-4 py-2 bg-[#3182F6] text-white text-sm font-medium rounded-lg hover:bg-[#1B6EEB] transition-colors"
            >
              무료로 시작하기
            </Link>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="max-w-screen-xl mx-auto px-6 pt-28 pb-24 text-center">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#EBF3FF] dark:bg-[#1E3A5F] text-[#3182F6] text-xs font-medium mb-8">
          AI 기반 광고 성과 예측 플랫폼
        </div>
        <h1 className="text-5xl font-bold text-[#191F28] dark:text-[#F2F4F6] leading-tight mb-6 tracking-tight">
          광고 성과,<br />런칭 전에 검증하세요
        </h1>
        <p className="text-lg text-[#8B95A1] dark:text-[#6B7280] mb-10 max-w-md mx-auto leading-relaxed">
          AI로 만든 가상 소비자에게 먼저 테스트하여<br />
          CTR·CVR을 사전에 예측합니다
        </p>
        <div className="flex items-center justify-center gap-3">
          <Link
            href="/dashboard"
            className="px-6 py-3 bg-[#3182F6] text-white font-medium rounded-xl hover:bg-[#1B6EEB] transition-colors shadow-sm"
          >
            무료로 시작하기
          </Link>
          <Link
            href="/chat"
            className="px-6 py-3 border border-[#E5E8EB] dark:border-[#2D3748] text-[#4E5968] dark:text-[#9CA3AF] font-medium rounded-xl hover:bg-[#F9FAFB] dark:hover:bg-[#1C2333] transition-colors"
          >
            AI에게 물어보기
          </Link>
        </div>
      </section>

      {/* How it works */}
      <section className="bg-[#F9FAFB] dark:bg-[#1C2333] py-20 transition-colors">
        <div className="max-w-screen-xl mx-auto px-6">
          <div className="text-center mb-12">
            <h2 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6] mb-2">3단계로 시작하세요</h2>
            <p className="text-sm text-[#8B95A1] dark:text-[#6B7280]">복잡한 설정 없이 바로 시작할 수 있습니다</p>
          </div>
          <div className="grid grid-cols-3 gap-8">
            {steps.map((s) => (
              <div key={s.step} className="text-center">
                <div className="inline-flex items-center justify-center w-10 h-10 rounded-full bg-[#EBF3FF] dark:bg-[#1E3A5F] text-[#3182F6] text-sm font-bold mb-4">
                  {s.step}
                </div>
                <h3 className="text-base font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-2">{s.title}</h3>
                <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] leading-relaxed">{s.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="max-w-screen-xl mx-auto px-6 py-20">
        <div className="text-center mb-12">
          <h2 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6] mb-2">핵심 기능</h2>
          <p className="text-sm text-[#8B95A1] dark:text-[#6B7280]">광고 기획부터 성과 관리까지 한 플랫폼에서</p>
        </div>
        <div className="grid grid-cols-3 gap-6">
          {features.map((f) => (
            <div
              key={f.title}
              className="p-6 bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl hover:shadow-md hover:border-[#3182F6]/20 transition-all group"
            >
              <div className="w-10 h-10 flex items-center justify-center rounded-xl bg-[#EBF3FF] dark:bg-[#1E3A5F] text-[#3182F6] mb-4 group-hover:bg-[#3182F6] group-hover:text-white transition-colors">
                {f.icon}
              </div>
              <h3 className="text-base font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-2">{f.title}</h3>
              <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] leading-relaxed mb-5">{f.desc}</p>
              <Link
                href={f.href}
                className="text-sm font-medium text-[#3182F6] hover:underline"
              >
                {f.label} →
              </Link>
            </div>
          ))}
        </div>
      </section>

      {/* CTA Banner */}
      <section className="bg-[#3182F6] py-16 text-center">
        <h2 className="text-2xl font-bold text-white mb-3">지금 바로 시작해보세요</h2>
        <p className="text-[#93C5FD] text-sm mb-8">광고 예산을 낭비하기 전에 먼저 검증하세요</p>
        <Link
          href="/dashboard"
          className="inline-block px-8 py-3 bg-white text-[#3182F6] font-semibold rounded-xl hover:bg-[#F0F7FF] transition-colors"
        >
          무료로 시작하기
        </Link>
      </section>

      {/* Footer */}
      <footer className="border-t border-[#E5E8EB] dark:border-[#2D3748] py-8 bg-white dark:bg-[#0F1117] transition-colors">
        <div className="max-w-screen-xl mx-auto px-6 flex items-center justify-between">
          <span className="text-[#3182F6] font-bold text-sm">ClickMe</span>
          <p className="text-xs text-[#B0B8C1] dark:text-[#4B5563]">
            © 2026 ClickMe. AI 시뮬레이션 결과는 참고용이며 실제 성과와 차이가 있을 수 있습니다.
          </p>
        </div>
      </footer>
    </div>
  );
}
