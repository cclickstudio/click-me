'use client';
// 통합 리포트(ReportView) 화면 렌더 — 백엔드 build_report_view 단일 소스를 그대로 그린다.
// "화면 최종 결과 = 리포트 = PDF" — 이 컴포넌트와 pdf_report.py가 같은 report_view를 소비한다.

import { API_BASE } from '@/lib/api';
import type {
  ConfidenceBadge,
  DebateDigest,
  ObjectiveFit,
  ReportView,
  SegmentCell,
  SimulationReport,
} from '@/lib/types';

const STOP_LABEL: Record<string, string> = {
  consensus: '합의 도달',
  dissensus: '이견 잔존',
  dissent: '이견 잔존',
  max: '최대 라운드',
};

/* ─── 한글 라벨(백엔드 enums 동기화) ─── */
const AISAS_KO: Record<string, string> = {
  attention: '주목',
  interest: '흥미',
  search: '탐색',
  action: '행동',
  share: '공유',
};
const EMOTION_KO: Record<string, string> = {
  curiosity: '호기심',
  delight: '만족',
  empathy: '공감',
  trust: '신뢰',
  indifference: '무관심',
  annoyance: '거부감',
  distrust: '불신',
  other: '기타',
};
const REJECTION_KO: Record<string, string> = {
  irrelevant: '나와 무관',
  offensive: '불쾌함',
  overpriced: '비쌈',
  overpromise: '과장된 표현',
  distrust: '브랜드 불신',
  ad_fatigue: '광고 거부감',
  other: '기타',
};
const RUBRIC_KO: Record<string, string> = {
  hook: '훅(첫 3초)',
  message_clarity: '메시지 명료성',
  message_alignment: '메시지 정합',
  usp: 'USP 전달',
  visual_copy_fit: '비주얼-카피 정합',
  cta_clarity: '행동 유도(CTA)',
  target_fit: '타깃 적합성',
  brand_memory: '브랜드 기억도',
  category_alignment: '카테고리 정합',
  objective_alignment: '목표 정합',
};
const GENDER_KO: Record<string, string> = { M: '남성', F: '여성' };
const GROUP_KO: Record<string, string> = {
  finishers: '완주자',
  undecided: '미온',
  rejectors: '거부자',
  distrusters: '불신자',
  early_drop: '초기 이탈',
};

const pct = (x: number | null | undefined) =>
  `${Math.round((x ?? 0) * 100)}%`;
const n100 = (x: number | null | undefined) => Math.round((x ?? 0) * 100);

/* ─── 작은 공용 UI ─── */
function Bar({
  label,
  ratio,
  disp,
  color = '#3182F6',
}: {
  label: string;
  ratio: number;
  disp: string;
  color?: string;
}) {
  const w = Math.max(0, Math.min(1, ratio)) * 100;
  return (
    <div className='flex items-center gap-3 my-1'>
      <span className='w-20 shrink-0 text-[11px] text-[#4E5968] dark:text-[#9CA3AF]'>
        {label}
      </span>
      <div className='flex-1 h-2.5 rounded-full bg-[#F2F4F6] dark:bg-[#252D3D] overflow-hidden'>
        <div
          className='h-full rounded-full'
          style={{ width: `${w}%`, background: color }}
        />
      </div>
      <span className='w-[78px] shrink-0 text-right text-[10px] text-[#8B95A1] dark:text-[#6B7280]'>
        {disp}
      </span>
    </div>
  );
}

function Section({
  title,
  tip,
  children,
}: {
  title: string;
  tip?: string;
  children: React.ReactNode;
}) {
  return (
    <section className='rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#1C2333] p-5'>
      <h3 className='text-sm font-bold text-[#191F28] dark:text-[#F2F4F6] mb-1'>
        {title}
      </h3>
      {tip && (
        <p className='text-[11px] leading-relaxed text-[#8B95A1] dark:text-[#6B7280] bg-[#F9FAFB] dark:bg-[#252D3D] rounded-lg px-3 py-2 mb-3'>
          {tip}
        </p>
      )}
      {children}
    </section>
  );
}

function signal(score: number) {
  return score >= 70 ? '#10B981' : score >= 50 ? '#F59E0B' : '#EF4444';
}

/* 종합 점수(PDF _overall과 동일 산식) */
function overallScore(rep: SimulationReport): number {
  const k = rep.kpi;
  const parts = [
    k.click_intent_rate,
    k.purchase_intent / 5,
    k.trust_avg / 5,
    1 - k.rejection_rate,
    k.brand_recognition_rate,
  ];
  if (rep.rubric_scores.length > 0) {
    parts.push(
      rep.rubric_scores.reduce((s, r) => s + r.score, 0) /
        (rep.rubric_scores.length * 100)
    );
  }
  return Math.round((parts.reduce((s, p) => s + p, 0) / parts.length) * 100);
}

function verdict(cir: number, rej: number): [string, string] {
  if (rej >= 0.4 || cir < 0.05)
    return [
      '재제작 권장',
      '거부 반응이 크거나 클릭으로 잘 이어지지 않아, 지금 그대로 내보내기엔 무리가 있어요.',
    ];
  if (cir >= 0.2 && rej < 0.2)
    return ['집행 권장', '전반적으로 반응이 좋아 지금 내보내도 큰 무리가 없어요.'];
  return [
    '조건부 집행 권장',
    "가능성은 보이지만, '아쉬운 점'을 손보고 내보내는 걸 권해요.",
  ];
}

/* ─── 신뢰 배지 ─── */
function ConfidenceStrip({ c }: { c: ConfidenceBadge }) {
  const tone =
    c.level === 'high'
      ? { t: 'text-[#15803D] dark:text-[#4ADE80]', label: '신뢰 높음' }
      : c.level === 'medium'
        ? { t: 'text-[#B45309] dark:text-[#F4A100]', label: '신뢰 보통' }
        : { t: 'text-[#DC2626] dark:text-[#FCA5A5]', label: '신뢰 낮음' };
  return (
    <div className='rounded-xl bg-[#F9FAFB] dark:bg-[#252D3D] border border-[#E5E8EB] dark:border-[#2D3748] px-4 py-3'>
      <div className='flex flex-wrap items-center gap-2 text-xs'>
        <span className={`font-bold ${tone.t}`}>● {tone.label}</span>
        <span className='text-[#8B95A1] dark:text-[#6B7280]'>
          유효표본 {c.effective_n} / 총 {c.total_n}명
        </span>
        <span className='text-[#8B95A1] dark:text-[#6B7280]'>
          신뢰구간 폭 {pct(c.ci_width)}
        </span>
      </div>
      <ul className='mt-2 space-y-0.5'>
        {c.warnings.map((w, i) => (
          <li
            key={i}
            className='text-[11px] text-[#8B95A1] dark:text-[#6B7280] leading-relaxed'>
            · {w}
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ─── 목표 달성 가능성 ─── */
function ObjectiveFitCard({ f }: { f: ObjectiveFit }) {
  const tone =
    f.grade === '높음'
      ? { text: 'text-[#15803D] dark:text-[#4ADE80]', bar: 'bg-[#22C55E]' }
      : f.grade === '보통'
        ? { text: 'text-[#B45309] dark:text-[#F4A100]', bar: 'bg-[#F4A100]' }
        : { text: 'text-[#DC2626] dark:text-[#FCA5A5]', bar: 'bg-[#F04452]' };
  return (
    <Section
      title='캠페인 목표 달성 가능성'
      tip='결정권자가 가장 먼저 보는 판정 — 이 광고가 설정한 목표에 얼마나 부합하는지 시뮬 신호로 가늠한 상대 지수입니다(실측 아님, exploratory).'>
      <div className='flex items-start justify-between gap-4 flex-wrap'>
        <p className='text-sm text-[#4E5968] dark:text-[#9CA3AF]'>
          목표: {f.objective}
        </p>
        <div className='flex items-baseline gap-2'>
          <span className={`text-3xl font-bold ${tone.text}`}>{f.grade}</span>
          <span className='text-sm text-[#8B95A1] dark:text-[#6B7280]'>
            지수 {f.score}/100
          </span>
        </div>
      </div>
      <div className='mt-3 h-2 rounded-full bg-[#F2F4F6] dark:bg-[#252D3D] overflow-hidden'>
        <div
          className={`h-full rounded-full ${tone.bar}`}
          style={{ width: `${f.score}%` }}
        />
      </div>
      <p className='text-sm text-[#4E5968] dark:text-[#9CA3AF] mt-3'>
        {f.rationale}
      </p>
      {f.contributions.length > 0 && (
        <div className='mt-3 space-y-1'>
          {f.contributions.map(c => (
            <Bar
              key={c.label}
              label={c.label}
              ratio={c.value}
              disp={`${n100(c.value)}% ·가중 ${n100(c.weight)}%`}
              color='#4F46E5'
            />
          ))}
        </div>
      )}
      {f.low_confidence && (
        <p className='text-[11px] text-[#F4A100] mt-2'>
          ⚠ 표본이 적어 신뢰가 낮습니다.
        </p>
      )}
    </Section>
  );
}

/* ─── 연령×성별 세그먼트 히트맵(최대 차별점) ─── */
function SegmentHeatmap({ segments }: { segments: SegmentCell[] }) {
  if (segments.length === 0) return null;
  // 클릭 의향률 기준 최고/최저 셀 표시.
  const ranked = [...segments].sort(
    (a, b) => b.click_intent_rate - a.click_intent_rate
  );
  const best = ranked[0];
  const worst = ranked[ranked.length - 1];
  const cellTone = (r: number) =>
    r >= 0.3
      ? 'bg-[#EAF7EF] dark:bg-[#0B2E13] text-[#15803D] dark:text-[#4ADE80]'
      : r >= 0.15
        ? 'bg-[#FFF8E6] dark:bg-[#2D2000] text-[#B45309] dark:text-[#F4A100]'
        : 'bg-[#FEF2F2] dark:bg-[#3B0D0D] text-[#DC2626] dark:text-[#FCA5A5]';
  return (
    <Section
      title='누구에게 통하나 — 연령대×성별'
      tip='같은 광고도 누가 보느냐에 따라 반응이 다릅니다. 셀이 진할수록 클릭 의향이 높아요(얇은 셀은 신뢰 낮음 표시).'>
      <div className='overflow-x-auto'>
        <table className='w-full text-xs border-collapse'>
          <thead>
            <tr className='text-[#8B95A1] dark:text-[#6B7280]'>
              <th className='text-left font-medium py-1.5 pr-2'>세그먼트</th>
              <th className='text-right font-medium px-2'>인원</th>
              <th className='text-right font-medium px-2'>클릭 의향</th>
              <th className='text-right font-medium px-2'>구매(5)</th>
              <th className='text-right font-medium px-2'>신뢰(5)</th>
              <th className='text-right font-medium pl-2'>거부율</th>
            </tr>
          </thead>
          <tbody>
            {segments.map(s => (
              <tr
                key={`${s.age_band}-${s.gender}`}
                className='border-t border-[#F2F4F6] dark:border-[#252D3D]'>
                <td className='py-1.5 pr-2 text-[#191F28] dark:text-[#F2F4F6]'>
                  {s.age_band} {GENDER_KO[s.gender] ?? s.gender}
                  {s.low_confidence && (
                    <span className='ml-1 text-[10px] text-[#B0B8C1] dark:text-[#4B5563]'>
                      ⓘ얇음
                    </span>
                  )}
                </td>
                <td className='text-right px-2 text-[#8B95A1] dark:text-[#6B7280]'>
                  {s.n}
                </td>
                <td className='text-right px-2'>
                  <span
                    className={`inline-block px-2 py-0.5 rounded-md font-semibold ${cellTone(s.click_intent_rate)}`}>
                    {pct(s.click_intent_rate)}
                  </span>
                </td>
                <td className='text-right px-2 text-[#4E5968] dark:text-[#9CA3AF]'>
                  {s.purchase_intent.toFixed(1)}
                </td>
                <td className='text-right px-2 text-[#4E5968] dark:text-[#9CA3AF]'>
                  {s.trust_avg.toFixed(1)}
                </td>
                <td className='text-right pl-2 text-[#4E5968] dark:text-[#9CA3AF]'>
                  {pct(s.rejection_rate)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {best && worst && best !== worst && (
        <p className='text-[11px] text-[#4E5968] dark:text-[#9CA3AF] mt-3'>
          실질 타깃은{' '}
          <b className='text-[#15803D] dark:text-[#4ADE80]'>
            {best.age_band} {GENDER_KO[best.gender] ?? best.gender}
          </b>
          (클릭 {pct(best.click_intent_rate)}), 가장 안 통한 층은{' '}
          <b className='text-[#DC2626] dark:text-[#FCA5A5]'>
            {worst.age_band} {GENDER_KO[worst.gender] ?? worst.gender}
          </b>
          (클릭 {pct(worst.click_intent_rate)})입니다.
        </p>
      )}
    </Section>
  );
}

/* ─── 메시지 수신(의도 vs 저항) ─── */
function MessageCard({ m }: { m: NonNullable<ReportView['message_reception']> }) {
  return (
    <Section
      title='메시지가 의도대로 받아들여졌나'
      tip='광고가 던진 메시지(의도)가 소비자에게 어떻게 닿았는지 — 과장·식상·무관심 같은 저항 표현 비율로 가늠합니다.'>
      {m.intended && (
        <p className='text-sm text-[#191F28] dark:text-[#F2F4F6] mb-2'>
          의도 메시지:{' '}
          <span className='font-medium'>“{m.intended}”</span>
        </p>
      )}
      <Bar
        label='저항 반응'
        ratio={m.resistance_rate}
        disp={pct(m.resistance_rate)}
        color={m.resistance_rate >= 0.3 ? '#EF4444' : '#64748B'}
      />
      {Object.keys(m.resistance_terms).length > 0 && (
        <p className='text-[11px] text-[#8B95A1] dark:text-[#6B7280] mt-2'>
          저항 표현:{' '}
          {Object.entries(m.resistance_terms)
            .map(([k, v]) => `${k}(${v})`)
            .join(', ')}
        </p>
      )}
      {m.resisted_quotes.length > 0 && (
        <ul className='mt-2 space-y-1'>
          {m.resisted_quotes.slice(0, 3).map((q, i) => (
            <li
              key={i}
              className='text-[11px] text-[#4E5968] dark:text-[#9CA3AF] bg-[#F9FAFB] dark:bg-[#252D3D] rounded-lg px-3 py-1.5'>
              “{q}”
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

/* ─── 토론 1건 다이제스트 — 주제 + 대표 인용 1~2 + 결론(합의/이견) 간결 렌더 ─── */
function DebateDigestItem({ d, index }: { d: DebateDigest; index?: number }) {
  const quotes = (d.quotes ?? []).slice(0, 2);
  const consensus = d.consensus ?? [];
  const dissent = d.dissent ?? [];
  return (
    <div className='rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] bg-[#F9FAFB] dark:bg-[#252D3D] p-4'>
      <div className='flex items-start gap-2 flex-wrap'>
        {typeof index === 'number' && (
          <span className='shrink-0 mt-0.5 w-5 h-5 rounded-full bg-[#3182F6] text-white text-[11px] font-bold flex items-center justify-center'>
            {index + 1}
          </span>
        )}
        <p className='min-w-0 flex-1 text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] leading-snug'>
          {d.topic_headline}
        </p>
        {d.stop_reason && (
          <span className='shrink-0 px-2 py-0.5 rounded-full bg-white dark:bg-[#1C2333] text-[10px] text-[#8B95A1] dark:text-[#6B7280]'>
            {STOP_LABEL[d.stop_reason] ?? d.stop_reason}
          </span>
        )}
      </div>

      {quotes.length > 0 && (
        <ul className='mt-2.5 space-y-1.5'>
          {quotes.map((q, i) => (
            <li
              key={i}
              className='text-[12px] text-[#4E5968] dark:text-[#9CA3AF] bg-white dark:bg-[#1C2333] rounded-lg px-3 py-2 leading-relaxed'>
              “{q.text}”
              {q.persona_name && (
                <span className='block mt-0.5 text-[10px] text-[#B0B8C1] dark:text-[#4B5563]'>
                  — {q.persona_name}
                  {q.role ? ` · ${q.role}` : ''}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}

      {(consensus.length > 0 || dissent.length > 0) && (
        <div className='mt-2.5 grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1.5'>
          {consensus.length > 0 && (
            <div>
              <p className='text-[11px] font-semibold text-[#00A661] mb-0.5'>
                합의
              </p>
              <ul className='space-y-0.5'>
                {consensus.map((c, i) => (
                  <li
                    key={i}
                    className='text-[11px] text-[#4E5968] dark:text-[#9CA3AF] leading-relaxed'>
                    · {c}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {dissent.length > 0 && (
            <div>
              <p className='text-[11px] font-semibold text-[#F4A100] mb-0.5'>
                이견
              </p>
              <ul className='space-y-0.5'>
                {dissent.map((c, i) => (
                  <li
                    key={i}
                    className='text-[11px] text-[#4E5968] dark:text-[#9CA3AF] leading-relaxed'>
                    · {c}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ─── 토론 섹션 — debates(합산)면 각 토론 나열, 없으면 단일 debate 렌더(하위호환) ─── */
function DebateSection({ rv }: { rv: ReportView }) {
  const rep = rv.report;
  // 합산 토론(여러 토론 누적) 우선.
  if (rv.debates && rv.debates.length > 0) {
    return (
      <Section
        title={`페르소나 토론 요약 (${rv.debates.length}건)`}
        tip='개선 방향을 도출한 전문가·일반인 토론입니다. 토론할수록 항목이 늘어나요 — 각 토론의 주제·대표 발언·결론만 간추렸습니다.'>
        <div className='space-y-3'>
          {rv.debates.map((d, i) => (
            <DebateDigestItem key={d.debate_id ?? i} d={d} index={i} />
          ))}
        </div>
      </Section>
    );
  }

  // 하위호환: 단일 토론 — report 필드로 다이제스트 구성.
  if (!rep.debate_available) return null;
  const single: DebateDigest = {
    topic_headline: rep.topic || rep.headline || '페르소나 토론',
    rounds_run: rep.rounds_run,
    stop_reason: rep.stop_reason,
    consensus: rep.consensus ?? [],
    dissent: rep.dissent ?? [],
    ranked_actions: rep.ranked_actions ?? [],
    quotes: rep.quotes ?? [],
  };
  return (
    <Section
      title='페르소나 토론 요약'
      tip='개선 방향을 도출한 전문가·일반인 토론입니다 — 주제·대표 발언·결론만 간추렸습니다.'>
      <DebateDigestItem d={single} />
    </Section>
  );
}

/* ─── 메인 ─── */
export function SimulationReportView({ rv }: { rv: ReportView }) {
  const rep = rv.report;
  const k = rep.kpi;
  const totalN = rv.confidence.total_n || k.effective_n || 0;
  const overall = overallScore(rep);
  const [vLabel, vDesc] = verdict(k.click_intent_rate, k.rejection_rate);
  const oc = signal(overall);
  const sm = rv.summary_metrics;

  const pdfUrl = `${API_BASE}/api/debate/${rv.run_id}/report.pdf`;

  // 구매의도 분포 라벨.
  const piLabel: Record<number, string> = {
    1: '전혀 없음',
    2: '낮음',
    3: '보통',
    4: '높음',
    5: '매우 높음',
  };
  const piCol: Record<number, string> = {
    1: '#EF4444',
    2: '#F59E0B',
    3: '#64748B',
    4: '#3182F6',
    5: '#10B981',
  };
  const piTotal =
    Object.values(rep.purchase_intent_dist).reduce((s, v) => s + v, 0) || 1;
  const emoTotal =
    Object.values(rep.emotion_dist).reduce((s, v) => s + v, 0) || 1;

  return (
    <div className='space-y-4'>
      {/* 헤더 + PDF */}
      <div className='flex items-center justify-between gap-3 flex-wrap'>
        <div>
          <h2 className='text-base font-bold text-[#191F28] dark:text-[#F2F4F6]'>
            최종 결과 리포트
          </h2>
          <p className='text-xs text-[#8B95A1] dark:text-[#6B7280] mt-0.5'>
            AI 가상 소비자 {totalN}명의 반응을 종합한 단일 리포트입니다 (화면 =
            PDF 동일).
          </p>
        </div>
        <a
          href={pdfUrl}
          target='_blank'
          rel='noopener noreferrer'
          className='shrink-0 inline-flex items-center gap-1.5 px-4 py-2 bg-[#3182F6] hover:bg-[#1B6EEB] text-white rounded-lg text-sm font-semibold transition-colors'>
          <svg className='w-4 h-4' fill='currentColor' viewBox='0 0 24 24'>
            <path d='M5 20h14v-2H5v2zM19 9h-4V3H9v6H5l7 7 7-7z' />
          </svg>
          PDF 다운로드
        </a>
      </div>

      {/* 종합 판정 */}
      <div className='rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#1C2333] p-5 flex items-center gap-5 flex-wrap'>
        <div className='shrink-0 text-center'>
          <div
            className='w-[88px] h-[88px] rounded-full grid place-items-center'
            style={{
              background: `conic-gradient(${oc} ${(overall / 100) * 360}deg, #E5E8EB 0)`,
            }}>
            <div className='w-[64px] h-[64px] rounded-full bg-white dark:bg-[#1C2333] grid place-items-center text-2xl font-extrabold text-[#191F28] dark:text-[#F2F4F6]'>
              {overall}
            </div>
          </div>
          <p className='text-[10px] text-[#8B95A1] dark:text-[#6B7280] mt-1'>
            종합 점수 / 100
          </p>
        </div>
        <div className='min-w-0 flex-1'>
          <span
            className='inline-block px-3 py-1 rounded-full text-white text-xs font-bold'
            style={{ background: oc }}>
            {vLabel}
          </span>
          {(rep.plain_summary || rep.headline) && (
            <p className='text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mt-2 leading-snug'>
              {rep.plain_summary || rep.headline}
            </p>
          )}
          <p className='text-xs text-[#8B95A1] dark:text-[#6B7280] mt-1 leading-relaxed'>
            {vDesc}
          </p>
        </div>
      </div>

      {/* 목표 달성 가능성 */}
      {rv.objective_fit && <ObjectiveFitCard f={rv.objective_fit} />}

      {/* 신뢰 배지 */}
      <ConfidenceStrip c={rv.confidence} />

      {/* 4대 KPI 요약 */}
      <Section title='4대 KPI 요약'>
        <div className='grid grid-cols-2 md:grid-cols-4 gap-3'>
          {[
            {
              label: '클릭 의향',
              value: pct(k.click_intent_rate),
              sub: `CI ${pct(k.ci_low)}~${pct(k.ci_high)}`,
              color: '#3182F6',
            },
            {
              label: '구매의도 (5점)',
              value: k.purchase_intent.toFixed(1),
              sub: `강한 구매의향 ${pct(sm.top2box_purchase)}`,
              color: '#4F46E5',
            },
            {
              label: '신뢰도 (5점)',
              value: k.trust_avg.toFixed(1),
              sub: sm.trust_action_label,
              color: '#0D9488',
            },
            {
              label: '거부율',
              value: pct(k.rejection_rate),
              sub: '낮을수록 좋아요',
              color: k.rejection_rate >= 0.3 ? '#EF4444' : '#64748B',
            },
          ].map(c => (
            <div
              key={c.label}
              className='rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] p-3 border-t-4'
              style={{ borderTopColor: c.color }}>
              <p className='text-[11px] font-bold text-[#8B95A1] dark:text-[#6B7280]'>
                {c.label}
              </p>
              <p
                className='text-2xl font-extrabold mt-0.5'
                style={{ color: c.color }}>
                {c.value}
              </p>
              <p className='text-[10px] text-[#B0B8C1] dark:text-[#4B5563] mt-0.5'>
                {c.sub}
              </p>
            </div>
          ))}
        </div>
      </Section>

      {/* 세그먼트 히트맵 */}
      <SegmentHeatmap segments={rv.segments} />

      {/* AISAS 퍼널 */}
      {rep.funnel.length > 0 && (
        <Section
          title='소비자 반응 — 어디서 새는가'
          tip='주목→흥미→탐색→행동→공유 순으로 가는 길이에요. 갑자기 확 빠지는 구간이 고쳐야 할 곳입니다.'>
          {rep.funnel.map(f => (
            <Bar
              key={f.stage}
              label={AISAS_KO[f.stage] ?? f.stage}
              ratio={f.pass_rate}
              disp={`${pct(f.pass_rate)} (${f.passed}명)`}
            />
          ))}
          {rep.bottleneck && (
            <p className='mt-2 text-[11px] text-[#B45309] dark:text-[#F4A100] bg-[#FFF8E6] dark:bg-[#2D2000] rounded-lg px-3 py-2'>
              ⬇ 가장 많이 빠진 구간 —{' '}
              <b>
                {AISAS_KO[rep.bottleneck.from_stage] ?? rep.bottleneck.from_stage}{' '}
                → {AISAS_KO[rep.bottleneck.to_stage] ?? rep.bottleneck.to_stage}
              </b>{' '}
              {rep.bottleneck.dropped}명 이탈 ({pct(rep.bottleneck.drop_rate)}). 이
              지점을 고치면 효과가 가장 큽니다.
            </p>
          )}
        </Section>
      )}

      {/* 구매의도 분포 + 감정 */}
      <div className='grid grid-cols-1 md:grid-cols-2 gap-4'>
        <Section title='구매의도 분포'>
          {[1, 2, 3, 4, 5].map(i => {
            const v =
              rep.purchase_intent_dist[String(i)] ??
              rep.purchase_intent_dist[i] ??
              0;
            return (
              <Bar
                key={i}
                label={piLabel[i]}
                ratio={v / piTotal}
                disp={`${v}명`}
                color={piCol[i]}
              />
            );
          })}
        </Section>
        <Section title='광고를 보고 든 느낌'>
          {Object.entries(rep.emotion_dist).map(([key, v]) => (
            <Bar
              key={key}
              label={EMOTION_KO[key] ?? key}
              ratio={v / emoTotal}
              disp={`${v}명`}
              color='#0D9488'
            />
          ))}
        </Section>
      </div>

      {/* 메시지 수신 */}
      {rv.message_reception && <MessageCard m={rv.message_reception} />}

      {/* 거부 사유 + 브랜드 식별 */}
      <div className='grid grid-cols-1 md:grid-cols-2 gap-4'>
        {rep.rejection && (
          <Section title={`광고를 거부한 이유 (${pct(rep.rejection.rejection_rate)})`}>
            {Object.keys(rep.rejection.by_rejection_reason_tag).length > 0 ? (
              Object.entries(rep.rejection.by_rejection_reason_tag).map(
                ([key, v]) => (
                  <Bar
                    key={key}
                    label={REJECTION_KO[key] ?? key}
                    ratio={v / (rep.rejection!.rejected_count || 1)}
                    disp={`${v}명`}
                    color='#EF4444'
                  />
                )
              )
            ) : (
              <p className='text-[11px] text-[#B0B8C1] dark:text-[#4B5563]'>
                거부 없음
              </p>
            )}
          </Section>
        )}
        {rep.brand_recognition && (
          <Section
            title='브랜드가 기억에 남았나'
            tip='광고를 보고 "어느 브랜드인지" 알아봤는지예요(Fluency).'>
            <Bar
              label='기억함'
              ratio={rep.brand_recognition.recognition_rate}
              disp={`${rep.brand_recognition.recognized_count}명`}
              color='#10B981'
            />
            <Bar
              label='기억 못 함'
              ratio={
                rep.brand_recognition.unrecognized_count / (totalN || 1)
              }
              disp={`${rep.brand_recognition.unrecognized_count}명`}
              color='#64748B'
            />
            {Object.keys(rep.brand_recognition.perceived_brands).length > 0 && (
              <p className='mt-2 text-[10px] text-[#8B95A1] dark:text-[#6B7280]'>
                떠올린 브랜드 —{' '}
                {Object.entries(rep.brand_recognition.perceived_brands)
                  .map(([key, v]) => `${key}(${v}명)`)
                  .join(', ')}
              </p>
            )}
          </Section>
        )}
      </div>

      {/* 크리에이티브 진단(루브릭) */}
      {rep.rubric_scores.length > 0 && (
        <Section
          title='광고 자체의 완성도 진단'
          tip='항목별 100점 만점 채점이에요. 초록=좋음 · 주황=보통 · 빨강=손봐야 함.'>
          {rep.rubric_scores.map(s => (
            <Bar
              key={s.dimension}
              label={RUBRIC_KO[s.dimension] ?? s.dimension}
              ratio={s.score / 100}
              disp={`${s.score}/100`}
              color={signal(s.score)}
            />
          ))}
        </Section>
      )}

      {/* 그룹 프로필 */}
      {Object.keys(rv.group_profiles).length > 0 && (
        <Section
          title='완주자·이탈자는 누구인가'
          tip='어떤 사람들이 끝까지 보고, 어떤 사람들이 떠났는지 — 세그먼트 액션의 근거입니다.'>
          <div className='grid grid-cols-2 md:grid-cols-3 gap-3'>
            {Object.entries(rv.group_profiles)
              .filter(([, g]) => g.count > 0)
              .map(([key, g]) => (
                <div
                  key={key}
                  className='rounded-xl bg-[#F9FAFB] dark:bg-[#252D3D] p-3'>
                  <p className='text-xs font-bold text-[#191F28] dark:text-[#F2F4F6]'>
                    {GROUP_KO[key] ?? key}{' '}
                    <span className='text-[#8B95A1] dark:text-[#6B7280] font-normal'>
                      {g.count}명
                    </span>
                  </p>
                  <p className='text-[11px] text-[#4E5968] dark:text-[#9CA3AF] mt-1'>
                    평균 {g.avg_age}세
                    {g.top_emotion &&
                      ` · ${EMOTION_KO[g.top_emotion] ?? g.top_emotion}`}
                  </p>
                  {Object.keys(g.gender_ratio).length > 0 && (
                    <p className='text-[10px] text-[#8B95A1] dark:text-[#6B7280] mt-0.5'>
                      {Object.entries(g.gender_ratio)
                        .map(([gn, r]) => `${GENDER_KO[gn] ?? gn} ${pct(r)}`)
                        .join(' · ')}
                    </p>
                  )}
                </div>
              ))}
          </div>
        </Section>
      )}

      {/* 개선 권고 */}
      {rep.ranked_actions.length > 0 && (
        <Section
          title='그래서, 무엇을 고치면 되나'
          tip='효과가 큰 순서대로 정리한 개선 액션이에요.'>
          <div className='space-y-2'>
            {rep.ranked_actions.map(a => (
              <div
                key={a.rank}
                className='flex gap-3 p-3 rounded-xl bg-[#F9FAFB] dark:bg-[#252D3D]'>
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
        </Section>
      )}

      {/* 페르소나 토론 요약 — debates(합산) 또는 단일 debate(하위호환) */}
      <DebateSection rv={rv} />

      <p className='text-[11px] text-[#B0B8C1] dark:text-[#4B5563] leading-relaxed border-t border-[#E5E8EB] dark:border-[#2D3748] pt-4'>
        이 리포트는 실제 사람이 아니라 한국 인구·성격·미디어 통계로 만든 AI 가상
        소비자의 반응을 모은 예측 참고 자료입니다. 클릭 의향률은 실측 CTR이
        아니며(calibration 전), 수치는 방향과 범위로 읽어 주세요.
      </p>
    </div>
  );
}
