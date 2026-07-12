// 발표 부록 전용 시각 자료 부품 — 파이프라인·레이어 구조도·매트릭스·타임라인·상태 체크리스트·막대분포.
// 프로젝트 디자인 토큰(surface/ink/line/semantic)만 사용, 텍스트는 항상 ink 토큰(색상은 마크에만).

import { ArrowRight } from 'lucide-react';

export type Tone = 'neutral' | 'primary' | 'point' | 'success' | 'warning' | 'danger' | 'muted';

export const TONE_CLASS: Record<Tone, { bg: string; border: string; text: string; dot: string }> = {
  neutral: { bg: 'bg-surface-1', border: 'border-line', text: 'text-ink-secondary', dot: 'bg-ink-tertiary' },
  primary: { bg: 'bg-primary-subtle', border: 'border-primary/30', text: 'text-primary', dot: 'bg-primary' },
  point: { bg: 'bg-point-subtle', border: 'border-point/30', text: 'text-point', dot: 'bg-point' },
  success: { bg: 'bg-success-subtle', border: 'border-success-border', text: 'text-success', dot: 'bg-success' },
  warning: { bg: 'bg-warning-subtle', border: 'border-warning-border', text: 'text-warning', dot: 'bg-warning' },
  danger: { bg: 'bg-danger-subtle', border: 'border-danger-border', text: 'text-danger', dot: 'bg-danger' },
  muted: { bg: 'bg-surface-1', border: 'border-line-strong border-dashed', text: 'text-ink-muted', dot: 'bg-ink-disabled' },
};

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
  return (
    <div className={`rounded-lg border ${t.bg} ${t.border} min-w-[140px] px-4 py-3 text-center`}>
      {icon && <div className={`mb-1 flex justify-center ${t.text}`}>{icon}</div>}
      <p className={`text-sm font-semibold ${t.text}`}>{label}</p>
      {detail && <p className="mt-0.5 text-xs leading-snug text-ink-tertiary">{detail}</p>}
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
  return (
    <div className={`flex ${vertical ? 'flex-col items-start' : 'flex-wrap items-center'} gap-0`}>
      {steps.map((s, i) => (
        <div key={i} className={vertical ? 'flex flex-col items-start' : 'flex items-center'}>
          <StepBox {...s} />
          {i < steps.length - 1 &&
            (vertical ? (
              <div className="my-1 ml-6 h-5 w-px bg-line-strong" />
            ) : (
              <ArrowRight size={18} className="mx-2 shrink-0 text-ink-tertiary" />
            ))}
        </div>
      ))}
    </div>
  );
}

export function LayerStack({ layers }: { layers: { label: string; detail?: string; tone?: Tone }[] }) {
  return (
    <div className="space-y-1.5">
      {layers.map((l, i) => {
        const t = TONE_CLASS[l.tone ?? 'neutral'];
        return (
          <div key={i} className={`rounded-lg border ${t.bg} ${t.border} px-4 py-2.5`}>
            <p className={`text-sm font-semibold ${t.text}`}>{l.label}</p>
            {l.detail && <p className="mt-0.5 text-xs text-ink-tertiary">{l.detail}</p>}
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
  return (
    <div className="overflow-x-auto rounded-lg border border-line">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="bg-surface-1">
            <th className="border-b border-line px-3 py-2 text-left text-xs font-semibold text-ink-tertiary" />
            {columns.map((c) => (
              <th key={c} className="border-b border-line px-3 py-2 text-left text-xs font-semibold text-ink-tertiary">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label} className="border-b border-line last:border-0">
              <td className="whitespace-nowrap px-3 py-2 text-sm font-medium text-ink">{r.label}</td>
              {r.cells.map((c, i) => {
                const t = TONE_CLASS[c.tone ?? 'neutral'];
                return (
                  <td key={i} className="px-3 py-2">
                    <span className={`inline-block whitespace-nowrap rounded px-2 py-0.5 text-xs font-medium ${t.bg} ${t.text}`}>
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
  return (
    <div className="flex gap-0 overflow-x-auto pb-2">
      {events.map((e, i) => {
        const t = TONE_CLASS[e.tone ?? 'neutral'];
        return (
          <div key={i} className="flex items-start">
            <div className="flex w-44 shrink-0 flex-col items-start">
              <span className="text-caption">{e.date}</span>
              <div className={`mt-1 h-2.5 w-2.5 rounded-full ${t.dot}`} />
              <p className={`mt-1.5 text-sm font-semibold ${t.text}`}>{e.label}</p>
              {e.detail && <p className="mt-0.5 text-xs leading-snug text-ink-tertiary">{e.detail}</p>}
            </div>
            {i < events.length - 1 && <div className="mt-[38px] h-px w-8 shrink-0 bg-line-strong" />}
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
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {items.map((it, i) => {
        const t = TONE_CLASS[it.tone ?? 'primary'];
        return (
          <div key={i} className={`rounded-lg border ${t.border} bg-card p-4`}>
            <p className="text-caption">{it.label}</p>
            <p className={`mt-1 text-lg font-bold leading-tight ${t.text}`}>{it.value}</p>
            {it.detail && <p className="mt-1 text-xs leading-snug text-ink-tertiary">{it.detail}</p>}
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
  return (
    <div className="space-y-2">
      {items.map((it, i) => {
        const t = TONE_CLASS[it.state];
        return (
          <div key={i} className={`flex items-start gap-3 rounded-lg border ${t.border} ${t.bg} px-4 py-3`}>
            {it.icon && <span className={`mt-0.5 ${t.text}`}>{it.icon}</span>}
            <div>
              <p className={`text-sm font-semibold ${t.text}`}>{it.label}</p>
              {it.detail && <p className="mt-0.5 text-xs leading-snug text-ink-secondary">{it.detail}</p>}
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
}: {
  bars: { label: string; value: number }[];
  hue?: Tone;
}) {
  const max = Math.max(...bars.map((b) => b.value));
  const t = TONE_CLASS[hue];
  return (
    <div className="flex h-40 items-end gap-3">
      {bars.map((b, i) => (
        <div key={i} className="flex h-full flex-1 flex-col items-center justify-end gap-1.5">
          <span className="text-xs font-semibold text-ink">{b.value}%</span>
          <div
            className={`w-full max-w-[28px] rounded-t ${t.dot}`}
            style={{ height: `${(b.value / max) * 100}%` }}
          />
          <span className="text-caption text-center">{b.label}</span>
        </div>
      ))}
    </div>
  );
}
