// Recharts용 테마 색 훅 — CSS 변수(RGB 채널)를 읽어 rgb() 문자열로 반환, 테마 전환 시 갱신.
'use client';

import { useEffect, useState } from 'react';
import { useTheme } from '@/components/ThemeProvider';

const VARS = [
  'primary',
  'point',
  'success',
  'warning',
  'danger',
  'info',
  'border',
  'text-secondary',
  'text-tertiary',
  'surface-2',
] as const;

type VarKey = (typeof VARS)[number];
export type ChartColors = Record<VarKey, string> & {
  /** 시리즈 순환용 팔레트. */
  series: string[];
};

function read(name: string): string {
  if (typeof window === 'undefined') return 'rgb(37 99 235)';
  const raw = getComputedStyle(document.documentElement)
    .getPropertyValue(`--${name}`)
    .trim();
  return raw ? `rgb(${raw})` : 'rgb(37 99 235)';
}

export function useChartColors(): ChartColors {
  const { theme } = useTheme();
  const [colors, setColors] = useState<ChartColors>(() => buildFallback());

  useEffect(() => {
    const next = Object.fromEntries(VARS.map(v => [v, read(v)])) as Record<
      VarKey,
      string
    >;
    setColors({
      ...next,
      series: [
        next.primary,
        next.point,
        next.success,
        next.warning,
        next.info,
        next.danger,
      ],
    });
    // theme 바뀌면 CSS 변수 재판독.
  }, [theme]);

  return colors;
}

function buildFallback(): ChartColors {
  const base: Record<VarKey, string> = {
    primary: 'rgb(37 99 235)',
    point: 'rgb(99 102 241)',
    success: 'rgb(22 163 74)',
    warning: 'rgb(217 119 6)',
    danger: 'rgb(239 68 68)',
    info: 'rgb(49 130 246)',
    border: 'rgb(229 232 235)',
    'text-secondary': 'rgb(78 89 104)',
    'text-tertiary': 'rgb(139 149 161)',
    'surface-2': 'rgb(255 255 255)',
  };
  return {
    ...base,
    series: [
      base.primary,
      base.point,
      base.success,
      base.warning,
      base.info,
      base.danger,
    ],
  };
}
