'use client';

// 관리자 대시보드 — 시스템·조직·사용 지표 요약 + 최근 가입/생성. 크레딧 UI 미표시(ADMIN=슈퍼유저).

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  Users,
  Building2,
  BarChart3,
  Sparkles,
  ArrowRight,
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
import { authedFetch } from '@/lib/api';
import { formatKST } from '@/lib/datetime';
import ModeBadge from '@/components/ModeBadge';
import { Card } from '@/components/ui/card';
import { Section } from '@/components/ui/section';
import { StatCard } from '@/components/ui/stat-card';
import { Skeleton } from '@/components/ui/skeleton';
import { useChartColors } from '@/components/ui/chart-theme';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

type Summary = {
  sims_total: number;
  gens_total: number;
  avg_click_intent_rate: number | null;
  weekly_trend: { label: string; simulations: number; generations: number }[];
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
type RecentGeneration = {
  id: string;
  status: string;
  product_name: string | null;
  mode: string;
  format: string;
  created_at: string;
};

const roleBadge: Record<string, string> = {
  ADMIN: 'text-danger bg-danger-subtle',
  COMPANY: 'text-primary bg-primary-subtle',
  USER: 'text-ink-secondary bg-surface-1',
};
const statusLabel: Record<string, { text: string; color: string }> = {
  completed: { text: '완료', color: 'text-success bg-success-subtle' },
  running: { text: '진행 중', color: 'text-info bg-info-subtle' },
  pending: { text: '대기', color: 'text-warning bg-warning-subtle' },
  failed: { text: '실패', color: 'text-danger bg-danger-subtle' },
};

export default function AdminDashboardPage() {
  const router = useRouter();
  const chart = useChartColors();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [orgs, setOrgs] = useState<OrgRow[]>([]);
  const [recentGens, setRecentGens] = useState<RecentGeneration[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    Promise.all([
      authedFetch(`${API_BASE}/api/dashboard/summary`).then((r) => r.json()).catch(() => null),
      authedFetch(`${API_BASE}/api/admin/users?limit=200`).then((r) => r.json()).catch(() => []),
      authedFetch(`${API_BASE}/api/admin/organizations?limit=200`).then((r) => r.json()).catch(() => []),
      authedFetch(`${API_BASE}/api/dashboard/recent-generations?limit=6`).then((r) => r.json()).catch(() => []),
    ]).then(([sum, us, og, gens]) => {
      if (sum) setSummary(sum);
      if (Array.isArray(us)) setUsers(us);
      if (Array.isArray(og)) setOrgs(og);
      if (Array.isArray(gens)) setRecentGens(gens);
      setLoaded(true);
    });
  }, []);

  const recentSignups = [...users]
    .sort((a, b) => (a.created_at < b.created_at ? 1 : -1))
    .slice(0, 6);

  return (
    <div className="p-6 sm:p-8 max-w-6xl mx-auto space-y-8">
      {/* 헤더 */}
      <div>
        <h1 className="text-h2">관리자 대시보드</h1>
        <p className="text-sm text-ink-secondary mt-1">전체 시스템·조직·사용 현황을 한눈에 확인하세요.</p>
      </div>

      {/* KPI 스트립 — 크레딧/비용 미표시 */}
      {!loaded ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-[124px] rounded-xl" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard label="전체 사용자" value={users.length} unit="명" icon={<Users />} tone="primary" hint="가입 계정" />
          <StatCard label="전체 조직" value={orgs.length} unit="개" icon={<Building2 />} tone="primary" hint="등록 기업" />
          <StatCard label="전체 시뮬레이션" value={summary?.sims_total ?? 0} unit="건" icon={<BarChart3 />} tone="primary" hint="누적 실행" />
          <StatCard label="전체 광고 생성" value={summary?.gens_total ?? 0} unit="건" icon={<Sparkles />} tone="point" hint="누적 생성" />
        </div>
      )}

      {/* 주간 추이 + 최근 가입 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <Card className="lg:col-span-2 p-5">
          <Section size="sm" title="주간 활동 추이" description="최근 8주 전체 시뮬레이션·광고 생성 건수" />
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
                    contentStyle={{ background: chart['surface-2'], border: `1px solid ${chart.border}`, borderRadius: 12, fontSize: 12 }}
                  />
                  <Legend wrapperStyle={{ fontSize: 12 }} iconType="circle" />
                  <Bar name="시뮬레이션" dataKey="simulations" fill={chart.primary} radius={[4, 4, 0, 0]} maxBarSize={22} />
                  <Bar name="광고 생성" dataKey="generations" fill={chart.point} radius={[4, 4, 0, 0]} maxBarSize={22} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </Card>

        {/* 최근 가입 */}
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

      {/* 최근 광고 생성 (전역) */}
      <Card className="overflow-hidden p-0">
        <div className="flex items-center justify-between px-5 py-4 border-b border-line">
          <p className="text-sm font-semibold text-ink">최근 광고 생성</p>
          <Link href="/admin/generations" className="text-xs text-primary hover:underline font-medium">전체 보기 →</Link>
        </div>
        {!loaded ? (
          <div className="p-5 space-y-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-8 rounded" />)}</div>
        ) : recentGens.length === 0 ? (
          <div className="py-12 text-center text-xs text-ink-muted">아직 생성 내역이 없습니다</div>
        ) : (
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-line">
                <th className="text-left px-5 py-2.5 text-ink-tertiary font-medium">ID</th>
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
                    <td className="px-5 py-3 font-mono text-ink-secondary">{g.id.slice(0, 8)}</td>
                    <td className="px-5 py-3 text-ink-secondary whitespace-nowrap">
                      <div className="flex items-center gap-1.5 max-w-[200px]">
                        <span className="shrink-0"><ModeBadge mode={g.mode} format={g.format} /></span>
                        <span className="truncate min-w-0">{g.product_name ?? '—'}</span>
                      </div>
                    </td>
                    <td className="px-3 py-3">
                      <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-medium ${s.color}`}>{s.text}</span>
                    </td>
                    <td className="px-3 py-3 text-ink-muted">{formatKST(g.created_at)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Card>

      {/* 관리 바로가기 */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {[
          { label: '조직 관리', href: '/admin/companies', Icon: Building2 },
          { label: '회원 관리', href: '/admin/manage-user', Icon: Users },
          { label: '생성 내역', href: '/admin/generations', Icon: Sparkles },
        ].map(({ label, href, Icon }) => (
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
    </div>
  );
}
