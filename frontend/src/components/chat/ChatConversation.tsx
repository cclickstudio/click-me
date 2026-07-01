'use client';

// 채팅 대화 본체 — 메시지 렌더 + 입력 + 위젯 + 이미지 첨부 + SSE 전송. /chat 페이지와 플로팅 공용.
// 세션은 props로 제어(sessionId=null이면 새 채팅). 사이드바·프로젝트 게이트는 바깥에서 처리.
import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { getToken } from '@/lib/authApi';
import { formatRelativeKST, formatKSTFull } from '@/lib/datetime';
import SimFormWidget from './SimFormWidget';
import SimInputWidget from './SimInputWidget';
import SimResultWidget from './SimResultWidget';
import DebateStreamWidget from './DebateStreamWidget';
import DebateSummaryWidget from './DebateSummaryWidget';
import GenFormWidget from './GenFormWidget';
import GenResultWidget from './GenResultWidget';
import SimGenListWidget from './SimGenListWidget';
import ActionCards, { type ActionCard } from './ActionCards';
import ApprovalWidget, { type ApprovalSpec } from './ApprovalWidget';
import BatchSimWidget from './BatchSimWidget';
import ReportWidget from './ReportWidget';
import AnalysisSummaryWidget from './AnalysisSummaryWidget';
import RecommendFormWidget from './RecommendFormWidget';
import KeywordWidget from './KeywordWidget';
import CitationChips from './CitationChips';
import PlanChecklist, { type PlanStep } from './PlanChecklist';
import ErrorCard from './ErrorCard';
// 챗→매니지먼트 카드(재이식) — widget.type=create_campaign|campaign_action으로 렌더.
import ChatCreateCampaignCard from './ChatCreateCampaignCard';
import ChatCampaignActionCard, { type CampaignActionPayload } from './ChatCampaignActionCard';
import ChatBudgetProposalCard, { type BudgetActionPayload } from './ChatBudgetProposalCard';
import type { CampaignPrefill } from '@/components/manage/campaigns/CampaignForm';
import type { SimRunResult } from '@/lib/types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

// 상대 프록시 URL(/api/...)은 API_BASE를 붙여 렌더. blob:·http:는 그대로 통과.
const fullUrl = (u?: string) =>
  u && u.startsWith('/') ? `${API_BASE}${u}` : u;

// N4 선제적 말걸기 — 미열람 완료 시뮬 결과를 챗봇이 먼저 알린다. 빈도 가드로 스팸 방지.
const PROACTIVE_GUARD_MS = 1000 * 60 * 20; // 프로젝트당 20분에 1회만 선제 알림
const PROACTIVE_RECENCY_MS = 1000 * 60 * 60 * 48; // 최근 48시간 내 완료만 대상(오래된 결과 제외)
const proactiveSeenKey = (pid: string) => `chat_proactive_seen_${pid}`; // 이미 알린 결과 id 집합
const proactiveLastKey = (pid: string) => `chat_proactive_last_${pid}`; // 마지막 선제 알림 시각

// 빈 상태 퀵스타트 — 예시 질문 프롬프트 대신 흐름을 바로 여는 액션 칩(P4/P14).
const welcomeActions: { label: string; cmd: string }[] = [
  { label: '🧪 시뮬 돌리기', cmd: '/시뮬레이션' },
  { label: '🎨 시안 만들기', cmd: '/제너레이터' },
  { label: '📊 리포트', cmd: '/리포트' },
  { label: '💡 전략 추천', cmd: '/추천' },
];

// Web Speech API — 브라우저 내장, 무료, API 키 불필요. Chrome/Edge 지원.
type SpeechRecCtor = new () => {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onend: (() => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  start(): void;
  stop(): void;
};
type SpeechWindow = Window & {
  SpeechRecognition?: SpeechRecCtor;
  webkitSpeechRecognition?: SpeechRecCtor;
};

type SlashCommand = { cmd: string; label: string; desc: string };
const slashCommands: SlashCommand[] = [
  {
    cmd: '/시뮬레이션',
    label: '/시뮬레이션',
    desc: '광고 시뮬레이션 입력 위젯을 띄웁니다',
  },
  {
    cmd: '/제너레이터',
    label: '/제너레이터',
    desc: '광고 생성 입력 위젯을 띄웁니다',
  },
  {
    cmd: '/배치',
    label: '/배치 (별칭 /AB)',
    desc: '광고 2개를 동시에 비교 시뮬레이션합니다',
  },
  {
    cmd: '/AB',
    label: '/AB',
    desc: '/배치와 동일 — 광고 2개 동시 비교 시뮬레이션',
  },
  {
    cmd: '/리포트',
    label: '/리포트',
    desc: '시뮬·생성 성과를 PDF 리포트로 받습니다',
  },
  {
    cmd: '/시뮬목록',
    label: '/시뮬목록',
    desc: '최근 시뮬레이션 목록을 봅니다',
  },
  {
    cmd: '/시안목록',
    label: '/시안목록',
    desc: '최근 생성 광고 시안 목록을 봅니다',
  },
  {
    cmd: '/분석',
    label: '/분석',
    desc: '과거 시뮬·생성 성과를 종합 요약합니다',
  },
  {
    cmd: '/추천',
    label: '/추천',
    desc: '목표·예산을 입력하면 전략·플랫폼을 추천합니다',
  },
  {
    cmd: '/비교',
    label: '/비교',
    desc: '시뮬레이션 2개의 KPI를 나란히 비교합니다',
  },
  {
    cmd: '/키워드',
    label: '/키워드',
    desc: '광고 맥락 기반 SNS 해시태그·키워드를 추천받습니다',
  },
  {
    cmd: '/도움말',
    label: '/도움말',
    desc: '사용 가능한 명령어와 예시를 봅니다',
  },
];

type Citation = { kind: string; source: string; title?: string };
type ListItem = {
  id: string;
  title: string;
  status?: string;
  created_at?: string | null;
  sample_size?: number;
  mode?: string;
};
type WidgetSpec = {
  type: string;
  mode?: 'read' | 'select' | 'compare';
  data?: {
    ad_content?: string;
    ad_title?: string;
    product_category?: string;
    ad_objective?: string;
    product_name?: string;
    product_description?: string;
    target_audience?: string;
    campaign_objective?: string;
    items?: ListItem[];
    project_id?: string;
    period?: string;
    simulation_id?: string; // sim_result·debate_stream 위젯 — 결과/토론 연결용
    run_id?: string; // debate_stream·debate_summary 위젯 — 토론 스트림/결과 조회용
    sample_size?: number; // sim_input 위젯 — 실제 돌린 가상 소비자 수
    generation_id?: string; // gen_result 위젯 — 생성 결과(후보·이미지) 조회용
    prefill?: CampaignPrefill; // create_campaign 위젯 — 캠페인 생성 폼 초기값
    action?: CampaignActionPayload | BudgetActionPayload; // campaign_action 위젯 — 조치 페이로드
  };
};
type SourceMeta = {
  source: string;
  label: string;
  engine?: string;
  citations?: Citation[];
  used_tools?: string[];
  widget?: WidgetSpec;
  approval?: ApprovalSpec; // 개선 루프 HITL 수락/거절 카드
  cards?: ActionCard[]; // Deep Agent·매니지먼트 추천 조치 카드(RESULT/REVIEW/ACTIONBAR)
  plan?: PlanStep[]; // Deep Agent 실행 계획(plan→act→observe) — 체크리스트로 표시
  error?: boolean; // 에러 메시지 — 공통 ErrorCard로 렌더 + 재시도(X1)
};
// 채팅으로 실제 돌린 시뮬/생성 결과 참조 — 내역에 남겨 재로드 시 "결과 보기" 링크로 렌더.
type ResultRef = { kind: 'sim' | 'gen'; id: string };
type Message = {
  id?: string; // DB 메시지 id(영속된 메시지에만)
  role: 'user' | 'assistant';
  content: string;
  meta?: SourceMeta;
  imageUrl?: string;
  imageFile?: File;
  result?: ResultRef;
  created_at?: string | null; // 영속 메시지의 생성 시각(상대시간 표시용, P9)
};

// 마지막에 추가한 목록 위젯 메시지(빈 items)에 비동기로 받아온 items를 채워 넣는다.
function patchLastListWidget(
  messages: Message[],
  type: string,
  items: ListItem[]
): Message[] {
  const idx = messages.map(m => m.meta?.widget?.type).lastIndexOf(type);
  if (idx < 0) return messages;
  return messages.map((m, i) =>
    i === idx && m.meta?.widget
      ? {
          ...m,
          meta: {
            ...m.meta,
            widget: {
              ...m.meta.widget,
              data: { ...m.meta.widget.data, items },
            },
          },
        }
      : m
  );
}

function SendIcon() {
  return (
    <svg
      width='18'
      height='18'
      viewBox='0 0 24 24'
      fill='none'
      stroke='currentColor'
      strokeWidth='2'
      strokeLinecap='round'
      strokeLinejoin='round'>
      <line x1='22' y1='2' x2='11' y2='13' />
      <polygon points='22 2 15 22 11 13 2 9 22 2' />
    </svg>
  );
}

function MicIcon() {
  return (
    <svg
      width='18'
      height='18'
      viewBox='0 0 24 24'
      fill='none'
      stroke='currentColor'
      strokeWidth='2'
      strokeLinecap='round'
      strokeLinejoin='round'>
      <path d='M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z' />
      <path d='M19 10v2a7 7 0 0 1-14 0v-2' />
      <line x1='12' y1='19' x2='12' y2='23' />
      <line x1='8' y1='23' x2='16' y2='23' />
    </svg>
  );
}

function SpeakerIcon() {
  return (
    <svg
      width='13'
      height='13'
      viewBox='0 0 24 24'
      fill='none'
      stroke='currentColor'
      strokeWidth='2'
      strokeLinecap='round'
      strokeLinejoin='round'>
      <polygon points='11 5 6 9 2 9 2 15 6 15 11 19 11 5' />
      <path d='M15.54 8.46a5 5 0 0 1 0 7.07' />
      <path d='M19.07 4.93a10 10 0 0 1 0 14.14' />
    </svg>
  );
}

function TypingIndicator() {
  return (
    <div className='flex gap-3 justify-start'>
      <div className='w-7 h-7 shrink-0 flex items-center justify-center rounded-lg bg-[#EBF3FF] dark:bg-[#1E3A5F] text-[#3182F6] mt-1'>
        <svg
          width='14'
          height='14'
          viewBox='0 0 24 24'
          fill='none'
          stroke='currentColor'
          strokeWidth='2'
          strokeLinecap='round'
          strokeLinejoin='round'>
          <path d='M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z' />
        </svg>
      </div>
      <div className='px-4 py-3 rounded-2xl rounded-bl-md bg-[#F2F4F6] dark:bg-[#252D3D] flex items-center gap-1.5'>
        <span className='w-2 h-2 rounded-full bg-[#8B95A1] dark:bg-[#6B7280] animate-bounce [animation-delay:-0.3s]' />
        <span className='w-2 h-2 rounded-full bg-[#8B95A1] dark:bg-[#6B7280] animate-bounce [animation-delay:-0.15s]' />
        <span className='w-2 h-2 rounded-full bg-[#8B95A1] dark:bg-[#6B7280] animate-bounce' />
      </div>
    </div>
  );
}

export default function ChatConversation({
  projectId,
  sessionId,
  onSessionCreated,
  onActivity,
  onProgress,
  onResultComplete,
}: {
  projectId: string;
  sessionId: string | null; // null = 새 채팅
  onSessionCreated?: (id: string) => void; // 첫 전송으로 세션이 생성되면 알림
  onActivity?: () => void; // 전송 후(제목·갱신 변경) 세션 목록 새로고침 신호
  onProgress?: (
    p: { label: string; pct?: number | null; run_id?: string } | null
  ) => void; // 진행 트레이(T17)
  onResultComplete?: (ref: ResultRef) => void; // 시뮬/생성 결과가 도착했을 때(프로액티브 푸시, T18)
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  // N7 — 새 채팅 진입 시 최근 시뮬/제너 기반 다음 단계 제안(시뮬 후 'improve', 제너 후 'simulate').
  const [nextSuggest, setNextSuggest] = useState<'improve' | 'simulate' | null>(null);
  const [slashIndex, setSlashIndex] = useState(0);
  const [attachedImage, setAttachedImage] = useState<File | null>(null);
  const [attachedPreview, setAttachedPreview] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null); // 완료 토스트(P9)
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSendRef = useRef<{ text: string; resultRef?: ResultRef } | null>(
    null
  ); // 에러 재시도용(X1)
  const [rated, setRated] = useState<Record<number, number>>({}); // 메시지 피드백 ±1(F1, 인덱스 기준)
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null); // 복사 완료 표시(F1)
  const pendingImageRef = useRef<File | null>(null);
  const abortRef = useRef<AbortController | null>(null); // 스트리밍 중단(P3)
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── Web Speech API: STT(마이크 입력) + TTS(읽어주기). 무료, API 키 불필요 ──
  const [listening, setListening] = useState(false);
  const recognitionRef = useRef<{ stop: () => void } | null>(null);
  const voiceTextRef = useRef(''); // STT 결과를 onend에서 자동전송하기 위한 ref
  const voiceCancelledRef = useRef(false); // 수동 중지 시 자동전송 방지
  const [voiceSupported, setVoiceSupported] = useState(false);
  const [ttsSupported, setTtsSupported] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [isSpeaking, setIsSpeaking] = useState(false); // TTS 재생 중 여부
  const [autoRead, setAutoRead] = useState(false); // 시각장애 접근성 — 응답 완료 시 자동 읽기
  const textareaRef = useRef<HTMLTextAreaElement>(null); // 멀티라인 자동 높이(P8)
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null); // 메시지 스크롤 컨테이너(P11)
  const [atBottom, setAtBottom] = useState(true); // 사용자가 하단 근처인지(자동 스크롤 판단)
  const router = useRouter();
  // 이미 로드/생성한 세션 — prop이 같은 값으로 바뀌어도 재로드하지 않게 추적.
  const loadedRef = useRef<string | null | undefined>(undefined);
  // 실제 활성 세션 id — 첫 전송으로 만든 세션은 shallow routing(URL만 갱신)이라 prop엔 안 들어온다.
  // 후속 전송·승인은 prop 대신 이 ref를 써서 같은 세션을 이어간다.
  const sidRef = useRef<string | null>(sessionId);
  // N4 선제 알림 — 최신 메시지/스트리밍/콜백을 effect 재생성 없이 참조하기 위한 ref.
  const messagesRef = useRef<Message[]>([]);
  messagesRef.current = messages;
  const streamingRef = useRef(false);
  streamingRef.current = isStreaming;
  const onResultCompleteRef = useRef(onResultComplete);
  onResultCompleteRef.current = onResultComplete;
  const proactiveBusyRef = useRef(false); // 동시 실행 방지
  // 개선 루프 컨텍스트 — 직전 시뮬 광고를 보관해 '개선 시안 만들기' 수락 시 제너 폼에 옮긴다.
  // (없으면 백엔드가 맥락 없는 합성 질문으로 엉뚱한 상품을 환각함.)
  const loopCtxRef = useRef<{
    ad_title: string;
    ad_content: string;
    ad_objective: string;
  } | null>(null);

  const attachImage = (file: File | null) => {
    setAttachedPreview(prev => {
      if (prev) URL.revokeObjectURL(prev);
      return file ? URL.createObjectURL(file) : null;
    });
    setAttachedImage(file);
  };

  // 완료 토스트(P9) — 3초 후 자동 사라짐.
  const showToast = useCallback((msg: string) => {
    setToast(msg);
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    toastTimerRef.current = setTimeout(() => setToast(null), 3000);
  }, []);

  // 메시지 본문 복사(F1) — 클립보드 API + execCommand 폴백(P10과 동일).
  const copyMessage = useCallback(async (idx: number, text: string) => {
    let ok = false;
    try {
      await navigator.clipboard.writeText(text);
      ok = true;
    } catch {
      try {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        ok = document.execCommand('copy');
        document.body.removeChild(ta);
      } catch {
        ok = false;
      }
    }
    if (ok) {
      setCopiedIdx(idx);
      setTimeout(() => setCopiedIdx(c => (c === idx ? null : c)), 1500);
    }
  }, []);

  // 좋아요/싫어요 피드백(F1) — POST /api/chat/feedback(rating ±1). 직전 사용자 질문을 맥락으로.
  const sendFeedback = useCallback(
    (idx: number, answer: string, rating: number) => {
      setRated(prev => ({ ...prev, [idx]: rating }));
      const question = [...messages.slice(0, idx)]
        .reverse()
        .find(m => m.role === 'user')?.content;
      void api.chat
        .feedback({
          thread_id: sidRef.current ?? undefined,
          rating,
          question,
          answer,
        })
        .catch(() => {});
    },
    [messages]
  );

  // 새 메시지·스트리밍 시 하단으로 — 단, 사용자가 위로 스크롤해 둔 상태면 유지(P11).
  useEffect(() => {
    if (atBottom) bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isStreaming, atBottom]);

  const scrollToBottom = () => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    setAtBottom(true);
  };

  // 스크롤 위치 추적 — 하단 80px 이내면 atBottom.
  const onMessagesScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 80);
  };

  // 입력창 멀티라인 자동 높이(P8) — 내용에 맞춰 최대 120px까지 늘고, 비면 1줄로 복귀.
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, 120)}px`;
  }, [input]);

  // sessionId가 바뀌면 그 세션의 DB 내역을 로드(또는 새 채팅이면 비움).
  useEffect(() => {
    if (loadedRef.current === sessionId) return; // 우리가 방금 만든/이미 연 세션 — 재로드 금지
    loadedRef.current = sessionId;
    sidRef.current = sessionId; // prop으로 들어온 세션을 활성 세션으로 동기화
    if (!sessionId) {
      setMessages([]);
      return;
    }
    // N5 — 세션을 열면 읽음 처리(last_read_at 갱신) → 성공 후 사이드바·벨 배지를 다시 조회해 미확인 0 반영.
    api.chat
      .markRead(sessionId)
      .then(() => onActivity?.())
      .catch(() => {});
    (async () => {
      try {
        const { messages: rows } = await api.chat.messages(sessionId);
        setMessages(
          rows.map(m => {
            const rawMeta = m.meta as Record<string, unknown> | null;
            const imageUrl =
              typeof rawMeta?.image_url === 'string'
                ? rawMeta.image_url
                : undefined;
            const rr = rawMeta?.result as ResultRef | undefined;
            const result =
              rr && (rr.kind === 'sim' || rr.kind === 'gen') && rr.id
                ? rr
                : undefined;
            // 어시스턴트 메시지만 출처/위젯 meta로 사용. 사용자 메시지 meta는 이미지·결과 참조 보관용.
            const meta =
              m.role === 'assistant'
                ? ((rawMeta as SourceMeta | null) ?? undefined)
                : undefined;
            return {
              id: m.id,
              role: m.role,
              content: m.content,
              meta,
              imageUrl,
              result,
              created_at: m.created_at,
            };
          })
        );
      } catch {
        setMessages([]);
      }
    })();
  }, [sessionId]);

  // N7 — 빈 채팅(새 채팅) 진입 시 최근 활동을 보고 다음 단계를 제안한다.
  // 가장 최근이 시뮬이면 개선(제너) 제안, 제너면 시뮬 제안. 활동 없으면 미표시.
  useEffect(() => {
    if (messages.length > 0 || !projectId) {
      setNextSuggest(null);
      return;
    }
    let alive = true;
    const latestTs = (rows: Record<string, unknown>[]) => {
      let t = 0;
      for (const r of rows) {
        const ts = Date.parse(String(r.created_at ?? ''));
        if (!Number.isNaN(ts) && ts > t) t = ts;
      }
      return t;
    };
    (async () => {
      try {
        const [sims, gens] = await Promise.all([
          api.projects.simulations(projectId, 5).catch(() => [] as Record<string, unknown>[]),
          api.projects.generations(projectId, 5).catch(() => [] as Record<string, unknown>[]),
        ]);
        if (!alive) return;
        const simTs = latestTs(sims);
        const genTs = latestTs(gens);
        if (simTs === 0 && genTs === 0) setNextSuggest(null);
        else setNextSuggest(simTs >= genTs ? 'improve' : 'simulate');
      } catch {
        if (alive) setNextSuggest(null);
      }
    })();
    return () => {
      alive = false;
    };
  }, [messages.length, projectId]);

  const showSlashMenu = input.startsWith('/') && !input.includes(' ');
  const slashMatches = showSlashMenu
    ? slashCommands.filter(c => c.cmd.startsWith(input))
    : [];

  // 가장 최근 sim_form 위젯 인덱스 — 이 위젯만 새로고침 시 진행중 런을 복원(중복 방지).
  const lastSimFormIdx = messages.reduce(
    (acc, m, i) => (m.meta?.widget?.type === 'sim_form' ? i : acc),
    -1
  );
  const lastGenFormIdx = messages.reduce(
    (acc, m, i) => (m.meta?.widget?.type === 'gen_form' ? i : acc),
    -1
  );

  const addLocalAssistant = (
    content: string,
    meta?: SourceMeta,
    imageFile?: File
  ) => {
    setMessages(prev => [
      ...prev,
      { role: 'assistant', content, meta, imageFile },
    ]);
  };

  // F8 — 생성 후보 카피로 시뮬 진입(제너→시뮬 루프). 후보 카피를 sim_form 초기값으로 띄운다.
  const handleSimulateCandidate = (adTitle: string, adContent: string) => {
    addLocalAssistant('이 시안으로 반응을 예측해볼게요. 아래에서 확인·실행하세요.', {
      source: 'simulation',
      label: '시뮬레이션',
      widget: { type: 'sim_form', data: { ad_title: adTitle, ad_content: adContent } },
    });
  };

  const runSlashCommand = (cmd: string) => {
    setInput('');
    setSlashIndex(0);
    const img = attachedImage ?? undefined;
    switch (cmd) {
      case '/시뮬레이션':
        addLocalAssistant(
          '광고 시뮬레이션 입력 위젯입니다. 아래에서 실행하세요.',
          {
            source: 'simulation',
            label: '광고 시뮬레이터',
            widget: { type: 'sim_form' },
          },
          img
        );
        attachImage(null);
        break;
      case '/제너레이터':
        addLocalAssistant(
          '광고 생성 입력 위젯입니다. 아래에서 실행하세요.',
          {
            source: 'generator',
            label: '광고 생성',
            widget: { type: 'gen_form' },
          },
          img
        );
        attachImage(null);
        break;
      case '/배치':
      case '/AB':
        addLocalAssistant(
          '광고 2개를 동시에 비교하는 배치 시뮬레이션이에요. 아래에서 입력·실행하세요.',
          {
            source: 'simulation',
            label: '배치 시뮬레이션',
            widget: { type: 'batch_sim_form' },
          }
        );
        break;
      case '/리포트':
        addLocalAssistant('성과 리포트예요. 아래에서 PDF로 받을 수 있어요.', {
          source: 'simulation',
          label: '리포트',
          widget: { type: 'report_ready' },
        });
        break;
      case '/시뮬목록':
        addLocalAssistant('최근 시뮬레이션 목록을 불러올게요.', {
          source: 'simulation',
          label: '내 시뮬레이션',
          widget: { type: 'sim_list', mode: 'read', data: { items: [] } },
        });
        if (projectId) {
          void api.projects
            .simulations(projectId)
            .then(rows => {
              const items = rows.map(r => ({
                id: String(r.id),
                title: (r.ad_title as string) || '(제목 없음)',
                status: r.status as string | undefined,
                created_at: r.created_at as string | undefined,
                sample_size: r.sample_size as number | undefined,
              }));
              setMessages(prev => patchLastListWidget(prev, 'sim_list', items));
            })
            .catch(() => {});
        }
        break;
      case '/시안목록':
        addLocalAssistant('최근 생성 광고 시안 목록을 불러올게요.', {
          source: 'generator',
          label: '내 광고 생성',
          widget: { type: 'gen_list', mode: 'read', data: { items: [] } },
        });
        if (projectId) {
          void api.projects
            .generations(projectId)
            .then(rows => {
              const items = rows.map(r => ({
                id: String(r.id),
                title: (r.product_name as string) || '(제목 없음)',
                status: r.status as string | undefined,
                created_at: r.created_at as string | undefined,
                mode: r.mode as string | undefined,
              }));
              setMessages(prev => patchLastListWidget(prev, 'gen_list', items));
            })
            .catch(() => {});
        }
        break;
      case '/분석':
        addLocalAssistant('이 프로젝트의 시뮬·생성 활동을 요약해 드릴게요.', {
          source: 'simulation',
          label: '활동 요약',
          widget: { type: 'analysis_summary' },
        });
        break;
      case '/추천':
        addLocalAssistant(
          '목표·예산을 알려주시면 전략·플랫폼을 추천해 드릴게요.',
          {
            source: 'simulation',
            label: '전략 추천',
            widget: { type: 'recommend_form' },
          }
        );
        break;
      case '/비교':
        // 백엔드로 보내 시뮬 목록(비교 모드) 위젯을 받는다.
        handleSend('/비교');
        break;
      case '/키워드':
        addLocalAssistant(
          '광고 맥락을 알려주시면 SNS 해시태그·키워드를 추천해 드릴게요.',
          {
            source: 'generator',
            label: '키워드 추천',
            widget: { type: 'keyword_form' },
          }
        );
        break;
      case '/도움말':
        addLocalAssistant(
          [
            '사용할 수 있는 명령어예요.',
            '',
            '/시뮬레이션   광고 반응 시뮬레이션 입력 위젯',
            '/제너레이터   광고 시안 생성 입력 위젯',
            '/배치(/AB)    광고 2개 동시 비교 시뮬레이션',
            '/리포트       성과 PDF 리포트',
            '/시뮬목록     최근 시뮬레이션 목록',
            '/시안목록     최근 광고 시안 목록',
            '/분석         시뮬·생성 성과 종합 요약',
            '/추천         목표·예산 → 전략·플랫폼 추천',
            '/비교         시뮬레이션 2개 KPI 비교',
            '/키워드       광고 맥락 → SNS 해시태그·키워드 추천',
            '/도움말       이 화면',
            '',
            '이렇게 말해도 돼요',
            '  "이 광고 반응 예측해줘"',
            '  "수분크림 광고 시안 만들어줘"',
            '  "우리 캠페인 예산 소진율 알려줘"',
            '  "저번 시뮬보다 이번 게 왜 낮아?"',
            '  "이번 달 시뮬 결과 PDF로 뽑아줘"',
            '  "이 설정 저장해줘"',
          ].join('\n'),
          { source: 'simulation', label: '도움말' }
        );
        break;
    }
  };

  // SSE 스트림 1건을 소비해 마지막 어시스턴트 메시지에 토큰·meta·approval을 누적.
  // 호출 전 빈 어시스턴트 메시지를 push해둔다(/complete·/approve 공용).
  const consumeStream = useCallback(
    async (res: Response) => {
      setMessages(prev => [...prev, { role: 'assistant', content: '' }]);
      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const raw = line.slice(6).trim();
          if (!raw) continue;
          try {
            const data = JSON.parse(raw) as {
              kind?: string;
              token?: string;
              done?: boolean;
              meta?: SourceMeta;
              approval?: ApprovalSpec;
              progress?: {
                label: string;
                pct?: number | null;
                run_id?: string;
              };
            };
            // kind 우선 분기, 없으면 레거시 필드(token/meta/done)로 폴백.
            const kind =
              data.kind ?? (data.done ? 'done' : data.meta ? 'meta' : 'text');
            if (kind === 'done') {
              setIsStreaming(false);
              onProgress?.(null); // 완료 → 진행 트레이 닫기
            } else if (kind === 'progress') {
              onProgress?.(data.progress ?? null);
            } else if (kind === 'meta' && data.meta) {
              setMessages(prev => {
                const last = prev[prev.length - 1];
                const imageFile = data.meta?.widget
                  ? (pendingImageRef.current ?? undefined)
                  : last.imageFile;
                return [
                  ...prev.slice(0, -1),
                  { ...last, meta: data.meta, imageFile },
                ];
              });
            } else if (kind === 'approval' && data.approval) {
              setMessages(prev => {
                const last = prev[prev.length - 1];
                const meta = {
                  ...(last.meta ?? {
                    source: 'simulation',
                    label: '개선 제안',
                  }),
                  approval: data.approval,
                };
                return [...prev.slice(0, -1), { ...last, meta }];
              });
            } else if (kind === 'text' && data.token) {
              setMessages(prev => {
                const last = prev[prev.length - 1];
                return [
                  ...prev.slice(0, -1),
                  { ...last, content: last.content + data.token },
                ];
              });
            }
          } catch {
            // ignore malformed SSE line
          }
        }
      }
    },
    [onProgress]
  );

  // 개선 루프 수락 — POST /api/chat/approve 로 왕복 카운트를 올리고 다음 위젯을 스트리밍.
  const handleApprove = useCallback(
    async (action: string) => {
      const sid = sidRef.current;
      if (isStreaming || !sid) return;
      setIsStreaming(true);
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        const res = await fetch(`${API_BASE}/api/chat/approve`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
          },
          signal: controller.signal,
          body: JSON.stringify({
            action,
            session_id: sid,
            project_id: projectId,
            // 시뮬→제너 개선 루프 — 직전 시뮬 광고 맥락을 함께 보내 폼을 실제 광고로 채운다.
            ...(action === 'run_generator' && loopCtxRef.current
              ? { context: loopCtxRef.current }
              : {}),
          }),
        });
        if (!res.ok || !res.body) {
          setIsStreaming(false);
          return;
        }
        await consumeStream(res);
      } catch (e) {
        if ((e as Error)?.name !== 'AbortError') {
          setMessages(prev => [
            ...prev,
            {
              role: 'assistant',
              content:
                '진행 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.',
              meta: { source: 'orchestrator', label: '오류', error: true },
            },
          ]);
        }
      } finally {
        abortRef.current = null;
        setIsStreaming(false);
        onProgress?.(null);
        onActivity?.();
      }
    },
    [isStreaming, projectId, consumeStream, onActivity, onProgress]
  );

  // 단독 위젯 메시지(결과 요약·토론·토론 요약)를 DB에 영속화하고 화면에도 추가 — 새로고침 복원 가능.
  const appendWidgetMessages = useCallback(
    async (
      items: { content: string; meta: SourceMeta & { widget: WidgetSpec } }[]
    ) => {
      // 화면엔 즉시 반영(영속화는 best-effort).
      const local: Message[] = items.map(it => ({
        role: 'assistant',
        content: it.content,
        meta: it.meta,
      }));
      setMessages(prev => [...prev, ...local]);
      // 세션이 없으면(빈 화면 칩으로 시작한 시뮬/제너 등) 먼저 DB 세션을 만든다.
      // 없으면 위젯이 영속되지 않아 새로고침 시 전부 유실된다(시뮬 입력·결과·토론 누락).
      let sid = sidRef.current;
      if (!sid) {
        try {
          const created = await api.chat.createSession(projectId);
          sid = created.id;
          loadedRef.current = sid;
          sidRef.current = sid;
          onSessionCreated?.(sid);
        } catch {
          return; // 세션 생성 실패 — 화면 표시는 유지, 영속만 생략
        }
      }
      try {
        const { messages: saved } = await api.chat.appendWidgets(
          sid,
          items.map(it => ({ content: it.content, meta: it.meta }))
        );
        // 저장된 id를 반영 — 방금 추가한 같은 수의 말풍선을 교체.
        if (saved?.length === local.length) {
          setMessages(prev => {
            const next = [...prev];
            for (let k = 0; k < saved.length; k++) {
              const idx = next.length - saved.length + k;
              const m = saved[k];
              next[idx] = {
                id: m.id,
                role: 'assistant',
                content: m.content,
                meta: (m.meta as SourceMeta | null) ?? undefined,
              };
            }
            return next;
          });
        }
      } catch {
        // 영속화 실패 — 화면 표시는 유지(새로고침 시 사라질 수 있음)
      }
    },
    [projectId, onSessionCreated]
  );

  // 시뮬 완료 → 토론 자동 시작 + 결과 요약 위젯·토론 stream 위젯을 별도 메시지로 띄운다(파이프라인).
  const handleSimComplete = useCallback(
    async (
      result: SimRunResult,
      input: {
        adTitle: string;
        adContent: string;
        category: string;
        objective: string;
        sampleSize: number;
      }
    ) => {
      const simId = result.simulation_id;
      showToast('🧪 시뮬레이션이 완료됐어요');
      // 입력 요약은 백엔드 결과(실제 제출값)를 우선 출처로, 폼 상태(input)는 폴백.
      // 새로고침 중 완료된 런을 복원할 땐 폼 상태가 비어 있어(빈 initial로 재마운트)
      // input만 쓰면 소비자 수만 남는다 → result.ad/result.simulation에서 복구한다.
      const adBlock = (result.ad ?? {}) as Record<string, unknown>;
      const simBlock = (result.simulation ?? {}) as Record<string, unknown>;
      // 개선 루프 — 방금 시뮬한 광고를 보관(이후 '개선 시안 만들기' 수락 시 제너 폼에 전달).
      loopCtxRef.current = {
        ad_title: (adBlock.title as string) || input.adTitle || '',
        ad_content: (adBlock.copy_text as string) || input.adContent || '',
        ad_objective: (adBlock.ad_objective as string) || input.objective || '',
      };
      // 1) 결과(입력 요약 + 결과 KPI)는 준비되는 즉시 띄운다 — 토론 시작을 기다리지 않는다.
      const resultItems: {
        content: string;
        meta: SourceMeta & { widget: WidgetSpec };
      }[] = [];
      // 숨겨진 입력 폼 자리 — 실제 돌린 입력값을 요약해 보여준다.
      resultItems.push({
        content: '시뮬레이션 입력값이에요.',
        meta: {
          source: 'simulation',
          label: '시뮬레이션',
          widget: {
            type: 'sim_input',
            data: {
              ad_title: (adBlock.title as string) || input.adTitle,
              ad_content: (adBlock.copy_text as string) || input.adContent,
              product_category:
                (adBlock.product_category as string) || input.category,
              ad_objective: (adBlock.ad_objective as string) || input.objective,
              sample_size: (simBlock.sample_size as number) ?? input.sampleSize,
            },
          },
        },
      });
      if (simId) {
        resultItems.push({
          content: '시뮬레이션 결과예요.',
          meta: {
            source: 'simulation',
            label: '시뮬레이션',
            widget: { type: 'sim_result', data: { simulation_id: simId } },
          },
        });
      }
      if (resultItems.length) await appendWidgetMessages(resultItems);

      // 2) 토론은 시작 즉시 stream 위젯을 띄운다(준비 중에도 진행 상태를 보이게).
      if (result.reactions?.length) {
        try {
          const { run_id } = await api.debate.start({
            reactions: result.reactions,
            ad_analysis: result.ad_analysis ?? undefined,
            personas: result.personas?.length ? result.personas : undefined,
            simulation_id: simId,
            rubric_scores: result.rubric_scores?.length
              ? result.rubric_scores
              : undefined,
            objective_fit: result.objective_fit ?? undefined,
            ad_title: input.adTitle || undefined,
            ad_description: input.adContent || undefined,
          });
          await appendWidgetMessages([
            {
              content: 'AI 소비자 토론을 시작했어요.',
              meta: {
                source: 'simulation',
                label: '토론',
                widget: {
                  type: 'debate_stream',
                  data: { run_id, simulation_id: simId },
                },
              },
            },
          ]);
        } catch {
          // 토론 시작 실패 — 결과 요약만 표시
        }
      }
      // 이 시뮬은 실행한 바로 이 세션에 결과 위젯으로 표시됐다 → 프로젝트 seen 집합에
      // 등록해 다른 세션에서 N4 선제 알림으로 다시 뜨지 않게 한다(세션 간 알림 누수 방지).
      if (simId) {
        try {
          const seen: string[] = JSON.parse(
            localStorage.getItem(proactiveSeenKey(projectId)) || '[]'
          );
          if (!seen.includes(simId)) {
            localStorage.setItem(
              proactiveSeenKey(projectId),
              JSON.stringify([...seen, simId].slice(-200))
            );
          }
        } catch {
          /* localStorage 불가 — 무시 */
        }
      }
    },
    [appendWidgetMessages, showToast, projectId]
  );

  // 토론 요약 보기 — 토론 요약 위젯을 새 메시지로 추가(영속화).
  const handleDebateSummary = useCallback(
    (runId: string) => {
      void appendWidgetMessages([
        {
          content: '토론 요약이에요.',
          meta: {
            source: 'simulation',
            label: '토론 요약',
            widget: { type: 'debate_summary', data: { run_id: runId } },
          },
        },
      ]);
    },
    [appendWidgetMessages]
  );

  // N4 — 선제적 말걸기: 채팅에서 아직 안 본(미열람) 완료 시뮬 결과를 챗봇이 먼저 알린다.
  // N1(실행 즉시 주입)이 못 잡은 경우(다른 화면에서 완료 등)를 폴링으로 보완. 빈도 가드로 스팸 방지.
  // 제너레이터는 외부 403 블로커로 보류 → 동작하는 시뮬 완료만 대상으로 한다(N1·N2 자산 재사용).
  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;

    const runProactiveCheck = async () => {
      const sid = sidRef.current;
      if (!sid || streamingRef.current || proactiveBusyRef.current) return;
      // N6 — 제너 전용 세션엔 시뮬 선제 알림을 본문에 주입하지 않는다(도메인 불일치 오염 방지).
      // gen 위젯만 있고 sim 위젯이 없는 세션은 제너 전용으로 보고 스킵(알림은 N5 벨로 노출).
      const wtypes = messagesRef.current
        .map(m => m.meta?.widget?.type)
        .filter((t): t is string => typeof t === 'string');
      const hasGen = wtypes.some(t => t === 'gen_form' || t === 'gen_result');
      const hasSim = wtypes.some(
        t => t === 'sim_form' || t === 'sim_result' || t === 'debate_stream'
      );
      if (hasGen && !hasSim) return;
      // 빈도 가드 — 프로젝트당 일정 시간 1회.
      let lastAt = 0;
      try {
        lastAt = Number(localStorage.getItem(proactiveLastKey(projectId)) || 0);
      } catch {
        /* localStorage 불가 — 가드 생략 */
      }
      if (Date.now() - lastAt < PROACTIVE_GUARD_MS) return;

      proactiveBusyRef.current = true;
      try {
        const sims = await api.projects
          .simulations(projectId, 20)
          .catch(() => [] as Record<string, unknown>[]);
        // await 도중 채팅 스트리밍이 시작됐으면 알림 주입을 미룬다 — 안 그러면
        // consumeStream이 이어붙이는 말풍선에 선제 알림이 끼어들어 답변과 한 덩어리로 렌더된다.
        if (cancelled || streamingRef.current) return;
        let seen: string[] = [];
        try {
          seen = JSON.parse(
            localStorage.getItem(proactiveSeenKey(projectId)) || '[]'
          );
        } catch {
          seen = [];
        }
        const seenSet = new Set(seen);
        const now = Date.now();
        const completed = sims.filter(s => {
          if (String(s.status).toUpperCase() !== 'COMPLETED') return false;
          if (typeof s.id !== 'string') return false;
          const ts = Date.parse(String(s.created_at ?? ''));
          return !Number.isNaN(ts) && now - ts <= PROACTIVE_RECENCY_MS;
        });
        // 이미 이 세션에 떠 있는 시뮬 id는 제외(N1 중복 주입 방지).
        const shownIds = new Set(
          messagesRef.current
            .map(m => m.meta?.widget?.data?.simulation_id)
            .filter((x): x is string => typeof x === 'string')
        );
        const unseen = completed.filter(
          s => !seenSet.has(String(s.id)) && !shownIds.has(String(s.id))
        );
        if (unseen.length === 0) return;

        // 목록은 최신순 — 가장 최근 완료 1건을 대표로 선제 알림.
        const latest = unseen[0];
        const simId = String(latest.id);
        const title = (latest.ad_title as string) || '시뮬레이션';
        const more =
          unseen.length > 1 ? ` (확인 안 한 결과가 ${unseen.length}건 더 있어요)` : '';
        await appendWidgetMessages([
          {
            content: `🔔 아직 확인하지 않은 시뮬레이션 결과가 있어요. "${title}" 결과를 정리해 드릴게요.${more}`,
            meta: {
              source: 'simulation',
              label: '선제 알림',
              widget: { type: 'sim_result', data: { simulation_id: simId } },
            },
          },
        ]);
        // 가드·seen 갱신 — 이번에 확인한 unseen 전부 seen 처리(다음부턴 새 완료만 알림).
        try {
          localStorage.setItem(proactiveLastKey(projectId), String(Date.now()));
          const merged = Array.from(
            new Set([...seen, ...unseen.map(s => String(s.id))])
          ).slice(-200);
          localStorage.setItem(proactiveSeenKey(projectId), JSON.stringify(merged));
        } catch {
          /* 영속 실패 — 다음 폴링에서 재시도될 수 있음 */
        }
        // 패널이 닫혀 있으면 빨간 배지로 알린다(N2).
        onResultCompleteRef.current?.({ kind: 'sim', id: simId });
      } finally {
        proactiveBusyRef.current = false;
      }
    };

    // 세션 로드 직후 한 번 + 주기 폴링(다른 화면에서 완료된 결과 캐치업).
    const t = setTimeout(runProactiveCheck, 3000);
    const iv = setInterval(runProactiveCheck, 60000);
    return () => {
      cancelled = true;
      clearTimeout(t);
      clearInterval(iv);
    };
  }, [projectId, appendWidgetMessages]);

  const handleSend = useCallback(
    async (text?: string, resultRef?: ResultRef) => {
      const content = text ?? input.trim();
      if (!content || isStreaming || !projectId) return;
      lastSendRef.current = { text: content, resultRef }; // 에러 재시도용(X1)

      pendingImageRef.current = attachedImage;
      const imgFile = attachedImage; // S3 영속화용(위젯엔 pendingImageRef로 따로 전달)
      // resultRef: 위젯이 실제 시뮬/생성을 돌린 결과 참조 — 메시지에 남겨 "결과 보기" 링크로.
      const userMsg: Message = {
        role: 'user',
        content,
        imageUrl: attachedPreview ?? undefined,
        result: resultRef,
      };
      // 직전에 다른 경로(appendWidgetMessages 등)가 비동기로 메시지를 추가했을 수 있어
      // 클로저의 stale `messages` 대신 살아있는 ref를 base로 쓰고, 추가는 함수형 업데이트로 한다.
      // (G6) 제너 완료 시 handleGenComplete가 gen_result를 append한 직후 handleSend를 부르는데,
      // 과거엔 stale base로 전체 배열을 덮어써 gen_result가 사라지고 gen_form이 다시 떴다.
      const base = messagesRef.current;
      const newMessages: Message[] = [...base, userMsg];
      setMessages(prev => [...prev, userMsg]);
      setInput('');
      setAttachedImage(null);
      setAttachedPreview(null);
      setIsStreaming(true);

      // 세션이 없으면(새 채팅) 먼저 DB 세션을 만들어 프로젝트에 귀속.
      // prop sessionId는 shallow routing 후에도 null이라 sidRef(생성된 실제 세션)를 우선 사용.
      let sid = sidRef.current ?? sessionId;
      if (!sid) {
        try {
          const created = await api.chat.createSession(projectId);
          sid = created.id;
          loadedRef.current = sid; // prop 변경 시 재로드 방지(현재 대화 유지)
          sidRef.current = sid; // 후속 전송이 같은 세션을 잇도록
          onSessionCreated?.(sid);
        } catch {
          setMessages(prev => [
            ...prev,
            {
              role: 'assistant',
              content:
                '채팅 세션을 만들지 못했습니다. 잠시 후 다시 시도해주세요.',
              meta: { source: 'orchestrator', label: '오류', error: true },
            },
          ]);
          setIsStreaming(false);
          return;
        }
      }

      // 첨부 이미지를 S3에 1회 업로드 → 사용자 메시지에 영속화(실패해도 표시만 하고 진행).
      let imageUrl: string | undefined;
      if (imgFile) {
        try {
          imageUrl = (await api.chat.uploadImage(imgFile)).url;
        } catch {
          // 업로드 실패 — 이번 세션 표시는 유지되나 내역엔 안 남음
        }
      }

      const controller = new AbortController();
      abortRef.current = controller;
      try {
        const res = await fetch(`${API_BASE}/api/chat/complete`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
          },
          signal: controller.signal,
          body: JSON.stringify({
            session_id: sid,
            project_id: projectId,
            messages: newMessages.map(m => ({
              role: m.role,
              content: m.content,
            })),
            image_url: imageUrl,
            result_ref: resultRef,
          }),
        });

        if (!res.ok || !res.body) {
          setMessages(prev => [
            ...prev,
            {
              role: 'assistant',
              content: '응답을 가져오는 중 오류가 발생했습니다.',
              meta: { source: 'orchestrator', label: '오류', error: true },
            },
          ]);
          setIsStreaming(false);
          return;
        }

        await consumeStream(res);
        // 시뮬/생성 결과가 도착한 턴이면 완료 알림(플로팅 배지 등, T18).
        if (resultRef) onResultComplete?.(resultRef);
      } catch (e) {
        // 사용자가 중단(■) → 부분 응답 유지, 에러 메시지 없음.
        if ((e as Error)?.name !== 'AbortError') {
          setMessages(prev => [
            ...prev,
            {
              role: 'assistant',
              content: '서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.',
              meta: { source: 'orchestrator', label: '오류', error: true },
            },
          ]);
        }
      } finally {
        abortRef.current = null;
        setIsStreaming(false);
        onProgress?.(null);
        pendingImageRef.current = null;
        onActivity?.();
      }
    },
    [
      input,
      isStreaming,
      projectId,
      attachedImage,
      attachedPreview,
      sessionId,
      onSessionCreated,
      onActivity,
      onProgress,
      onResultComplete,
      consumeStream,
    ]
  );

  // ── 음성(STT/TTS) — 옛 chat/page.tsx에서 포팅. Web Speech API, 무료, ko-KR ──
  // 브라우저 지원 여부 감지(마운트 1회). 미지원이면 버튼 자체를 숨긴다.
  useEffect(() => {
    const sw = window as SpeechWindow;
    setVoiceSupported(
      typeof sw.SpeechRecognition === 'function' ||
        typeof sw.webkitSpeechRecognition === 'function'
    );
    setTtsSupported(typeof window.speechSynthesis !== 'undefined');
  }, []);

  // STT: 마이크 버튼 → Web Speech API로 입력창 채움 → 인식 완료 시 자동 전송.
  const startVoice = () => {
    setVoiceError(null);
    const sw = window as SpeechWindow;
    const Ctor = sw.SpeechRecognition ?? sw.webkitSpeechRecognition;
    if (!Ctor) return;
    const rec = new Ctor();
    rec.lang = 'ko-KR';
    rec.continuous = false;
    rec.interimResults = true;
    rec.onresult = e => {
      let t = '';
      for (let i = 0; i < e.results.length; i++) t += e.results[i][0].transcript;
      voiceTextRef.current = t;
      setInput(t);
    };
    // 인식 완료 → 수동 중지가 아닐 때만 자동 전송(음성으로 검색).
    rec.onend = () => {
      setListening(false);
      const text = voiceTextRef.current.trim();
      const cancelled = voiceCancelledRef.current;
      voiceTextRef.current = '';
      voiceCancelledRef.current = false;
      if (text && !cancelled) handleSend(text);
    };
    rec.onerror = e => {
      setListening(false);
      voiceTextRef.current = '';
      if (e.error === 'not-allowed' || e.error === 'audio-capture') {
        setVoiceError(
          '마이크 권한이 필요해요. 주소창 왼쪽 🔒 → 사이트 설정 → 마이크 허용 후 새로고침해 주세요.'
        );
      } else if (e.error === 'no-speech') {
        setVoiceError('소리가 감지되지 않았어요. 다시 눌러 말씀해 주세요.');
      }
    };
    recognitionRef.current = rec;
    rec.start();
    setListening(true);
  };

  const stopVoice = () => {
    voiceCancelledRef.current = true; // onend에서 자동전송 방지
    voiceTextRef.current = '';
    recognitionRef.current?.stop();
    setListening(false);
  };

  // TTS: 마크다운 기호 제거 후 음성으로 읽어주기. 무료, API 키 없음.
  const speakText = (text: string) => {
    if (!window.speechSynthesis) return;
    const plain = text
      .replace(/#{1,3}\s+/g, '')
      .replace(/\*\*(.+?)\*\*/g, '$1')
      .replace(/\*(.+?)\*/g, '$1')
      .replace(/`(.+?)`/g, '$1')
      .replace(/^[-•]\s+/gm, '')
      .replace(/^\d+\.\s+/gm, '')
      .trim();
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(plain);
    u.lang = 'ko-KR';
    u.rate = 1.1;
    u.onend = () => setIsSpeaking(false);
    u.onerror = () => setIsSpeaking(false);
    setIsSpeaking(true);
    window.speechSynthesis.speak(u);
  };

  const stopSpeak = () => {
    window.speechSynthesis?.cancel();
    setIsSpeaking(false);
  };

  // 운동장애 접근성 — Escape 키로 음성입력·TTS·스트리밍 즉시 중지.
  useEffect(() => {
    const onEsc = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      if (listening) stopVoice();
      if (window.speechSynthesis?.speaking) {
        window.speechSynthesis.cancel();
        setIsSpeaking(false);
      }
      abortRef.current?.abort();
    };
    document.addEventListener('keydown', onEsc);
    return () => document.removeEventListener('keydown', onEsc);
  }, [listening]);

  // 시각장애 접근성 — 자동 읽기: 스트리밍 완료 후 마지막 AI 메시지 자동 TTS.
  useEffect(() => {
    if (!autoRead || !ttsSupported || isStreaming) return;
    const last = messagesRef.current[messagesRef.current.length - 1];
    if (last?.role === 'assistant' && last.content) speakText(last.content);
    // isStreaming이 false로 바뀌는 순간만 트리거.
  }, [isStreaming, autoRead, ttsSupported]);

  // 제너 완료 → 시뮬과 동일하게 어시스턴트가 결과를 준다.
  // ① 결과를 assistant gen_result 위젯(가로 스크롤 이미지)으로 영속·표시.
  // ② "[생성결과] …" 신호를 오케스트레이터에 보내 재시뮬 제안·루프 상태를 받는다
  //    (이 user 메시지는 렌더에서 숨겨 버블로 안 보인다).
  const handleGenComplete = useCallback(
    async (gid: string, count: number) => {
      await appendWidgetMessages([
        {
          content: `광고 시안 ${count}개가 나왔어요.`,
          meta: {
            source: 'generator',
            label: '광고 생성',
            widget: { type: 'gen_result', data: { generation_id: gid } },
          },
        },
      ]);
      handleSend(`[생성결과] 광고 시안 ${count}개 생성 완료`, {
        kind: 'gen',
        id: gid,
      });
    },
    [appendWidgetMessages, handleSend]
  );

  return (
    <div className='relative flex flex-col h-full min-h-0 bg-white dark:bg-[#0F1117] transition-colors'>
      {/* 맨 아래로 버튼(P11) — 메시지가 있고 사용자가 위로 스크롤했을 때만 */}
      {messages.length > 0 && !atBottom && (
        <button
          onClick={scrollToBottom}
          aria-label='맨 아래로'
          title='맨 아래로'
          className='absolute bottom-[88px] right-4 z-20 w-9 h-9 flex items-center justify-center rounded-full bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] text-[#4E5968] dark:text-[#9CA3AF] shadow-md hover:text-[#3182F6] hover:border-[#3182F6] transition-colors'>
          <svg
            width='18'
            height='18'
            viewBox='0 0 24 24'
            fill='none'
            stroke='currentColor'
            strokeWidth='2'
            strokeLinecap='round'
            strokeLinejoin='round'>
            <line x1='12' y1='5' x2='12' y2='19' />
            <polyline points='19 12 12 19 5 12' />
          </svg>
        </button>
      )}
      {/* 완료 토스트(P9) — 입력창 위 중앙에 잠깐 나타났다 사라짐 */}
      {toast && (
        <div className='chat-pop pointer-events-none absolute bottom-24 left-1/2 -translate-x-1/2 z-30 px-4 py-2 rounded-full bg-[#191F28] dark:bg-[#F2F4F6] text-white dark:text-[#191F28] text-sm font-medium shadow-lg'>
          {toast}
        </div>
      )}
      {messages.length === 0 ? (
        /* ── Welcome state ── */
        <div className='flex-1 flex flex-col items-center justify-center px-4 pb-10 overflow-y-auto'>
          <div className='mb-2 w-10 h-10 flex items-center justify-center rounded-2xl bg-[#EBF3FF] dark:bg-[#1E3A5F]'>
            <svg
              width='20'
              height='20'
              viewBox='0 0 24 24'
              fill='none'
              stroke='#3182F6'
              strokeWidth='2'
              strokeLinecap='round'
              strokeLinejoin='round'>
              <path d='M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z' />
            </svg>
          </div>
          <h2 className='text-lg font-bold text-[#191F28] dark:text-[#F2F4F6] mb-2 mt-3'>
            무엇을 도와드릴까요?
          </h2>
          <p className='text-sm text-[#8B95A1] dark:text-[#6B7280] mb-8 text-center leading-relaxed'>
            아래에서 바로 시작하거나,
            <br />
            광고에 대해 무엇이든 물어보세요
          </p>
          {/* N7 — 최근 시뮬/제너 활동 기반 다음 단계 제안 카드 */}
          {nextSuggest && (
            <button
              onClick={() =>
                runSlashCommand(nextSuggest === 'improve' ? '/제너레이터' : '/시뮬레이션')
              }
              className='w-full max-w-md mb-3 flex items-center gap-3 p-3 rounded-xl border border-[#3182F6]/30 bg-[#EBF3FF] dark:bg-[#1E3A5F]/40 text-left hover:border-[#3182F6] transition-all'>
              <span className='text-lg shrink-0'>
                {nextSuggest === 'improve' ? '✨' : '🧪'}
              </span>
              <span className='min-w-0'>
                <span className='block text-sm font-semibold text-[#3182F6]'>
                  {nextSuggest === 'improve'
                    ? '방금 시뮬레이션을 돌리셨네요 — 개선하시겠어요?'
                    : '광고 시안을 만드셨네요 — 시뮬레이션 해보시겠어요?'}
                </span>
                <span className='block text-[12px] text-[#4E5968] dark:text-[#9CA3AF] truncate'>
                  {nextSuggest === 'improve'
                    ? '결과를 반영해 개선 시안을 만들어 드릴게요.'
                    : '새 시안의 소비자 반응을 예측해 드릴게요.'}
                </span>
              </span>
            </button>
          )}
          <div className='grid grid-cols-2 gap-2 w-full max-w-md'>
            {welcomeActions.map(a => (
              <button
                key={a.cmd}
                onClick={() => runSlashCommand(a.cmd)}
                className='p-3 text-center text-sm font-medium text-[#4E5968] dark:text-[#9CA3AF] bg-[#F9FAFB] dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-xl hover:border-[#3182F6] hover:text-[#3182F6] hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F] transition-all'>
                {a.label}
              </button>
            ))}
          </div>
        </div>
      ) : (
        /* ── Messages ── */
        <div
          ref={scrollRef}
          onScroll={onMessagesScroll}
          className='flex-1 overflow-y-auto'>
          <div className='max-w-2xl mx-auto px-4 py-6 space-y-6'>
            {messages.map((msg, i) => {
              if (msg.role === 'assistant' && msg.content === '') return null;
              // 생성 결과 신호([생성결과] …)는 오케스트레이터 재시뮬 제안용 system 메시지 —
              // user 버블로 노출하지 않는다(결과는 assistant gen_result 위젯이 보여준다).
              if (msg.role === 'user' && msg.content?.startsWith('[생성결과]')) {
                return null;
              }
              // 이미 결과가 나온 시뮬 입력 위젯은 메시지째 숨긴다 — 결과/토론 위젯이 대신 표시된다.
              if (
                msg.meta?.widget?.type === 'sim_form' &&
                messages
                  .slice(i + 1)
                  .some(m => m.meta?.widget?.type === 'sim_result')
              ) {
                return null;
              }
              // 제너도 동일 — 결과가 나온 gen_form은 숨기고 gen_result 위젯이 대신 표시된다.
              if (
                msg.meta?.widget?.type === 'gen_form' &&
                messages
                  .slice(i + 1)
                  .some(m => m.meta?.widget?.type === 'gen_result')
              ) {
                return null;
              }
              const isStreamingMsg =
                isStreaming &&
                i === messages.length - 1 &&
                msg.role === 'assistant' &&
                !msg.meta?.widget;
              return (
                <div
                  key={i}
                  className={`chat-pop flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  {msg.role === 'assistant' && (
                    <div className='w-7 h-7 shrink-0 flex items-center justify-center rounded-lg bg-[#EBF3FF] dark:bg-[#1E3A5F] text-[#3182F6] mt-1'>
                      <svg
                        width='14'
                        height='14'
                        viewBox='0 0 24 24'
                        fill='none'
                        stroke='currentColor'
                        strokeWidth='2'
                        strokeLinecap='round'
                        strokeLinejoin='round'>
                        <path d='M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z' />
                      </svg>
                    </div>
                  )}
                  <div
                    className={`flex flex-col gap-1 ${msg.meta?.widget ? 'max-w-md w-full' : 'max-w-sm'} ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
                    {msg.role === 'assistant' && msg.meta && (
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                          msg.meta.source === 'management'
                            ? 'bg-[#EBF3FF] text-[#3182F6] dark:bg-[#1E3A5F] dark:text-[#7BB4F5]'
                            : 'bg-[#F2E9FF] text-[#7C3AED] dark:bg-[#2E1F47] dark:text-[#C4A8F5]'
                        }`}>
                        {msg.meta.source === 'management' ? '⚙' : '🧠'}{' '}
                        {msg.meta.label}
                      </span>
                    )}
                    {msg.role === 'user' && msg.imageUrl && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={fullUrl(msg.imageUrl)}
                        alt='첨부 이미지'
                        className='max-w-[200px] max-h-[200px] rounded-2xl rounded-br-md object-cover border border-[#E5E8EB] dark:border-[#2D3748]'
                      />
                    )}
                    {msg.meta?.error ? (
                      <ErrorCard
                        message={msg.content}
                        onRetry={
                          i === messages.length - 1 && lastSendRef.current
                            ? () =>
                                handleSend(
                                  lastSendRef.current?.text,
                                  lastSendRef.current?.resultRef
                                )
                            : undefined
                        }
                      />
                    ) : (
                      <div
                        className={`px-4 py-3 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap ${
                          msg.role === 'user'
                            ? 'bg-[#3182F6] text-white rounded-br-md'
                            : 'bg-[#F2F4F6] dark:bg-[#252D3D] text-[#191F28] dark:text-[#F2F4F6] rounded-bl-md'
                        }`}>
                        {msg.content}
                        {isStreamingMsg && (
                          <span className='typing-caret' aria-hidden />
                        )}
                      </div>
                    )}
                    {msg.created_at && (
                      <span
                        className='px-1 text-[10px] text-[#B0B8C1] dark:text-[#4B5563]'
                        title={formatKSTFull(msg.created_at)}>
                        {formatRelativeKST(msg.created_at)}
                      </span>
                    )}
                    {/* 메시지 액션 바(F1) — 일반 텍스트 답변에 복사·재생성·피드백 */}
                    {msg.role === 'assistant' &&
                      !msg.meta?.widget &&
                      !msg.meta?.error &&
                      !!msg.content &&
                      !isStreamingMsg && (
                        <div className='self-start mt-0.5 flex items-center gap-2 text-[#B0B8C1] dark:text-[#6B7280]'>
                          <button
                            onClick={() => copyMessage(i, msg.content)}
                            title='복사'
                            className='inline-flex items-center gap-1 text-[11px] font-semibold hover:text-[#3182F6] transition-colors'>
                            {copiedIdx === i ? '✓ 복사됨' : '복사'}
                          </button>
                          {i === messages.length - 1 && lastSendRef.current && (
                            <button
                              onClick={() =>
                                handleSend(
                                  lastSendRef.current?.text,
                                  lastSendRef.current?.resultRef
                                )
                              }
                              disabled={isStreaming}
                              title='재생성'
                              className='inline-flex items-center gap-1 text-[11px] font-semibold hover:text-[#3182F6] transition-colors disabled:opacity-40'>
                              ↻ 재생성
                            </button>
                          )}
                          <button
                            onClick={() => sendFeedback(i, msg.content, 1)}
                            title='좋아요'
                            className={`text-[12px] transition-colors ${rated[i] === 1 ? 'opacity-100' : 'opacity-50 hover:opacity-100'}`}>
                            👍
                          </button>
                          <button
                            onClick={() => sendFeedback(i, msg.content, -1)}
                            title='싫어요'
                            className={`text-[12px] transition-colors ${rated[i] === -1 ? 'opacity-100' : 'opacity-50 hover:opacity-100'}`}>
                            👎
                          </button>
                          {/* 읽어주기(TTS) — 브라우저 SpeechSynthesis, 무료 */}
                          {ttsSupported && (
                            <button
                              onClick={() =>
                                isSpeaking ? stopSpeak() : speakText(msg.content)
                              }
                              title={isSpeaking ? '읽기 중지' : '읽어주기'}
                              className='inline-flex items-center gap-1 text-[11px] font-semibold hover:text-[#3182F6] transition-colors'>
                              <SpeakerIcon />
                              {isSpeaking ? '중지' : '읽기'}
                            </button>
                          )}
                        </div>
                      )}
                    {msg.result && (
                      <button
                        onClick={() =>
                          router.push(
                            msg.result!.kind === 'sim'
                              ? `/simulation/${msg.result!.id}`
                              : `/generations/${msg.result!.id}`
                          )
                        }
                        className='self-start mt-0.5 inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-[#3182F6]/30 text-[#3182F6] text-xs font-semibold hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F] transition-colors'>
                        {msg.result.kind === 'sim'
                          ? '시뮬레이션 결과 보기'
                          : '생성 결과 보기'}{' '}
                        →
                      </button>
                    )}
                    {msg.meta?.widget?.type === 'sim_form' && (
                      <SimFormWidget
                        initial={msg.meta.widget.data}
                        initialImage={msg.imageFile}
                        projectId={projectId}
                        latest={i === lastSimFormIdx}
                        onSimComplete={handleSimComplete}
                      />
                    )}
                    {msg.meta?.widget?.type === 'sim_input' && (
                      <SimInputWidget data={msg.meta.widget.data} />
                    )}
                    {msg.meta?.widget?.type === 'sim_result' &&
                      msg.meta.widget.data?.simulation_id && (
                        <SimResultWidget
                          simulationId={msg.meta.widget.data.simulation_id}
                        />
                      )}
                    {msg.meta?.widget?.type === 'debate_stream' &&
                      msg.meta.widget.data?.run_id && (
                        <DebateStreamWidget
                          runId={msg.meta.widget.data.run_id}
                          sessionId={sidRef.current ?? sessionId ?? undefined}
                          onSummary={handleDebateSummary}
                          onAccept={handleApprove}
                          proposalDisabled={isStreaming}
                        />
                      )}
                    {msg.meta?.widget?.type === 'debate_summary' &&
                      msg.meta.widget.data?.run_id && (
                        <DebateSummaryWidget
                          runId={msg.meta.widget.data.run_id}
                        />
                      )}
                    {msg.meta?.widget?.type === 'gen_form' && (
                      <GenFormWidget
                        initial={msg.meta.widget.data}
                        initialImage={msg.imageFile}
                        latest={i === lastGenFormIdx}
                        onResult={handleSend}
                        onComplete={handleGenComplete}
                      />
                    )}
                    {msg.meta?.widget?.type === 'gen_result' &&
                      msg.meta.widget.data?.generation_id && (
                        <GenResultWidget
                          generationId={msg.meta.widget.data.generation_id}
                          onSimulate={handleSimulateCandidate}
                        />
                      )}
                    {msg.meta?.widget?.type === 'sim_list' && (
                      <SimGenListWidget
                        domain='sim'
                        mode={msg.meta.widget.mode ?? 'read'}
                        items={msg.meta.widget.data?.items ?? []}
                        onResult={handleSend}
                      />
                    )}
                    {msg.meta?.widget?.type === 'gen_list' && (
                      <SimGenListWidget
                        domain='gen'
                        mode={msg.meta.widget.mode ?? 'read'}
                        items={msg.meta.widget.data?.items ?? []}
                        onResult={handleSend}
                      />
                    )}
                    {msg.meta?.widget?.type === 'batch_sim_form' && (
                      <BatchSimWidget projectId={projectId} />
                    )}
                    {msg.meta?.widget?.type === 'report_ready' && (
                      <ReportWidget
                        projectId={
                          msg.meta.widget.data?.project_id ?? projectId
                        }
                        period={msg.meta.widget.data?.period}
                      />
                    )}
                    {msg.meta?.widget?.type === 'analysis_summary' && (
                      <AnalysisSummaryWidget projectId={projectId} />
                    )}
                    {msg.meta?.widget?.type === 'recommend_form' && (
                      <RecommendFormWidget onSubmit={handleSend} />
                    )}
                    {msg.meta?.widget?.type === 'keyword_form' && (
                      <KeywordWidget />
                    )}
                    {/* 챗→매니지먼트 카드(재이식) — deep_agent의 create_campaign/manage_campaign 신호 */}
                    {msg.meta?.widget?.type === 'create_campaign' && (
                      <ChatCreateCampaignCard
                        prefill={msg.meta.widget.data?.prefill}
                      />
                    )}
                    {msg.meta?.widget?.type === 'campaign_action' &&
                      (() => {
                        const a = msg.meta.widget.data?.action;
                        if (!a) return null;
                        if (a.action === 'pause' || a.action === 'activate')
                          return (
                            <ChatCampaignActionCard
                              action={a as CampaignActionPayload}
                            />
                          );
                        return (
                          <ChatBudgetProposalCard
                            action={a as BudgetActionPayload}
                          />
                        );
                      })()}
                    {msg.role === 'assistant' && msg.meta?.plan?.length ? (
                      <PlanChecklist plan={msg.meta.plan} />
                    ) : null}
                    {msg.role === 'assistant' && msg.meta?.cards?.length ? (
                      <ActionCards cards={msg.meta.cards} />
                    ) : null}
                    {msg.meta?.approval && (
                      <ApprovalWidget
                        approval={msg.meta.approval}
                        onAccept={handleApprove}
                        disabled={isStreaming}
                      />
                    )}
                    {msg.role === 'assistant' &&
                    (msg.meta?.citations?.length ||
                      msg.meta?.used_tools?.length) ? (
                      <CitationChips
                        citations={msg.meta.citations}
                        usedTools={msg.meta.used_tools}
                      />
                    ) : null}
                  </div>
                </div>
              );
            })}

            {isStreaming &&
              messages.length > 0 &&
              messages[messages.length - 1].role === 'assistant' &&
              messages[messages.length - 1].content === '' && (
                <TypingIndicator />
              )}

            <div ref={bottomRef} />
          </div>
        </div>
      )}

      {/* ── Input bar ── */}
      <div className='border-t border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#1C2333] px-4 py-3 transition-colors shrink-0'>
        {voiceError && (
          <div className='max-w-2xl mx-auto mb-2 flex items-start gap-2 rounded-lg bg-[#FEF3F2] dark:bg-[#3A1A1F] px-3 py-2 text-xs text-[#B42318] dark:text-[#FDA29B]'>
            <span className='flex-1'>{voiceError}</span>
            <button
              onClick={() => setVoiceError(null)}
              className='shrink-0 opacity-60 hover:opacity-100'
              aria-label='닫기'>
              ✕
            </button>
          </div>
        )}
        {attachedPreview && (
          <div className='max-w-2xl mx-auto mb-2 flex items-center gap-2'>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={attachedPreview}
              alt='첨부 미리보기'
              className='w-14 h-14 rounded-lg object-cover border border-[#E5E8EB] dark:border-[#2D3748]'
            />
            <button
              onClick={() => attachImage(null)}
              className='text-xs text-[#8B95A1] hover:text-[#F04452]'>
              이미지 제거 ✕
            </button>
          </div>
        )}
        <input
          ref={fileInputRef}
          type='file'
          accept='image/*'
          className='hidden'
          onChange={e => {
            const f = e.target.files?.[0] ?? null;
            attachImage(f);
            e.target.value = '';
          }}
        />
        {/* Quick Action 칩 — 자주 쓰는 명령을 한 번에 보낸다 */}
        <div className='max-w-2xl mx-auto mb-2 flex gap-1.5 overflow-x-auto pb-0.5'>
          {[
            {
              label: '🧪 시뮬 돌리기',
              run: () => handleSend('시뮬레이션 돌려줘'),
            },
            {
              label: '🎨 시안 만들기',
              run: () => handleSend('광고 시안 만들어줘'),
            },
            {
              label: '📋 내역 보기',
              run: () => handleSend('내가 돌린 시뮬레이션 뭐 있어?'),
            },
            { label: '📊 비교하기', run: () => runSlashCommand('/비교') },
            { label: '❓ 도움말', run: () => runSlashCommand('/도움말') },
          ].map(chip => (
            <button
              key={chip.label}
              onClick={chip.run}
              disabled={isStreaming}
              className='shrink-0 px-3 py-1.5 rounded-full border border-[#E5E8EB] dark:border-[#2D3748] text-xs text-[#4E5968] dark:text-[#9CA3AF] hover:border-[#3182F6] hover:text-[#3182F6] hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F] disabled:opacity-40 transition-all whitespace-nowrap'>
              {chip.label}
            </button>
          ))}
        </div>
        <div className='max-w-2xl mx-auto flex items-end gap-2 relative'>
          {slashMatches.length > 0 && (
            <div className='absolute bottom-full left-0 right-0 mb-2 bg-white dark:bg-[#252D3D] border border-[#E5E8EB] dark:border-[#2D3748] rounded-xl shadow-lg overflow-hidden z-10'>
              {slashMatches.map((c, i) => {
                const active =
                  i === Math.min(slashIndex, slashMatches.length - 1);
                return (
                  <button
                    key={c.cmd}
                    onMouseDown={e => {
                      e.preventDefault();
                      runSlashCommand(c.cmd);
                    }}
                    onMouseEnter={() => setSlashIndex(i)}
                    className={`w-full flex flex-col items-start px-4 py-2.5 text-left transition-colors ${
                      active
                        ? 'bg-[#EBF3FF] dark:bg-[#1E3A5F]'
                        : 'hover:bg-[#F9FAFB] dark:hover:bg-[#1C2333]'
                    }`}>
                    <span className='text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]'>
                      {c.label}
                    </span>
                    <span className='text-xs text-[#8B95A1] dark:text-[#6B7280]'>
                      {c.desc}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isStreaming}
            title='이미지 첨부'
            className='p-3 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] text-[#8B95A1] hover:text-[#3182F6] hover:border-[#3182F6] disabled:opacity-30 transition-all shrink-0'>
            <svg
              width='18'
              height='18'
              viewBox='0 0 24 24'
              fill='none'
              stroke='currentColor'
              strokeWidth='2'
              strokeLinecap='round'
              strokeLinejoin='round'>
              <path d='M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48' />
            </svg>
          </button>
          <textarea
            ref={textareaRef}
            value={input}
            onChange={e => {
              setInput(e.target.value);
              setSlashIndex(0);
            }}
            onKeyDown={e => {
              if (slashMatches.length > 0) {
                if (e.key === 'ArrowDown') {
                  e.preventDefault();
                  setSlashIndex(i => (i + 1) % slashMatches.length);
                  return;
                }
                if (e.key === 'ArrowUp') {
                  e.preventDefault();
                  setSlashIndex(
                    i => (i - 1 + slashMatches.length) % slashMatches.length
                  );
                  return;
                }
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  runSlashCommand(
                    slashMatches[Math.min(slashIndex, slashMatches.length - 1)]
                      .cmd
                  );
                  return;
                }
                if (e.key === 'Escape') {
                  e.preventDefault();
                  setInput('');
                  return;
                }
              }
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder='메시지를 입력하세요... (/로 명령어, Shift+Enter로 줄바꿈)'
            rows={1}
            disabled={isStreaming}
            className='flex-1 px-4 py-3 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] text-sm text-[#191F28] dark:text-[#F2F4F6] placeholder-[#B0B8C1] dark:placeholder-[#4B5563] focus:outline-none focus:border-[#3182F6] focus:ring-2 focus:ring-[#3182F6]/10 transition-colors resize-none overflow-y-auto bg-white dark:bg-[#252D3D] leading-relaxed disabled:opacity-60'
            style={{ maxHeight: '120px' }}
          />
          {/* 음성 입력(STT) — Web Speech API, 무료. 미지원 브라우저는 숨김 */}
          {voiceSupported && (
            <button
              onClick={listening ? stopVoice : startVoice}
              aria-label={listening ? '음성 입력 중지' : '음성으로 입력'}
              title={listening ? '음성 입력 중지' : '음성으로 입력 (ko-KR)'}
              className={`p-3 rounded-xl border transition-all shrink-0 ${
                listening
                  ? 'border-[#F04452] bg-[#FEE] text-[#F04452] animate-pulse dark:bg-[#3A1A1F]'
                  : 'border-[#E5E8EB] dark:border-[#2D3748] text-[#8B95A1] hover:text-[#3182F6] hover:border-[#3182F6]'
              }`}>
              <MicIcon />
            </button>
          )}
          {/* 자동 읽기(TTS) 토글 — 응답 완료 시 자동 음성 재생. 미지원 브라우저는 숨김 */}
          {ttsSupported && (
            <button
              onClick={() => {
                if (isSpeaking) stopSpeak();
                setAutoRead(v => !v);
              }}
              aria-label={autoRead ? '자동 읽기 끄기' : '자동 읽기 켜기'}
              aria-pressed={autoRead}
              title={autoRead ? '자동 읽기 끄기' : '자동 읽기 켜기'}
              className={`p-3 rounded-xl border transition-all shrink-0 ${
                autoRead
                  ? 'border-[#3182F6] bg-[#EBF3FF] text-[#3182F6] dark:bg-[#1E3A5F]'
                  : 'border-[#E5E8EB] dark:border-[#2D3748] text-[#8B95A1] hover:text-[#3182F6] hover:border-[#3182F6]'
              }`}>
              <SpeakerIcon />
            </button>
          )}
          {isStreaming ? (
            <button
              onClick={() => abortRef.current?.abort()}
              aria-label='응답 중단'
              title='응답 중단'
              className='p-3 bg-[#F04452] text-white rounded-xl hover:bg-[#D93C48] transition-all shrink-0'>
              <svg
                width='18'
                height='18'
                viewBox='0 0 24 24'
                fill='currentColor'
                aria-hidden>
                <rect x='6' y='6' width='12' height='12' rx='2' />
              </svg>
            </button>
          ) : (
            <button
              onClick={() => handleSend()}
              disabled={!input.trim()}
              className='p-3 bg-[#3182F6] text-white rounded-xl hover:bg-[#1B6EEB] disabled:opacity-30 disabled:cursor-not-allowed transition-all shrink-0'>
              <SendIcon />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
