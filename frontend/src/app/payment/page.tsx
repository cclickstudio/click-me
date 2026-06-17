'use client';

import { useState } from 'react';
import { loadTossPayments, type TossPaymentsWidgets } from '@tosspayments/tosspayments-sdk';
import AppLayout from '@/components/AppLayout';
import { api } from '@/lib/api';

const PRESETS = [10_000, 50_000, 100_000];
const CUSTOMER_KEY = 'clickme-demo-user'; // 6.12: 인증 미구현 — 데모 고정 사용자

export default function Page() {
  const [amount, setAmount] = useState<number>(50_000);
  const [step, setStep] = useState<'select' | 'pay'>('select');
  const [orderId, setOrderId] = useState<string | null>(null);
  const [widgets, setWidgets] = useState<TossPaymentsWidgets | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    } catch (e) {
      setError(e instanceof Error ? e.message : '결제 위젯을 불러오지 못했습니다');
      setStep('select');
    } finally {
      setLoading(false);
    }
  };

  const requestPayment = async () => {
    if (!widgets || !orderId) return;
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

  return (
    <AppLayout>
      <div className="max-w-screen-md mx-auto px-6 py-8">
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">크레딧 충전</h1>
          <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mt-1">
            충전한 크레딧만큼 광고를 집행할 수 있습니다 · 테스트 결제 (실제 출금 없음)
          </p>
        </div>

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
      </div>
    </AppLayout>
  );
}
