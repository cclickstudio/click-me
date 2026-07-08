import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { formatKSTDate } from "./datetime";

// shadcn/ui 표준 클래스 병합 헬퍼 — 조건부 클래스(clsx) + Tailwind 충돌 해소(tailwind-merge).
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// 백엔드는 시각을 UTC로 저장·직렬화하므로 KST로 변환해 표시(타임존 표기 없으면 UTC 간주).
export function formatDate(iso: string) {
  return formatKSTDate(iso);
}

export function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

export function calcDistributionMean(dist: number[]): number {
  const levels = dist.length;
  return dist.reduce((acc, p, i) => acc + p * (i / (levels - 1)), 0);
}

// 보안 컨텍스트가 아니어도 동작하는 UUID v4 생성기
export function safeRandomUUID(): string {
  if (typeof crypto !== "undefined") {
    if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
    if (typeof crypto.getRandomValues === "function") {
      const b = crypto.getRandomValues(new Uint8Array(16));
      b[6] = (b[6] & 0x0f) | 0x40;
      b[8] = (b[8] & 0x3f) | 0x80;
      const h = [...b].map((x) => x.toString(16).padStart(2, "0"));
      return `${h[0]}${h[1]}${h[2]}${h[3]}-${h[4]}${h[5]}-${h[6]}${h[7]}-${h[8]}${h[9]}-${h[10]}${h[11]}${h[12]}${h[13]}${h[14]}${h[15]}`;
    }
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}
