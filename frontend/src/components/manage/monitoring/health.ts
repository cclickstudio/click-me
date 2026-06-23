// 캠페인 요약(/campaigns)에서 운영 건강신호를 도출 — 시간대 비의존, 실측 필드만 사용.
import type { CampaignSummary } from '@/components/manage/campaigns/types';

export type HealthLevel = 'critical' | 'warn' | 'info' | 'ok' | 'ended';

export type HealthSignal = {
  level: HealthLevel;
  label: string; // 배지 문구
  hint: string; // 한 줄 설명(왜·무엇을)
};

// 심각도 정렬용 가중치 (높을수록 먼저).
export const SEVERITY: Record<HealthLevel, number> = {
  critical: 4,
  warn: 3,
  info: 2,
  ok: 1,
  ended: 0,
};

// 주의가 필요한 신호인지 — 집계 카운트·정렬에 사용.
export const needsAttention = (level: HealthLevel): boolean =>
  level === 'critical' || level === 'warn';

// 단일 캠페인의 가장 시급한 신호 하나를 반환. 우선순위: 게재중단 > 예산소진 > 목표미달 > 상태/소진더딤.
export function campaignHealth(c: CampaignSummary): HealthSignal {
  if (c.state === 'ended') {
    return { level: 'ended', label: '종료', hint: '게재가 끝난 캠페인입니다.' };
  }
  if (c.delivery_blocked) {
    return {
      level: 'critical',
      label: '게재 중단',
      hint: c.block_reason ?? '계정 선불 잔액 부족 — 충전 전까지 게재되지 않습니다.',
    };
  }
  if (c.pacing_pct >= 100) {
    return {
      level: 'warn',
      label: '일예산 소진',
      hint: '오늘 일예산을 다 써 게재가 멈출 수 있어요. 증액을 검토하세요.',
    };
  }
  if (c.pacing_pct >= 90) {
    return {
      level: 'warn',
      label: '소진 임박',
      hint: `일예산 ${c.pacing_pct.toFixed(0)}% 소진 — 곧 오늘 게재가 종료될 수 있어요.`,
    };
  }
  if (c.target_missed) {
    return {
      level: 'warn',
      label: '목표 ROAS 미달',
      hint: `목표 ${c.target_roas ?? '-'}x 대비 실측 ${(c.roas ?? 0).toFixed(2)}x — 소재·타겟 점검이 필요해요.`,
    };
  }
  if (c.state === 'under_review' || c.state === 'active_pending_review') {
    return { level: 'info', label: '심사 중', hint: 'Meta 심사 통과 후 게재가 시작됩니다.' };
  }
  if (c.state === 'paused' || c.state === 'draft') {
    return {
      level: 'info',
      label: c.state === 'paused' ? '일시정지' : '초안',
      hint: '현재 게재되지 않는 상태입니다.',
    };
  }
  if (c.pacing_pct < 15) {
    return {
      level: 'info',
      label: '소진 더딤',
      hint: `일예산 ${c.pacing_pct.toFixed(0)}%만 소진 — 노출이 적거나 입찰이 약할 수 있어요.`,
    };
  }
  return { level: 'ok', label: '정상', hint: '특이 신호 없이 게재 중입니다.' };
}

// 노출 피로 — 같은 사람에게 반복 노출(frequency)이 높으면 CTR 붕괴·CPM 상승. primary와 직교라
// 별도 배지로 노출한다. 임계: 4.0+ 경고, 2.8+ 주의(업계 통용 휴리스틱 — 추정).
export type FatigueSignal = { level: 'warn' | 'info'; label: string; hint: string } | null;

export function frequencyFatigue(c: CampaignSummary): FatigueSignal {
  if (c.state !== 'active' || !Number.isFinite(c.frequency)) return null;
  if (c.frequency >= 4.0) {
    return {
      level: 'warn',
      label: `피로 ${c.frequency.toFixed(1)}`,
      hint: '동일인 반복 노출이 높아요 — 소재 교체·타겟 확장을 검토하세요.',
    };
  }
  if (c.frequency >= 2.8) {
    return {
      level: 'info',
      label: `빈도 ${c.frequency.toFixed(1)}`,
      hint: '노출 빈도가 올라가는 중 — 곧 소재 피로가 올 수 있어요.',
    };
  }
  return null;
}

export const LEVEL_STYLE: Record<HealthLevel, { dot: string; text: string; chip: string }> = {
  critical: {
    dot: 'bg-red-500',
    text: 'text-red-600 dark:text-red-400',
    chip: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  },
  warn: {
    dot: 'bg-amber-500',
    text: 'text-amber-700 dark:text-amber-400',
    chip: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  },
  info: {
    dot: 'bg-[#3182F6]',
    text: 'text-[#3182F6]',
    chip: 'bg-[#EBF3FF] text-[#3182F6] dark:bg-[#1E3A5F] dark:text-[#73A9FF]',
  },
  ok: {
    dot: 'bg-green-500',
    text: 'text-green-600 dark:text-green-400',
    chip: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  },
  ended: {
    dot: 'bg-[#B0B8C1]',
    text: 'text-[#8B95A1]',
    chip: 'bg-[#F2F4F6] text-[#8B95A1] dark:bg-[#2D3748] dark:text-[#6B7280]',
  },
};
