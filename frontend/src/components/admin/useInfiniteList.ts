// 목록 무한스크롤 공용 훅 — resetKey 변경 시 첫 페이지부터, 센티넬이 보이면 다음 페이지를 이어 붙인다.
'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

// 백엔드가 배열(list)을 반환하므로 has_more는 "받은 개수 >= pageSize"로 추정한다.
export function useInfiniteList<T extends { id: string }>(
  fetcher: (offset: number, limit: number) => Promise<T[]>,
  resetKey: string,
  pageSize = 20,
) {
  const [items, setItems] = useState<T[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const offsetRef = useRef(0); // 다음 요청의 SQL offset(= 지금까지 백엔드에서 받은 총 개수)
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  // fetcher는 매 렌더 새로 생성될 수 있으므로 ref로 최신값을 잡아 effect deps에서 뺀다.
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  // resetKey(정렬·검색·상태 등) 변경 시 첫 페이지부터 다시 로드.
  useEffect(() => {
    let alive = true;
    setLoading(true);
    offsetRef.current = 0;
    fetcherRef.current(0, pageSize)
      .then((rows) => {
        if (!alive) return;
        setItems(rows);
        offsetRef.current = rows.length;
        setHasMore(rows.length >= pageSize);
      })
      .catch(() => {
        if (alive) {
          setItems([]);
          setHasMore(false);
        }
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [resetKey, pageSize]);

  const loadMore = useCallback(async () => {
    if (loadingMore) return;
    setLoadingMore(true);
    try {
      const rows = await fetcherRef.current(offsetRef.current, pageSize);
      offsetRef.current += rows.length;
      setItems((prev) => {
        const seen = new Set(prev.map((r) => r.id));
        return [...prev, ...rows.filter((r) => !seen.has(r.id))];
      });
      setHasMore(rows.length >= pageSize);
    } catch {
      // 다음 페이지 실패는 조용히 무시 — 재스크롤로 재시도.
    } finally {
      setLoadingMore(false);
    }
  }, [loadingMore, pageSize]);

  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (e) => {
        if (e[0]?.isIntersecting && hasMore && !loading && !loadingMore) loadMore();
      },
      { rootMargin: '200px' },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [hasMore, loading, loadingMore, loadMore]);

  return { items, loading, loadingMore, hasMore, sentinelRef };
}

// 검색 입력 디바운스 — 키 입력마다 재요청하지 않도록 delay 후 값 확정.
export function useDebouncedValue<T>(value: T, delay = 300): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return v;
}
