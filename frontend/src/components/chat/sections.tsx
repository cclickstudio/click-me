// 섹션 렌더러 레지스트리 — kind → 렌더러. 새 섹션 추가 = 여기 한 줄 등록(스펙 §5.1).
import type { ReactNode } from 'react';
import type { CardSection } from '@/lib/chatCard';
import Markdown from './Markdown';

type Renderer<K extends CardSection['kind']> = (s: Extract<CardSection, { kind: K }>) => ReactNode;
type Registry = { [K in CardSection['kind']]?: Renderer<K> };

function Title({ title }: { title?: string }) {
  if (!title) return null;
  return <p className="text-[11px] font-semibold text-[#8B95A1] dark:text-[#6B7280] mb-1">{title}</p>;
}

export const SECTION_RENDERERS: Registry = {
  summary: (s) => (
    <div className="text-[#191F28] dark:text-[#F2F4F6]">
      <Title title={s.title} />
      <Markdown>{s.text}</Markdown>
    </div>
  ),
  metrics: (s) => (
    <div>
      <Title title={s.title} />
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {s.items.map((m, i) => (
          <span key={i} className="text-sm text-[#4E5968] dark:text-[#9CA3AF]">
            {m.label} <b className="text-[#191F28] dark:text-[#F2F4F6]">{m.value}</b>
          </span>
        ))}
      </div>
    </div>
  ),
  entity: (s) => (
    <div>
      <Title title={s.title} />
      {s.items.map((kv, i) => (
        <p key={i} className="text-sm text-[#4E5968] dark:text-[#9CA3AF]">
          {kv.key} · {kv.value}
        </p>
      ))}
    </div>
  ),
  proposal: (s) => (
    <div>
      <Title title={s.title} />
      <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">
        {s.action_type}
        {s.executable === false && (
          <span className="ml-2 text-[10px] font-normal text-[#8B95A1]">draft · 실행 미연결</span>
        )}
      </p>
      {typeof s.budget_before_krw === 'number' && typeof s.budget_after_krw === 'number' && (
        <p className="text-xs text-[#4E5968] dark:text-[#9CA3AF] mt-0.5">
          예산 {s.budget_before_krw.toLocaleString()}원 → {s.budget_after_krw.toLocaleString()}원
        </p>
      )}
      {s.rationale && <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mt-0.5">근거: {s.rationale}</p>}
    </div>
  ),
  review: (s) => (
    <div>
      <Title title={s.title} />
      <p className="text-sm text-[#4E5968] dark:text-[#9CA3AF]">{s.decision}</p>
      {s.rationale && <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mt-0.5">{s.rationale}</p>}
    </div>
  ),
  diagnosis: (s) => (
    <div>
      <Title title={s.title} />
      <p className="text-sm text-[#191F28] dark:text-[#F2F4F6]">
        {s.anomaly_type} · 신뢰도 {Math.round(s.confidence * 100)}%
      </p>
      {s.hypothesis && <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mt-0.5">{s.hypothesis}</p>}
    </div>
  ),
  evidence: (s) => {
    // 모든 근거를 표시 — live 인용/툴은 "실측·", kb 인용은 title||source. 중복 제거.
    const tools = (s.used_tools ?? []).map((t) => t.replace('live_', '실측·'));
    const cites = (s.citations ?? []).map((c) =>
      c.kind === 'kb' ? c.title || c.source : c.source.replace('live_', '실측·'),
    );
    const all = [...new Set([...tools, ...cites])];
    if (all.length === 0) return null;
    return <p className="text-[11px] text-[#B0B8C1] dark:text-[#6B7280]">근거: {all.join(' · ')}</p>;
  },
  empty_state: (s) => (
    <div>
      <Title title={s.title} />
      <p className="text-sm text-[#8B95A1] dark:text-[#6B7280]">{s.text}</p>
    </div>
  ),
};
