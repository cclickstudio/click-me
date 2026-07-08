'use client';

// 크레딧 관리(COMPANY 전용) — 잔액(₩)·충전 진입(Toss 샌드박스)·기능별 사용 추이·크레딧 내역.

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Wallet, Plus, Users, Sparkles, ArrowRight, ArrowDownRight, ArrowUpRight } from 'lucide-react';
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
import { api, authedFetch } from '@/lib/api';
import { formatKST } from '@/lib/datetime';
import { Card } from '@/components/ui/card';
import { Section } from '@/components/ui/section';
import { StatCard } from '@/components/ui/stat-card';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import { useChartColors } from '@/components/ui/chart-theme';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

type Summary = {
  sims_total: number;
  sims_this_week: number;
  gens_total: number;
  gens_this_week: number;
  weekly_trend: { label: string; simulations: number; generations: number }[];
};
type Entry = {
  entry_id: string;
  delta_krw: number;
  balance_after_krw: number;
  reason: string;
  ref_id: string;
  created_at: string;
};

export default function CompanyCreditsPage() {
  const { user } = useAuth();
  const router = useRouter();
  const chart = useChartColors();
  const [balance, setBalance] = useState<number | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [loaded, setLoaded] = useState(false);

  // COMPANY 전용 — 다른 역할은 대시보드로.
  useEffect(() => {
    if (user && user.role !== 'COMPANY') router.replace('/dashboard');
  }, [user, router]);

  useEffect(() => {
    Promise.all([
      api.billing.balance().then((r) => r.balance_krw).catch(() => null),
      authedFetch(`${API_BASE}/api/dashboard/summary`).then((r) => r.json()).catch(() => null),
      api.billing.history().then((r) => r.entries).catch(() => []),
    ]).then(([bal, sum, hist]) => {
      setBalance(bal);
      if (sum) setSummary(sum);
      if (Array.isArray(hist)) setEntries(hist);
      setLoaded(true);
    });
  }, []);

  const reasonLabel = (reason: string) => {
    const r = reason.toLowerCase();
    if (r.includes('charge') || r.includes('충전') || r.includes('topup')) return '충전';
    if (r.includes('refund') || r.includes('cancel') || r.includes('취소')) return '취소·환불';
    return '사용';
  };

  return (
    <div className="p-6 sm:p-8 max-w-5xl mx-auto space-y-8">
      {/* 헤더 */}
      <div>
        <h1 className="text-h2">크레딧 관리</h1>
        <p className="text-sm text-ink-secondary mt-1">조직 공유 예산 한도를 충전하고 기능별 사용을 확인하세요.</p>
      </div>

      {/* 잔액 + 사용 요약 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* 잔액 카드 (강조) */}
        <Card className="lg:col-span-1 p-6 flex flex-col">
          <div className="flex items-center gap-2 text-ink-secondary">
            <Wallet size={18} />
            <span className="text-sm font-medium">보유 크레딧</span>
          </div>
          {!loaded ? (
            <Skeleton className="mt-4 h-9 w-32 rounded" />
          ) : (
            <p className="mt-4 text-3xl font-bold text-ink tracking-tight">
              {balance === null ? '—' : `${balance.toLocaleString()}원`}
            </p>
          )}
          <p className="mt-1 text-xs text-ink-tertiary">조직 공유 예산 한도 · 광고 집행 상한</p>
          <Link
            href="/payment"
            className="mt-5 inline-flex items-center justify-center gap-1.5 px-4 py-2.5 bg-primary text-primary-foreground text-sm font-medium rounded-lg hover:bg-primary-hover transition-colors"
          >
            <Plus size={16} strokeWidth={2.2} />
            크레딧 충전
          </Link>
          <p className="mt-2 text-[11px] text-ink-muted">TossPayments 샌드박스(테스트키) · 실 과금 없음</p>
        </Card>

        {/* 기능별 사용 요약 */}
        <div className="lg:col-span-2 grid grid-cols-2 gap-4">
          <StatCard
            label="이번 주 시뮬레이션"
            value={summary?.sims_this_week ?? 0}
            unit="건"
            hint={`누적 ${summary?.sims_total ?? 0}건`}
            icon={<Users />}
            tone="primary"
          />
          <StatCard
            label="이번 주 광고 생성"
            value={summary?.gens_this_week ?? 0}
            unit="건"
            hint={`누적 ${summary?.gens_total ?? 0}건`}
            icon={<Sparkles />}
            tone="point"
          />
          <Card className="col-span-2 p-5">
            <Section size="sm" title="기능별 사용 추이" description="최근 8주 시뮬레이션·광고 생성 사용 건수" />
            <div className="h-52 mt-4">
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
                    <Bar name="시뮬레이션" dataKey="simulations" fill={chart.primary} radius={[4, 4, 0, 0]} maxBarSize={20} />
                    <Bar name="광고 생성" dataKey="generations" fill={chart.point} radius={[4, 4, 0, 0]} maxBarSize={20} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
          </Card>
        </div>
      </div>

      {/* 크레딧 내역 */}
      <Card className="overflow-hidden p-0">
        <div className="flex items-center justify-between px-5 py-4 border-b border-line">
          <p className="text-sm font-semibold text-ink">크레딧 내역</p>
          <Link href="/payment" className="text-xs text-primary hover:underline font-medium">충전하기 →</Link>
        </div>
        {!loaded ? (
          <div className="p-5 space-y-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-9 rounded" />)}</div>
        ) : entries.length === 0 ? (
          <EmptyState
            className="border-0"
            icon={<Wallet />}
            title="크레딧 내역이 없습니다"
            description="첫 충전을 진행하면 여기에 충전·사용 내역이 표시됩니다."
            action={
              <Link href="/payment" className="inline-flex items-center gap-1.5 px-4 py-2 bg-primary text-primary-foreground text-sm font-medium rounded-lg hover:bg-primary-hover transition-colors">
                크레딧 충전 <ArrowRight size={15} strokeWidth={2.2} />
              </Link>
            }
          />
        ) : (
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-line">
                <th className="text-left px-5 py-2.5 text-ink-tertiary font-medium">구분</th>
                <th className="text-left px-3 py-2.5 text-ink-tertiary font-medium">금액</th>
                <th className="text-left px-3 py-2.5 text-ink-tertiary font-medium">잔액</th>
                <th className="text-left px-3 py-2.5 text-ink-tertiary font-medium">일시</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => {
                const positive = e.delta_krw >= 0;
                return (
                  <tr key={e.entry_id} className="border-b border-line/60 last:border-0">
                    <td className="px-5 py-3">
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium ${positive ? 'bg-success-subtle text-success' : 'bg-ink-muted/10 text-ink-secondary'}`}>
                        {positive ? <ArrowUpRight size={11} /> : <ArrowDownRight size={11} />}
                        {reasonLabel(e.reason)}
                      </span>
                    </td>
                    <td className={`px-3 py-3 font-medium ${positive ? 'text-success' : 'text-ink'}`}>
                      {positive ? '+' : ''}{e.delta_krw.toLocaleString()}원
                    </td>
                    <td className="px-3 py-3 text-ink-secondary">{e.balance_after_krw.toLocaleString()}원</td>
                    <td className="px-3 py-3 text-ink-muted">{formatKST(e.created_at)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
