// 신뢰도 리포트 — 지표 정의 → 개선 전/후(그래프) → 표준 기반 개선 → 적대적 셋 자기검증 → 한계와 극복
'use client';

import { Bar, BarChart, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import {
  EVAL_ACTIONS,
  EVAL_META,
  GOLDEN_SETS,
  IMPROVEMENT,
  LIMITATION,
  METHOD,
  METRIC_TAXONOMY,
  STANDARD_BASIS,
  TARGET_POLICY,
} from './data';

const BLUE = '#3182F6';
const GRAY = '#C7D2E5';
const MUTED = '#8B95A1';

function Pill({ text, cls }: { text: string; cls: string }) {
  return (
    <span className={`inline-flex items-center h-5 px-2 rounded-full text-[11px] font-medium ${cls}`}>
      {text}
    </span>
  );
}

function Card({ title, sub, children }: { title?: string; sub?: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-line bg-card p-5">
      {title && <h3 className="text-[14px] font-semibold text-ink">{title}</h3>}
      {sub && <p className="mt-0.5 text-[12px] text-ink-tertiary">{sub}</p>}
      <div className={title ? 'mt-3' : ''}>{children}</div>
    </div>
  );
}

// 번호 붙은 섹션 제목
function SectionTitle({ n, title, desc }: { n: number; title: string; desc?: string }) {
  return (
    <div className="mb-3 mt-8 first:mt-0">
      <div className="flex items-center gap-2">
        <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-primary text-primary-foreground text-[12px] font-bold">
          {n}
        </span>
        <h2 className="text-[16px] font-bold text-ink">{title}</h2>
      </div>
      {desc && <p className="mt-1 ml-8 text-[12px] text-ink-tertiary">{desc}</p>}
    </div>
  );
}

function groupCls(group: string) {
  return group === '검색 품질'
    ? 'bg-primary-subtle text-primary'
    : 'bg-[#E7F7EF] dark:bg-[#153027] text-[#12A05C]';
}

// 막대에 올리면 뜨는 설명 — 쉬운 말
function ChartTooltip({ active, payload }: { active?: boolean; payload?: { payload: Record<string, unknown> }[] }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload as {
    eng: string;
    plain: string;
    initial: number | null;
    improved: number;
    work: string;
    note?: string;
  };
  return (
    <div className="rounded-xl border border-line bg-card px-3 py-2 shadow-sm max-w-[240px]">
      <p className="text-[12px] font-semibold text-ink">
        {d.eng} <span className="font-normal text-ink-tertiary">({d.plain})</span>
      </p>
      <p className="mt-0.5 text-[11px] text-ink-tertiary">
        {d.initial != null && <span>개선 전 {d.initial.toFixed(2)} → </span>}
        <span className="font-bold text-primary">개선 후 {d.improved.toFixed(2)}</span>
      </p>
      <p className="mt-1 text-[11px] leading-relaxed text-ink-secondary">
        {d.work}
        {d.note ? ` · ${d.note}` : ''}
      </p>
    </div>
  );
}

export default function ReliabilityPage() {
  return (
    <div className="max-w-screen-lg mx-auto px-6 py-6">
      {/* 헤더 */}
      <div className="mb-2">
        <h1 className="text-[20px] font-bold text-ink">신뢰도 리포트</h1>
        <p className="mt-1 text-[13px] text-ink-tertiary">
          {EVAL_META.target}의 검색·답변 품질을, 정답을 고정한 평가셋으로 측정한 결과입니다. 각 셋{' '}
          {EVAL_META.n}문항 · {EVAL_META.asOf}.
        </p>
      </div>

      {/* 1. 지표 의미 정의 */}
      <SectionTitle n={1} title="지표가 뭘 재나" desc="앞 3개는 자료를 잘 찾는지(검색 품질), 뒤 2개는 찾은 자료로 정확히 답하는지(답변 품질)." />
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-[13px] border-collapse">
            <thead>
              <tr className="text-ink-tertiary text-left">
                <th className="py-2 pr-3 font-medium">지표 (Metric)</th>
                <th className="py-2 pr-3 font-medium">구분</th>
                <th className="py-2 font-medium">무엇을 보나</th>
              </tr>
            </thead>
            <tbody>
              {METRIC_TAXONOMY.map((m) => (
                <tr key={m.eng} className="border-t border-line align-top">
                  <td className="py-2.5 pr-3 whitespace-nowrap">
                    <span className="font-semibold text-ink">{m.eng}</span>
                    <span className="block text-[11px] text-ink-tertiary">{m.metric}</span>
                  </td>
                  <td className="py-2.5 pr-3">
                    <Pill text={m.group} cls={groupCls(m.group)} />
                  </td>
                  <td className="py-2.5 text-[12px] text-ink-secondary">{m.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* 2. 개선 전 → 개선 후 (하나의 그래프) */}
      <SectionTitle n={2} title="개선 전 → 개선 후" desc="셋마다 5개 지표를 한 그래프에. 막대에 마우스를 올리면 자세한 설명이 나옵니다." />
      <div className="grid lg:grid-cols-2 gap-3">
        {GOLDEN_SETS.map((s) => {
          const chartData = s.metrics.map((m) => ({
            short: m.short,
            eng: m.eng,
            plain: m.plain,
            initial: m.initial,
            improved: m.improved,
            work: m.work,
            note: m.note,
          }));
          return (
            <Card key={s.key} title={s.name} sub={s.sub}>
              <ResponsiveContainer width="100%" height={230}>
                <BarChart data={chartData} margin={{ top: 8, right: 8, left: -24, bottom: 0 }} barGap={2} barCategoryGap="24%">
                  <XAxis dataKey="short" tick={{ fill: MUTED, fontSize: 10 }} axisLine={false} tickLine={false} interval={0} />
                  <YAxis domain={[0, 1]} ticks={[0, 0.5, 1]} tick={{ fill: MUTED, fontSize: 11 }} axisLine={false} tickLine={false} />
                  <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(49,130,246,0.06)' }} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar dataKey="initial" name="개선 전" fill={GRAY} radius={[4, 4, 0, 0]} maxBarSize={22} />
                  <Bar dataKey="improved" name="개선 후" fill={BLUE} radius={[4, 4, 0, 0]} maxBarSize={22} />
                </BarChart>
              </ResponsiveContainer>
              <div className="mt-3 border-t border-line pt-2.5">
                <p className="text-[11px] font-medium text-ink-tertiary mb-1.5">예시 질문</p>
                <ul className="space-y-1">
                  {s.examples.map((q) => (
                    <li key={q} className="flex gap-1.5 text-[12px] text-ink-secondary">
                      <span className="text-primary">·</span>
                      <span>{q}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </Card>
          );
        })}
      </div>
      <p className="mt-2 text-[12px] text-ink-tertiary">
        회색 = 개선 전, 파랑 = 개선 후. <b>Hit Rate·Faithfulness·Factual Correctness</b>는 100%가 목표,
        <b> MRR·Context Precision</b>은 최대한 높게가 목표. {EVAL_META.note}
      </p>

      {/* 3. 어떻게 개선했나 — 표준 기반 */}
      <SectionTitle n={3} title="어떻게 개선했나 — 표준에 따라" desc="RAGAS·LlamaIndex 같은 표준 평가·개선 방식을 그대로 따랐습니다." />
      <div className="grid md:grid-cols-3 gap-3 mb-3">
        {STANDARD_BASIS.map((b) => (
          <a
            key={b.area}
            href={b.url}
            target="_blank"
            rel="noreferrer"
            className="block rounded-2xl border border-line bg-surface-1 px-4 py-3 hover:border-primary transition-colors"
          >
            <p className="text-[12px] font-semibold text-primary">{b.area}</p>
            <p className="mt-1 text-[12px] leading-relaxed text-ink-secondary">{b.basis}</p>
            <p className="mt-1.5 text-[11px] text-ink-tertiary underline">출처 보기 ↗</p>
          </a>
        ))}
      </div>
      <Card title="구체적으로 한 일">
        <ul className="space-y-3">
          {EVAL_ACTIONS.map((a) => (
            <li key={a.title} className="flex gap-3">
              <span
                className={`shrink-0 mt-0.5 inline-flex items-center h-5 px-2 rounded-full text-[10px] font-semibold ${
                  a.tag === '방법론'
                    ? 'bg-primary-subtle text-primary'
                    : a.tag === '검색'
                      ? 'bg-surface-1 text-ink-tertiary'
                      : a.tag === '답변'
                        ? 'bg-[#E7F7EF] dark:bg-[#153027] text-[#12A05C]'
                        : 'bg-[#FFF4E5] dark:bg-[#3A2E1A] text-[#B8791B]'
                }`}
              >
                {a.tag}
              </span>
              <div>
                <p className="text-[13px] font-medium text-ink">{a.title}</p>
                <p className="mt-0.5 text-[12px] leading-relaxed text-ink-secondary">{a.effect}</p>
              </div>
            </li>
          ))}
        </ul>
      </Card>

      {/* 4. 적대적 셋으로 자기 검증 */}
      <SectionTitle n={4} title="함정 질문으로 자기 검증" desc="일부러 함정을 판 질문 23개로, 모르면 지어내지 않고 모른다고 답하는지 확인." />
      <Card>
        <div className="flex flex-wrap items-center gap-3 mb-3">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-primary-subtle px-3 py-1 text-[12px] font-medium text-primary">
            {IMPROVEMENT.action}
          </span>
          <div className="flex items-center gap-2 text-[15px]">
            <span className="text-ink-tertiary">{IMPROVEMENT.beforeLabel}</span>
            <span className="font-bold text-ink-secondary">{IMPROVEMENT.overall.before.toFixed(3)}</span>
            <span className="text-primary">→</span>
            <span className="text-ink-tertiary">{IMPROVEMENT.afterLabel}</span>
            <span className="font-bold text-primary">{IMPROVEMENT.overall.after.toFixed(3)}</span>
            <span className="text-[12px] font-semibold text-primary">
              (+{(IMPROVEMENT.overall.after - IMPROVEMENT.overall.before).toFixed(3)})
            </span>
          </div>
        </div>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={IMPROVEMENT.categories} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
            <XAxis dataKey="label" tick={{ fill: MUTED, fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis domain={[0, 1]} tick={{ fill: MUTED, fontSize: 11 }} axisLine={false} tickLine={false} />
            <Tooltip contentStyle={{ borderRadius: 12, border: 'none', fontSize: 12 }} cursor={{ fill: 'rgba(49,130,246,0.06)' }} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="before" name={IMPROVEMENT.beforeLabel} fill={GRAY} radius={[4, 4, 0, 0]} maxBarSize={26} />
            <Bar dataKey="after" name={IMPROVEMENT.afterLabel} fill={BLUE} radius={[4, 4, 0, 0]} maxBarSize={26} />
          </BarChart>
        </ResponsiveContainer>
        <p className="mt-2 text-[12px] leading-relaxed text-ink-tertiary">
          방법 — {IMPROVEMENT.selfCheck}. 점수(0~1, 1.0=모른다/정확교정)는 <b>숫자 함정·분야 밖</b>에서 크게 올랐습니다.
        </p>
      </Card>

      {/* 5. 한계와 극복 */}
      <SectionTitle n={5} title="한계와 극복" desc="솔직하게 — 남은 한계와 그 해결 방법." />
      <Card>
        <ul className="space-y-3">
          {LIMITATION.map((l) => (
            <li key={l.limit} className="flex gap-3">
              <span
                className={`shrink-0 mt-0.5 inline-flex items-center h-5 px-2 rounded-full text-[10px] font-semibold ${
                  l.done
                    ? 'bg-[#E7F7EF] dark:bg-[#153027] text-[#12A05C]'
                    : 'bg-[#FFF4E5] dark:bg-[#3A2E1A] text-[#B8791B]'
                }`}
              >
                {l.done ? '해결' : '진행'}
              </span>
              <div>
                <p className="text-[13px] font-medium text-ink">{l.limit}</p>
                <p className="mt-0.5 text-[12px] leading-relaxed text-ink-secondary">→ {l.fix}</p>
              </div>
            </li>
          ))}
        </ul>
      </Card>

      {/* 목표 방침 + 방법 */}
      <div className="mt-3 rounded-2xl border border-line bg-surface-1 px-5 py-4">
        <p className="text-[13px] font-semibold text-ink">목표는 평가셋 성격에 따라 다르게</p>
        <ul className="mt-2 space-y-1.5 text-[12px] leading-relaxed text-ink-secondary">
          <li>
            <b>지금 평가셋</b> — {TARGET_POLICY.curated}
          </li>
          <li>
            <b>실제 트래픽</b> — {TARGET_POLICY.prod}
          </li>
        </ul>
      </div>
      <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
        {METHOD.map((m) => (
          <div
            key={m.title}
            className="rounded-2xl border border-line bg-surface-1 px-5 py-4"
          >
            <p className="text-[13px] font-semibold text-ink">{m.title}</p>
            <p className="mt-1 text-[12px] leading-relaxed text-ink-secondary">{m.body}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
