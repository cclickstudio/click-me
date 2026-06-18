export type MetaPixelParams = Record<string, string | number | boolean | string[]>;

const pendingEventIds = new Set<string>();

declare global {
  interface Window {
    fbq?: (...args: unknown[]) => void;
  }
}

export function trackMetaPixelEvent(
  eventName: 'PageView' | 'InitiateCheckout' | 'Purchase',
  params: MetaPixelParams = {},
  eventId?: string,
): boolean {
  if (typeof window === 'undefined' || typeof window.fbq !== 'function') {
    return false;
  }

  if (eventId) {
    window.fbq('track', eventName, params, { eventID: eventId });
  } else {
    window.fbq('track', eventName, params);
  }
  return true;
}

export function trackMetaPixelEventOnce(
  eventName: 'InitiateCheckout' | 'Purchase',
  params: MetaPixelParams,
  eventId: string,
): void {
  if (typeof window === 'undefined') return;

  const storageKey = `clickme:meta-pixel:${eventId}`;
  if (pendingEventIds.has(eventId)) return;
  pendingEventIds.add(eventId);

  const attempt = (remaining: number) => {
    try {
      if (window.localStorage.getItem(storageKey)) {
        pendingEventIds.delete(eventId);
        return;
      }
    } catch {
      // 저장소가 차단돼도 이벤트 전송 자체는 계속 시도한다.
    }

    if (trackMetaPixelEvent(eventName, params, eventId)) {
      try {
        window.localStorage.setItem(storageKey, new Date().toISOString());
      } catch {
        // 이벤트는 이미 전송됐으므로 저장 실패는 무시한다.
      }
      pendingEventIds.delete(eventId);
      return;
    }

    if (remaining <= 0) {
      pendingEventIds.delete(eventId);
      return;
    }
    window.setTimeout(() => attempt(remaining - 1), 250);
  };

  attempt(20); // Pixel 스크립트가 늦게 로드돼도 최대 5초 기다린다.
}
