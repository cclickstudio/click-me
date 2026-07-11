// 발표 부록 전용 시각 자료 부품 — 프레젠테이션(빔 프로젝터용 확대)/기본 열람 두 밀도를 지원한다.
// 밀도는 DensityProvider로 감싼 트리 안에서 useDensity()로 읽는다(exhibits.tsx는 밀도를 몰라도 됨).
// 프로젝트 디자인 토큰(surface/ink/line/semantic)만 사용, 텍스트는 항상 ink 토큰(색상은 마크에만).

import { createContext, useContext } from 'react';
import { ArrowRight } from 'lucide-react';

export type Tone = 'neutral' | 'primary' | 'point' | 'success' | 'warning' | 'danger' | 'muted';
export type Density = 'presentation' | 'normal';

export const TONE_CLASS: Record<Tone, { bg: string; border: string; text: string; dot: string }> = {
  neutral: { bg: 'bg-surface-1', border: 'border-line', text: 'text-ink-secondary', dot: 'bg-ink-tertiary' },
  primary: { bg: 'bg-primary-subtle', border: 'border-primary/30', text: 'text-primary', dot: 'bg-primary' },
  point: { bg: 'bg-point-subtle', border: 'border-point/30', text: 'text-point', dot: 'bg-point' },
  success: { bg: 'bg-success-subtle', border: 'border-success-border', text: 'text-success', dot: 'bg-success' },
  warning: { bg: 'bg-warning-subtle', border: 'border-warning-border', text: 'text-warning', dot: 'bg-warning' },
  danger: { bg: 'bg-danger-subtle', border: 'border-danger-border', text: 'text-danger', dot: 'bg-danger' },
  muted: { bg: 'bg-surface-1', border: 'border-line-strong border-dashed', text: 'text-ink-muted', dot: 'bg-ink-disabled' },
};

const DensityContext = createContext<Density>('presentation');
export function DensityProvider({ density, children }: { density: Density; children: React.ReactNode }) {
  return <DensityContext.Provider value={density}>{children}</DensityContext.Provider>;
}
function useDensity() {
  return useContext(DensityContext);
}

const SIZES = {
  presentation: {
    stepBox: 'rounded-xl border-2 min-w-[200px] px-6 py-5',
    stepLabel: 'text-xl font-semibold',
    stepDetail: 'mt-1 text-base leading-snug',
    stepIconWrap: 'mb-2',
    arrowSize: 28,
    arrowGap: 'mx-3',
    vGap: 'my-2 ml-8 h-8 w-0.5',
    layerBox: 'rounded-xl border-2 px-6 py-4',
    layerGap: 'space-y-2.5',
    layerLabel: 'text-xl font-semibold',
    layerDetail: 'mt-1 text-base',
    table: 'rounded-xl border-2 text-lg',
    thCell: 'border-b-2 px-5 py-3 text-base',
    tdLabel: 'px-5 py-3 text-lg',
    tdPill: 'px-3 py-1 text-base',
    tlWidth: 'w-60',
    tlDate: 'text-sm',
    tlDot: 'mt-1.5 h-3.5 w-3.5',
    tlLabel: 'mt-2 text-xl font-semibold',
    tlDetail: 'mt-1 text-base leading-snug',
    tlConnector: 'mt-[52px] h-0.5 w-10',
    cardsGrid: 'grid-cols-1 gap-4 sm:grid-cols-2',
    card: 'rounded-xl border-2 p-6',
    cardLabel: 'text-base',
    cardValue: 'mt-1.5 text-3xl font-bold leading-tight',
    cardDetail: 'mt-2 text-base leading-snug',
    statusGap: 'space-y-3',
    statusBox: 'gap-4 rounded-xl border-2 px-6 py-5',
    statusLabel: 'text-xl font-semibold',
    statusDetail: 'mt-1 text-base leading-snug',
    barHeight: 'h-64',
    barValue: 'text-lg font-semibold',
    barWidth: 'max-w-[48px]',
    barLabel: 'text-sm',
  },
  normal: {
    stepBox: 'rounded-lg border min-w-[140px] px-4 py-3',
    stepLabel: 'text-sm font-semibold',
    stepDetail: 'mt-0.5 text-xs leading-snug',
    stepIconWrap: 'mb-1',
    arrowSize: 18,
    arrowGap: 'mx-2',
    vGap: 'my-1 ml-6 h-5 w-px',
    layerBox: 'rounded-lg border px-4 py-2.5',
    layerGap: 'space-y-1.5',
    layerLabel: 'text-sm font-semibold',
    layerDetail: 'mt-0.5 text-xs',
    table: 'rounded-lg border text-sm',
    thCell: 'border-b px-3 py-2 text-xs',
    tdLabel: 'px-3 py-2 text-sm',
    tdPill: 'px-2 py-0.5 text-xs',
    tlWidth: 'w-44',
    tlDate: 'text-xs',
    tlDot: 'mt-1 h-2.5 w-2.5',
    tlLabel: 'mt-1.5 text-sm font-semibold',
    tlDetail: 'mt-0.5 text-xs leading-snug',
    tlConnector: 'mt-[38px] h-px w-8',
    cardsGrid: 'grid-cols-2 gap-3 sm:grid-cols-4',
    card: 'rounded-lg border p-4',
    cardLabel: 'text-xs',
    cardValue: 'mt-1 text-lg font-bold leading-tight',
    cardDetail: 'mt-1 text-xs leading-snug',
    statusGap: 'space-y-2',
    statusBox: 'gap-3 rounded-lg border px-4 py-3',
    statusLabel: 'text-sm font-semibold',
    statusDetail: 'mt-0.5 text-xs leading-snug',
    barHeight: 'h-40',
    barValue: 'text-xs font-semibold',
    barWidth: 'max-w-[28px]',
    barLabel: 'text-xs',
  },
} as const;

export function StepBox({
  label,
  detail,
  tone = 'neutral',
  icon,
}: {
  label: string;
  detail?: string;
  tone?: Tone;
  icon?: React.ReactNode;
}) {
  const t = TONE_CLASS[tone];
  const s = SIZES[useDensity()];
  return (
    <div className={`${s.stepBox} ${t.bg} ${t.border} text-center`}>
      {icon && <div className={`${s.stepIconWrap} flex justify-center ${t.text}`}>{icon}</div>}
      <p className={`${s.stepLabel} ${t.text}`}>{label}</p>
      {detail && <p className={`${s.stepDetail} text-ink-tertiary`}>{detail}</p>}
    </div>
  );
}

export function Pipeline({
  steps,
  vertical = false,
}: {
  steps: { label: string; detail?: string; tone?: Tone; icon?: React.ReactNode }[];
  vertical?: boolean;
}) {
  const s = SIZES[useDensity()];
  return (
    <div className={vertical ? 'flex flex-col items-start gap-0' : 'flex items-center gap-0 overflow-x-auto pb-2'}>
      {steps.map((step, i) => (
        <div key={i} className={vertical ? 'flex flex-col items-start' : 'flex shrink-0 items-center'}>
          <StepBox {...step} />
          {i < steps.length - 1 &&
            (vertical ? (
              <div className={`${s.vGap} bg-line-strong`} />
            ) : (
              <ArrowRight size={s.arrowSize} className={`${s.arrowGap} shrink-0 text-ink-tertiary`} />
            ))}
        </div>
      ))}
    </div>
  );
}

export function LayerStack({ layers }: { layers: { label: string; detail?: string; tone?: Tone }[] }) {
  const s = SIZES[useDensity()];
  return (
    <div className={s.layerGap}>
      {layers.map((l, i) => {
        const t = TONE_CLASS[l.tone ?? 'neutral'];
        return (
          <div key={i} className={`${s.layerBox} ${t.bg} ${t.border}`}>
            <p className={`${s.layerLabel} ${t.text}`}>{l.label}</p>
            {l.detail && <p className={`${s.layerDetail} text-ink-tertiary`}>{l.detail}</p>}
          </div>
        );
      })}
    </div>
  );
}

export function Matrix({
  columns,
  rows,
}: {
  columns: string[];
  rows: { label: string; cells: { text: string; tone?: Tone }[] }[];
}) {
  const s = SIZES[useDensity()];
  return (
    <div className={`overflow-x-auto ${s.table} border-line`}>
      <table className="w-full border-collapse">
        <thead>
          <tr className="bg-surface-1">
            <th className={`${s.thCell} border-line text-left font-semibold text-ink-tertiary`} />
            {columns.map((c) => (
              <th key={c} className={`${s.thCell} border-line text-left font-semibold text-ink-tertiary`}>
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label} className="border-b border-line last:border-0">
              <td className={`${s.tdLabel} whitespace-nowrap font-medium text-ink`}>{r.label}</td>
              {r.cells.map((c, i) => {
                const t = TONE_CLASS[c.tone ?? 'neutral'];
                return (
                  <td key={i} className="px-3 py-2">
                    <span className={`inline-block whitespace-nowrap rounded-md font-medium ${s.tdPill} ${t.bg} ${t.text}`}>
                      {c.text}
                    </span>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Timeline({
  events,
}: {
  events: { date: string; label: string; detail?: string; tone?: Tone }[];
}) {
  const s = SIZES[useDensity()];
  return (
    <div className="flex gap-0 overflow-x-auto pb-2">
      {events.map((e, i) => {
        const t = TONE_CLASS[e.tone ?? 'neutral'];
        return (
          <div key={i} className="flex items-start">
            <div className={`flex ${s.tlWidth} shrink-0 flex-col items-start`}>
              <span className={`${s.tlDate} text-ink-tertiary`}>{e.date}</span>
              <div className={`${s.tlDot} rounded-full ${t.dot}`} />
              <p className={`${s.tlLabel} ${t.text}`}>{e.label}</p>
              {e.detail && <p className={`${s.tlDetail} text-ink-tertiary`}>{e.detail}</p>}
            </div>
            {i < events.length - 1 && <div className={`${s.tlConnector} shrink-0 bg-line-strong`} />}
          </div>
        );
      })}
    </div>
  );
}

export function InfoCards({
  items,
}: {
  items: { label: string; value: string; detail?: string; tone?: Tone }[];
}) {
  const s = SIZES[useDensity()];
  return (
    <div className={`grid ${s.cardsGrid}`}>
      {items.map((it, i) => {
        const t = TONE_CLASS[it.tone ?? 'primary'];
        return (
          <div key={i} className={`${s.card} ${t.border} bg-card`}>
            <p className={`${s.cardLabel} text-ink-tertiary`}>{it.label}</p>
            <p className={`${s.cardValue} ${t.text}`}>{it.value}</p>
            {it.detail && <p className={`${s.cardDetail} text-ink-tertiary`}>{it.detail}</p>}
          </div>
        );
      })}
    </div>
  );
}

export function StatusRow({
  items,
}: {
  items: { label: string; state: Tone; detail?: string; icon?: React.ReactNode }[];
}) {
  const s = SIZES[useDensity()];
  return (
    <div className={s.statusGap}>
      {items.map((it, i) => {
        const t = TONE_CLASS[it.state];
        return (
          <div key={i} className={`flex items-start ${s.statusBox} ${t.border} ${t.bg}`}>
            {it.icon && <span className={`mt-0.5 ${t.text}`}>{it.icon}</span>}
            <div>
              <p className={`${s.statusLabel} ${t.text}`}>{it.label}</p>
              {it.detail && <p className={`${s.statusDetail} text-ink-secondary`}>{it.detail}</p>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// 막대 값은 항상 예시 데이터 — 실측이 아님을 호출부 note에서 명시할 것.
export function BarDistribution({
  bars,
  hue = 'primary',
  scaleMin = 0,
}: {
  bars: { label: string; value: number; display?: string }[];
  hue?: Tone;
  scaleMin?: number;
}) {
  const max = Math.max(...bars.map((b) => b.value));
  const t = TONE_CLASS[hue];
  const range = Math.max(max - scaleMin, 0.0001);
  const s = SIZES[useDensity()];
  return (
    <div className={`flex ${s.barHeight} items-end gap-4`}>
      {bars.map((b, i) => (
        <div key={i} className="flex h-full flex-1 flex-col items-center justify-end gap-2">
          <span className={`${s.barValue} text-ink`}>{b.display ?? `${b.value}%`}</span>
          <div
            className={`w-full ${s.barWidth} rounded-t-md ${t.dot}`}
            style={{ height: `${((b.value - scaleMin) / range) * 100}%` }}
          />
          <span className={`${s.barLabel} text-center text-ink-tertiary`}>{b.label}</span>
        </div>
      ))}
    </div>
  );
}
