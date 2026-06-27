// 광고 매니지먼트 — 연동: 조직이 자기 Meta(Facebook·Instagram) 광고 자산을 연결하는 진입점
'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';

export default function ManageConnectPage() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ ok: boolean; msg: string } | null>(null);

  // 콜백이 ?meta=connected|cancelled 로 돌려보내면 안내 표시 (raw 에러 대신).
  useEffect(() => {
    const meta = new URLSearchParams(window.location.search).get('meta');
    if (meta === 'connected') setNotice({ ok: true, msg: 'Meta 계정이 연결되었습니다.' });
    else if (meta === 'cancelled')
      setNotice({ ok: false, msg: '연결이 취소되었거나 완료되지 않았습니다. 다시 시도하세요.' });
  }, []);

  // 인증 XHR로 받은 Facebook 로그인 URL로 이동 → 동의 후 콜백이 토큰을 암호화 저장.
  const connectMeta = async () => {
    setBusy(true);
    setError(null);
    try {
      const { login_url } = await api.management.connectMeta();
      window.location.href = login_url;
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Meta 연결 시작에 실패했습니다.');
      setBusy(false);
    }
  };

  return (
      <div className="px-8 py-8 max-w-3xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">연동</h1>
          <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mt-1">
            우리 조직의 광고 플랫폼 계정을 연결합니다.
          </p>
        </div>

        {notice && (
          <div
            className={`rounded-xl px-4 py-3 text-sm ${
              notice.ok
                ? 'bg-[#EBF3FF] text-[#1B64DA] dark:bg-[#1E3A5F] dark:text-[#9DC3FF]'
                : 'bg-[#FFF1F0] text-[#E03131] dark:bg-[#3A1E1E] dark:text-[#FF9D9D]'
            }`}
          >
            {notice.ok ? '✓ ' : '⚠ '}
            {notice.msg}
          </div>
        )}

        <section className="rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#161B27] p-6">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <h2 className="text-base font-semibold text-[#191F28] dark:text-[#F2F4F6]">Meta 계정 연결</h2>
              <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mt-1">
                Facebook 로그인으로 광고 계정·페이지·Instagram 접근 권한을 부여하면 성과 조회·비교·관리가 가능합니다.
              </p>
              <p className="text-xs text-[#B0B8C1] dark:text-[#4B5563] mt-2">
                조직 단위 연결입니다 — 조직 오너 계정으로 로그인해 진행하세요.
              </p>
            </div>
            <button
              onClick={connectMeta}
              disabled={busy}
              className="shrink-0 rounded-xl bg-[#3182F6] px-4 py-2.5 text-sm font-medium text-white hover:bg-[#1B64DA] disabled:opacity-50"
            >
              {busy ? '연결 중…' : 'Meta 계정 연결'}
            </button>
          </div>
          {error && <p className="mt-3 text-sm text-red-500">{error}</p>}
        </section>
      </div>
  );
}
