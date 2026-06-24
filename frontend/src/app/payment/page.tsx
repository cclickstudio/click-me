'use client';

import { useEffect, useMemo, useState } from 'react';
import { loadTossPayments, type TossPaymentsWidgets } from '@tosspayments/tosspayments-sdk';
import AppLayout from '@/components/AppLayout';
import { api } from '@/lib/api';
import { trackMetaPixelEventOnce } from '@/lib/metaPixel';

const PRESETS = [10_000, 50_000, 100_000];
const MIN_CHARGE = 1_521; // 광고 집행 최소 금액(Meta floor) — 기본은 최소로(테스트 시 실차감 최소화)
const CUSTOMER_KEY = 'clickme-demo-user'; // 6.12: 인증 미구현 — 데모 고정 사용자

type LedgerEntry = {
  entry_id: string;
  delta_krw: number;
  balance_after_krw: number;
  reason: string;
  ref_id: string;
  created_at: string;
};

export default function Page() {
  const [amount, setAmount] = useState<number>(MIN_CHARGE);
  const [step, setStep] = useState<'select' | 'pay'>('select');
  const [orderId, setOrderId] = useState<string | null>(null);
  const [widgets, setWidgets] = useState<TossPaymentsWidgets | null>(null);
  const [loading, setLoading] = useState(false);
  const [cancelingOrderId, setCancelingOrderId] = useState<string | null>(null);
  const [history, setHistory] = useState<LedgerEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [presetFromCampaign, setPresetFromCampaign] = useState(false);

  const loadHistory = () => {
    api.billing
      .history()
      .then((res) => setHistory(res.entries))
      .catch(() => setHistory([]));
  };

  useEffect(() => {
    loadHistory();
    // 게재 시작 중 잔액 부족으로 넘어온 경우 — 잡아둔 예산(부족액)을 충전 금액으로 자동 적용.
    const need = Number(new URLSearchParams(window.location.search).get('amount'));
    if (Number.isFinite(need) && need > 0) {
      setAmount(Math.ceil(need / 1000) * 1000); // 1,000원 단위로 올림
      setPresetFromCampaign(true);
    }
  }, []);

  const refundedOrderIds = useMemo(
    () => new Set(history.filter((entry) => entry.reason === 'refund').map((entry) => entry.ref_id)),
    [history],
  );
  const charges = useMemo(
    () => history.filter((entry) => entry.reason === 'charge').slice().reverse(),
    [history],
  );

  const startCheckout = async () => {
    setLoading(true);
    setError(null);
    try {
      // 금액은 서버가 주문으로 기억 — confirm 때 대조해 변조를 차단한다
      const order = await api.billing.createOrder(amount);
      setOrderId(order.order_id);

      const toss = await loadTossPayments(order.client_key);
      const w = toss.widgets({ customerKey: CUSTOMER_KEY });
      await w.setAmount({ currency: 'KRW', value: order.amount_krw });
      setStep('pay');
      await w.renderPaymentMethods({ selector: '#payment-methods', variantKey: 'DEFAULT' });
      await w.renderAgreement({ selector: '#agreement', variantKey: 'AGREEMENT' });
      setWidgets(w);
      trackMetaPixelEventOnce(
        'InitiateCheckout',
        {
          value: order.amount_krw,
          currency: 'KRW',
          content_type: 'product',
          content_ids: ['clickme-ad-credit'],
          content_name: 'ClickMe 광고 크레딧',
          num_items: 1,
        },
        `checkout-${order.order_id}`,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : '결제 위젯을 불러오지 못했습니다');
      setStep('select');
    } finally {
      setLoading(false);
    }
  };

  const requestPayment = async () => {
    if (!widgets || !orderId) return;
    if (
      !window.confirm(
        '카카오페이 등 외부 간편결제는 테스트 키에서도 실제 잔액이 차감될 수 있습니다. 결제를 계속할까요?',
      )
    ) {
      return;
    }
    setError(null);
    try {
      await widgets.requestPayment({
        orderId,
        orderName: `ClickMe 광고 크레딧 ${amount.toLocaleString()}원`,
        successUrl: `${window.location.origin}/payment/success`,
        failUrl: `${window.location.origin}/payment/fail`,
      });
    } catch (e) {
      // 사용자가 결제창을 닫은 경우 포함
      setError(e instanceof Error ? e.message : '결제가 진행되지 않았습니다');
    }
  };

  const cancelPayment = async (orderId: string) => {
    if (!window.confirm('이 결제를 전액 취소하고 충전 크레딧을 회수할까요?')) return;
    setCancelingOrderId(orderId);
    setError(null);
    try {
      await api.billing.cancel(orderId);
      loadHistory();
    } catch (e) {
      setError(e instanceof Error ? e.message : '결제를 취소하지 못했습니다');
    } finally {
      setCancelingOrderId(null);
    }
  };

  return (
    <AppLayout>
      <div className="max-w-screen-md mx-auto px-6 py-8">
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">크레딧 충전</h1>
          <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mt-1">
            충전한 크레딧만큼 광고를 집행할 수 있습니다 · 테스트 키 사용 중
          </p>
          <p className="text-xs text-red-500 mt-2">
            카카오페이 등 외부 간편결제는 테스트 중에도 실제 잔액이 차감될 수 있습니다.
            가능하면 최소 금액으로 진행하고, 완료 후 충전 내역에서 즉시 취소하세요.
          </p>
        </div>

        {presetFromCampaign && step === 'select' && (
          <div className="mb-4 rounded-xl bg-[#EBF3FF] dark:bg-[#1E3A5F] border border-[#3182F6]/30 p-3">
            <p className="text-sm text-[#3182F6] font-medium">
              게재에 필요한 예산만큼 충전 금액을 채워뒀어요.
            </p>
            <p className="text-xs text-[#4E5968] dark:text-[#9CA3AF] mt-1">
              충전을 완료하면 만들던 캠페인 게재가 자동으로 이어집니다.
            </p>
          </div>
        )}

        {step === 'select' && (
          <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-6">
            <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-4">충전 금액</p>
            <div className="grid grid-cols-3 gap-3 mb-4">
              {PRESETS.map((preset) => (
                <button
                  key={preset}
                  onClick={() => setAmount(preset)}
                  className={`py-3 rounded-xl text-sm font-medium border transition-colors ${
                    amount === preset
                      ? 'border-[#3182F6] bg-[#3182F6]/10 text-[#3182F6]'
                      : 'border-[#E5E8EB] dark:border-[#2D3748] text-[#191F28] dark:text-[#F2F4F6]'
                  }`}
                >
                  {preset.toLocaleString()}원
                </button>
              ))}
            </div>
            <input
              type="number"
              min={1000}
              step={1000}
              value={amount}
              onChange={(e) => setAmount(Math.max(0, Number(e.target.value)))}
              className="w-full px-4 py-3 mb-6 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] bg-transparent text-[#191F28] dark:text-[#F2F4F6] text-sm"
            />
            <button
              onClick={startCheckout}
              disabled={loading || amount <= 0}
              className="w-full py-3 bg-[#3182F6] text-white text-sm font-medium rounded-xl hover:bg-[#1B6EEB] transition-colors disabled:opacity-40"
            >
              {loading ? '결제 준비 중…' : `${amount.toLocaleString()}원 결제 진행`}
            </button>
          </div>
        )}

        {step === 'pay' && (
          <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-6">
            <div id="payment-methods" />
            <div id="agreement" />
            <button
              onClick={requestPayment}
              className="w-full mt-4 py-3 bg-[#3182F6] text-white text-sm font-medium rounded-xl hover:bg-[#1B6EEB] transition-colors"
            >
              {amount.toLocaleString()}원 결제하기
            </button>
          </div>
        )}

        {error && (
          <p className="mt-4 text-sm text-red-500" role="alert">
            {error}
          </p>
        )}

        {charges.length > 0 && (
          <div className="mt-8 bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-6">
            <h2 className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-4">
              충전 내역
            </h2>
            <div className="space-y-3">
              {charges.map((entry) => {
                const refunded = refundedOrderIds.has(entry.ref_id);
                return (
                  <div
                    key={entry.entry_id}
                    className="flex items-center justify-between gap-4 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] p-4"
                  >
                    <div>
                      <p className="text-sm font-medium text-[#191F28] dark:text-[#F2F4F6]">
                        {entry.delta_krw.toLocaleString()}원
                      </p>
                      <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mt-1">
                        {new Date(entry.created_at).toLocaleString('ko-KR')}
                      </p>
                    </div>
                    {refunded ? (
                      <span className="text-xs font-medium text-[#8B95A1]">취소 완료</span>
                    ) : (
                      <button
                        type="button"
                        onClick={() => cancelPayment(entry.ref_id)}
                        disabled={cancelingOrderId === entry.ref_id}
                        className="px-3 py-2 text-xs font-medium rounded-lg border border-red-200 text-red-500 hover:bg-red-50 disabled:opacity-40"
                      >
                        {cancelingOrderId === entry.ref_id ? '취소 중…' : '결제 취소'}
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </AppLayout>
  );
}
