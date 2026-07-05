// 내부 동작(arch) 전용 — 백엔드 워커가 도는 이상대응 파이프라인을 reactflow 그래프로 시각화.
// 감지→진단→처방→승인→집행을 소유자(🅰🅱🤝) 노드로 그리고, 현재 run/승인/실행 상태로 단계가 켜진다.
'use client';

import { memo, useMemo } from 'react';
import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeTypes,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import type { ActionResult, RunResult } from './types';
import { actionLabel } from './types';

const OWNER = {
  A: { emoji: '🅰', color: '#3182F6', lane: '측정·진단' },
  B: { emoji: '🅱', color: '#0F9D58', lane: '개선·실행' },
  AB: { emoji: '🤝', color: '#8B95A1', lane: '승인(HITL)' },
} as const;

type Owner = keyof typeof OWNER;
type StageState = 'done' | 'active' | 'pending' | 'blocked';
type StageData = { title: string; owner: Owner; state: StageState; detail?: string };

const STATE_LABEL: Record<StageState, string> = {
  done: '✓ 완료',
  active: '● 진행',
  pending: '· 대기',
  blocked: '🚫 차단',
};

// 커스텀 노드 — 소유자 레인·단계명·상세·상태를 한 카드로. 대기 단계는 흐리게.
function StageNode({ data }: { data: StageData }) {
  const o = OWNER[data.owner];
  const dim = data.state === 'pending';
  const stroke = data.state === 'blocked' ? '#E5484D' : o.color;
  return (
    <div
      className="rounded-xl border-2 bg-white px-3 py-2 text-center dark:bg-[#1C2333]"
      style={{ borderColor: stroke, opacity: dim ? 0.5 : 1, minWidth: 118 }}
    >
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      <div className="text-[10px] font-semibold" style={{ color: o.color }}>
        {o.emoji} {o.lane}
      </div>
      <div className="text-sm font-bold text-[#191F28] dark:text-[#F2F4F6]">{data.title}</div>
      {data.detail && <div className="mt-0.5 text-[10px] text-[#8B95A1]">{data.detail}</div>}
      <div
        className="mt-0.5 text-[10px] font-medium"
        style={{ color: data.state === 'blocked' ? '#E5484D' : data.state === 'pending' ? '#B0B8C1' : o.color }}
      >
        {STATE_LABEL[data.state]}
      </div>
      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
    </div>
  );
}

const nodeTypes: NodeTypes = { stage: StageNode };

function PipelineGraph({
  run,
  decided,
  result,
}: {
  run: RunResult;
  decided: 'approved' | 'rejected' | null;
  result: ActionResult | null;
}) {
  const { nodes, edges } = useMemo(() => {
    const detected = run.anomaly_hours.length > 0;
    const dx = run.diagnosis;
    const prop = run.proposal;

    const detect: StageState = 'done';
    const diagnose: StageState = dx ? 'done' : 'active';
    const prescribe: StageState = prop ? 'done' : dx ? 'active' : 'pending';
    const approve: StageState =
      decided === 'approved' ? 'done' : decided === 'rejected' ? 'blocked' : prop ? 'active' : 'pending';
    const execute: StageState = result
      ? result.status === 'failed' || result.status === 'rejected'
        ? 'blocked'
        : 'done'
      : decided === 'approved'
        ? 'active'
        : 'pending';

    const stages: (StageData & { id: string })[] = [
      {
        id: 'detect',
        title: '감지',
        owner: 'A',
        state: detect,
        detail: detected ? `이상 ${run.anomaly_hours.length}구간` : '정상 판정',
      },
      {
        id: 'diagnose',
        title: '진단',
        owner: 'A',
        state: diagnose,
        detail: dx ? `${dx.source} · 확신 ${Math.round(dx.confidence * 100)}%` : undefined,
      },
      {
        id: 'prescribe',
        title: '처방',
        owner: 'B',
        state: prescribe,
        detail: prop ? `${actionLabel(prop.action_type)} · Tier ${prop.action_tier}` : undefined,
      },
      {
        id: 'approve',
        title: '승인',
        owner: 'AB',
        state: approve,
        detail: run.relabeled ? 'Tier 1▶3 재라벨' : 'HITL',
      },
      {
        id: 'execute',
        title: '집행',
        owner: 'B',
        state: execute,
        detail: result ? `DRY-RUN · ${result.status}` : undefined,
      },
    ];

    const nodes: Node[] = stages.map((s, i) => ({
      id: s.id,
      type: 'stage',
      position: { x: i * 190, y: 0 },
      data: { title: s.title, owner: s.owner, state: s.state, detail: s.detail },
      draggable: false,
    }));

    // 엣지 = 소유자 간 계약 흐름. 목적지 단계가 활성/완료면 애니메이션으로 흐름을 강조.
    const flow: [string, string, string][] = [
      ['detect', 'diagnose', '노출 신호'],
      ['diagnose', 'prescribe', 'DiagnosisResult'],
      ['prescribe', 'approve', 'ActionProposal'],
      ['approve', 'execute', 'ApprovedAction'],
    ];
    const stateOf = Object.fromEntries(stages.map((s) => [s.id, s.state])) as Record<string, StageState>;
    const edges: Edge[] = flow.map(([source, target, label]) => {
      const active = stateOf[target] === 'done' || stateOf[target] === 'active';
      const blocked = stateOf[target] === 'blocked';
      return {
        id: `${source}-${target}`,
        source,
        target,
        label,
        animated: active,
        style: { stroke: blocked ? '#E5484D' : active ? '#3182F6' : '#D1D6DB', strokeWidth: 1.5 },
        labelStyle: { fontSize: 10, fill: '#8B95A1' },
        labelBgStyle: { fill: '#F9FAFB' },
      };
    });
    return { nodes, edges };
  }, [run, decided, result]);

  return (
    <div className="mb-4 rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-[#E5E8EB] dark:border-[#2D3748]">
        <p className="text-sm font-bold text-[#191F28] dark:text-[#F2F4F6]">🔧 파이프라인 (내부 동작)</p>
        <p className="text-[11px] text-[#8B95A1]">
          서버 워커(APScheduler)가 자동 실행 · 승인만 사람(HITL) · 집행은 DRY-RUN
        </p>
      </div>
      {/* 노드가 한 줄이라 높이를 낮춰 위아래 빈 공간을 없앤다. maxZoom=1로 과확대 방지. */}
      <div style={{ height: 132 }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.12, maxZoom: 1 }}
          minZoom={0.4}
          nodesDraggable={false}
          nodesConnectable={false}
          panOnDrag={false}
          zoomOnScroll={false}
          preventScrolling={false}
          proOptions={{ hideAttribution: true }}
        >
          <Background gap={16} color="#E5E8EB" />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
    </div>
  );
}

export default memo(PipelineGraph);
