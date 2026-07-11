'use client';

// 발표 Q&A 부록 — 기능별(제너레이터·시뮬레이션·매니지먼트·채팅) 예상 질문을 클릭하면, 그 질문에
// 답하며 보여줄 시각 자료(파이프라인·구조도·매트릭스·타임라인 등)를 바로 띄우는 프레젠테이션 보조 페이지.
// 로그인 없이 접근 가능한 공개 라우트. 질문에 대한 글로 쓴 정답은 두지 않는다 — 자료만 스위칭한다.

import { useMemo, useState } from 'react';
import { Search } from 'lucide-react';
import { DOMAINS, EXHIBITS } from './_lib/exhibits';
import { TONE_CLASS } from './_lib/primitives';

export default function AppendixPage() {
  const [query, setQuery] = useState('');
  const [selectedKey, setSelectedKey] = useState<string>(`${DOMAINS[0].id}:${DOMAINS[0].questions[0].id}`);
  const [openNav, setOpenNav] = useState<string | null>(null);

  const selected = useMemo(() => {
    for (const d of DOMAINS) {
      const found = d.questions.find((q) => `${d.id}:${q.id}` === selectedKey);
      if (found) return { domain: d, question: found, exhibit: EXHIBITS[found.exhibitKey] };
    }
    const q0 = DOMAINS[0].questions[0];
    return { domain: DOMAINS[0], question: q0, exhibit: EXHIBITS[q0.exhibitKey] };
  }, [selectedKey]);

  const filteredDomains = useMemo(() => {
    const q = query.trim();
    if (!q) return DOMAINS;
    return DOMAINS.map((d) => ({
      ...d,
      questions: d.questions.filter((item) => item.q.includes(q) || EXHIBITS[item.exhibitKey].title.includes(q)),
    })).filter((d) => d.questions.length > 0);
  }, [query]);

  const pick = (domainId: string, questionId: string) => {
    setSelectedKey(`${domainId}:${questionId}`);
    setOpenNav(null);
  };

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <div className="mb-6">
        <h1 className="text-h1">발표 Q&A 부록</h1>
        <p className="text-body mt-1">예상 질문을 클릭하면 답변에 쓸 시각 자료가 바로 뜹니다. 기능별 nav에 커서를 올리면 10문항 목록이 드롭다운으로 나옵니다.</p>
      </div>

      {/* 상단 nav — 호버 드롭다운 */}
      <div className="sticky top-0 z-30 -mx-6 mb-6 border-b border-line bg-surface-0/95 px-6 py-3 backdrop-blur">
        <nav className="flex flex-wrap gap-2">
          {DOMAINS.map((d) => (
            <div
              key={d.id}
              className="relative"
              onMouseEnter={() => setOpenNav(d.id)}
              onMouseLeave={() => setOpenNav((cur) => (cur === d.id ? null : cur))}
            >
              <button
                type="button"
                onClick={() => setOpenNav((cur) => (cur === d.id ? null : d.id))}
                className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium transition-colors ${
                  selected.domain.id === d.id
                    ? `${TONE_CLASS[d.accent].bg} ${TONE_CLASS[d.accent].text} ${TONE_CLASS[d.accent].border}`
                    : 'border-line text-ink-secondary hover:bg-accent hover:text-ink'
                }`}
              >
                <span className={selected.domain.id === d.id ? TONE_CLASS[d.accent].text : 'text-ink-tertiary'}>{d.icon}</span>
                {d.label}
                <span className="text-caption">{d.questions.length}</span>
              </button>

              {openNav === d.id && (
                <div className="absolute left-0 top-full z-40 mt-1 w-80 rounded-lg border border-line bg-popover p-1.5 shadow-lg">
                  {d.questions.map((item, idx) => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => pick(d.id, item.id)}
                      className={`flex w-full items-start gap-2 rounded-md px-2.5 py-2 text-left text-sm transition-colors ${
                        selectedKey === `${d.id}:${item.id}` ? TONE_CLASS[d.accent].bg : 'hover:bg-accent'
                      }`}
                    >
                      <span className="text-caption mt-0.5 w-4 shrink-0 text-right">{idx + 1}</span>
                      <span className="flex-1 text-ink-secondary">{item.q}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </nav>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[400px_1fr]">
        {/* 좌측 — 40문항 전체를 한눈에 스캔하는 맵 */}
        <div>
          <div className="relative mb-3">
            <Search size={15} strokeWidth={1.8} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-tertiary" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="키워드로 질문 찾기 (예: SSR, HITL, DDD)"
              className="w-full rounded-lg border border-line bg-card py-2 pl-9 pr-3 text-sm text-ink placeholder:text-ink-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>

          <div className="max-h-[70vh] space-y-5 overflow-y-auto rounded-lg border border-line bg-card p-4">
            {filteredDomains.length === 0 && (
              <p className="text-body py-8 text-center">일치하는 질문이 없습니다.</p>
            )}
            {filteredDomains.map((d) => (
              <div key={d.id}>
                <div className="mb-1.5 flex items-center gap-2">
                  <span className={TONE_CLASS[d.accent].text}>{d.icon}</span>
                  <span className="text-h3">{d.label}</span>
                  <span className="text-caption">{d.questions.length}문항</span>
                </div>
                <div className="space-y-0.5">
                  {d.questions.map((item) => {
                    const active = selectedKey === `${d.id}:${item.id}`;
                    return (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => pick(d.id, item.id)}
                        title={item.q}
                        className={`flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-sm transition-colors ${
                          active ? `${TONE_CLASS[d.accent].bg} ${TONE_CLASS[d.accent].text} font-medium` : 'text-ink-secondary hover:bg-accent hover:text-ink'
                        }`}
                      >
                        <span
                          className={`inline-block h-1.5 w-1.5 shrink-0 rounded-full transition-colors ${
                            active ? TONE_CLASS[d.accent].dot : 'bg-line-strong'
                          }`}
                        />
                        <span className="flex-1 truncate">{item.q}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 우측 — 선택한 질문에 쓸 시각 자료 */}
        <div className="lg:sticky lg:top-24 lg:self-start">
          <div className={`rounded-xl border p-8 ${TONE_CLASS[selected.domain.accent].border} bg-card`}>
            <div className={`mb-4 inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold ${TONE_CLASS[selected.domain.accent].bg} ${TONE_CLASS[selected.domain.accent].text}`}>
              {selected.domain.icon}
              {selected.domain.label}
            </div>
            <p className="text-caption mb-1">Q. {selected.question.q}</p>
            <h2 className="text-h2 mb-5 leading-snug">{selected.exhibit.title}</h2>
            <div className="mb-4">{selected.exhibit.render()}</div>
            {selected.exhibit.note && (
              <p className="border-t border-line pt-3 text-xs leading-relaxed text-ink-tertiary">{selected.exhibit.note}</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
