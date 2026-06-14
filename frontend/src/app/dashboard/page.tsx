'use client';

import { useState, useRef, useEffect } from 'react';
import Link from 'next/link';
import AppLayout from '@/components/AppLayout';
import { getToken } from '@/lib/authApi';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

// ────────────────── Types ──────────────────

type DashboardStats = {
  total_simulations: number;
  total_generations: number;
  avg_purchase_intent: number | null;
};

type RecentSimulation = {
  id: string;
  ad_id: string;
  persona_count: number;
  avg_intent: number | null;
  created_at: string;
};

type RecentGeneration = {
  id: string;
  status: string;
  product_name: string | null;
  created_at: string;
};

type Message = { role: 'user' | 'assistant'; content: string };
type Project = { id: string; name: string; description: string | null; created_at: string };

// ────────────────── 상수 ──────────────────

const featureCards = [
  {
    title: '광고 시뮬레이션',
    desc: 'OCEAN 모델 기반 AI 가상 소비자 20명에게 광고를 테스트하고 구매의향 분포를 예측합니다.',
    href: '/simulation',
    label: '시뮬레이션 시작',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" />
        <path d="M23 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" />
      </svg>
    ),
  },
  {
    title: '광고 제너레이터',
    desc: '시뮬레이션 결과를 기반으로 최적화된 광고 카피와 소재를 AI가 자동으로 생성합니다.',
    href: '/generator',
    label: '광고 생성하기',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
      </svg>
    ),
  },
  {
    title: '광고 매니지먼트',
    desc: '집행한 광고의 실제 성과를 시뮬레이션 예측치와 비교하고 캠페인을 관리합니다.',
    href: '/manage',
    label: '성과 확인하기',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <line x1="18" y1="20" x2="18" y2="10" /><line x1="12" y1="20" x2="12" y2="4" /><line x1="6" y1="20" x2="6" y2="14" />
      </svg>
    ),
  },
];

const quickPrompts = [
  '이 광고의 예상 CTR을 분석해줘',
  '20대 여성 타겟 광고 전략을 추천해줘',
  '경쟁사 광고와 비교 분석해줘',
  '광고 카피 개선 방법을 알려줘',
];

const statusLabel: Record<string, { text: string; color: string }> = {
  completed: { text: '완료', color: 'text-emerald-500 bg-emerald-50 dark:bg-emerald-900/20' },
  running: { text: '진행 중', color: 'text-blue-500 bg-blue-50 dark:bg-blue-900/20' },
  pending: { text: '대기', color: 'text-yellow-500 bg-yellow-50 dark:bg-yellow-900/20' },
  failed: { text: '실패', color: 'text-red-500 bg-red-50 dark:bg-red-900/20' },
};

// ────────────────── Utils ──────────────────

function formatDate(iso: string) {
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function shortId(id: string) {
  return id.slice(0, 8);
}

// ────────────────── Sub-components ──────────────────

function SendIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  );
}

function ArrowIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="5" y1="12" x2="19" y2="12" /><polyline points="12 5 19 12 12 19" />
    </svg>
  );
}

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl px-6 py-5">
      <p className="text-xs font-medium text-[#8B95A1] dark:text-[#6B7280] mb-1">{label}</p>
      <p className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">{value}</p>
      {sub && <p className="text-xs text-[#B0B8C1] dark:text-[#4B5563] mt-1">{sub}</p>}
    </div>
  );
}

// ────────────────── Main ──────────────────

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [recentSims, setRecentSims] = useState<RecentSimulation[]>([]);
  const [recentGens, setRecentGens] = useState<RecentGeneration[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const sessionId = useRef(crypto.randomUUID());
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE}/api/dashboard/stats`).then((r) => r.json()).catch(() => null),
      fetch(`${API_BASE}/api/dashboard/recent-simulations?limit=5`).then((r) => r.json()).catch(() => []),
      fetch(`${API_BASE}/api/dashboard/recent-generations?limit=5`).then((r) => r.json()).catch(() => []),
      fetch(`${API_BASE}/api/projects`, { headers: { Authorization: `Bearer ${getToken()}` } }).then((r) => r.json()).catch(() => []),
    ]).then(([s, sims, gens, projs]) => {
      if (s) setStats(s);
      if (Array.isArray(sims)) setRecentSims(sims);
      if (Array.isArray(gens)) setRecentGens(gens);
      if (Array.isArray(projs)) setProjects(projs);
    });
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isStreaming]);

  const handleSend = async (text?: string) => {
    const content = text ?? input.trim();
    if (!content || isStreaming) return;

    const newMessages: Message[] = [...messages, { role: 'user', content }];
    setMessages(newMessages);
    setInput('');
    setIsStreaming(true);

    try {
      const res = await fetch(`${API_BASE}/api/chat/complete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId.current, messages: newMessages }),
      });

      if (!res.ok || !res.body) {
        setMessages((prev) => [...prev, { role: 'assistant', content: '응답을 가져오는 중 오류가 발생했습니다.' }]);
        setIsStreaming(false);
        return;
      }

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
            const data = JSON.parse(raw) as { token?: string; done?: boolean };
            if (data.done) setIsStreaming(false);
            else if (data.token) {
              setMessages((prev) => {
                const last = prev[prev.length - 1];
                return [...prev.slice(0, -1), { ...last, content: last.content + data.token }];
              });
            }
          } catch { /* ignore */ }
        }
      }
    } catch {
      setMessages((prev) => [...prev, { role: 'assistant', content: '서버에 연결할 수 없습니다.' }]);
    } finally {
      setIsStreaming(false);
    }
  };

  return (
    <AppLayout>
      <div className="p-8 max-w-6xl mx-auto space-y-7">

        {/* ── 타이틀 ── */}
        <div>
          <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">대시보드</h1>
          <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mt-1">광고 기획부터 성과 관리까지 한곳에서</p>
        </div>

        {/* ── KPI 카드 ── */}
        <div className="grid grid-cols-3 gap-4">
          <StatCard
            label="전체 시뮬레이션"
            value={stats ? `${stats.total_simulations}건` : '—'}
            sub="누적 실행 횟수"
          />
          <StatCard
            label="전체 광고 생성"
            value={stats ? `${stats.total_generations}건` : '—'}
            sub="누적 생성 횟수"
          />
          <StatCard
            label="평균 구매의향"
            value={
              stats?.avg_purchase_intent != null
                ? `${stats.avg_purchase_intent > 0 ? '+' : ''}${stats.avg_purchase_intent}`
                : '—'
            }
            sub="전체 시뮬레이션 기준"
          />
        </div>

        {/* ── 프로젝트 ── */}
        <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl overflow-hidden">
          <div className="flex items-center justify-between px-6 py-4 border-b border-[#E5E8EB] dark:border-[#2D3748]">
            <div className="flex items-center gap-2">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#3182F6" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
              </svg>
              <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">프로젝트</p>
              {projects.length > 0 && (
                <span className="text-xs text-[#8B95A1] dark:text-[#6B7280]">({projects.length}개)</span>
              )}
            </div>
            <Link href="/projects" className="text-xs text-[#3182F6] hover:underline font-medium">관리하기 →</Link>
          </div>
          {projects.length === 0 ? (
            <div className="px-6 py-8 text-center">
              <p className="text-xs text-[#B0B8C1] dark:text-[#4B5563] mb-3">아직 프로젝트가 없습니다</p>
              <Link href="/projects" className="inline-flex items-center gap-1 px-3 py-1.5 bg-[#3182F6] text-white text-xs font-medium rounded-lg hover:bg-[#1B6EEB] transition-colors">
                첫 프로젝트 만들기
              </Link>
            </div>
          ) : (
            <div className="divide-y divide-[#F2F4F6] dark:divide-[#252D3D]">
              {projects.slice(0, 5).map((p) => (
                <div key={p.id} className="flex items-center gap-3 px-6 py-3 hover:bg-[#F9FAFB] dark:hover:bg-[#252D3D] transition-colors">
                  <div className="w-7 h-7 rounded-lg bg-[#EBF3FF] dark:bg-[#1E3A5F] flex items-center justify-center shrink-0">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#3182F6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
                    </svg>
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-[#191F28] dark:text-[#F2F4F6] truncate">{p.name}</p>
                    {p.description && <p className="text-[10px] text-[#8B95A1] truncate">{p.description}</p>}
                  </div>
                  <p className="text-[10px] text-[#B0B8C1] dark:text-[#4B5563] shrink-0">{formatDate(p.created_at)}</p>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ── 기능 카드 ── */}
        <div className="grid grid-cols-3 gap-4">
          {featureCards.map((card) => (
            <div
              key={card.href}
              className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-5 hover:shadow-md hover:border-[#3182F6]/30 transition-all group"
            >
              <div className="w-9 h-9 flex items-center justify-center rounded-xl bg-[#EBF3FF] dark:bg-[#1E3A5F] text-[#3182F6] mb-3 group-hover:bg-[#3182F6] group-hover:text-white transition-colors">
                {card.icon}
              </div>
              <h3 className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-1">{card.title}</h3>
              <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] leading-relaxed mb-4">{card.desc}</p>
              <Link href={card.href} className="inline-flex items-center gap-1 text-xs font-medium text-[#3182F6] hover:underline">
                {card.label} <ArrowIcon />
              </Link>
            </div>
          ))}
        </div>

        {/* ── 최근 내역 2열 ── */}
        <div className="grid grid-cols-2 gap-5">

          {/* 최근 시뮬레이션 */}
          <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-[#E5E8EB] dark:border-[#2D3748]">
              <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">최근 시뮬레이션</p>
              <Link href="/simulation" className="text-xs text-[#3182F6] hover:underline font-medium">전체 보기 →</Link>
            </div>
            {recentSims.length === 0 ? (
              <div className="py-12 text-center text-xs text-[#B0B8C1] dark:text-[#4B5563]">
                아직 시뮬레이션 내역이 없습니다
              </div>
            ) : (
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-[#F2F4F6] dark:border-[#252D3D]">
                    <th className="text-left px-5 py-2.5 text-[#8B95A1] dark:text-[#6B7280] font-medium">ID</th>
                    <th className="text-left px-3 py-2.5 text-[#8B95A1] dark:text-[#6B7280] font-medium">페르소나</th>
                    <th className="text-left px-3 py-2.5 text-[#8B95A1] dark:text-[#6B7280] font-medium">평균 의향</th>
                    <th className="text-left px-3 py-2.5 text-[#8B95A1] dark:text-[#6B7280] font-medium">일시</th>
                  </tr>
                </thead>
                <tbody>
                  {recentSims.map((s) => (
                    <tr key={s.id} className="border-b border-[#F9FAFB] dark:border-[#1C2333] last:border-0 hover:bg-[#F9FAFB] dark:hover:bg-[#252D3D] transition-colors">
                      <td className="px-5 py-3 font-mono text-[#4E5968] dark:text-[#9CA3AF]">{shortId(s.id)}</td>
                      <td className="px-3 py-3 text-[#4E5968] dark:text-[#9CA3AF]">{s.persona_count}명</td>
                      <td className="px-3 py-3 text-[#4E5968] dark:text-[#9CA3AF]">
                        {s.avg_intent != null
                          ? <span className={s.avg_intent >= 0 ? 'text-emerald-500' : 'text-red-400'}>{s.avg_intent > 0 ? '+' : ''}{s.avg_intent}</span>
                          : '—'
                        }
                      </td>
                      <td className="px-3 py-3 text-[#B0B8C1] dark:text-[#4B5563]">{formatDate(s.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* 최근 제너레이터 */}
          <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-[#E5E8EB] dark:border-[#2D3748]">
              <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">최근 제너레이터</p>
              <Link href="/generator" className="text-xs text-[#3182F6] hover:underline font-medium">전체 보기 →</Link>
            </div>
            {recentGens.length === 0 ? (
              <div className="py-12 text-center text-xs text-[#B0B8C1] dark:text-[#4B5563]">
                아직 생성 내역이 없습니다
              </div>
            ) : (
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-[#F2F4F6] dark:border-[#252D3D]">
                    <th className="text-left px-5 py-2.5 text-[#8B95A1] dark:text-[#6B7280] font-medium">ID</th>
                    <th className="text-left px-3 py-2.5 text-[#8B95A1] dark:text-[#6B7280] font-medium">상품명</th>
                    <th className="text-left px-3 py-2.5 text-[#8B95A1] dark:text-[#6B7280] font-medium">상태</th>
                    <th className="text-left px-3 py-2.5 text-[#8B95A1] dark:text-[#6B7280] font-medium">일시</th>
                  </tr>
                </thead>
                <tbody>
                  {recentGens.map((g) => {
                    const s = statusLabel[g.status] ?? { text: g.status, color: 'text-[#8B95A1]' };
                    return (
                      <tr key={g.id} className="border-b border-[#F9FAFB] dark:border-[#1C2333] last:border-0 hover:bg-[#F9FAFB] dark:hover:bg-[#252D3D] transition-colors">
                        <td className="px-5 py-3 font-mono text-[#4E5968] dark:text-[#9CA3AF]">{shortId(g.id)}</td>
                        <td className="px-3 py-3 text-[#4E5968] dark:text-[#9CA3AF] max-w-[100px] truncate">{g.product_name ?? '—'}</td>
                        <td className="px-3 py-3">
                          <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-medium ${s.color}`}>{s.text}</span>
                        </td>
                        <td className="px-3 py-3 text-[#B0B8C1] dark:text-[#4B5563]">{formatDate(g.created_at)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* ── CLIO 챗봇 ── */}
        <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl overflow-hidden">
          <div className="flex items-center justify-between px-6 py-4 border-b border-[#E5E8EB] dark:border-[#2D3748]">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 flex items-center justify-center rounded-xl bg-[#EBF3FF] dark:bg-[#1E3A5F] text-[#3182F6]">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                </svg>
              </div>
              <div>
                <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">CLIO</p>
                <p className="text-xs text-[#8B95A1] dark:text-[#6B7280]">광고 전략 AI 어드바이저</p>
              </div>
            </div>
            <Link href="/chat" className="text-xs text-[#3182F6] hover:underline font-medium">전체 화면으로 →</Link>
          </div>

          {/* 메시지 영역 */}
          <div className="h-64 overflow-y-auto px-6 py-4 space-y-3">
            {messages.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-center">
                <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mb-3">광고 전략에 대해 무엇이든 물어보세요</p>
                <div className="grid grid-cols-2 gap-2 w-full max-w-md">
                  {quickPrompts.map((prompt) => (
                    <button
                      key={prompt}
                      onClick={() => handleSend(prompt)}
                      className="p-2.5 text-left text-xs text-[#4E5968] dark:text-[#9CA3AF] bg-[#F9FAFB] dark:bg-[#252D3D] border border-[#E5E8EB] dark:border-[#2D3748] rounded-xl hover:border-[#3182F6] hover:text-[#3182F6] hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F] transition-all"
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <>
                {messages.map((msg, i) => {
                  if (msg.role === 'assistant' && msg.content === '') return null;
                  return (
                    <div key={i} className={`flex gap-2 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                      {msg.role === 'assistant' && (
                        <div className="w-5 h-5 shrink-0 flex items-center justify-center rounded-md bg-[#EBF3FF] dark:bg-[#1E3A5F] text-[#3182F6] mt-0.5">
                          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                          </svg>
                        </div>
                      )}
                      <div className={`max-w-xs px-3 py-2 rounded-xl text-xs leading-relaxed whitespace-pre-wrap ${
                        msg.role === 'user'
                          ? 'bg-[#3182F6] text-white rounded-br-sm'
                          : 'bg-[#F2F4F6] dark:bg-[#252D3D] text-[#191F28] dark:text-[#F2F4F6] rounded-bl-sm'
                      }`}>
                        {msg.content}
                      </div>
                    </div>
                  );
                })}
                {isStreaming && messages.at(-1)?.content === '' && (
                  <div className="flex gap-2 justify-start">
                    <div className="px-3 py-2 rounded-xl bg-[#F2F4F6] dark:bg-[#252D3D] flex items-center gap-1">
                      <span className="w-1.5 h-1.5 rounded-full bg-[#8B95A1] animate-bounce [animation-delay:-0.3s]" />
                      <span className="w-1.5 h-1.5 rounded-full bg-[#8B95A1] animate-bounce [animation-delay:-0.15s]" />
                      <span className="w-1.5 h-1.5 rounded-full bg-[#8B95A1] animate-bounce" />
                    </div>
                  </div>
                )}
                <div ref={bottomRef} />
              </>
            )}
          </div>

          {/* 입력창 */}
          <div className="px-4 py-3 border-t border-[#E5E8EB] dark:border-[#2D3748] flex items-end gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
              placeholder="메시지를 입력하세요..."
              rows={1}
              disabled={isStreaming}
              className="flex-1 px-3 py-2.5 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] text-sm text-[#191F28] dark:text-[#F2F4F6] placeholder-[#B0B8C1] dark:placeholder-[#4B5563] focus:outline-none focus:border-[#3182F6] focus:ring-2 focus:ring-[#3182F6]/10 transition-colors resize-none bg-white dark:bg-[#252D3D] disabled:opacity-60"
              style={{ maxHeight: '80px' }}
            />
            <button
              onClick={() => handleSend()}
              disabled={!input.trim() || isStreaming}
              className="p-2.5 bg-[#3182F6] text-white rounded-xl hover:bg-[#1B6EEB] disabled:opacity-30 disabled:cursor-not-allowed transition-all shrink-0"
            >
              <SendIcon />
            </button>
          </div>
        </div>

      </div>
    </AppLayout>
  );
}
