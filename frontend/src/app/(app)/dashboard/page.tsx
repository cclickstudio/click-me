'use client';

// 역할별(USER/COMPANY/ADMIN) 대시보드 — 한 페이지에서 역할로 분기.
// ADMIN: 시스템·조직 운영 지표(성과 KPI·재시도 알림 없음). USER/COMPANY: 성과 KPI·주목할 것·크레딧(COMPANY는 예산 관점 강화).

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  Users,
  Sparkles,
  BarChart3,
  MousePointerClick,
  ShoppingCart,
  ArrowRight,
  Send,
  MessageSquare,
  Wallet,
  Activity,
  Building2,
} from 'lucide-react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts';
import { useAuth } from '@/components/AuthProvider';
import { authedFetch, api } from '@/lib/api';
import { formatKST } from '@/lib/datetime';
import ModeBadge from '@/components/ModeBadge';
import { Card } from '@/components/ui/card';
import { Section } from '@/components/ui/section';
import { StatCard } from '@/components/ui/stat-card';
import { EmptyState } from '@/components/ui/empty-state';
import { Skeleton } from '@/components/ui/skeleton';
import { useChartColors } from '@/components/ui/chart-theme';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

// ────────────────── Types ──────────────────

type DashboardSummary = {
  sims_total: number;
  sims_this_week: number;
  sims_prev_week: number;
  gens_total: number;
  gens_this_week: number;
  gens_prev_week: number;
  avg_purchase_intent: number | null;
  avg_click_intent_rate: number | null;
  weekly_trend: { label: string; simulations: number; generations: number }[];
};

type RecentSimulation = {
  id: string;
  ad_id: string;
  ad_title: string | null;
  persona_count: number;
  avg_intent: number | null;
  status: string;
  created_at: string;
};

type RecentGeneration = {
  id: string;
  status: string;
  product_name: string | null;
  mode: string;
  format: string;
  created_at: string;
};

type UserRow = {
  id: string;
  login_id: string;
  name: string;
  role: string;
  status: string;
  created_at: string;
  organization_name: string | null;
};

type OrgRow = { id: string; name: string; status: string; created_at: string };


// ────────────────── 상수 ──────────────────

const featureCards = [
  {
    title: '광고 시뮬레이션',
    desc: 'OCEAN 모델 기반 AI 가상 소비자 20명에게 광고를 테스트하고 구매의향 분포를 예측합니다.',
    href: '/simulation',
    label: '시뮬레이션 시작',
    Icon: Users,
  },
  {
    title: '광고 제너레이터',
    desc: '시뮬레이션 결과를 기반으로 최적화된 광고 카피와 소재를 AI가 자동으로 생성합니다.',
    href: '/generator',
    label: '광고 생성하기',
    Icon: Sparkles,
  },
  {
    title: '광고 매니지먼트',
    desc: '집행한 광고의 실제 성과를 시뮬레이션 예측치와 비교하고 캠페인을 관리합니다.',
    href: '/manage',
    label: '성과 확인하기',
    Icon: BarChart3,
  },
];

// COMPANY 전용 관리 바로가기 — 조직 관리자 관점(팀·프로젝트·예산).
const companyQuickLinks = [
  { label: '프로젝트 관리', href: '/company/projects', Icon: BarChart3 },
  { label: '팀 관리', href: '/company/teams', Icon: Users },
  { label: '크레딧 관리', href: '/company/credits', Icon: Wallet },
];

// ADMIN 전용 관리 바로가기 — 시스템 운영 관점.
const adminQuickLinks = [
  { label: '조직 관리', href: '/admin/companies', Icon: Building2 },
  { label: '회원 관리', href: '/admin/manage-user', Icon: Users },
  { label: '생성 내역', href: '/admin/generations', Icon: Sparkles },
];

const quickPrompts = [
  '이 광고의 예상 CTR을 분석해줘',
  '20대 여성 타겟 광고 전략을 추천해줘',
  '경쟁사 광고와 비교 분석해줘',
  '광고 카피 개선 방법을 알려줘',
];

const statusLabel: Record<string, { text: string; color: string }> = {
  completed: { text: '완료', color: 'text-success bg-success-subtle' },
  running: { text: '진행 중', color: 'text-info bg-info-subtle' },
  pending: { text: '대기', color: 'text-warning bg-warning-subtle' },
  failed: { text: '실패', color: 'text-danger bg-danger-subtle' },
};

const roleBadge: Record<string, string> = {
  ADMIN: 'text-danger bg-danger-subtle',
  COMPANY: 'text-primary bg-primary-subtle',
  USER: 'text-ink-secondary bg-surface-1',
};

// ────────────────── Utils ──────────────────

function formatDate(iso: string) {
  return formatKST(iso);
}

function shortId(id: string) {
  return id.slice(0, 8);
}

// 이번 주 vs 지난 주 증감률(%) — 지난 주 0이면 이번 주 유무로 100/0.
function deltaPct(cur: number, prev: number): number {
  if (prev === 0) return cur > 0 ? 100 : 0;
  return Math.round(((cur - prev) / prev) * 100);
}

// ────────────────── Main ──────────────────

export default function DashboardPage() {
  const { user } = useAuth();
  const router = useRouter();
  const chart = useChartColors();
  const role = user?.role;
  const isAdmin = role === 'ADMIN';
  const isCompany = role === 'COMPANY';

  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [recentSims, setRecentSims] = useState<RecentSimulation[]>([]);
  const [recentGens, setRecentGens] = useState<RecentGeneration[]>([]);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [orgs, setOrgs] = useState<OrgRow[]>([]);
  const [credit, setCredit] = useState<number | null>(null);
  const [loaded, setLoaded] = useState(false);

  const [input, setInput] = useState('');

  useEffect(() => {
    Promise.all([
      authedFetch(`${API_BASE}/api/dashboard/summary`).then((r) => r.json()).catch(() => null),
      authedFetch(`${API_BASE}/api/dashboard/recent-simulations?limit=5`).then((r) => r.json()).catch(() => []),
      authedFetch(`${API_BASE}/api/dashboard/recent-generations?limit=6`).then((r) => r.json()).catch(() => []),
    ]).then(([sum, sims, gens]) => {
      if (sum) setSummary(sum);
      if (Array.isArray(sims)) setRecentSims(sims);
      if (Array.isArray(gens)) setRecentGens(gens);
      setLoaded(true);
    });
  }, []);

  // ADMIN 전용 — 전체 사용자·조직(운영 KPI·최근 가입).
  useEffect(() => {
    if (!isAdmin) return;
    Promise.all([
      authedFetch(`${API_BASE}/api/admin/users?limit=200`).then((r) => r.json()).catch(() => []),
      authedFetch(`${API_BASE}/api/admin/organizations?limit=200`).then((r) => r.json()).catch(() => []),
    ]).then(([us, og]) => {
      if (Array.isArray(us)) setUsers(us);
      if (Array.isArray(og)) setOrgs(og);
    });
  }, [isAdmin]);

  // 크레딧 — ADMIN(슈퍼유저)은 미표시. USER 읽기 전용, COMPANY 충전 진입.
  useEffect(() => {
    if (isAdmin) return;
    api.billing.balance().then((res) => setCredit(res.balance_krw)).catch(() => setCredit(null));
  }, [isAdmin]);

  // CLIO 런처 — 입력/프롬프트를 /chat으로 실어 보냄. 프로젝트 선택 → 세션 → 딥에이전트 대화(시뮬·시안·리포트·전략).
  const launchChat = (text?: string) => {
    const content = (text ?? input).trim();
    if (!content) return;
    try {
      sessionStorage.setItem('clio:draft', content);
    } catch {
      /* sessionStorage 불가 환경 — 초안 없이 /chat 진입 */
    }
    router.push('/chat');
  };

  // 역할별 인사·주요 CTA
  const greeting = isAdmin
    ? '전체 시스템·조직·사용 현황을 한눈에 확인하세요.'
    : isCompany
      ? '팀의 광고 성과와 크레딧 사용을 관리하세요.'
      : '광고를 집행 전에 검증하고 성과를 예측하세요.';
  const cta = isAdmin
    ? { label: '회원 관리', href: '/admin/manage-user' }
    : isCompany
      ? { label: '프로젝트 관리', href: '/company/projects' }
      : { label: '새 시뮬레이션', href: '/simulation' };

  // 활동 피드 — 최근 시뮬/생성을 시간순 병합.
  const activity = [
    ...recentSims.map((s) => ({
      kind: 'sim' as const,
      id: s.id,
      title: s.ad_title || '제목 없음',
      status: s.status,
      created_at: s.created_at,
      href: `/simulation/${s.id}`,
    })),
    ...recentGens.map((g) => ({
      kind: 'gen' as const,
      id: g.id,
      title: g.product_name || '제목 없음',
      status: g.status,
      created_at: g.created_at,
      href: `/generations/${g.id}`,
    })),
  ]
    .sort((a, b) => (a.created_at < b.created_at ? 1 : -1))
    .slice(0, 6);

  const clickRate =
    summary?.avg_click_intent_rate != null
      ? `${(summary.avg_click_intent_rate * 100).toFixed(1)}`
      : '—';
  const isEmpty = loaded && (summary?.sims_total ?? 0) === 0 && (summary?.gens_total ?? 0) === 0;

  // "지금 주목할 것" — 실패한 생성·진행 중 시뮬(개인/조직 실무 액션). ADMIN 제외.
  const failedGens = recentGens.filter((g) => g.status.toLowerCase() === 'failed');
  const runningSims = recentSims.filter((s) => ['running', 'queued', 'pending'].includes(s.status.toLowerCase()));
  const attention = [
    ...failedGens.map((g) => ({
      key: `gf-${g.id}`,
      tone: 'danger' as const,
      label: '생성 실패',
      title: g.product_name || '광고 생성',
      desc: '재시도가 필요합니다',
      href: `/generations/${g.id}`,
    })),
    ...runningSims.map((s) => ({
      key: `sr-${s.id}`,
      tone: 'info' as const,
      label: '진행 중',
      title: s.ad_title || '시뮬레이션',
      desc: '결과 생성 중입니다',
      href: `/simulation/${s.id}`,
    })),
  ].slice(0, 4);

  // ADMIN 최근 가입 — 사용자 최신순.
  const recentSignups = [...users]
    .sort((a, b) => (a.created_at < b.created_at ? 1 : -1))
    .slice(0, 6);

  // 주간 활동 추이 차트 — 역할 공통.
  const weeklyChart = (
    <Card className="lg:col-span-2 p-5">
      <Section
        size="sm"
        title="주간 활동 추이"
        description={isAdmin ? '최근 8주 전체 시뮬레이션·광고 생성 건수' : '최근 8주 시뮬레이션·광고 생성 건수'}
      />
      <div className="h-64 mt-4">
        {!loaded ? (
          <Skeleton className="h-full w-full rounded-lg" />
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={summary?.weekly_trend ?? []} barGap={4}>
              <CartesianGrid strokeDasharray="3 3" stroke={chart.border} vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 11, fill: chart['text-tertiary'] }} tickLine={false} axisLine={{ stroke: chart.border }} />
              <YAxis tick={{ fontSize: 11, fill: chart['text-tertiary'] }} tickLine={false} axisLine={false} width={28} allowDecimals={false} />
              <Tooltip
                cursor={{ fill: chart.border, opacity: 0.2 }}
                contentStyle={{
                  background: chart['surface-2'],
                  border: `1px solid ${chart.border}`,
                  borderRadius: 12,
                  fontSize: 12,
                }}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} iconType="circle" />
              <Bar name="시뮬레이션" dataKey="simulations" fill={chart.primary} radius={[4, 4, 0, 0]} maxBarSize={22} />
              <Bar name="광고 생성" dataKey="generations" fill={chart.point} radius={[4, 4, 0, 0]} maxBarSize={22} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </Card>
  );

  // 최근 광고 생성 테이블 — ADMIN은 ID 열 표시.
  const recentGensTable = (
    <Card className="overflow-hidden p-0">
      <div className="flex items-center justify-between px-5 py-4 border-b border-line">
        <p className="text-sm font-semibold text-ink">최근 광고 생성</p>
        <Link href={isAdmin ? '/admin/generations' : isCompany ? '/company/generations' : '/simulations'} className="text-xs text-primary hover:underline font-medium">전체 보기 →</Link>
      </div>
      {recentGens.length === 0 ? (
        <div className="py-12 text-center text-xs text-ink-muted">아직 생성 내역이 없습니다</div>
      ) : (
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-line">
              {isAdmin && <th className="text-left px-5 py-2.5 text-ink-tertiary font-medium">ID</th>}
              <th className="text-left px-5 py-2.5 text-ink-tertiary font-medium">상품명</th>
              <th className="text-left px-3 py-2.5 text-ink-tertiary font-medium">상태</th>
              <th className="text-left px-3 py-2.5 text-ink-tertiary font-medium">일시</th>
            </tr>
          </thead>
          <tbody>
            {recentGens.map((g) => {
              const s = statusLabel[g.status] ?? { text: g.status, color: 'text-ink-tertiary bg-surface-1' };
              return (
                <tr
                  key={g.id}
                  onClick={() => router.push(`/generations/${g.id}`)}
                  className="border-b border-line/60 last:border-0 hover:bg-accent cursor-pointer transition-colors"
                >
                  {isAdmin && <td className="px-5 py-3 font-mono text-ink-secondary">{shortId(g.id)}</td>}
                  <td className="px-5 py-3 text-ink-secondary whitespace-nowrap">
                    <div className="flex items-center gap-1.5 max-w-[180px]">
                      <span className="shrink-0"><ModeBadge mode={g.mode} format={g.format} /></span>
                      <span className="truncate min-w-0">{g.product_name ?? '—'}</span>
                    </div>
                  </td>
                  <td className="px-3 py-3">
                    <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-medium ${s.color}`}>{s.text}</span>
                  </td>
                  <td className="px-3 py-3 text-ink-muted">{formatDate(g.created_at)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </Card>
  );

  return (
    <div className="p-6 sm:p-8 max-w-6xl mx-auto space-y-8">
      {/* ── 헤더 ── */}
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div>
          <h1 className="text-h2">안녕하세요, {user?.name ?? '사용자'}님</h1>
          <p className="text-sm text-ink-secondary mt-1">{greeting}</p>
        </div>
        <Link
          href={cta.href}
          className="inline-flex items-center justify-center gap-1.5 px-4 py-2.5 bg-primary text-primary-foreground text-sm font-medium rounded-lg hover:bg-primary-hover transition-colors shrink-0"
        >
          {cta.label}
          <ArrowRight size={16} strokeWidth={2.2} />
        </Link>
      </div>

      {/* ── KPI 스트립 (역할별) ── */}
      {!loaded ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-[124px] rounded-xl" />
          ))}
        </div>
      ) : isAdmin ? (
        /* ADMIN — 운영 규모 지표(성과 KPI 대신 계정·조직·누적) */
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard label="전체 사용자" value={users.length} unit="명" icon={<Users />} tone="primary" hint="가입 계정" />
          <StatCard label="전체 조직" value={orgs.length} unit="개" icon={<Building2 />} tone="primary" hint="등록 기업" />
          <StatCard label="전체 시뮬레이션" value={summary?.sims_total ?? 0} unit="건" icon={<BarChart3 />} tone="primary" hint="누적 실행" />
          <StatCard label="전체 광고 생성" value={summary?.gens_total ?? 0} unit="건" icon={<Sparkles />} tone="point" hint="누적 생성" />
        </div>
      ) : (
        /* USER/COMPANY — 성과 지표(클릭 의향률·구매 의향 포함) */
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            label="이번 주 시뮬레이션"
            value={summary?.sims_this_week ?? 0}
            unit="건"
            delta={summary ? deltaPct(summary.sims_this_week, summary.sims_prev_week) : undefined}
            deltaSuffix="%"
            hint="지난주 대비"
            icon={<Users />}
            tone="primary"
          />
          <StatCard
            label="이번 주 광고 생성"
            value={summary?.gens_this_week ?? 0}
            unit="건"
            delta={summary ? deltaPct(summary.gens_this_week, summary.gens_prev_week) : undefined}
            deltaSuffix="%"
            hint="지난주 대비"
            icon={<Sparkles />}
            tone="point"
          />
          <StatCard
            label="평균 클릭 의향률"
            value={clickRate}
            unit="%"
            hint={isCompany ? '조직 시뮬레이션 기준' : '내 시뮬레이션 기준'}
            icon={<MousePointerClick />}
            tone="primary"
          />
          <StatCard
            label="평균 구매 의향"
            value={summary?.avg_purchase_intent != null ? summary.avg_purchase_intent : '—'}
            unit="/ 5"
            hint="1~5점 척도"
            icon={<ShoppingCart />}
            tone="primary"
          />
        </div>
      )}

      {isAdmin ? (
        /* ══════════ ADMIN 대시보드 — 시스템 운영 ══════════ */
        <>
          {/* 주간 추이 + 최근 가입 */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
            {weeklyChart}
            <Card className="p-5">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-semibold text-ink">최근 가입</span>
                <Link href="/admin/manage-user" className="text-xs text-primary hover:underline font-medium">전체 보기 →</Link>
              </div>
              {!loaded ? (
                <div className="space-y-2">
                  {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-11 rounded-lg" />)}
                </div>
              ) : recentSignups.length === 0 ? (
                <p className="text-xs text-ink-tertiary py-4 text-center">가입 내역이 없습니다</p>
              ) : (
                <ul className="space-y-1">
                  {recentSignups.map((u) => (
                    <li key={u.id} className="flex items-center gap-2.5 rounded-lg px-2 py-2 hover:bg-accent transition-colors">
                      <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary-subtle text-primary text-[11px] font-semibold">
                        {u.name.slice(0, 1)}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block text-xs font-medium text-ink truncate">{u.name}</span>
                        <span className="block text-[11px] text-ink-tertiary truncate">
                          {u.organization_name ?? '미소속'} · {formatKST(u.created_at)}
                        </span>
                      </span>
                      <span className={`shrink-0 px-1.5 py-0.5 rounded text-[9px] font-medium ${roleBadge[u.role] ?? 'text-ink-tertiary bg-surface-1'}`}>
                        {u.role}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>

          {/* 최근 광고 생성(전역) */}
          {recentGensTable}

          {/* 관리 바로가기 */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {adminQuickLinks.map(({ label, href, Icon }) => (
              <Link key={href} href={href}>
                <Card className="p-5 flex items-center gap-3 hover:shadow-md hover:border-primary/30 hover:-translate-y-0.5 transition-all group">
                  <span className="flex size-10 items-center justify-center rounded-xl bg-primary-subtle text-primary group-hover:bg-primary group-hover:text-primary-foreground transition-colors">
                    <Icon size={20} strokeWidth={1.8} />
                  </span>
                  <span className="flex-1 text-sm font-semibold text-ink">{label}</span>
                  <ArrowRight size={16} className="text-ink-tertiary group-hover:text-primary transition-colors" />
                </Card>
              </Link>
            ))}
          </div>
        </>
      ) : isEmpty ? (
        <EmptyState
          icon={<Users />}
          title="아직 데이터가 없습니다"
          description="첫 시뮬레이션을 실행하면 여기에 성과 요약이 표시됩니다."
          action={
            <Link
              href="/simulation"
              className="inline-flex items-center gap-1.5 px-4 py-2 bg-primary text-primary-foreground text-sm font-medium rounded-lg hover:bg-primary-hover transition-colors"
            >
              시뮬레이션 시작 <ArrowRight size={15} strokeWidth={2.2} />
            </Link>
          }
        />
      ) : (
        /* ══════════ USER / COMPANY 대시보드 — 성과·크레딧 ══════════ */
        <>
          {/* 지금 주목할 것 (주의 필요 항목) */}
          {attention.length > 0 && (
            <div>
              <p className="mb-2 text-sm font-semibold text-ink">지금 주목할 것</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {attention.map((a) => (
                  <Link
                    key={a.key}
                    href={a.href}
                    className={`flex items-center gap-3 rounded-xl border p-3.5 transition-colors ${
                      a.tone === 'danger'
                        ? 'border-danger-border bg-danger-subtle hover:bg-danger-subtle/70'
                        : 'border-info-border bg-info-subtle hover:bg-info-subtle/70'
                    }`}
                  >
                    <span className={`shrink-0 rounded-md px-1.5 py-0.5 text-[10px] font-semibold ${a.tone === 'danger' ? 'bg-danger text-danger-foreground' : 'bg-info text-info-foreground'}`}>
                      {a.label}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-xs font-medium text-ink truncate">{a.title}</span>
                      <span className="block text-[11px] text-ink-secondary">{a.desc}</span>
                    </span>
                    <ArrowRight size={14} className={a.tone === 'danger' ? 'text-danger' : 'text-info'} />
                  </Link>
                ))}
              </div>
            </div>
          )}

          {/* 주간 추이 + 크레딧/활동 */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
            {weeklyChart}

            <div className="space-y-5">
              {/* 크레딧 — USER 읽기전용 / COMPANY 충전·예산 관점 */}
              <Card className="p-5">
                <div className="flex items-center gap-2 text-ink-secondary">
                  <Wallet size={16} />
                  <span className="text-sm font-medium">남은 공유 크레딧</span>
                </div>
                <p className="mt-3 text-2xl font-bold text-ink tracking-tight">
                  {credit === null ? '—' : `${credit.toLocaleString()}원`}
                </p>
                <p className="mt-1 text-xs text-ink-tertiary">조직 공유 예산 한도</p>
                {isCompany ? (
                  <div className="mt-4 flex items-center gap-2">
                    <Link
                      href="/payment"
                      className="inline-flex flex-1 items-center justify-center gap-1.5 px-3 py-2 bg-primary text-primary-foreground text-sm font-medium rounded-lg hover:bg-primary-hover transition-colors"
                    >
                      크레딧 충전
                    </Link>
                    <Link
                      href="/company/credits"
                      className="inline-flex items-center justify-center gap-1 px-3 py-2 border border-line text-ink-secondary text-sm font-medium rounded-lg hover:bg-accent transition-colors"
                    >
                      사용 추이
                    </Link>
                  </div>
                ) : (
                  <p className="mt-4 text-xs text-ink-muted">충전은 조직 관리자(COMPANY)가 진행합니다.</p>
                )}
              </Card>

              {/* 활동 피드 */}
              <Card className="p-5">
                <div className="flex items-center gap-2 text-ink-secondary mb-3">
                  <Activity size={16} />
                  <span className="text-sm font-medium">최근 활동</span>
                </div>
                {activity.length === 0 ? (
                  <p className="text-xs text-ink-tertiary py-4 text-center">활동 내역이 없습니다</p>
                ) : (
                  <ul className="space-y-1">
                    {activity.map((a) => (
                      <li key={`${a.kind}-${a.id}`}>
                        <Link
                          href={a.href}
                          className="flex items-center gap-2.5 rounded-lg px-2 py-2 hover:bg-accent transition-colors group"
                        >
                          <span
                            className={`flex size-7 shrink-0 items-center justify-center rounded-lg ${
                              a.kind === 'sim' ? 'bg-primary-subtle text-primary' : 'bg-point-subtle text-point'
                            }`}
                          >
                            {a.kind === 'sim' ? <Users size={14} /> : <Sparkles size={14} />}
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="block text-xs font-medium text-ink truncate group-hover:text-primary transition-colors">
                              {a.title}
                            </span>
                            <span className="block text-[11px] text-ink-tertiary">
                              {a.kind === 'sim' ? '시뮬레이션' : '광고 생성'} · {formatDate(a.created_at)}
                            </span>
                          </span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            </div>
          </div>

          {/* COMPANY 전용 — 조직 관리 바로가기(팀·프로젝트·예산) */}
          {isCompany && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              {companyQuickLinks.map(({ label, href, Icon }) => (
                <Link key={href} href={href}>
                  <Card className="p-5 flex items-center gap-3 hover:shadow-md hover:border-primary/30 hover:-translate-y-0.5 transition-all group">
                    <span className="flex size-10 items-center justify-center rounded-xl bg-primary-subtle text-primary group-hover:bg-primary group-hover:text-primary-foreground transition-colors">
                      <Icon size={20} strokeWidth={1.8} />
                    </span>
                    <span className="flex-1 text-sm font-semibold text-ink">{label}</span>
                    <ArrowRight size={16} className="text-ink-tertiary group-hover:text-primary transition-colors" />
                  </Card>
                </Link>
              ))}
            </div>
          )}

          {/* 3기능 요약 — COMPANY는 시뮬레이션·제너레이터 실행이 차단(AppLayout COMPANY_BLOCKED)돼 있어 매니지먼트만 노출 */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {featureCards.filter((card) => !isCompany || card.href === '/manage').map((card) => {
              const Icon = card.Icon;
              return (
                <Card
                  key={card.href}
                  className="p-5 hover:shadow-md hover:border-primary/30 hover:-translate-y-0.5 transition-all group"
                >
                  <div className="w-9 h-9 flex items-center justify-center rounded-xl bg-primary-subtle text-primary mb-3 group-hover:bg-primary group-hover:text-primary-foreground transition-colors">
                    <Icon size={20} strokeWidth={1.8} />
                  </div>
                  <h3 className="text-sm font-semibold text-ink mb-1">{card.title}</h3>
                  <p className="text-xs text-ink-tertiary leading-relaxed mb-4">{card.desc}</p>
                  <Link href={card.href} className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:gap-1.5 transition-all">
                    {card.label} <ArrowRight size={13} strokeWidth={2.2} />
                  </Link>
                </Card>
              );
            })}
          </div>

          {/* 최근 내역 2열 */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {/* 최근 시뮬레이션 */}
            <Card className="overflow-hidden p-0">
              <div className="flex items-center justify-between px-5 py-4 border-b border-line">
                <p className="text-sm font-semibold text-ink">최근 시뮬레이션</p>
                <Link href="/simulations" className="text-xs text-primary hover:underline font-medium">전체 보기 →</Link>
              </div>
              {recentSims.length === 0 ? (
                <div className="py-12 text-center text-xs text-ink-muted">아직 시뮬레이션 내역이 없습니다</div>
              ) : (
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-line">
                      <th className="text-left px-5 py-2.5 text-ink-tertiary font-medium">광고</th>
                      <th className="text-left px-3 py-2.5 text-ink-tertiary font-medium">페르소나</th>
                      <th className="text-left px-3 py-2.5 text-ink-tertiary font-medium">평균 의향</th>
                      <th className="text-left px-3 py-2.5 text-ink-tertiary font-medium">일시</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentSims.map((s) => (
                      <tr
                        key={s.id}
                        onClick={() => router.push(`/simulation/${s.id}`)}
                        className="border-b border-line/60 last:border-0 hover:bg-accent cursor-pointer transition-colors"
                      >
                        <td className="px-5 py-3 text-ink-secondary max-w-[140px] truncate">{s.ad_title ?? '—'}</td>
                        <td className="px-3 py-3 text-ink-secondary">{s.persona_count}명</td>
                        <td className="px-3 py-3 text-ink-secondary">{s.avg_intent != null ? s.avg_intent.toFixed(2) : '—'}</td>
                        <td className="px-3 py-3 text-ink-muted">{formatDate(s.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Card>

            {/* 최근 제너레이터 */}
            {recentGensTable}
          </div>
        </>
      )}

      {/* ── CLIO 어시스턴트 런처 (ADMIN·COMPANY 제외) — /chat은 COMPANY_BLOCKED라 COMPANY는 진입 즉시 튕긴다 ── */}
      {!isAdmin && !isCompany && (
        <Card className="overflow-hidden p-0">
          <div className="flex items-center justify-between px-6 py-4 border-b border-line">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 flex items-center justify-center rounded-xl bg-primary-subtle text-primary">
                <MessageSquare size={15} />
              </div>
              <div>
                <p className="text-sm font-semibold text-ink">CLIO</p>
                <p className="text-xs text-ink-tertiary">광고 전략 AI 어드바이저</p>
              </div>
            </div>
            <Link href="/chat" className="text-xs text-primary hover:underline font-medium">전체 화면으로 →</Link>
          </div>

          <div className="px-6 py-5">
            <p className="text-xs text-ink-tertiary mb-3">
              무엇이든 물어보세요 — 프로젝트를 고르면 시뮬레이션·시안 생성·리포트·전략까지 이어집니다.
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mb-4">
              {quickPrompts.map((prompt) => (
                <button
                  key={prompt}
                  onClick={() => launchChat(prompt)}
                  className="p-2.5 text-left text-xs text-ink-secondary bg-surface-1 border border-line rounded-xl hover:border-primary hover:text-primary hover:bg-primary-subtle transition-all"
                >
                  {prompt}
                </button>
              ))}
            </div>
            <div className="flex items-end gap-2">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); launchChat(); } }}
                placeholder="메시지를 입력하고 Enter — CLIO 채팅으로 이동합니다"
                rows={1}
                className="flex-1 px-3 py-2.5 rounded-xl border border-line text-sm text-ink placeholder:text-ink-muted focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/10 transition-colors resize-none bg-surface-2"
                style={{ maxHeight: '80px' }}
              />
              <button
                onClick={() => launchChat()}
                disabled={!input.trim()}
                className="p-2.5 bg-primary text-primary-foreground rounded-xl hover:bg-primary-hover disabled:opacity-30 disabled:cursor-not-allowed transition-all shrink-0"
              >
                <Send size={15} />
              </button>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
