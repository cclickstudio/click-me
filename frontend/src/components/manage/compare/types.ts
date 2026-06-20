// 오가닉↔광고 비교 응답 타입 — 백엔드 comparison/schemas.py 대응

export type LiftVerdict = 'pass' | 'caution' | 'fail';

export type PostInsights = {
  post_id: string;
  post_type: 'organic' | 'paid';
  as_of: string;
  reach: number;
  impressions: number;
  engagement: number;
  clicks: number;
  spend_krw: number;
};

export type LiftResult = {
  post_id: string;
  organic: PostInsights;
  paid: PostInsights;
  reach_lift_abs: number;
  reach_lift_ratio: number;
  impressions_lift_abs: number;
  verdict: LiftVerdict;
  computed_at: string;
};

export type BoardRow = { title: string; lift: LiftResult };
export type BoardResponse = { rows: BoardRow[] };

// 비율(%) — 분모 0 보호. engagement/impressions 또는 clicks/impressions.
export const rate = (num: number, den: number): number => (den > 0 ? (num / den) * 100 : 0);
