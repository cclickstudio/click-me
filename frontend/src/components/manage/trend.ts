// 추세 델타 계산 — 마지막 값 vs 직전 구간(최대 6일) 평균의 등락률. 데이터 부족이면 null.
export function trendDelta(values: number[]): number | null {
  const v = values.filter((x) => Number.isFinite(x));
  if (v.length < 2) return null;
  const last = v[v.length - 1];
  const prev = v.slice(0, -1).slice(-6);
  const avg = prev.reduce((a, b) => a + b, 0) / prev.length;
  if (avg <= 0) return null;
  return (last - avg) / avg;
}
