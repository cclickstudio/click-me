'use client';

import { useState, useRef, useEffect } from 'react';
import Link from 'next/link';
import { safeRandomUUID } from '@/lib/utils';
import { api } from '@/lib/api';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

const quickPrompts = [
  '이 광고의 예상 CTR을 분석해줘',
  '20대 여성 타겟 광고 전략을 추천해줘',
  '경쟁사 광고와 비교 분석해줘',
  '광고 카피 개선 방법을 알려줘',
];

type Citation = {
  kind: string;
  source: string;
  title?: string;
  trust?: string; // system_backed | advisory | reference (KB 근거 신뢰도)
  source_url?: string;
  as_of?: string;
};
type Campaign = {
  campaign_id: string;
  name: string;
  status: string;
  spend?: number;
  impressions?: number;
  clicks?: number;
  ctr?: number;
};
type SourceMeta = {
  source: string; // management | clio
  label: string; // 매니지먼트 어시스턴트 | CLIO
  engine: string; // OpenAI · 실측+KB | Gemini
  citations?: Citation[];
  used_tools?: string[];
  thread_id?: string; // 피드백 적재 키
  campaigns?: Campaign[]; // live_campaigns 결과 — 클릭해서 관리 페이지로 이동
};
type Message = {
  role: 'user' | 'assistant';
  content: string;
  meta?: SourceMeta;
};

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

// AI 답변의 마크다운을 렌더링 — **bold**, *italic*, `code`, 리스트, 헤딩 지원
function renderMarkdown(text: string) {
  const parseInline = (s: string) =>
    s.split(/(\*\*[^*\n]+\*\*|`[^`\n]+`|\*[^*\n]+\*)/).map((part, i) => {
      if (part.startsWith('**') && part.endsWith('**'))
        return <strong key={i}>{part.slice(2, -2)}</strong>;
      if (part.startsWith('`') && part.endsWith('`'))
        return (
          <code key={i} className="text-[11px] bg-black/[0.07] dark:bg-white/10 px-1 py-0.5 rounded font-mono">
            {part.slice(1, -1)}
          </code>
        );
      if (part.startsWith('*') && part.endsWith('*'))
        return <em key={i}>{part.slice(1, -1)}</em>;
      return part;
    });

  const nodes = text.split('\n').map((line, i) => {
    if (line.startsWith('### '))
      return <p key={i} className="font-bold text-sm mt-1.5">{parseInline(line.slice(4))}</p>;
    if (line.startsWith('## '))
      return <p key={i} className="font-semibold text-sm mt-1.5">{parseInline(line.slice(3))}</p>;
    if (line.startsWith('# '))
      return <p key={i} className="font-bold mt-1.5">{parseInline(line.slice(2))}</p>;
    if (line.startsWith('- ') || line.startsWith('• '))
      return (
        <p key={i} className="flex gap-1.5 pl-1">
          <span className="shrink-0 opacity-50 mt-0.5">•</span>
          <span>{parseInline(line.slice(2))}</span>
        </p>
      );
    if (/^\d+\. /.test(line)) {
      const m = line.match(/^(\d+)\. (.*)/)!;
      return (
        <p key={i} className="flex gap-1.5 pl-1">
          <span className="shrink-0 opacity-50 tabular-nums">{m[1]}.</span>
          <span>{parseInline(m[2])}</span>
        </p>
      );
    }
    if (line === '') return <div key={i} className="h-1.5" />;
    return <p key={i}>{parseInline(line)}</p>;
  });
  return <>{nodes}</>;
}

function MicIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
      <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
      <line x1="12" y1="19" x2="12" y2="23" />
      <line x1="8" y1="23" x2="16" y2="23" />
    </svg>
  );
}

function SpeakerIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
      <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
      <path d="M19.07 4.93a10 10 0 0 1 0 14.14" />
    </svg>
  );
}

function SendIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  );
}

function StopStreamIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
      <rect x="4" y="4" width="16" height="16" rx="2" />
    </svg>
  );
}

function SpeakerOffIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
      <line x1="23" y1="9" x2="17" y2="15" />
      <line x1="17" y1="9" x2="23" y2="15" />
    </svg>
  );
}

function TypingIndicator() {
  return (
    <div className="flex gap-3 justify-start">
      <div className="w-7 h-7 shrink-0 flex items-center justify-center rounded-lg bg-[#EBF3FF] dark:bg-[#1E3A5F] text-[#3182F6] mt-1">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
      </div>
      <div className="px-4 py-3 rounded-2xl rounded-bl-md bg-[#F2F4F6] dark:bg-[#252D3D] flex items-center gap-1.5">
        <span className="w-2 h-2 rounded-full bg-[#8B95A1] dark:bg-[#6B7280] animate-bounce [animation-delay:-0.3s]" />
        <span className="w-2 h-2 rounded-full bg-[#8B95A1] dark:bg-[#6B7280] animate-bounce [animation-delay:-0.15s]" />
        <span className="w-2 h-2 rounded-full bg-[#8B95A1] dark:bg-[#6B7280] animate-bounce" />
      </div>
    </div>
  );
}

export default function Page() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [fb, setFb] = useState<Record<number, number>>({}); // 메시지 index → 평가(1/-1)

  // 어시스턴트 답변 평가 적재(좋아요/싫어요) — RAG 품질 개선.
  const sendFeedback = async (i: number, rating: number) => {
    const msg = messages[i];
    setFb((p) => ({ ...p, [i]: rating }));
    try {
      await api.chat.feedback({
        thread_id: msg.meta?.thread_id,
        rating,
        question: messages[i - 1]?.content,
        answer: msg.content,
      });
    } catch {
      /* 적재 실패는 조용히 무시 */
    }
  };

  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const sessionId = useRef<string>('');
  if (!sessionId.current) sessionId.current = safeRandomUUID();
  const bottomRef = useRef<HTMLDivElement>(null);

  // Web Speech API 상태 — STT(마이크 입력) + TTS(읽어주기)
  const [listening, setListening] = useState(false);
  const recognitionRef = useRef<{ stop: () => void } | null>(null);
  const voiceTextRef = useRef(''); // STT 결과를 onend에서 자동전송하기 위한 ref
  const [voiceSupported, setVoiceSupported] = useState(false);
  const [ttsSupported, setTtsSupported] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [isSpeaking, setIsSpeaking] = useState(false); // TTS 재생 중 여부
  // 시각장애 접근성 — 자동 읽기: AI 응답 완료 시 TTS 자동 재생
  const [autoRead, setAutoRead] = useState(false);
  // 스트리밍 중지용 AbortController
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isStreaming]);

  useEffect(() => {
    const sw = window as SpeechWindow;
    setVoiceSupported(typeof sw.SpeechRecognition === 'function' || typeof sw.webkitSpeechRecognition === 'function');
    setTtsSupported(typeof window.speechSynthesis !== 'undefined');
  }, []);

  // STT: 마이크 버튼 클릭 → 브라우저 Web Speech API → 입력창에 채움. 무료, API 키 없음.
  const startVoice = () => {
    setVoiceError(null);
    const sw = window as SpeechWindow;
    const Ctor = sw.SpeechRecognition ?? sw.webkitSpeechRecognition;
    if (!Ctor) return;
    setVoiceError(null);
    const rec = new Ctor();
    rec.lang = 'ko-KR';
    rec.continuous = false;
    rec.interimResults = true;
    rec.onresult = (e) => {
      let t = '';
      for (let i = 0; i < e.results.length; i++) t += e.results[i][0].transcript;
      voiceTextRef.current = t;
      setInput(t);
    };
    // 인식 완료 → 텍스트가 있으면 자동 전송 (음성으로 검색)
    rec.onend = () => {
      setListening(false);
      const text = voiceTextRef.current.trim();
      voiceTextRef.current = '';
      if (text) handleSend(text);
    };
    rec.onerror = (e) => {
      setListening(false);
      voiceTextRef.current = '';
      if (e.error === 'not-allowed' || e.error === 'audio-capture') {
        setVoiceError('마이크 권한이 필요해요. 주소창 왼쪽 🔒 → 사이트 설정 → 마이크 허용 후 새로고침해 주세요.');
      } else if (e.error === 'no-speech') {
        setVoiceError('소리가 감지되지 않았어요. 다시 눌러 말씀해 주세요.');
      }
    };
    recognitionRef.current = rec;
    rec.start();
    setListening(true);
  };

  const stopVoice = () => {
    voiceTextRef.current = ''; // 수동 중지 시 자동전송 방지
    recognitionRef.current?.stop();
    setListening(false);
  };

  // TTS: 마크다운 기호 제거 후 음성으로 읽어주기. 무료, API 키 없음.
  const speakText = (text: string) => {
    if (!window.speechSynthesis) return;
    // 마크다운 제거 — **bold**, *italic*, `code`, ## heading, - bullet 등
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

  // 운동장애 — Escape 키로 음성입력·TTS·스트리밍 즉시 중지
  useEffect(() => {
    const onEsc = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      if (listening) stopVoice();
      if (window.speechSynthesis?.speaking) { window.speechSynthesis.cancel(); setIsSpeaking(false); }
      abortRef.current?.abort();
    };
    document.addEventListener('keydown', onEsc);
    return () => document.removeEventListener('keydown', onEsc);
  }, [listening]);

  // 시각장애 — 자동 읽기: 스트리밍 완료 후 마지막 AI 메시지 자동 TTS
  useEffect(() => {
    if (!autoRead || !ttsSupported || isStreaming) return;
    const last = messages[messages.length - 1];
    if (last?.role === 'assistant' && last.content) speakText(last.content);
    // messages는 isStreaming이 false로 바뀌는 순간 최신 상태. 이 시점만 트리거.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isStreaming, autoRead, ttsSupported]);

  const handleStopStream = () => {
    abortRef.current?.abort();
  };

  const handleSend = async (text?: string) => {
    const content = text ?? input.trim();
    if (!content || isStreaming) return;

    const newMessages: Message[] = [...messages, { role: 'user', content }];
    setMessages(newMessages);
    setInput('');
    setIsStreaming(true);

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    try {
      const res = await fetch(`${API_BASE}/api/chat/complete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId.current, messages: newMessages }),
        signal: ctrl.signal,
      });

      if (!res.ok || !res.body) {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: '응답을 가져오는 중 오류가 발생했습니다.' },
        ]);
        setIsStreaming(false);
        return;
      }

      // add empty assistant placeholder
      setMessages((prev) => [...prev, { role: 'assistant', content: '' }]);

      const reader = res.body.getReader();
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
              token?: string;
              done?: boolean;
              meta?: SourceMeta;
            };
            if (data.done) {
              setIsStreaming(false);
            } else if (data.meta) {
              setMessages((prev) => {
                const last = prev[prev.length - 1];
                return [...prev.slice(0, -1), { ...last, meta: data.meta }];
              });
            } else if (data.token) {
              setMessages((prev) => {
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
    } catch (e) {
      // AbortError는 사용자가 직접 중지한 것 — 에러 메시지 불필요
      if (!(e instanceof Error) || e.name !== 'AbortError') {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: '서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.' },
        ]);
      }
    } finally {
      setIsStreaming(false);
      abortRef.current = null;
    }
  };

  return (
    <div className="h-screen bg-white dark:bg-[#0F1117] flex flex-col transition-colors">
      <div className="flex-1 flex flex-col overflow-hidden">
        {messages.length === 0 ? (
          /* ── Welcome state ── */
          <div className="flex-1 flex flex-col items-center justify-center px-4 pb-28">
            <div className="mb-2 w-10 h-10 flex items-center justify-center rounded-2xl bg-[#EBF3FF] dark:bg-[#1E3A5F]">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#3182F6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
            </div>
            <h2 className="text-xl font-bold text-[#191F28] dark:text-[#F2F4F6] mb-2 mt-3">무엇을 도와드릴까요?</h2>
            <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mb-10 text-center leading-relaxed">
              광고 분석, 성과 예측, 전략 제안까지<br />자유롭게 물어보세요
            </p>
            <div className="grid grid-cols-2 gap-3 w-full max-w-lg">
              {quickPrompts.map((prompt) => (
                <button
                  key={prompt}
                  onClick={() => handleSend(prompt)}
                  className="p-4 text-left text-sm text-[#4E5968] dark:text-[#9CA3AF] bg-[#F9FAFB] dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-xl hover:border-[#3182F6] hover:text-[#3182F6] hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F] transition-all"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        ) : (
          /* ── Messages ── */
          <div className="flex-1 overflow-y-auto">
            {/* aria-live: 스크린리더가 새 AI 응답을 자동으로 읽어줌 (시각장애 접근성) */}
            <div role="log" aria-live="polite" aria-atomic="false" aria-label="대화 내용" className="max-w-2xl mx-auto px-4 py-8 space-y-6">
              {messages.map((msg, i) => {
                // 빈 assistant placeholder는 타이핑 인디케이터로 대체
                if (msg.role === 'assistant' && msg.content === '') return null;
                return (
                  <div
                    key={i}
                    className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                  >
                    {msg.role === 'assistant' && (
                      <div className="w-7 h-7 shrink-0 flex items-center justify-center rounded-lg bg-[#EBF3FF] dark:bg-[#1E3A5F] text-[#3182F6] mt-1">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                        </svg>
                      </div>
                    )}
                    <div className={`flex flex-col gap-1 max-w-sm ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
                      {msg.role === 'assistant' && msg.meta && (
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                            msg.meta.source === 'management'
                              ? 'bg-[#EBF3FF] text-[#3182F6] dark:bg-[#1E3A5F] dark:text-[#7BB4F5]'
                              : 'bg-[#F2E9FF] text-[#7C3AED] dark:bg-[#2E1F47] dark:text-[#C4A8F5]'
                          }`}
                        >
                          {msg.meta.source === 'management' ? '⚙' : '🧠'} {msg.meta.label} · {msg.meta.engine}
                        </span>
                      )}
                      {/* 메시지 버블 — 사용자: plain text, 어시스턴트: 마크다운 렌더링 */}
                      <div
                        className={`px-4 py-3 rounded-2xl text-sm leading-relaxed ${
                          msg.role === 'user'
                            ? 'bg-[#3182F6] text-white rounded-br-md whitespace-pre-wrap'
                            : 'bg-[#F2F4F6] dark:bg-[#252D3D] text-[#191F28] dark:text-[#F2F4F6] rounded-bl-md'
                        }`}
                      >
                        {msg.role === 'user' ? msg.content : renderMarkdown(msg.content)}
                      </div>
                      {/* TTS 읽어주기 버튼 — 브라우저 SpeechSynthesis, 무료 */}
                      {msg.role === 'assistant' && msg.content && ttsSupported && (
                        <button
                          onClick={() => speakText(msg.content)}
                          title="소리로 읽기"
                          aria-label="이 답변 소리로 읽기"
                          className="self-start text-[#B0B8C1] dark:text-[#4B5563] hover:text-[#3182F6] dark:hover:text-[#7BB4F5] px-1 py-0.5 transition-colors"
                        >
                          <SpeakerIcon />
                        </button>
                      )}
                      {msg.role === 'assistant' &&
                        msg.meta?.source === 'management' &&
                        (msg.meta.citations?.length || msg.meta.used_tools?.length) ? (
                        <div className="flex flex-wrap items-center gap-1 px-1">
                          <span className="text-[10px] text-[#B0B8C1] dark:text-[#6B7280]">근거:</span>
                          {(msg.meta.used_tools ?? []).map((t, ti) => (
                            <span
                              key={`t${ti}`}
                              className="text-[10px] px-1.5 py-0.5 rounded bg-[#EAF2FF] text-[#3182F6] dark:bg-[#1E2A44] dark:text-[#8AB4F8]"
                            >
                              {t
                                .replace('live_campaigns', '실측·캠페인')
                                .replace('live_budget', '실측·예산')
                                .replace('live_campaign_detail', '실측·캠페인')
                                .replace('live_before_after', '실측·전후비교')
                                .replace('search_kb', 'KB')
                                .replace('web_search', '웹')}
                            </span>
                          ))}
                          {(msg.meta.citations ?? [])
                            .filter((c) => c.kind === 'kb' || c.kind === 'web')
                            .map((c, ci) => {
                              if (c.kind === 'web') {
                                const label = (c.title || c.source_url || '웹') + ' · 웹';
                                const chip = (
                                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-sky-50 text-sky-700 dark:bg-sky-900/30 dark:text-sky-300">
                                    🌐 {label}
                                  </span>
                                );
                                return c.source_url ? (
                                  <a key={`c${ci}`} href={c.source_url} target="_blank" rel="noreferrer" className="hover:underline" title={c.source_url}>
                                    {chip}
                                  </a>
                                ) : (
                                  <span key={`c${ci}`}>{chip}</span>
                                );
                              }
                              const trust = c.trust ?? 'system_backed';
                              const style =
                                trust === 'advisory'
                                  ? 'bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300'
                                  : trust === 'reference'
                                    ? 'bg-[#F2F4F6] text-[#6B7280] dark:bg-[#252D3D] dark:text-[#9CA3AF]'
                                    : 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300';
                              const tag =
                                trust === 'advisory' ? '참고' : trust === 'reference' ? '구성' : '기준';
                              const label =
                                (c.title || c.source.replace('.md', '')) +
                                (c.as_of ? ` · ${c.as_of}` : '') +
                                ` · ${tag}`;
                              const chip = (
                                <span className={`text-[10px] px-1.5 py-0.5 rounded ${style}`}>
                                  {label}
                                </span>
                              );
                              return c.source_url ? (
                                <a
                                  key={`c${ci}`}
                                  href={c.source_url}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="hover:underline"
                                  title={c.source_url}
                                >
                                  {chip}
                                </a>
                              ) : (
                                <span key={`c${ci}`}>{chip}</span>
                              );
                            })}
                        </div>
                      ) : null}
                      {msg.role === 'assistant' &&
                        msg.meta?.source === 'management' &&
                        (msg.meta.campaigns?.length ?? 0) > 0 ? (
                        <div className="flex flex-wrap items-center gap-1 px-1">
                          <span className="text-[10px] text-[#B0B8C1] dark:text-[#6B7280]">캠페인:</span>
                          {(msg.meta.campaigns ?? []).map((c) => (
                            <Link key={c.campaign_id} href={`/manage/campaigns?open=${c.campaign_id}`}>
                              <span
                                className={`text-[10px] px-1.5 py-0.5 rounded border cursor-pointer transition-colors ${
                                  c.status === 'ACTIVE'
                                    ? 'border-emerald-200 text-emerald-700 hover:bg-emerald-50 dark:border-emerald-800 dark:text-emerald-400 dark:hover:bg-emerald-900/20'
                                    : 'border-[#E5E8EB] text-[#4E5968] hover:bg-[#EBF3FF] hover:text-[#3182F6] dark:border-[#2D3748] dark:text-[#9CA3AF] dark:hover:bg-[#1E3A5F]'
                                }`}
                                title={`${c.status}${c.spend != null ? ` · ${c.spend.toLocaleString()} KRW` : ''}`}
                              >
                                {c.name} →
                              </span>
                            </Link>
                          ))}
                        </div>
                      ) : null}
                      {/* 매니지먼트 답변 평가(좋아요/싫어요) — RAG 개선 적재 */}
                      {msg.role === 'assistant' && msg.meta?.source === 'management' && msg.content ? (
                        <div className="flex items-center gap-1 px-1">
                          <button
                            onClick={() => sendFeedback(i, 1)}
                            disabled={fb[i] !== undefined}
                            className={`text-[12px] px-1.5 py-0.5 rounded ${
                              fb[i] === 1 ? 'text-[#3182F6]' : 'text-[#B0B8C1] hover:text-[#3182F6]'
                            } disabled:cursor-default`}
                            title="도움이 됐어요"
                            aria-label="도움이 됐어요"
                          >
                            👍
                          </button>
                          <button
                            onClick={() => sendFeedback(i, -1)}
                            disabled={fb[i] !== undefined}
                            className={`text-[12px] px-1.5 py-0.5 rounded ${
                              fb[i] === -1 ? 'text-red-500' : 'text-[#B0B8C1] hover:text-red-500'
                            } disabled:cursor-default`}
                            title="별로예요"
                            aria-label="별로예요"
                          >
                            👎
                          </button>
                          {fb[i] !== undefined && (
                            <span className="text-[10px] text-[#B0B8C1]">평가 감사합니다</span>
                          )}
                        </div>
                      ) : null}
                    </div>
                  </div>
                );
              })}

              {/* 타이핑 인디케이터: 스트리밍 중이고 아직 토큰 미도착 */}
              {isStreaming && messages.length > 0 && messages[messages.length - 1].role === 'assistant' && messages[messages.length - 1].content === '' && (
                <TypingIndicator />
              )}

              <div ref={bottomRef} />
            </div>
          </div>
        )}

        {/* ── Input bar ── */}
        <div className="border-t border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#1C2333] px-4 py-4 transition-colors">
          <div className="max-w-2xl mx-auto flex items-end gap-3">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder={listening ? '듣는 중…' : '메시지를 입력하세요... (Shift+Enter로 줄바꿈)'}
              rows={1}
              aria-label="메시지 입력창"
              className="flex-1 px-4 py-3 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] text-sm text-[#191F28] dark:text-[#F2F4F6] placeholder-[#B0B8C1] dark:placeholder-[#4B5563] focus:outline-none focus:border-[#3182F6] focus:ring-2 focus:ring-[#3182F6]/10 transition-colors resize-none overflow-hidden bg-white dark:bg-[#252D3D] leading-relaxed"
              style={{ maxHeight: '120px' }}
            />
            {/* 소리 정지 — TTS 재생 중일 때만 표시 */}
            {isSpeaking && (
              <button
                onClick={stopSpeak}
                title="소리 정지"
                aria-label="소리 정지"
                className="p-3 rounded-xl bg-red-100 text-red-500 hover:bg-red-200 dark:bg-red-900/30 dark:text-red-400 animate-pulse transition-all shrink-0"
              >
                <SpeakerOffIcon />
              </button>
            )}
            {/* 시각장애 자동읽기 토글 — AI 응답 완료 시 TTS 자동 재생 */}
            {ttsSupported && (
              <button
                onClick={() => setAutoRead((v) => !v)}
                title={autoRead ? '자동 읽기 끄기' : '자동 읽기 켜기'}
                aria-label={autoRead ? '자동 읽기 끄기' : '자동 읽기 켜기'}
                aria-pressed={autoRead}
                className={`p-3 rounded-xl transition-all shrink-0 ${
                  autoRead
                    ? 'bg-[#EBF3FF] text-[#3182F6] dark:bg-[#1E3A5F] dark:text-[#7BB4F5]'
                    : 'text-[#B0B8C1] hover:text-[#3182F6] hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F]'
                }`}
              >
                <SpeakerIcon />
              </button>
            )}
            {/* 음성 입력 버튼 — Web Speech API, 무료, Chrome/Edge 지원 */}
            {voiceSupported && (
              <button
                onClick={listening ? stopVoice : startVoice}
                disabled={isStreaming}
                title={listening ? '음성 입력 중지' : '음성으로 입력 (ko-KR)'}
                aria-label={listening ? '음성 입력 중지' : '음성 입력 시작'}
                aria-pressed={listening}
                className={`p-3 rounded-xl transition-all shrink-0 ${
                  listening
                    ? 'bg-red-100 text-red-500 hover:bg-red-200 dark:bg-red-900/30 dark:text-red-400 animate-pulse'
                    : 'text-[#8B95A1] hover:text-[#3182F6] hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F]'
                } disabled:opacity-30 disabled:cursor-not-allowed`}
              >
                <MicIcon />
              </button>
            )}
            {/* 전송 버튼 — 스트리밍 중에는 중지 버튼으로 대체 */}
            {isStreaming ? (
              <button
                onClick={handleStopStream}
                title="응답 중지"
                aria-label="AI 응답 중지"
                className="p-3 bg-[#EF4444] text-white rounded-xl hover:bg-[#DC2626] transition-all shrink-0"
              >
                <StopStreamIcon />
              </button>
            ) : (
              <button
                onClick={() => handleSend()}
                disabled={!input.trim()}
                aria-label="메시지 전송"
                className="p-3 bg-[#3182F6] text-white rounded-xl hover:bg-[#1B6EEB] disabled:opacity-30 disabled:cursor-not-allowed transition-all shrink-0"
              >
                <SendIcon />
              </button>
            )}
          </div>
          {voiceError && (
            <p className="text-center text-xs text-amber-600 dark:text-amber-400 mt-2">
              🎤 {voiceError}
            </p>
          )}
          <p className="text-center text-xs text-[#B0B8C1] dark:text-[#4B5563] mt-1">
            AI 응답은 참고용이며 실제 광고 성과와 차이가 있을 수 있습니다
          </p>
        </div>
      </div>
    </div>
  );
}
