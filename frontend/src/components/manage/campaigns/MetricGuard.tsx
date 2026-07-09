// 권한 거부 등으로 못 불러온 지표 셀 표시 — 실제 0·미설정과 구분되는 '권한 없음' 배지.
export function Blocked({ label = '권한 없음' }: { label?: string }) {
  return (
    <span
      title="권한 없음 — Meta에서 이 값을 불러올 권한이 없어요. 토큰·자산 권한을 확인하세요."
      className="text-ink-muted"
    >
      {label}
    </span>
  );
}
