'use client';

// 채팅 안 토론(debate) 실시간 스트림 위젯 — 시뮬 완료 후 자동 시작된 토론을 SSE로 받아 보여준다.
// run_id는 SimFormWidget이 만들어 넘긴다(여기선 구독만 — 재구독해도 스트림이 리플레이돼 안전).
// 모델 칩은 표시하지 않는다(gpt 단일 사용).
import { useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { openReconnectingStream } from '@/lib/sse';
import type { DebateSSEEvent, DebateStance } from '@/lib/types';
import ApprovalWidget from './ApprovalWidget';

type Phase = 'running' | 'done' | 'error';

type Utterance = {
  round: number;
  phase: string;
  persona_name: string;
  role: string;
  stance: DebateStance;
  text: string;
  lever: string;
};

const STANCE: Record<DebateStance, { label: string; dot: string }> = {
  positive: { label: '긍정', dot: 'bg-[#00C471]' },
  neutral: { label: '중립', dot: 'bg-[#B0B8C1]' },
  negative: { label: '부정', dot: 'bg-[#F04452]' },
};

// 역할명 첫 글자 아바타 색 — 진영 구분용(엔진/모델은 노출하지 않음).
function avatarColor(role: string): string {
  if (role.includes('비판')) return 'bg-[#F04452]';
  if (role.includes('완주')) return 'bg-[#00C471]';
  if (role.includes('피벗')) return 'bg-[#3182F6]';
  if (role.includes('마케팅')) return 'bg-[#00B8B8]';
  if (role.includes('전문가')) return 'bg-[#7C5CFC]';
  return 'bg-[#8B95A1]';
}

const STAGE_LABEL: Record<string, string> = {
  analysis: '반응 분석',
  kpi: 'KPI 확정',
  topic: '토론 주제 제시',
  selection: '패널 구성',
  assignment: '참가자 배정',
  judge_final: '최종 결론 종합',
  report: '리포트 조립',
  persisted: '저장',
};

const cardCls =
  'mt-2 w-full rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#1C2333] p-4';

export default function DebateStreamWidget({
  runId,
  sessionId,
  onSummary,
  onAccept,
  proposalDisabled,
}: {
  runId: string;
  sessionId?: string; // 개선 루프 3턴 한도 조회용(없으면 제안 그대로 노출)
  onSummary?: (runId: string) => void; // "토론 요약" 클릭 → 요약 위젯 메시지 추가
  onAccept?: (action: string) => void; // 개선 제안 수락(토론 종료 후) → 개선 루프 진행
  proposalDisabled?: boolean;
}) {
  const [phase, setPhase] = useState<Phase>('running');
  const [pct, setPct] = useState(0);
  const [stageMsg, setStageMsg] = useState('토론 준비 중...');
  const [topic, setTopic] = useState<string | null>(null);
  const [utterances, setUtterances] = useState<Utterance[]>([]);
  const [summaries, setSummaries] = useState<{ round: number; text: string }[]>(
    []
  );
  const [err, setErr] = useState('');
  const [summaryShown, setSummaryShown] = useState(false);
  // 개선 루프 한도 — 토론 완료 시 조회. canImprove=false면 '개선 시안 만들기' 대신 완료 안내.
  const [loop, setLoop] = useState<{
    canImprove: boolean;
    count: number;
    max: number;
  } | null>(null);
  const esRef = useRef<(() => void) | null>(null); // SSE 재연결 구독 close 함수(X2)
  const doneRef = useRef(false);
  const logRef = useRef<HTMLDivElement>(null);

  // 새 발언이 쌓이면 로그 맨 아래로 스크롤.
  useEffect(() => {
    logRef.current?.scrollTo({
      top: logRef.current.scrollHeight,
      behavior: 'smooth',
    });
  }, [utterances, summaries]);

  useEffect(() => {
    if (!runId) return;
    doneRef.current = false;
    const finish = () => {
      if (doneRef.current) return;
      doneRef.current = true;
      setPhase('done'); // 결론·권고는 별도 "토론 요약" 위젯에서 본다
    };

    // SSE 자동 재연결(X2) — 끊기면 backoff 재구독(토론 stream은 재구독 시 리플레이돼 안전).
    esRef.current = openReconnectingStream(() => api.debate.stream(runId), {
      label: 'debate',
      isTerminal: x =>
        (x as DebateSSEEvent).event === 'completed' ||
        (x as DebateSSEEvent).event === 'error',
      onGiveUp: () => finish(), // 재연결도 실패하면 완료로 간주(이미 끝났을 수 있음)
      onEvent: raw => {
        const d = raw as DebateSSEEvent;
        if (d.event === 'error') {
          setErr(d.message ?? '토론 진행 중 오류');
          setPhase('error');
          return;
        }
        if (typeof d.pct === 'number') setPct(d.pct);

        if (d.stage === 'topic' && d.headline) {
          setTopic(d.headline);
          setStageMsg('토론 주제 제시');
        } else if (d.stage === 'utterance' && d.text) {
          setUtterances(prev => [
            ...prev,
            {
              round: d.round ?? 0,
              phase: d.phase ?? '',
              persona_name: d.persona_name ?? d.persona_id ?? '?',
              role: d.role ?? '',
              stance: d.stance ?? 'neutral',
              text: d.text!,
              lever: d.lever ?? '',
            },
          ]);
          setStageMsg(`R${d.round} ${d.phase} · ${d.persona_name}`);
        } else if (d.stage === 'round_summary') {
          setSummaries(prev => [
            ...prev,
            { round: d.round ?? 0, text: d.summary ?? '' },
          ]);
        } else if (d.stage && STAGE_LABEL[d.stage]) {
          setStageMsg(STAGE_LABEL[d.stage]);
        }

        if (d.event === 'completed') finish();
      },
    });

    return () => esRef.current?.();
  }, [runId]);

  // 토론 완료 후 개선 루프 한도 조회 — 3턴 도달 시 '개선 시안 만들기'를 숨긴다.
  useEffect(() => {
    if (phase !== 'done' || !sessionId || !onAccept) return;
    let alive = true;
    api.chat
      .loopState(sessionId)
      .then(s => {
        if (alive)
          setLoop({
            canImprove: s.can_improve,
            count: s.loop_count,
            max: s.max_loop,
          });
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [phase, sessionId, onAccept]);

  return (
    <div className={cardCls}>
      <div className='flex items-center gap-2 mb-2'>
        <span className='text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]'>
          🗣️ AI 소비자 토론
        </span>
        {phase === 'running' && (
          <>
            <div className='w-3.5 h-3.5 border-2 border-[#E5E8EB] dark:border-[#2D3748] border-t-[#3182F6] dark:border-t-[#5B9DF9] rounded-full animate-spin' />
            <span className='text-[11px] text-[#8B95A1]'>{stageMsg}</span>
            <span className='ml-auto text-[11px] text-[#8B95A1]'>{pct}%</span>
          </>
        )}
        {phase === 'done' && (
          <span className='text-[11px] text-[#00C471]'>완료</span>
        )}
      </div>

      {topic && (
        <p className='text-[12px] text-[#4E5968] dark:text-[#9CA3AF] mb-2 leading-snug'>
          <span className='font-semibold text-[#3182F6]'>주제 </span>
          {topic}
        </p>
      )}

      {phase === 'error' ? (
        <p className='text-sm text-[#F04452]'>토론 실패: {err}</p>
      ) : (
        <div
          ref={logRef}
          className='max-h-[340px] overflow-y-auto space-y-3 pr-1'>
          {utterances.length === 0 && phase === 'running' && (
            <p className='text-[12px] text-[#B0B8C1] py-2'>
              참가자들이 의견을 준비하고 있어요...
            </p>
          )}
          {utterances.map((u, i) => {
            const st = STANCE[u.stance];
            return (
              <div key={i} className='flex gap-2'>
                <div
                  className={`shrink-0 w-7 h-7 rounded-full ${avatarColor(u.role)} text-white text-[11px] font-bold flex items-center justify-center`}>
                  {u.persona_name.charAt(0) || '?'}
                </div>
                <div className='min-w-0 flex-1'>
                  <div className='flex flex-wrap items-center gap-1.5 mb-0.5'>
                    <span className='text-[11px] font-medium text-[#191F28] dark:text-[#F2F4F6]'>
                      {u.persona_name}
                    </span>
                    {u.role && (
                      <span className='text-[10px] text-[#8B95A1] dark:text-[#6B7280]'>
                        {u.role}
                      </span>
                    )}
                    <span className='flex items-center gap-1 text-[10px] text-[#8B95A1]'>
                      <span className={`w-1.5 h-1.5 rounded-full ${st.dot}`} />
                      {st.label}
                    </span>
                    {u.round > 0 && (
                      <span className='text-[10px] text-[#B0B8C1]'>
                        R{u.round} {u.phase}
                      </span>
                    )}
                  </div>
                  <div className='inline-block px-3 py-2 rounded-2xl rounded-tl-sm bg-[#F9FAFB] dark:bg-[#252D3D] border border-[#E5E8EB] dark:border-[#2D3748]'>
                    <p className='text-[13px] text-[#191F28] dark:text-[#F2F4F6] leading-relaxed whitespace-pre-wrap'>
                      {u.text}
                    </p>
                  </div>
                  {u.lever && (
                    <p className='text-[11px] text-[#B0B8C1] dark:text-[#4B5563] mt-0.5 pl-1'>
                      개선 레버: {u.lever}
                    </p>
                  )}
                </div>
              </div>
            );
          })}
          {summaries.map((s, i) => (
            <p
              key={`sum-${i}`}
              className='text-[11px] text-center text-[#8B95A1] dark:text-[#6B7280] border-t border-dashed border-[#E5E8EB] dark:border-[#2D3748] pt-2'>
              R{s.round} 정리 · {s.text}
            </p>
          ))}
        </div>
      )}

      {/* 완료 후 — 토론 요약 버튼 + 모든 결과가 나온 뒤 개선 제안(토론 종료 후 진행) */}
      {phase === 'done' && (
        <div className='mt-3 space-y-2'>
          {!summaryShown && (
            <button
              onClick={() => {
                setSummaryShown(true);
                onSummary?.(runId);
              }}
              className='w-full py-2 rounded-lg border border-[#3182F6]/30 text-[#3182F6] text-sm font-semibold hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F] transition-colors'>
              📝 토론 요약 보기
            </button>
          )}
          {onAccept &&
            (loop && !loop.canImprove ? (
              <div className='rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] bg-[#F9FAFB] dark:bg-[#252D3D] px-3 py-2.5 text-[12px] text-[#4E5968] dark:text-[#9CA3AF]'>
                ✅ 개선 루프 {loop.count}/{loop.max}턴을 다 돌았어요. 충분히 다듬었으니,
                새 방향은 새 채팅에서 시작해 주세요.
              </div>
            ) : (
              <ApprovalWidget
                approval={{
                  action: 'run_generator',
                  label: '개선 시안 만들기',
                  reasons: [
                    '토론에서 나온 개선 방향을 반영해 새 시안을 만들어볼까요?',
                  ],
                }}
                onAccept={onAccept}
                disabled={proposalDisabled}
              />
            ))}
        </div>
      )}
    </div>
  );
}
