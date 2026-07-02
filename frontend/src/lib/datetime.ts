// 전역 시각 표시 유틸 — 백엔드는 created_at 등을 UTC naive(타임존 정보 없는 ISO)로 저장·직렬화한다.
// 따라서 타임존 표기가 없으면 UTC로 간주하고 한국 시간(Asia/Seoul)으로 변환해 표시한다.
// (DB/모델 컬럼은 건드리지 않는 표시 전용 — P2 안전 경로.)

function toDate(iso?: string | null): Date | null {
  if (!iso) return null;
  const s = String(iso).trim();
  const hasTz = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(s);
  const norm = hasTz ? s : s.replace(' ', 'T') + 'Z';
  const d = new Date(norm);
  return isNaN(d.getTime()) ? null : d;
}

function partsKST(d: Date): Record<string, string> {
  return new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
    .formatToParts(d)
    .reduce<Record<string, string>>((a, x) => {
      a[x.type] = x.value;
      return a;
    }, {});
}

// 컴팩트: "M/D HH:MM" (KST) — 목록·세션 칩 등.
export function formatKST(iso?: string | null): string {
  const d = toDate(iso);
  if (!d) return '';
  const p = partsKST(d);
  return `${Number(p.month)}/${Number(p.day)} ${p.hour}:${p.minute}`;
}

// 풀: "YYYY-MM-DD HH:MM" (KST) — 상세·결과 등.
export function formatKSTFull(iso?: string | null): string {
  const d = toDate(iso);
  if (!d) return '';
  const p = partsKST(d);
  return `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute}`;
}

// 날짜만: "YYYY-MM-DD" (KST) — 표·목록의 날짜 칸.
export function formatKSTDate(iso?: string | null): string {
  const d = toDate(iso);
  if (!d) return '';
  const p = partsKST(d);
  return `${p.year}-${p.month}-${p.day}`;
}

// 상대시간: "방금 전 / N분 전 / N시간 전 / N일 전", 그 이상은 KST 절대시각.
export function formatRelativeKST(iso?: string | null, now: Date = new Date()): string {
  const d = toDate(iso);
  if (!d) return '';
  const diffSec = Math.round((now.getTime() - d.getTime()) / 1000);
  if (diffSec < 0) return formatKST(iso);
  if (diffSec < 60) return '방금 전';
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}분 전`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}시간 전`;
  if (diffSec < 86400 * 7) return `${Math.floor(diffSec / 86400)}일 전`;
  return formatKST(iso);
}
