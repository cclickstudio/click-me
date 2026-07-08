'use client';

// 랜딩(공개 진입) — Apple식 다이나믹 진입(순차 페이드·스크롤 리빌·패럴랙스) + 토큰 기반 리스킨.

import { useEffect, useRef } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { motion, useScroll, useTransform, type Variants } from 'framer-motion';
import { Users, Sparkles, BarChart3, Sun, Moon, ArrowRight, Check } from 'lucide-react';
import { useAuth } from '../components/AuthProvider';
import { useTheme } from '../components/ThemeProvider';

const features = [
  {
    icon: Users,
    title: '광고 시뮬레이션',
    desc: 'OCEAN 심리 모델 기반 AI 가상 소비자 20명에게 광고를 테스트하고 구매의향 분포를 사전에 예측합니다.',
    href: '/simulation',
    label: '시뮬레이션 시작',
  },
  {
    icon: Sparkles,
    title: '광고 제너레이터',
    desc: '시뮬레이션 분석 결과를 기반으로 최적화된 광고 카피와 소재를 AI가 자동으로 생성합니다.',
    href: '/generator',
    label: '광고 생성하기',
  },
  {
    icon: BarChart3,
    title: '광고 매니지먼트',
    desc: '집행한 광고의 실제 성과를 시뮬레이션 예측치와 비교하고 캠페인을 한곳에서 관리합니다.',
    href: '/manage',
    label: '성과 확인하기',
  },
];

const steps = [
  { step: '01', title: '광고 업로드', desc: '이미지 또는 텍스트 광고 소재를 업로드합니다.' },
  { step: '02', title: 'AI 시뮬레이션', desc: '가상 소비자 20명이 광고를 분석하고 반응합니다.' },
  { step: '03', title: '성과 예측', desc: '클릭 의향률·구매의향 분포를 신뢰구간과 함께 확인합니다.' },
];

// 사실 기반 소셜 프루프 — 과장 수치 대신 실제 데이터 근거를 제시.
const proofs = [
  { value: '81만', label: 'OCEAN 페르소나 데이터' },
  { value: '5요인', label: '심리 기반 조건부 샘플링' },
  { value: '분포·CI', label: '스칼라 아닌 신뢰구간 결과' },
];

// framer-motion 공용 variants — 순차 등장(stagger)과 스크롤 리빌에 재사용.
const fadeUp: Variants = {
  hidden: { opacity: 0, y: 24 },
  show: { opacity: 1, y: 0, transition: { duration: 0.6, ease: [0.22, 1, 0.36, 1] } },
};
const stagger: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.12 } },
};

export default function Page() {
  const { theme, toggle } = useTheme();
  const { user, loading } = useAuth();
  const router = useRouter();
  const heroRef = useRef<HTMLDivElement>(null);

  // 히어로 스크롤 패럴랙스 — 배경 blob이 스크롤에 따라 천천히 이동.
  // layoutEffect:false — early return(로딩/로그인 스피너) 시 heroRef가 미부착 상태라
  // useLayoutEffect 기반 측정이 "target ref not hydrated" 경고를 낸다. useEffect로 지연해 회피.
  const { scrollYProgress } = useScroll({
    target: heroRef,
    offset: ['start start', 'end start'],
    layoutEffect: false,
  });
  const blobY = useTransform(scrollYProgress, [0, 1], [0, 120]);
  const blobOpacity = useTransform(scrollYProgress, [0, 1], [1, 0.2]);

  // 로그인 상태면 랜딩 진입 차단 — 로그아웃 전엔 대시보드로 이동
  useEffect(() => {
    if (!loading && user) router.replace('/dashboard');
  }, [loading, user, router]);

  if (loading || user) {
    return (
      <div className="min-h-screen bg-surface-0 flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-surface-0 transition-colors">
      {/* Header */}
      <header className="border-b border-line sticky top-0 z-50 bg-surface-0/80 backdrop-blur-md transition-colors">
        <div className="max-w-screen-xl mx-auto px-6 h-14 flex items-center justify-between">
          <span className="text-primary font-bold text-lg tracking-tight">ClickMe</span>
          <div className="flex items-center gap-3">
            <button
              onClick={toggle}
              className="p-2 rounded-lg text-ink-tertiary hover:bg-accent hover:text-ink transition-colors"
              aria-label="다크 모드 전환"
            >
              {theme === 'dark' ? <Sun size={16} strokeWidth={2} /> : <Moon size={16} strokeWidth={2} />}
            </button>
            <Link
              href="/sign-in"
              className="text-sm text-ink-secondary hover:text-ink font-medium transition-colors"
            >
              로그인
            </Link>
            <Link
              href="/dashboard"
              className="px-4 py-2 bg-primary text-primary-foreground text-sm font-medium rounded-lg hover:bg-primary-hover transition-colors"
            >
              무료로 시작하기
            </Link>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section ref={heroRef} className="relative overflow-hidden">
        {/* 패럴랙스 배경 blob (장식) */}
        <motion.div
          aria-hidden
          style={{ y: blobY, opacity: blobOpacity }}
          className="pointer-events-none absolute left-1/2 top-[-10%] -translate-x-1/2 h-[520px] w-[820px] rounded-full bg-primary/10 blur-3xl"
        />
        <motion.div
          variants={stagger}
          initial="hidden"
          animate="show"
          className="relative max-w-screen-xl mx-auto px-6 pt-28 pb-24 text-center"
        >
          <motion.div variants={fadeUp} className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-primary-subtle text-primary text-xs font-medium mb-8">
            <span className="w-1.5 h-1.5 rounded-full bg-primary" />
            AI 기반 광고 성과 예측 플랫폼
          </motion.div>
          <motion.h1 variants={fadeUp} className="text-4xl sm:text-5xl md:text-6xl font-bold text-ink leading-[1.1] mb-6 tracking-tight">
            광고 성과,<br />런칭 전에 검증하세요
          </motion.h1>
          <motion.p variants={fadeUp} className="text-base sm:text-lg text-ink-tertiary mb-10 max-w-lg mx-auto leading-relaxed">
            AI로 만든 가상 소비자에게 먼저 테스트하여<br />
            클릭 의향과 구매의향을 집행 전에 예측합니다.
          </motion.p>
          <motion.div variants={fadeUp} className="flex flex-col sm:flex-row items-center justify-center gap-3">
            <Link
              href="/dashboard"
              className="inline-flex items-center gap-1.5 px-6 py-3 bg-primary text-primary-foreground font-medium rounded-xl hover:bg-primary-hover transition-colors shadow-sm"
            >
              무료로 시작하기
              <ArrowRight size={16} strokeWidth={2.2} />
            </Link>
            <Link
              href="/chat"
              className="px-6 py-3 border border-line text-ink-secondary font-medium rounded-xl hover:bg-surface-1 transition-colors"
            >
              AI에게 물어보기
            </Link>
          </motion.div>

          {/* 소셜 프루프 */}
          <motion.div variants={fadeUp} className="mt-16 grid grid-cols-3 gap-4 max-w-2xl mx-auto">
            {proofs.map((p) => (
              <div key={p.label} className="rounded-2xl border border-line bg-card px-4 py-5">
                <p className="text-2xl font-bold text-ink tracking-tight">{p.value}</p>
                <p className="mt-1 text-xs text-ink-tertiary leading-snug">{p.label}</p>
              </div>
            ))}
          </motion.div>
        </motion.div>
      </section>

      {/* How it works */}
      <section className="bg-surface-1 py-20 transition-colors">
        <div className="max-w-screen-xl mx-auto px-6">
          <motion.div
            variants={fadeUp} initial="hidden" whileInView="show" viewport={{ once: true, amount: 0.4 }}
            className="text-center mb-12"
          >
            <h2 className="text-2xl sm:text-3xl font-bold text-ink mb-2 tracking-tight">3단계로 시작하세요</h2>
            <p className="text-sm text-ink-tertiary">복잡한 설정 없이 바로 시작할 수 있습니다</p>
          </motion.div>
          <motion.div
            variants={stagger} initial="hidden" whileInView="show" viewport={{ once: true, amount: 0.3 }}
            className="grid grid-cols-1 sm:grid-cols-3 gap-8"
          >
            {steps.map((s) => (
              <motion.div key={s.step} variants={fadeUp} className="text-center">
                <div className="inline-flex items-center justify-center w-11 h-11 rounded-full bg-primary-subtle text-primary text-sm font-bold mb-4">
                  {s.step}
                </div>
                <h3 className="text-base font-semibold text-ink mb-2">{s.title}</h3>
                <p className="text-sm text-ink-tertiary leading-relaxed">{s.desc}</p>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* Features */}
      <section className="max-w-screen-xl mx-auto px-6 py-20">
        <motion.div
          variants={fadeUp} initial="hidden" whileInView="show" viewport={{ once: true, amount: 0.4 }}
          className="text-center mb-12"
        >
          <h2 className="text-2xl sm:text-3xl font-bold text-ink mb-2 tracking-tight">핵심 기능</h2>
          <p className="text-sm text-ink-tertiary">광고 기획부터 성과 관리까지 한 플랫폼에서</p>
        </motion.div>
        <motion.div
          variants={stagger} initial="hidden" whileInView="show" viewport={{ once: true, amount: 0.2 }}
          className="grid grid-cols-1 sm:grid-cols-3 gap-6"
        >
          {features.map((f) => {
            const Icon = f.icon;
            return (
              <motion.div
                key={f.title}
                variants={fadeUp}
                className="p-6 bg-card border border-line rounded-2xl hover:shadow-md hover:border-primary/30 hover:-translate-y-0.5 transition-all group"
              >
                <div className="w-11 h-11 flex items-center justify-center rounded-xl bg-primary-subtle text-primary mb-4 group-hover:bg-primary group-hover:text-primary-foreground transition-colors">
                  <Icon size={22} strokeWidth={1.7} />
                </div>
                <h3 className="text-base font-semibold text-ink mb-2">{f.title}</h3>
                <p className="text-sm text-ink-tertiary leading-relaxed mb-5">{f.desc}</p>
                <Link
                  href={f.href}
                  className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:gap-2 transition-all"
                >
                  {f.label}
                  <ArrowRight size={14} strokeWidth={2.2} />
                </Link>
              </motion.div>
            );
          })}
        </motion.div>
      </section>

      {/* CTA Banner */}
      <section className="px-6 pb-20">
        <motion.div
          variants={fadeUp} initial="hidden" whileInView="show" viewport={{ once: true, amount: 0.5 }}
          className="max-w-screen-xl mx-auto rounded-3xl bg-primary py-16 px-6 text-center relative overflow-hidden"
        >
          <div aria-hidden className="pointer-events-none absolute inset-0 bg-gradient-to-br from-white/10 to-transparent" />
          <div className="relative">
            <h2 className="text-2xl sm:text-3xl font-bold text-primary-foreground mb-3 tracking-tight">지금 바로 시작해보세요</h2>
            <p className="text-primary-foreground/80 text-sm mb-8">광고 예산을 낭비하기 전에 먼저 검증하세요</p>
            <Link
              href="/dashboard"
              className="inline-flex items-center gap-1.5 px-8 py-3 bg-white text-primary font-semibold rounded-xl hover:bg-white/90 transition-colors"
            >
              <Check size={16} strokeWidth={2.4} />
              무료로 시작하기
            </Link>
          </div>
        </motion.div>
      </section>

      {/* Footer */}
      <footer className="border-t border-line py-8 bg-surface-0 transition-colors">
        <div className="max-w-screen-xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-2">
          <span className="text-primary font-bold text-sm">ClickMe</span>
          <p className="text-xs text-ink-muted text-center sm:text-right">
            © 2026 ClickMe. AI 시뮬레이션 결과는 참고용이며 실제 성과와 차이가 있을 수 있습니다.
          </p>
        </div>
      </footer>
    </div>
  );
}
