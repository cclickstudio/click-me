// KPI 지표 카드 — label·value·unit·delta(증감 색)·아이콘·미니 스파크라인 조합 프리미티브.
'use client';

import * as React from 'react';
import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Card } from '@/components/ui/card';

interface StatCardProps extends React.HTMLAttributes<HTMLDivElement> {
  label: string;
  value: React.ReactNode;
  unit?: string;
  /** 증감률/증감값. 양수=상승(초록), 음수=하락(빨강), 0/undefined=중립. */
  delta?: number;
  /** delta 뒤에 붙는 표기(기본 %p). */
  deltaSuffix?: string;
  /** delta 방향의 좋음/나쁨이 반대인 지표(예: 거부율↑=나쁨)면 true. */
  invertDelta?: boolean;
  hint?: string;
  icon?: React.ReactNode;
  /** 아이콘 강조 톤. */
  tone?: 'primary' | 'point' | 'muted';
  sparkline?: number[];
}

function Sparkline({ data, positive }: { data: number[]; positive: boolean }) {
  if (data.length < 2) return null;
  const w = 72;
  const h = 24;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const pts = data
    .map((d, i) => {
      const x = (i / (data.length - 1)) * w;
      const y = h - ((d - min) / range) * h;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className='overflow-visible'>
      <polyline
        points={pts}
        fill='none'
        strokeWidth={2}
        strokeLinecap='round'
        strokeLinejoin='round'
        className={positive ? 'stroke-success' : 'stroke-danger'}
      />
    </svg>
  );
}

export function StatCard({
  label,
  value,
  unit,
  delta,
  deltaSuffix = '%p',
  invertDelta = false,
  hint,
  icon,
  tone = 'primary',
  sparkline,
  className,
  ...props
}: StatCardProps) {
  const hasDelta = typeof delta === 'number';
  const up = hasDelta && delta! > 0;
  const down = hasDelta && delta! < 0;
  const good = invertDelta ? down : up;
  const bad = invertDelta ? up : down;

  const toneClass =
    tone === 'point'
      ? 'bg-point-subtle text-point'
      : tone === 'muted'
        ? 'bg-surface-1 text-ink-secondary'
        : 'bg-primary-subtle text-primary';

  return (
    <Card
      className={cn('flex flex-col gap-3 p-5', className)}
      {...props}
    >
      <div className='flex items-start justify-between'>
        <span className='text-sm font-medium text-ink-secondary'>{label}</span>
        {icon && (
          <span
            className={cn(
              'flex size-9 items-center justify-center rounded-lg [&_svg]:size-[18px]',
              toneClass
            )}
          >
            {icon}
          </span>
        )}
      </div>

      <div className='flex items-end justify-between gap-2'>
        <div className='flex items-baseline gap-1'>
          <span className='text-[28px] font-bold leading-none tracking-tight text-ink'>
            {value}
          </span>
          {unit && <span className='text-sm font-medium text-ink-tertiary'>{unit}</span>}
        </div>
        {sparkline && <Sparkline data={sparkline} positive={!bad} />}
      </div>

      <div className='flex items-center gap-2'>
        {hasDelta && (
          <span
            className={cn(
              'inline-flex items-center gap-0.5 rounded-md px-1.5 py-0.5 text-xs font-semibold',
              good && 'bg-success-subtle text-success',
              bad && 'bg-danger-subtle text-danger',
              !good && !bad && 'bg-surface-1 text-ink-tertiary'
            )}
          >
            {up ? (
              <ArrowUpRight className='size-3' />
            ) : down ? (
              <ArrowDownRight className='size-3' />
            ) : (
              <Minus className='size-3' />
            )}
            {Math.abs(delta!)}
            {deltaSuffix}
          </span>
        )}
        {hint && <span className='text-xs text-ink-tertiary'>{hint}</span>}
      </div>
    </Card>
  );
}
