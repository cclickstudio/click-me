// 미니 추세선 — 값 배열을 정규화해 인라인 SVG 폴리라인으로 그린다(축·툴팁 없음).
export function Sparkline({
  values,
  width = 96,
  height = 28,
  stroke = '#2563EB',
}: {
  values: number[];
  width?: number;
  height?: number;
  stroke?: string;
}) {
  const pts = values.filter((v) => Number.isFinite(v));
  if (pts.length < 2) {
    return <div style={{ width, height }} className="text-[10px] text-ink-muted">추세 없음</div>;
  }
  const min = Math.min(...pts);
  const max = Math.max(...pts);
  const span = max - min || 1;
  const pad = 2;
  const stepX = (width - pad * 2) / (pts.length - 1);
  const path = pts
    .map((v, i) => {
      const x = pad + i * stepX;
      const y = pad + (height - pad * 2) * (1 - (v - min) / span);
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
  const lastX = pad + (pts.length - 1) * stepX;
  const lastY = pad + (height - pad * 2) * (1 - (pts[pts.length - 1] - min) / span);
  return (
    <svg width={width} height={height} className="overflow-visible">
      <path d={path} fill="none" stroke={stroke} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={lastX} cy={lastY} r={2} fill={stroke} />
    </svg>
  );
}
