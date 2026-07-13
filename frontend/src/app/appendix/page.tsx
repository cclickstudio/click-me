'use client';

// 발표 Q&A 부록 — 좌측은 AdminPanel과 같은 파일트리 스타일 내비게이터(도메인 폴더 → 질문 파일,
// 폴더 하나 열면 다른 폴더는 자동으로 닫힘), 우측은 선택한 질문에 답하며 보여줄 시각 자료 패널이다.
// 상단에는 포털사이트 스타일의 큰 검색창을 둔다. 우측 패널은 전체화면(진짜 PPT처럼) 전환 버튼을
// 지원 — Fullscreen API + CSS 오버레이를 함께 써서 iframe처럼 API가 막힌 환경에서도 동작한다.
// 프레젠테이션(빔 프로젝터용 확대) / 기본 열람 밀도를 라이트·다크 토글과 나란히 전환할 수 있다.
// 로그인 없이 접근 가능한 공개 라우트. 질문에 대한 글로 쓴 정답은 두지 않는다 — 자료만 스위칭한다.

import { useEffect, useMemo, useRef, useState } from 'react';
import { Search, ChevronRight, Sun, Moon, Maximize2, X } from 'lucide-react';
import { DOMAINS, EXHIBITS } from './_lib/exhibits';
import { TONE_CLASS, DensityProvider, type Density } from './_lib/primitives';
import { useTheme } from '@/components/ThemeProvider';

// 질문 번호 매핑 — 도메인 폴더 안에서의 원래 순서(1부터). 검색으로 목록이 걸러져도 번호는 유지된다.
const QUESTION_NO: Record<string, number> = Object.fromEntries(
  DOMAINS.flatMap((d) => d.questions.map((q, i) => [q.id, i + 1])),
);

// 초기 화면(질문 미선택)의 빈 여백을 채우는 실제 집행 스크린샷 — 매니지먼트 19번(mgmt-live-execution)과
// 같은 원본을 채널별(페북/인스타) 묶음으로 배치한다(좋아요 알림 컷은 제외).
const IDLE_SHOT_GROUPS = [
  [
    { src: '/appendix/fb-page.png', caption: 'Facebook 페이지 — 광고비피해자' },
    { src: '/appendix/fb-insights.png', caption: 'Facebook 프로페셔널 대시보드 인사이트' },
  ],
  [
    { src: '/appendix/ig-profile.png', caption: 'Instagram — @cclick_me 프로필' },
    { src: '/appendix/ig-insights.png', caption: 'Instagram 계정 인사이트' },
  ],
];

export default function AppendixPage() {
  const { theme, toggle } = useTheme();
  const [density, setDensity] = useState<Density>('presentation');
  const [query, setQuery] = useState('');
  // 첫 진입은 폴더 전부 닫힘 — 질문 미선택 상태의 실집행 스크린샷 화면이 먼저 보이게 한다.
  const [openDomain, setOpenDomain] = useState<string | null>(null);
  const [selectedByDomain, setSelectedByDomain] = useState<Record<string, string>>(() =>
    Object.fromEntries(DOMAINS.map((d) => [d.id, d.questions[0].id])),
  );
  const [fullscreen, setFullscreen] = useState(false);
  const stageRef = useRef<HTMLDivElement>(null);

  const big = density === 'presentation';
  const isSearching = query.trim().length > 0;

  const filteredDomains = useMemo(() => {
    const q = query.trim();
    if (!q) return DOMAINS;
    return DOMAINS.map((d) => ({
      ...d,
      questions: d.questions.filter((item) => item.q.includes(q) || EXHIBITS[item.exhibitKey].title.includes(q)),
    })).filter((d) => d.questions.length > 0);
  }, [query]);

  const activeDomainId = filteredDomains.find((d) => isSearching || d.id === openDomain)?.id ?? null;
  const activeDomain = filteredDomains.find((d) => d.id === activeDomainId) ?? null;
  const activeQuestion = activeDomain
    ? activeDomain.questions.find((q) => q.id === selectedByDomain[activeDomain.id]) ?? activeDomain.questions[0]
    : null;
  const activeExhibit = activeQuestion ? EXHIBITS[activeQuestion.exhibitKey] : null;

  const exitFullscreen = () => {
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    setFullscreen(false);
  };
  const enterFullscreen = async () => {
    setFullscreen(true);
    try {
      await stageRef.current?.requestFullscreen();
    } catch {
      // Fullscreen API가 막힌 환경(iframe 등) — CSS 오버레이만으로도 화면을 채운다.
    }
  };

  useEffect(() => {
    const onFsChange = () => {
      if (!document.fullscreenElement) setFullscreen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') exitFullscreen();
    };
    document.addEventListener('fullscreenchange', onFsChange);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('fullscreenchange', onFsChange);
      document.removeEventListener('keydown', onKey);
    };
  }, []);

  return (
    <div className={big ? 'mx-auto w-[90%] py-4' : 'mx-auto max-w-6xl px-6 py-8'}>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className={big ? 'text-4xl font-bold tracking-tight text-ink sm:text-5xl' : 'text-h1'}>발표 Q&A 부록</h1>
          <p className={big ? 'mt-2 text-lg text-ink-secondary' : 'text-body mt-1'}>
            아래 검색창이나 폴더에서 예상 질문을 클릭하면, 답변에 쓸 시각 자료가 우측에 뜹니다.
          </p>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <div className="flex rounded-lg border border-line bg-card p-0.5">
            {(['presentation', 'normal'] as const).map((d) => (
              <button
                key={d}
                type="button"
                onClick={() => setDensity(d)}
                className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                  density === d ? 'bg-primary text-primary-foreground' : 'text-ink-secondary hover:bg-accent hover:text-ink'
                }`}
              >
                {d === 'presentation' ? '프레젠테이션' : '기본 열람'}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={toggle}
            aria-label="다크 모드 전환"
            className="rounded-lg border border-line bg-card p-2 text-ink-tertiary transition-colors hover:bg-accent hover:text-ink"
          >
            {theme === 'dark' ? <Sun size={16} strokeWidth={1.8} /> : <Moon size={16} strokeWidth={1.8} />}
          </button>
        </div>
      </div>

      {/* 포털사이트 스타일 대형 검색창 */}
      <div className="relative mb-5">
        <Search
          size={big ? 22 : 20}
          strokeWidth={1.8}
          className={`pointer-events-none absolute top-1/2 -translate-y-1/2 text-ink-tertiary ${big ? 'left-6' : 'left-5'}`}
        />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="궁금한 키워드로 바로 찾기 — SSR, HITL, Meta API, DDD..."
          className={`w-full rounded-full border-2 border-line bg-card text-ink placeholder:text-ink-muted shadow-sm transition-colors focus:border-primary focus:outline-none focus-visible:ring-4 focus-visible:ring-ring/20 ${
            big ? 'py-3 pl-14 pr-6 text-lg' : 'py-3 pl-12 pr-5 text-base'
          }`}
        />
      </div>

      <div className={`grid grid-cols-1 gap-6 ${big ? 'lg:grid-cols-[340px_1fr]' : 'lg:grid-cols-[300px_1fr]'}`}>
        {/* 좌측 — 파일트리 내비게이터 */}
        <div>
          {filteredDomains.length === 0 && <p className="text-body py-8 text-center">일치하는 질문이 없습니다.</p>}

          <div className="max-h-[75vh] overflow-y-auto rounded-lg border border-line bg-card p-2">
            {filteredDomains.map((d) => {
              const open = isSearching || openDomain === d.id;
              const t = TONE_CLASS[d.accent];
              return (
                <div key={d.id}>
                  <button
                    type="button"
                    onClick={() => setOpenDomain((cur) => (cur === d.id ? null : d.id))}
                    className={`flex w-full items-center gap-1.5 rounded-md px-2 py-2 text-left transition-colors ${
                      open ? t.bg : 'hover:bg-accent'
                    }`}
                  >
                    <ChevronRight size={14} strokeWidth={2.5} className={`shrink-0 text-ink-tertiary transition-transform ${open ? 'rotate-90' : ''}`} />
                    <span className={open ? t.text : 'text-ink-tertiary'}>{d.icon}</span>
                    <span className={`flex-1 truncate text-sm font-medium ${open ? t.text : 'text-ink'}`}>{d.label}</span>
                    <span className="text-[11px] text-ink-muted">{d.questions.length}</span>
                  </button>

                  {open && (
                    <div className="mb-1 ml-4 space-y-0.5 border-l border-line py-0.5 pl-2">
                      {d.questions.map((item) => {
                        const active = activeDomainId === d.id && activeQuestion?.id === item.id;
                        return (
                          <button
                            key={item.id}
                            type="button"
                            onClick={() => {
                              setOpenDomain(d.id);
                              setSelectedByDomain((cur) => ({ ...cur, [d.id]: item.id }));
                            }}
                            title={item.q}
                            className={`flex w-full items-start gap-1.5 rounded-md px-2 py-1.5 text-left text-xs leading-snug transition-colors ${
                              active ? `${t.bg} ${t.text} font-medium` : 'text-ink-secondary hover:bg-accent hover:text-ink'
                            }`}
                          >
                            <span
                              className={`w-6 shrink-0 text-right font-medium tabular-nums ${active ? t.text : 'text-ink-muted'}`}
                            >
                              {QUESTION_NO[item.id]}.
                            </span>
                            <span className="flex-1">{item.q}</span>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* 우측 — 선택한 질문에 쓸 시각 자료 */}
        <div className="min-w-0 lg:sticky lg:top-8 lg:self-start">
          {activeDomain && activeQuestion && activeExhibit ? (
            <div
              ref={stageRef}
              className={
                fullscreen
                  ? 'fixed inset-0 z-50 overflow-y-auto bg-surface-0 p-12'
                  : big
                    ? `rounded-2xl border-2 p-10 ${TONE_CLASS[activeDomain.accent].border} bg-card`
                    : `rounded-xl border p-6 ${TONE_CLASS[activeDomain.accent].border} bg-card`
              }
            >
              {fullscreen && (
                <button
                  type="button"
                  onClick={exitFullscreen}
                  aria-label="전체화면 닫기"
                  className="fixed right-6 top-6 z-50 rounded-full border border-line bg-card p-3 text-ink-secondary shadow-md transition-colors hover:bg-accent hover:text-ink"
                >
                  <X size={24} />
                </button>
              )}

              <div className={fullscreen ? 'mx-auto max-w-6xl' : ''}>
                <div className="mb-5 flex items-center justify-between gap-3">
                  <div
                    className={
                      big || fullscreen
                        ? `inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-sm font-semibold ${TONE_CLASS[activeDomain.accent].bg} ${TONE_CLASS[activeDomain.accent].text}`
                        : `inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold ${TONE_CLASS[activeDomain.accent].bg} ${TONE_CLASS[activeDomain.accent].text}`
                    }
                  >
                    {activeDomain.icon}
                    {activeDomain.label}
                  </div>
                  {!fullscreen && (
                    <button
                      type="button"
                      onClick={enterFullscreen}
                      aria-label="전체화면으로 보기"
                      title="전체화면으로 보기"
                      className="rounded-lg border border-line p-2 text-ink-tertiary transition-colors hover:bg-accent hover:text-ink"
                    >
                      <Maximize2 size={16} strokeWidth={1.8} />
                    </button>
                  )}
                </div>

                <p className={big || fullscreen ? 'mb-2 text-sm text-ink-tertiary' : 'text-caption mb-1'}>
                  Q{QUESTION_NO[activeQuestion.id]}. {activeQuestion.q}
                </p>
                <h2 className={big || fullscreen ? 'mb-6 text-4xl font-bold leading-snug text-ink' : 'text-h3 mb-4'}>
                  {activeExhibit.title}
                </h2>
                <DensityProvider density={fullscreen ? 'presentation' : density}>
                  <div className="mb-4">{activeExhibit.render()}</div>
                </DensityProvider>
                {activeExhibit.note && (
                  <p
                    className={
                      big || fullscreen
                        ? 'border-t border-line pt-4 text-base leading-relaxed text-ink-tertiary'
                        : 'border-t border-line pt-3 text-xs leading-relaxed text-ink-tertiary'
                    }
                  >
                    {activeExhibit.note}
                  </p>
                )}
              </div>
            </div>
          ) : (
            <div className="rounded-2xl border-2 border-line bg-card p-4">
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                {IDLE_SHOT_GROUPS.map((group) => (
                  <div key={group[0].src} className="space-y-4">
                    {group.map((sh) => (
                      <div key={sh.src} className="overflow-hidden rounded-lg border border-line">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={sh.src} alt={sh.caption} className="block w-full" />
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
