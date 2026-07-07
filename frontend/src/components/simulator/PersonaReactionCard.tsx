'use client';
// 페르소나 반응 카드 — 탭 ② 그리드용. 요약(인적·AISAS·발화) + 클릭 시 상세(OCEAN·소비가치 등) 펼침.

import type { SimRunResult } from '@/lib/types';

type Reaction = SimRunResult['reactions'][number];
type Persona = SimRunResult['personas'][number];

/* ─── enum 한글 라벨(백엔드 contracts/enums.py 동기화) ─── */
export const EMOTION_LABEL: Record<string, string> = {
  curiosity: '호기심',
  delight: '즐거움',
  empathy: '공감',
  trust: '신뢰',
  indifference: '무관심',
  annoyance: '거부감',
  distrust: '불신',
  other: '기타',
};
export const REJECTION_LABEL: Record<string, string> = {
  irrelevant: '무관함',
  offensive: '불쾌함',
  overpriced: '비쌈',
  overpromise: '과장',
  distrust: '불신',
  ad_fatigue: '광고 피로',
  other: '기타',
};
export const DROP_LABEL: Record<string, string> = {
  no_reason_to_explore: '탐색 동기 없음',
  price_concern: '가격 부담',
  low_relevance: '낮은 관련성',
  unclear_message: '메시지 불명확',
  distrust: '불신',
  other: '기타',
};
export const GENDER_LABEL: Record<string, string> = { M: '남성', F: '여성' };
export const OCEAN_LABEL: Record<string, string> = {
  openness: '개방성',
  conscientiousness: '성실성',
  extraversion: '외향성',
  agreeableness: '친화성',
  neuroticism: '신경성',
};

export function aisasFunnel(a: Reaction['aisas']): string {
  const stages: [keyof typeof a, string][] = [
    ['attention', 'A'],
    ['interest', 'I'],
    ['search', 'S'],
    ['action', 'A'],
    ['share', 'S'],
  ];
  return stages.map(([k, label]) => (a[k] ? label : '·')).join('');
}

// object → "key: value" 줄 나열(JSON.stringify 노출 개선)
function kvList(obj: Record<string, unknown>) {
  return Object.entries(obj).map(([k, v]) => (
    <span key={k} className='mr-3'>
      {k}: {typeof v === 'object' ? JSON.stringify(v) : String(v)}
    </span>
  ));
}

interface Props {
  reaction: Reaction;
  persona?: Persona;
  isOpen: boolean;
  onToggle: () => void;
}

export function PersonaReactionCard({ reaction: r, persona: p, isOpen, onToggle }: Props) {
  return (
    <div
      className={`bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-xl p-4 transition-colors ${
        r.qa_passed ? '' : 'opacity-60'
      }`}>
      {/* 인적사항 + AISAS */}
      <div className='flex items-center justify-between gap-2 mb-1.5'>
        <button
          type='button'
          onClick={() => p && onToggle()}
          className='text-sm font-medium text-[#191F28] dark:text-[#F2F4F6] hover:text-[#3182F6] text-left'>
          {p ? (
            <>
              {p.age}세 {GENDER_LABEL[p.gender] ?? p.gender} · {p.region}
              <span className='ml-1 text-[10px] text-[#B0B8C1] dark:text-[#4B5563]'>
                {isOpen ? '▲' : '▼'}
              </span>
            </>
          ) : (
            r.persona_id
          )}
        </button>
        <span className='font-mono text-xs text-[#3182F6] dark:text-[#5B9DF9]'>
          {aisasFunnel(r.aisas)}
        </span>
      </div>

      {/* 반응 요약 뱃지 */}
      <div className='flex flex-wrap items-center gap-1.5 text-[11px] mb-1.5'>
        <span className='text-[#4E5968] dark:text-[#9CA3AF]'>
          구매 {r.purchase_intent} · 신뢰 {r.trust}
        </span>
        <span className='px-1.5 py-0.5 rounded bg-[#F2F4F6] dark:bg-[#252D3D] text-[#4E5968] dark:text-[#9CA3AF]'>
          {EMOTION_LABEL[r.emotion_tag] ?? r.emotion_tag}
        </span>
        {r.rejected && (
          <span className='px-1.5 py-0.5 rounded bg-[#F2F4F6] dark:bg-[#252D3D] text-[#191F28] dark:text-[#F2F4F6]'>
            거부
            {r.rejection_reason_tag
              ? `·${REJECTION_LABEL[r.rejection_reason_tag] ?? r.rejection_reason_tag}`
              : ''}
          </span>
        )}
        {r.drop_stage && (
          <span className='text-[#B0B8C1] dark:text-[#4B5563]'>
            이탈 {r.drop_stage}
            {r.drop_reason_tag ? `·${DROP_LABEL[r.drop_reason_tag] ?? r.drop_reason_tag}` : ''}
          </span>
        )}
        {r.exposure_context && (
          <span className='text-[#B0B8C1] dark:text-[#4B5563]'>노출 {r.exposure_context}</span>
        )}
        {!r.qa_passed && (
          <span className='text-[#D97706]'>
            QA 탈락{r.qa_fail_reason ? `·${r.qa_fail_reason}` : ''}
          </span>
        )}
      </div>

      {r.utterance && (
        <p className='text-sm text-[#4E5968] dark:text-[#9CA3AF]'>{r.utterance}</p>
      )}

      {/* 상세 펼침 */}
      {isOpen && p && (
        <div className='mt-2 p-3 rounded-lg bg-[#F9FAFB] dark:bg-[#252D3D] text-[11px] space-y-2'>
          <div>
            <span className='text-[#8B95A1] dark:text-[#6B7280]'>OCEAN</span>
            <div className='flex flex-wrap gap-x-3 gap-y-0.5 mt-0.5 text-[#4E5968] dark:text-[#9CA3AF]'>
              {Object.entries(p.ocean).map(([dim, v]) => (
                <span key={dim}>
                  {OCEAN_LABEL[dim] ?? dim} {v.toFixed(2)}
                </span>
              ))}
            </div>
          </div>
          {Object.keys(p.consumption_values).length > 0 && (
            <div>
              <span className='text-[#8B95A1] dark:text-[#6B7280]'>소비가치</span>
              <p className='mt-0.5 text-[#4E5968] dark:text-[#9CA3AF] break-all'>
                {kvList(p.consumption_values)}
              </p>
            </div>
          )}
          {Object.keys(p.media_behavior).length > 0 && (
            <div>
              <span className='text-[#8B95A1] dark:text-[#6B7280]'>미디어 행동</span>
              <p className='mt-0.5 text-[#4E5968] dark:text-[#9CA3AF] break-all'>
                {kvList(p.media_behavior)}
              </p>
            </div>
          )}
          {Object.keys(p.socioeconomic).length > 0 && (
            <div>
              <span className='text-[#8B95A1] dark:text-[#6B7280]'>사회경제</span>
              <p className='mt-0.5 text-[#4E5968] dark:text-[#9CA3AF] break-all'>
                {kvList(p.socioeconomic)}
              </p>
            </div>
          )}
          {p.profile_narrative && (
            <div>
              <span className='text-[#8B95A1] dark:text-[#6B7280]'>프로필 서사</span>
              <p className='mt-0.5 text-[#4E5968] dark:text-[#9CA3AF]'>{p.profile_narrative}</p>
            </div>
          )}
          <span className='inline-block text-[10px] text-[#B0B8C1] dark:text-[#4B5563]'>
            가중치 {p.weight}
          </span>
        </div>
      )}
    </div>
  );
}
