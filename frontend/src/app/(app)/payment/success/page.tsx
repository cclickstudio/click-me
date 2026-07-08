'use client';

import { Suspense, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { api } from '@/lib/api';
import { trackMetaPixelEventOnce } from '@/lib/metaPixel';
import { popPendingActivation } from '@/lib/pendingActivation';

function SuccessContent() {
  const params = useSearchParams();
  const [status, setStatus] = useState<'confirming' | 'done' | 'error'>('confirming');
  const [balance, setBalance] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  // 충전 후 게재 재개 — prompt(게재할지 확인) → running → served/failed. null이면 재개할 캠페인 없음.
  const [resume, setResume] = useState<
    null | { state: 'prompt' | 'running' | 'served' | 'failed'; text?: string }
  >(null);
  const [pending, setPending] = useState<{ campaignId: string; commit: number } | null>(null);
  const confirmedRef = useRef(false);

  useEffect(() => {
    const paymentKey = params.get('paymentKey');
    const orderId = params.get('orderId');
    const amount = params.get('amount');
    if (!paymentKey || !orderId || !amount) {
      setStatus('error');
      setMessage('결제 정보가 누락되었습니다');
      return;
    }
    if (confirmedRef.current) return; // StrictMode 중복 호출 방지 (서버도 멱등)
    confirmedRef.current = true;

    api.billing
      .confirm({ payment_key: paymentKey, order_id: orderId, amount_krw: Number(amount) })
      .then((res) => {
        trackMetaPixelEventOnce(
          'Purchase',
          {
            value: res.amount_krw,
            currency: 'KRW',
            content_type: 'product',
            content_ids: ['clickme-ad-credit'],
            content_name: 'ClickMe 광고 크레딧',
            num_items: 1,
          },
          `purchase-${res.order_id}`,
        );
        setBalance(res.balance_krw);
        setStatus('done');
        // 게재 시작 중 넘어온 경우 — 충전이 끝났으니 "게재할까요?"를 묻고, 동의해야 Meta로 넘긴다.
        const p = popPendingActivation();
        if (p) {
          setPending(p);
          setResume({ state: 'prompt' });
        }
      })
      .catch((e: Error) => {
        setStatus('error');
        setMessage(e.message);
      });
  }, [params]);

  // "게재하기" 동의 시에만 Meta로 활성화 요청을 보낸다(실과금 시작).
  const doResume = () => {
    if (!pending) return;
    setResume({ state: 'running' });
    api.management
      .activate(pending.campaignId, pending.commit)
      .then((r) => {
        setBalance(r.balance_krw);
        if (r.serving) {
          setResume({ state: 'served' });
        } else {
          setResume({ state: 'failed', text: r.causes[0]?.message ?? '게재를 시작하지 못했습니다.' });
        }
      })
      .catch((e: Error) => setResume({ state: 'failed', text: e.message }));
  };

  return (
    <div className="max-w-screen-md mx-auto px-6 py-16 text-center">
      {status === 'confirming' && (
        <p className="text-sm text-ink-tertiary">결제 승인 확인 중…</p>
      )}

      {status === 'done' && (
        <div className="bg-card border border-line rounded-2xl p-10">
          <div className="w-12 h-12 mx-auto mb-4 flex items-center justify-center rounded-full bg-primary/10 text-primary">
            ✓
          </div>
          <h1 className="text-xl font-bold text-ink mb-2">충전 완료</h1>
          <p className="text-sm text-ink-tertiary mb-6">
            현재 크레딧 잔액{' '}
            <span className="font-semibold text-primary">{balance?.toLocaleString()}원</span>
          </p>

          {/* 만들던 캠페인이 있으면 — 게재할지 묻고, 동의해야 Meta로 넘긴다 */}
          {resume?.state === 'prompt' && (
            <div className="mb-6 rounded-xl bg-surface-1 p-4">
              <p className="text-sm font-medium text-ink mb-1">
                만들던 캠페인을 지금 게재할까요?
              </p>
              <p className="text-xs text-ink-tertiary mb-3">
                게재하면 광고가 실제로 노출되고 집행분만큼 크레딧이 차감됩니다
                {pending ? ` (한도 ${pending.commit.toLocaleString()}원)` : ''}.
              </p>
              <button
                onClick={doResume}
                className="px-5 py-2.5 bg-[#191F28] text-white text-sm font-semibold rounded-lg hover:bg-black"
              >
                광고 게재하기
              </button>
            </div>
          )}
          {resume?.state === 'running' && (
            <p className="text-sm text-ink-tertiary mb-6">게재를 시작하는 중…</p>
          )}
          {resume?.state === 'served' && (
            <p className="text-sm text-green-600 dark:text-green-400 mb-6">
              캠페인 게재가 시작되었습니다.
            </p>
          )}
          {resume?.state === 'failed' && (
            <p className="text-sm text-amber-600 dark:text-amber-400 mb-6">
              충전은 됐지만 게재를 시작하지 못했어요 — {resume.text}
            </p>
          )}

          <Link
            href={resume ? '/manage/campaigns' : '/manage'}
            className="inline-block px-6 py-3 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:bg-primary-hover transition-colors"
          >
            {resume?.state === 'prompt' ? '나중에' : resume ? '캠페인으로 이동' : '광고 매니지먼트로 이동'}
          </Link>
        </div>
      )}

      {status === 'error' && (
        <div className="bg-card border border-line rounded-2xl p-10">
          <h1 className="text-xl font-bold text-ink mb-2">승인 실패</h1>
          <p className="text-sm text-red-500 mb-6">{message}</p>
          <Link
            href="/payment"
            className="inline-block px-6 py-3 border border-line text-sm font-medium rounded-xl text-ink"
          >
            다시 시도
          </Link>
        </div>
      )}
    </div>
  );
}

export default function Page() {
  return (
      <Suspense fallback={null}>
        <SuccessContent />
      </Suspense>
  );
}
