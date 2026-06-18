'use client';
// 시뮬 반응(reactions)으로 페르소나 토론을 돌리고, 여러 세션을 보관·전환하며 종료 후 같은 창에서 Q&A까지.
// 흐름: 마운트 시 DB 저장 토론 복원 → 없으면 첫 토론 자동 시작 → SSE(발언 실시간·진행바) → completed → 결과 박스.
// 한 시뮬에 토론 여러 번 가능 → 세션 탭으로 전환. 복원 세션은 runId 없음(Q&A 불가, 결과·로그만 표시).

import { useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import type {
  DebateResult,
  DebateSessionDetail,
  DebateSSEEvent,
  DebateStance,
  DebateTopic,
  ObjectiveFit,
  QAEvent,
  ReportView,
  SimAdAnalysis,
  SimPersona,
  SimPersonaReaction,
  SimRubricScore,
} from '@/lib/types';

interface DebatePanelProps {
  reactions: SimPersonaReaction[];
  adAnalysis: SimAdAnalysis | null;
  personas: SimPersona[];
  simulationId?: string;
  objectiveFit?: ObjectiveFit | null; // 토론 /start에 동봉 → ReportView 메인 판정
  rubricScores?: SimRubricScore[]; // 토론 /start에 동봉 → 리포트 §4 진단
  // 활성 세션의 통합 리포트를 부모('최종 결과' 영역)로 올린다. 토론 전·복원본은 null.
  onReportView?: (rv: ReportView | null) => void;
}

// 채팅 타임라인 1건 — 토론 발언/진행자 + Q&A 질문/답변/주최자(한 스트림에 통합).
type ChatMsg =
  | {
      kind: 'utterance';
      round: number;
      phase: string;
      persona_name: string;
      role: string;
      engine: string;
      stance: DebateStance;
      text: string;
      lever: string;
    }
  | {
      kind: 'judge';
      variant: 'topic' | 'round' | 'final';
      round?: number;
      text: string;
    }
  | { kind: 'qa_question'; text: string }
  | {
      kind: 'qa_answer';
      persona_name: string;
      role: string;
      engine: string;
      stance: DebateStance;
      text: string;
      lever: string;
    }
  | { kind: 'qa_moderator'; text: string };

// 토론 세션 1건 — 한 시뮬에 여러 토론을 보관·전환.
interface DebateSession {
  id: string;
  title: string;
  status: 'running' | 'done' | 'error';
  runId: string | null;
  messages: ChatMsg[];
  result: DebateResult | null;
  pct: number;
  stageMsg: string;
  errorMsg: string | null;
  qaBusy: boolean;
  restored?: boolean; // DB에서 복원된 과거 토론(runId 없음 → Q&A 불가)
}

// DB 저장 토론 상세(DebateSessionDetail) → 채팅 메시지 복원(주제·라운드 발언·라운드 정리·최종 결론).
function buildRestoredMessages(d: DebateSessionDetail): ChatMsg[] {
  const messages: ChatMsg[] = [];
  const topicText = d.topic ?? d.headline ?? '';
  if (topicText)
    messages.push({ kind: 'judge', variant: 'topic', text: topicText });

  const rounds = [...new Set(d.utterances.map(u => u.round))].sort(
    (a, b) => a - b
  );
  for (const r of rounds) {
    for (const u of d.utterances.filter(x => x.round === r)) {
      messages.push({
        kind: 'utterance',
        round: u.round,
        phase: u.phase ?? '',
        persona_name: u.persona_name ?? u.persona_id ?? '?',
        role: u.role ?? '',
        engine: u.engine ?? '',
        stance: u.stance ?? 'neutral',
        text: u.text ?? '',
        lever: u.lever ?? '',
      });
    }
    const summary = d.round_summaries?.[String(r)];
    if (summary)
      messages.push({
        kind: 'judge',
        variant: 'round',
        round: r,
        text: summary,
      });
  }
  if (d.final?.headline)
    messages.push({ kind: 'judge', variant: 'final', text: d.final.headline });
  return messages;
}

// DB 상세 → DebateOutcome가 쓰는 DebateResult 형태 재구성(analysis·aggregate·panel은 미저장 → 생략).
function buildRestoredResult(d: DebateSessionDetail): DebateResult {
  const final = d.final;
  const topic = d.topic ?? d.headline ?? '';
  return {
    run_id: '',
    simulation_id: d.simulation_id,
    debate_id: d.debate_id,
    topic: { headline: topic, diagnosis: '', question: '', primary_signal: '' },
    debate: {
      topic,
      rounds_run: d.rounds_run ?? 0,
      stop_reason: d.stop_reason ?? '',
      models: {
        judge: d.models?.judge ?? undefined,
        engines: d.models?.engines ?? [],
      },
      participants: [],
      round_summaries: d.round_summaries ?? {},
      proposed_actions: [],
      final,
    },
    report: {
      headline: final?.headline ?? d.headline ?? '',
      plain_summary: final?.plain_summary ?? d.plain_summary ?? '',
      topic,
      debate_available: true,
      rounds_run: d.rounds_run ?? 0,
      stop_reason: d.stop_reason ?? null,
      consensus: final?.consensus ?? [],
      dissent: final?.dissent ?? [],
      ranked_actions: final?.ranked_actions ?? [],
      quotes: [],
      consumer_groups: {},
    },
  };
}

// DB 상세 → 복원 세션(완료 상태). id는 debate_id 기반(라이브 세션과 충돌 없음).
function buildRestoredSession(d: DebateSessionDetail): DebateSession {
  return {
    id: `restored-${d.debate_id}`,
    title: d.headline ?? d.topic ?? '저장된 토론',
    status: 'done',
    runId: null,
    messages: buildRestoredMessages(d),
    result: buildRestoredResult(d),
    pct: 100,
    stageMsg: '',
    errorMsg: null,
    qaBusy: false,
    restored: true,
  };
}

export const STANCE_STYLE: Record<
  DebateStance,
  { label: string; dot: string }
> = {
  positive: { label: '긍정', dot: 'bg-[#00C471]' },
  neutral: { label: '중립', dot: 'bg-[#B0B8C1]' },
  negative: { label: '부정', dot: 'bg-[#F04452]' },
};

// 역할별 아바타 색 — 한눈에 누가 어떤 진영인지.
export const ROLE_AVATAR: Record<string, string> = {
  '도메인 전문가(제품·카테고리)': 'bg-[#7C5CFC]',
  '도메인 전문가(시장·유통)': 'bg-[#5B8DEF]',
  '마케팅 전문가(퍼포먼스)': 'bg-[#00B8B8]',
  '마케팅 전문가(브랜드)': 'bg-[#22A06B]',
  피벗: 'bg-[#3182F6]',
  완주자: 'bg-[#00C471]',
  비판자: 'bg-[#F04452]',
  미온: 'bg-[#8B95A1]',
};

const STOP_LABEL: Record<string, string> = {
  consensus: '합의 도달',
  dissensus: '이견 잔존',
  max: '최대 라운드',
};

const cardCls =
  'bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-6 transition-colors';
const chipIdle =
  'border-[#E5E8EB] dark:border-[#2D3748] text-[#8B95A1] dark:text-[#6B7280] hover:border-[#3182F6]';
const chipActive =
  'border-[#3182F6] bg-[#EEF4FF] dark:bg-[#1E3A5F] text-[#3182F6]';
export const engineBadge =
  'px-1.5 py-0.5 rounded text-[10px] font-mono bg-[#F2F4F6] dark:bg-[#252D3D] text-[#8B95A1] dark:text-[#6B7280]';

export function avatarColor(role: string): string {
  return ROLE_AVATAR[role] ?? 'bg-[#8B95A1]';
}

export function DebatePanel({
  reactions,
  adAnalysis,
  personas,
  simulationId,
  objectiveFit,
  rubricScores,
  onReportView,
}: DebatePanelProps) {
  const [sessions, setSessions] = useState<DebateSession[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [layCount] = useState<2 | 3 | 4>(3); // 첫 토론 기본값(지정 불필요)
  // 화면 단계: active(세션 보는 중) / topic_select(추가 토론 논제).
  const [view, setView] = useState<'active' | 'topic_select'>('active');
  const [topics, setTopics] = useState<DebateTopic[]>([]);
  const [topicsLoading, setTopicsLoading] = useState(false);
  const [topicsError, setTopicsError] = useState<string | null>(null);
  const [qaInput, setQaInput] = useState('');

  const esRef = useRef<EventSource | null>(null);
  const seqRef = useRef(0);
  const initRef = useRef(false);

  const active = sessions.find(s => s.id === activeId) ?? null;

  useEffect(() => () => esRef.current?.close(), []);

  // 활성 세션의 통합 리포트를 부모('최종 결과' 영역)로 올린다 — 탭 전환·완료 시 갱신.
  const activeReportView = active?.result?.report_view ?? null;
  useEffect(() => {
    onReportView?.(activeReportView);
    // onReportView는 매 렌더 새 함수일 수 있어 의존성에서 제외(값만 추적).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeReportView]);

  function patch(id: string, p: Partial<DebateSession>) {
    setSessions(prev => prev.map(s => (s.id === id ? { ...s, ...p } : s)));
  }
  function append(id: string, m: ChatMsg) {
    setSessions(prev =>
      prev.map(s => (s.id === id ? { ...s, messages: [...s.messages, m] } : s))
    );
  }

  // 추가 토론 논제 후보 5개 조회 → 선택 화면으로.
  async function enterTopicSelect() {
    setView('topic_select');
    setTopics([]);
    setTopicsError(null);
    setTopicsLoading(true);
    try {
      const { topics: fetched } = await api.debate.topics({
        reactions,
        ad_analysis: adAnalysis ?? undefined,
        personas: personas.length > 0 ? personas : undefined,
      });
      setTopics([...fetched].sort((a, b) => a.ranking - b.ranking));
    } catch (e) {
      setTopicsError(e instanceof Error ? e.message : '논제 후보 조회 실패');
    } finally {
      setTopicsLoading(false);
    }
  }

  // 토론 시작 — 새 세션 추가 후 SSE 구독(이전 세션들은 보관). 제목은 topic 이벤트로 채운다.
  async function startDebate(topic?: DebateTopic) {
    esRef.current?.close();
    esRef.current = null;
    const n = ++seqRef.current;
    const id = `sess-${n}-${Date.now()}`;
    const title = topic?.headline ?? '토론 주제 분석 중…';
    setSessions(prev => [
      ...prev,
      {
        id,
        title,
        status: 'running',
        runId: null,
        messages: [],
        result: null,
        pct: 0,
        stageMsg: '',
        errorMsg: null,
        qaBusy: false,
      },
    ]);
    setActiveId(id);
    setView('active');

    try {
      const { run_id } = await api.debate.start(
        {
          reactions,
          ad_analysis: adAnalysis ?? undefined,
          personas: personas.length > 0 ? personas : undefined,
          simulation_id: simulationId,
          topic,
          rubric_scores:
            rubricScores && rubricScores.length > 0 ? rubricScores : undefined,
          objective_fit: objectiveFit ?? undefined,
        },
        { layCount }
      );
      patch(id, { runId: run_id });

      const es = api.debate.stream(run_id);
      esRef.current = es;

      es.onmessage = (ev: MessageEvent) => {
        let data: DebateSSEEvent;
        try {
          data = JSON.parse(ev.data) as DebateSSEEvent;
        } catch {
          return;
        }

        if (data.event === 'error') {
          patch(id, {
            status: 'error',
            errorMsg: data.message ?? '토론 진행 중 오류',
          });
          es.close();
          esRef.current = null;
          return;
        }

        if (typeof data.pct === 'number') patch(id, { pct: data.pct });

        if (data.stage === 'topic' && data.headline) {
          append(id, { kind: 'judge', variant: 'topic', text: data.headline });
          // 세션 탭에 실제 주제 표시.
          patch(id, { stageMsg: '토론 주제 제시', title: data.headline });
        } else if (data.stage === 'utterance' && data.text) {
          append(id, {
            kind: 'utterance',
            round: data.round ?? 0,
            phase: data.phase ?? '',
            persona_name: data.persona_name ?? data.persona_id ?? '?',
            role: data.role ?? '',
            engine: data.engine ?? '',
            stance: data.stance ?? 'neutral',
            text: data.text,
            lever: data.lever ?? '',
          });
          patch(id, {
            stageMsg: `R${data.round} ${data.phase} · ${data.persona_name}`,
          });
        } else if (data.stage === 'round_summary') {
          append(id, {
            kind: 'judge',
            variant: 'round',
            round: data.round,
            text: data.summary ?? '',
          });
        } else if (data.stage === 'judge_final' && data.headline) {
          append(id, { kind: 'judge', variant: 'final', text: data.headline });
          patch(id, { stageMsg: '최종 결론 종합' });
        } else if (data.stage) {
          const labels: Record<string, string> = {
            analysis: '반응 분석',
            kpi: 'KPI 확정',
            selection: '패널 구성',
            assignment: '엔진·이름 배정',
            report: '리포트 조립',
          };
          if (labels[data.stage]) patch(id, { stageMsg: labels[data.stage] });
        }

        if (data.event === 'completed') {
          es.close();
          esRef.current = null;
          api.debate
            .result(run_id)
            .then(r => patch(id, { result: r, status: 'done', pct: 100 }))
            .catch(e =>
              patch(id, {
                status: 'error',
                errorMsg: e instanceof Error ? e.message : '결과 조회 실패',
              })
            );
        }
      };

      es.onerror = () => {
        if (esRef.current) {
          patch(id, { status: 'error', errorMsg: '스트림 연결이 끊겼습니다.' });
          es.close();
          esRef.current = null;
        }
      };
    } catch (e) {
      patch(id, {
        status: 'error',
        errorMsg: e instanceof Error ? e.message : '토론 시작 실패',
      });
    }
  }

  // 마운트 시: DB에 저장된 과거 토론을 복원 → 없으면 첫 토론 자동 시작. StrictMode 중복 방지 ref.
  useEffect(() => {
    if (initRef.current) return;
    initRef.current = true;

    void (async () => {
      // 1) DB 저장 토론 복원(simulationId 있을 때만 — 없으면 인메모리만)
      if (simulationId) {
        try {
          const { debates: saved } =
            await api.debate.bySimulation(simulationId);
          if (saved.length > 0) {
            // 목록은 최신순(desc) → 시간순(오래된→최신)으로 뒤집어 탭·복원 순서를 맞춘다.
            const ordered = [...saved].reverse();
            const details = await Promise.all(
              ordered.map(s => api.debate.detail(s.debate_id).catch(() => null))
            );
            const built = details
              .filter((d): d is DebateSessionDetail => d !== null)
              .map(buildRestoredSession);
            if (built.length > 0) {
              setSessions(built);
              setActiveId(built[built.length - 1].id); // 가장 최근 토론을 활성 탭으로
              return; // 복원본이 있으면 새 토론 자동 시작 안 함
            }
          }
        } catch {
          // 복원 실패는 무시 — 아래에서 새 토론으로 진행
        }
      }

      // 2) 복원본이 없고 반응이 있으면 첫 토론 자동 시작
      if (reactions.length > 0) void startDebate();
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 종료된 토론에 이어 Q&A 질문 — 답변은 같은 채팅 스트림에 쌓인다.
  async function askQuestion() {
    const q = qaInput.trim();
    if (
      !q ||
      !active ||
      active.status !== 'done' ||
      !active.runId ||
      active.qaBusy
    )
      return;
    const id = active.id;
    const runId = active.runId;
    setQaInput('');
    append(id, { kind: 'qa_question', text: q });
    patch(id, { qaBusy: true, errorMsg: null });
    try {
      await api.debate.question(
        runId,
        { question: q, reactions, ad_analysis: adAnalysis ?? undefined },
        (ev: QAEvent) => {
          if (ev.event === 'error') {
            patch(id, { errorMsg: ev.message ?? 'Q&A 진행 중 오류' });
            return;
          }
          if (ev.event === 'completed') return;
          if (ev.stage === 'qa_moderator') {
            append(id, { kind: 'qa_moderator', text: ev.text });
          } else if (ev.stage === 'qa_utterance') {
            append(id, {
              kind: 'qa_answer',
              persona_name: ev.persona_name || ev.persona_id || '?',
              role: ev.role ?? '',
              engine: ev.engine ?? '',
              stance: ev.stance ?? 'neutral',
              text: ev.text ?? '',
              lever: ev.lever ?? '',
            });
          }
        }
      );
    } catch (e) {
      patch(id, {
        errorMsg: e instanceof Error ? e.message : '질문 전송 실패',
      });
    } finally {
      patch(id, { qaBusy: false });
    }
  }

  const passedCount = reactions.filter(r => r.qa_passed).length;

  return (
    <div className='flex h-full flex-col gap-6'>
      {/* 토론 카드 — 헤더 + 세션 탭 + 채팅 + Q&A 입력 */}
      <div className={cardCls}>
        <div className='flex items-center justify-between mb-1'>
          <h2 className='text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]'>
            페르소나 토론
          </h2>
          {sessions.length > 0 && view !== 'topic_select' && (
            <button
              onClick={enterTopicSelect}
              className='text-xs font-medium text-[#3182F6] hover:text-[#1B6EEB]'>
              + 추가 토론
            </button>
          )}
        </div>
        <p className='text-xs text-[#8B95A1] dark:text-[#6B7280] mb-4'>
          반응 {reactions.length}건(QA 통과 {passedCount})을 전문가 4명 + 일반인{' '}
          {layCount}명이 토론해 개선 방향을 도출합니다.
        </p>

        {/* 세션 탭 — 주제로 표시(임시: 다음 단계에서 프로젝트 패널로 이전) */}
        {sessions.length > 0 && (
          <div className='flex flex-wrap gap-1.5 mb-4'>
            {sessions.map(s => (
              <button
                key={s.id}
                onClick={() => {
                  setActiveId(s.id);
                  setView('active');
                }}
                title={s.title}
                className={`max-w-[200px] truncate px-2.5 py-1 rounded-lg text-xs font-medium border transition-colors ${
                  s.id === activeId && view === 'active' ? chipActive : chipIdle
                }`}>
                {s.status === 'running' && (
                  <span className='inline-block w-1.5 h-1.5 rounded-full bg-[#3182F6] animate-pulse mr-1 align-middle' />
                )}
                {s.status === 'error' && (
                  <span className='text-[#F04452] mr-0.5'>!</span>
                )}
                {s.title}
              </button>
            ))}
          </div>
        )}

        {view === 'topic_select' ? (
          <TopicSelect
            topics={topics}
            loading={topicsLoading}
            error={topicsError}
            onPick={t => startDebate(t)}
            onRetry={enterTopicSelect}
            onCancel={() => setView('active')}
          />
        ) : active ? (
          <div className='space-y-4'>
            {/* 진행바 — 토론 진행 중 pct 표시 */}
            {active.status === 'running' && (
              <div className='space-y-2'>
                <div className='flex justify-between text-xs'>
                  <span className='text-[#8B95A1] dark:text-[#6B7280] flex items-center gap-1.5'>
                    <span className='w-1.5 h-1.5 rounded-full bg-[#3182F6] animate-pulse' />
                    {active.stageMsg || '토론 준비 중…'}
                  </span>
                  <span className='font-medium text-[#191F28] dark:text-[#F2F4F6]'>
                    {active.pct}%
                  </span>
                </div>
                <div className='w-full bg-[#F2F4F6] dark:bg-[#252D3D] rounded-full h-2 overflow-hidden'>
                  <div
                    className='h-full bg-[#3182F6] rounded-full transition-all duration-300'
                    style={{ width: `${active.pct}%` }}
                  />
                </div>
              </div>
            )}

            {active.errorMsg && (
              <div className='px-4 py-2.5 bg-[#FEF2F2] dark:bg-[#3B0D0D] rounded-xl border border-[#FECACA] dark:border-[#7F1D1D] text-sm text-[#DC2626] dark:text-[#FCA5A5]'>
                {active.errorMsg}
              </div>
            )}

            {/* 채팅 — 토론 발언 + Q&A 통합 스트림(고정 height) */}
            <ChatView
              messages={active.messages}
              typing={active.status === 'running' || active.qaBusy}
            />

            {/* Q&A 입력 — 토론 끝나기 전 비활성 */}
            <div className='flex items-end gap-2'>
              <textarea
                value={qaInput}
                onChange={e => setQaInput(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    askQuestion();
                  }
                }}
                rows={1}
                placeholder={
                  active.restored
                    ? '저장된 토론이에요 — Q&A는 새 토론에서 가능합니다'
                    : active.status === 'done'
                      ? '페르소나에게 질문하기 (Enter 전송 · Shift+Enter 줄바꿈)'
                      : '토론이 끝나면 질문할 수 있어요'
                }
                disabled={
                  active.status !== 'done' || active.qaBusy || !!active.restored
                }
                className='flex-1 px-4 py-2.5 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#252D3D] text-sm text-[#191F28] dark:text-[#F2F4F6] focus:outline-none focus:ring-2 focus:ring-[#3182F6] placeholder:text-[#B0B8C1] dark:placeholder:text-[#4B5563] transition-colors resize-none disabled:opacity-50'
              />
              <button
                onClick={askQuestion}
                disabled={
                  active.status !== 'done' ||
                  active.qaBusy ||
                  !!active.restored ||
                  !qaInput.trim()
                }
                className='shrink-0 px-5 py-2.5 bg-[#3182F6] hover:bg-[#1B6EEB] disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-xl text-sm font-semibold transition-colors'>
                전송
              </button>
            </div>
          </div>
        ) : (
          <div className='flex items-center gap-2 text-xs text-[#8B95A1] dark:text-[#6B7280] py-10 justify-center'>
            <span className='w-1.5 h-1.5 rounded-full bg-[#3182F6] animate-pulse' />
            토론을 시작하는 중…
          </div>
        )}
      </div>

      {/* 토론 결과 — 항상 박스 표시(완료 전엔 안내). 컬럼 남은 높이를 flex-1로 채움 */}
      {view === 'active' && (
        <div className={`${cardCls} flex-1`}>
          <h2 className='text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-4'>
            토론 결과
          </h2>
          {active?.status === 'done' && active.result ? (
            <DebateOutcome result={active.result} />
          ) : (
            <p className='text-sm text-[#8B95A1] dark:text-[#6B7280]'>
              토론이 끝나면 결과가 여기에 표시됩니다.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

/* ─── 추가 토론 논제 선택 ─── */
function TopicSelect({
  topics,
  loading,
  error,
  onPick,
  onRetry,
  onCancel,
}: {
  topics: DebateTopic[];
  loading: boolean;
  error: string | null;
  onPick: (t: DebateTopic) => void;
  onRetry: () => void;
  onCancel: () => void;
}) {
  return (
    <div className='space-y-4'>
      <div className='flex items-center justify-between'>
        <p className='text-xs font-semibold text-[#4E5968] dark:text-[#9CA3AF]'>
          추가로 다룰 논제를 하나 고르세요
        </p>
        <button
          onClick={onCancel}
          className='text-xs text-[#8B95A1] dark:text-[#6B7280] hover:text-[#3182F6]'>
          취소
        </button>
      </div>

      {loading && (
        <div className='flex items-center gap-2 text-xs text-[#8B95A1] dark:text-[#6B7280] py-6 justify-center'>
          <span className='w-1.5 h-1.5 rounded-full bg-[#3182F6] animate-pulse' />
          논제 후보를 분석하는 중…
        </div>
      )}

      {error && (
        <div className='px-4 py-2.5 bg-[#FEF2F2] dark:bg-[#3B0D0D] rounded-xl border border-[#FECACA] dark:border-[#7F1D1D] text-sm text-[#DC2626] dark:text-[#FCA5A5]'>
          {error}
          <button
            onClick={onRetry}
            className='ml-2 underline hover:no-underline'>
            다시 시도
          </button>
        </div>
      )}

      {!loading && !error && topics.length > 0 && (
        <div className='space-y-2'>
          {topics.map(t => (
            <button
              key={t.topic_id}
              type='button'
              onClick={() => onPick(t)}
              className='w-full text-left p-4 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] hover:border-[#3182F6] hover:bg-[#EEF4FF] dark:hover:bg-[#1E3A5F]/40 transition-colors group'>
              <div className='flex items-start gap-3'>
                <span className='shrink-0 w-6 h-6 rounded-full bg-[#F2F4F6] dark:bg-[#252D3D] group-hover:bg-[#3182F6] group-hover:text-white text-[#8B95A1] dark:text-[#6B7280] text-xs font-bold flex items-center justify-center transition-colors'>
                  {t.ranking}
                </span>
                <div className='min-w-0 flex-1'>
                  <p className='text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] leading-snug'>
                    {t.headline}
                  </p>
                  {t.question && (
                    <p className='text-xs text-[#4E5968] dark:text-[#9CA3AF] mt-1 leading-relaxed'>
                      {t.question}
                    </p>
                  )}
                  <div className='flex flex-wrap items-center gap-1.5 mt-2'>
                    {t.primary_signal && (
                      <span className='px-2 py-0.5 rounded-full bg-[#F2F4F6] dark:bg-[#252D3D] text-[10px] text-[#8B95A1] dark:text-[#6B7280]'>
                        {t.primary_signal}
                      </span>
                    )}
                    <span className='px-2 py-0.5 rounded-full bg-[#EEF4FF] dark:bg-[#1E3A5F] text-[10px] text-[#3182F6]'>
                      신뢰도 {(t.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                </div>
              </div>
            </button>
          ))}
        </div>
      )}

      {!loading && !error && topics.length === 0 && (
        <p className='text-xs text-[#B0B8C1] dark:text-[#4B5563] py-6 text-center'>
          제안할 논제가 없습니다.
        </p>
      )}
    </div>
  );
}

/* ─── 채팅뷰 (단톡방 스타일) — 토론 발언 + Q&A 통합, 고정 height ─── */
function ChatView({
  messages,
  typing = false,
}: {
  messages: ChatMsg[];
  typing?: boolean;
}) {
  const boxRef = useRef<HTMLDivElement | null>(null);

  // 새 메시지가 오면 맨 아래로 스크롤.
  useEffect(() => {
    if (boxRef.current) boxRef.current.scrollTop = boxRef.current.scrollHeight;
  }, [messages.length, typing]);

  return (
    <div
      ref={boxRef}
      className='h-[460px] overflow-y-auto rounded-xl bg-[#F9FAFB] dark:bg-[#161C29] border border-[#E5E8EB] dark:border-[#2D3748] p-4 space-y-3'>
      {messages.length === 0 ? (
        <p className='text-xs text-[#B0B8C1] dark:text-[#4B5563] py-6 text-center'>
          곧 진행자가 토론 주제를 제시합니다…
        </p>
      ) : (
        messages.map((m, i) => {
          const prev = messages[i - 1];
          // 라운드가 바뀌는 발언 앞에 구분 칩.
          const showRound =
            m.kind === 'utterance' &&
            (prev?.kind !== 'utterance' || prev.round !== m.round);
          return (
            <div key={i}>
              {showRound && m.kind === 'utterance' && (
                <div className='flex items-center gap-2 my-2'>
                  <div className='flex-1 h-px bg-[#E5E8EB] dark:bg-[#2D3748]' />
                  <span className='text-[10px] font-medium text-[#B0B8C1] dark:text-[#4B5563]'>
                    라운드 {m.round} · {m.phase}
                  </span>
                  <div className='flex-1 h-px bg-[#E5E8EB] dark:bg-[#2D3748]' />
                </div>
              )}
              <ChatBubble msg={m} />
            </div>
          );
        })
      )}
      {typing && messages.length > 0 && (
        <div className='flex items-center gap-1 pl-1 text-[#B0B8C1] dark:text-[#4B5563]'>
          <span className='w-1.5 h-1.5 rounded-full bg-current animate-bounce [animation-delay:-0.2s]' />
          <span className='w-1.5 h-1.5 rounded-full bg-current animate-bounce [animation-delay:-0.1s]' />
          <span className='w-1.5 h-1.5 rounded-full bg-current animate-bounce' />
        </div>
      )}
    </div>
  );
}

/* ─── 채팅 버블 1건 ─── */
function ChatBubble({ msg }: { msg: ChatMsg }) {
  // 내 질문 — 오른쪽 파란 말풍선.
  if (msg.kind === 'qa_question') {
    return (
      <div className='chat-pop flex justify-end'>
        <div className='max-w-[80%] inline-block px-3 py-2 rounded-2xl rounded-tr-sm bg-[#3182F6] text-white'>
          <p className='text-sm leading-relaxed'>{msg.text}</p>
        </div>
      </div>
    );
  }

  // 진행자(토론) / 주최자(Q&A) — 가운데 공지.
  if (msg.kind === 'judge' || msg.kind === 'qa_moderator') {
    const label =
      msg.kind === 'qa_moderator'
        ? '주최자'
        : msg.variant === 'topic'
          ? '진행자 · 토론 주제'
          : msg.variant === 'final'
            ? '진행자 · 최종 결론'
            : `진행자 · R${msg.round} 정리`;
    return (
      <div className='chat-pop flex justify-center'>
        <div className='max-w-[88%] text-center px-3 py-2 rounded-xl bg-[#EEF4FF] dark:bg-[#1E2A44] border border-[#D5E3FB] dark:border-[#26395C]'>
          <p className='text-[10px] font-semibold text-[#3182F6] mb-0.5'>
            {label}
          </p>
          <p className='text-xs text-[#4E5968] dark:text-[#C4CCD6] leading-relaxed'>
            {msg.text}
          </p>
        </div>
      </div>
    );
  }

  // 페르소나 발언(토론) / 답변(Q&A) — 왼쪽.
  const st = STANCE_STYLE[msg.stance];
  const initial = msg.persona_name.charAt(0) || '?';
  return (
    <div className='chat-pop flex gap-2'>
      <div
        className={`shrink-0 w-8 h-8 rounded-full ${avatarColor(msg.role)} text-white text-xs font-bold flex items-center justify-center`}>
        {initial}
      </div>
      <div className='min-w-0 flex-1'>
        <div className='flex flex-wrap items-center gap-1.5 mb-0.5'>
          <span className='text-[11px] font-medium text-[#191F28] dark:text-[#F2F4F6]'>
            {msg.persona_name}
          </span>
          {msg.role && (
            <span className='text-[10px] text-[#8B95A1] dark:text-[#6B7280]'>
              {msg.role}
            </span>
          )}
          {msg.engine && <span className={engineBadge}>{msg.engine}</span>}
          <span className='flex items-center gap-1 text-[10px] text-[#8B95A1] dark:text-[#6B7280]'>
            <span className={`w-1.5 h-1.5 rounded-full ${st.dot}`} />
            {st.label}
          </span>
        </div>
        <div className='inline-block px-3 py-2 rounded-2xl rounded-tl-sm bg-white dark:bg-[#252D3D] border border-[#E5E8EB] dark:border-[#2D3748]'>
          <p className='text-sm text-[#191F28] dark:text-[#F2F4F6] leading-relaxed'>
            {msg.text}
          </p>
        </div>
        {msg.lever && (
          <p className='text-[11px] text-[#B0B8C1] dark:text-[#4B5563] mt-0.5 pl-1'>
            개선 레버: {msg.lever}
          </p>
        )}
      </div>
    </div>
  );
}

/* ─── 토론 결론 (채팅 로그는 위 ChatView가 담당, 여기선 결론만) ─── */
function DebateOutcome({ result }: { result: DebateResult }) {
  const rep = result.report;
  const debate = result.debate;
  const roundSummaries = debate?.round_summaries ?? {};

  return (
    <div className='space-y-5'>
      {/* 메타 배지 */}
      <div className='flex flex-wrap gap-2 text-xs'>
        <span className='px-2.5 py-1 rounded-full bg-[#EEF4FF] dark:bg-[#1E3A5F] text-[#3182F6]'>
          {rep.rounds_run}라운드
        </span>
        {rep.stop_reason && (
          <span className='px-2.5 py-1 rounded-full bg-[#F2F4F6] dark:bg-[#252D3D] text-[#4E5968] dark:text-[#9CA3AF]'>
            {STOP_LABEL[rep.stop_reason] ?? rep.stop_reason}
          </span>
        )}
        {debate?.models.judge && (
          <span className='px-2.5 py-1 rounded-full bg-[#F2F4F6] dark:bg-[#252D3D] text-[#4E5968] dark:text-[#9CA3AF]'>
            Judge {debate.models.judge}
          </span>
        )}
        {debate?.models.engines && (
          <span className='px-2.5 py-1 rounded-full bg-[#F2F4F6] dark:bg-[#252D3D] text-[#4E5968] dark:text-[#9CA3AF]'>
            토론자 {debate.models.engines.join('·')}
          </span>
        )}
      </div>

      {/* 비전문가용 쉬운 결론 (강조) */}
      {rep.plain_summary && (
        <div className='rounded-xl bg-[#EEF4FF] dark:bg-[#162844] border border-[#D5E3FB] dark:border-[#1E3A5F] p-4'>
          <p className='text-xs font-semibold text-[#3182F6] mb-1.5'>
            한눈에 보는 결론
          </p>
          <p className='text-[15px] leading-relaxed text-[#191F28] dark:text-[#F2F4F6]'>
            {rep.plain_summary}
          </p>
        </div>
      )}

      {/* 전문가용 진단 헤드라인 */}
      <div>
        <p className='text-xs font-semibold text-[#8B95A1] dark:text-[#6B7280] mb-1'>
          진단 (전문가용)
        </p>
        <p className='text-sm text-[#191F28] dark:text-[#F2F4F6] leading-relaxed'>
          {rep.headline}
        </p>
      </div>

      {/* 합의 / 이견 */}
      <div className='grid grid-cols-1 md:grid-cols-2 gap-4'>
        {rep.consensus.length > 0 && (
          <div>
            <p className='text-xs font-semibold text-[#00A661] mb-1.5'>
              합의점
            </p>
            <ul className='space-y-1'>
              {rep.consensus.map((c, i) => (
                <li
                  key={i}
                  className='text-sm text-[#4E5968] dark:text-[#9CA3AF] flex gap-1.5'>
                  <span className='text-[#00A661]'>•</span>
                  <span>{c}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {rep.dissent.length > 0 && (
          <div>
            <p className='text-xs font-semibold text-[#F4A100] mb-1.5'>이견</p>
            <ul className='space-y-1'>
              {rep.dissent.map((d, i) => (
                <li
                  key={i}
                  className='text-sm text-[#4E5968] dark:text-[#9CA3AF] flex gap-1.5'>
                  <span className='text-[#F4A100]'>•</span>
                  <span>{d}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* 개선안 순위 */}
      {rep.ranked_actions.length > 0 && (
        <div>
          <p className='text-xs font-semibold text-[#8B95A1] dark:text-[#6B7280] mb-2'>
            개선안 (우선순위)
          </p>
          <div className='space-y-2'>
            {rep.ranked_actions.map(a => (
              <div
                key={a.rank}
                className='flex gap-3 p-3 rounded-xl bg-[#F9FAFB] dark:bg-[#252D3D] border border-[#E5E8EB] dark:border-[#2D3748]'>
                <span className='shrink-0 w-6 h-6 rounded-full bg-[#3182F6] text-white text-xs font-bold flex items-center justify-center'>
                  {a.rank}
                </span>
                <div className='min-w-0'>
                  <p className='text-sm font-medium text-[#191F28] dark:text-[#F2F4F6]'>
                    {a.action}
                  </p>
                  {a.expected_effect && (
                    <p className='text-xs text-[#8B95A1] dark:text-[#6B7280] mt-0.5'>
                      기대효과: {a.expected_effect}
                    </p>
                  )}
                  {a.supporting_personas.length > 0 && (
                    <p className='text-[11px] text-[#B0B8C1] dark:text-[#4B5563] mt-0.5'>
                      뒷받침: {a.supporting_personas.join(', ')}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 라운드 정리 (있으면) */}
      {Object.keys(roundSummaries).length > 0 && (
        <div>
          <p className='text-xs font-semibold text-[#8B95A1] dark:text-[#6B7280] mb-1.5'>
            라운드 정리
          </p>
          <ul className='space-y-1'>
            {Object.entries(roundSummaries).map(([round, summary]) => (
              <li
                key={round}
                className='text-xs text-[#4E5968] dark:text-[#9CA3AF]'>
                <span className='font-medium'>R{round}</span> · {summary}
              </li>
            ))}
          </ul>
        </div>
      )}

      {!rep.debate_available && (
        <p className='text-xs text-[#F4A100]'>
          토론 미실행 상태의 리포트입니다(KPI·분석만). 토론 엔진을 확인하세요.
        </p>
      )}
    </div>
  );
}
