export function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

export function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

export function calcDistributionMean(dist: number[]): number {
  const levels = dist.length;
  return dist.reduce((acc, p, i) => acc + p * (i / (levels - 1)), 0);
}
