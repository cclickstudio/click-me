'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import AppLayout from '@/components/AppLayout';
import { api } from '@/lib/api';
import { CampaignTable } from '@/components/manage/campaigns/CampaignTable';
import { CampaignCards } from '@/components/manage/campaigns/CampaignCards';
import { CampaignDetailModal } from '@/components/manage/campaigns/CampaignDetailModal';
import type {
  CampaignDetail as Detail,
  CampaignSource,
  CampaignSummary,
  CampaignView,
} from '@/components/manage/campaigns/types';

export default function Page() {
  const [view, setView] = useState<CampaignView>('table');
  const [campaigns, setCampaigns] = useState<CampaignSummary[]>([]);
  const [source, setSource] = useState<CampaignSource>('mock');
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setBusy(true);
    setError(null);
    api.management
      .campaigns()
      .then((r) => {
        if (!alive) return;
        setCampaigns(r.campaigns);
        setSource(r.source ?? 'mock');
      })
      .catch((e) => alive && setError(e instanceof Error ? e.message : '불러오기 실패'))
      .finally(() => alive && setBusy(false));
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      return;
    }
    let alive = true;
    api.management
      .campaign(selected)
      .then((d) => alive && setDetail(d))
      .catch(() => alive && setDetail(null));
    return () => {
      alive = false;
    };
  }, [selected]);

  return (
    <AppLayout>
      <div className="max-w-screen-xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">캠페인 대시보드</h1>
              {source === 'live' ? (
                <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">
                  실데이터
                </span>
              ) : (
                <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-300">
                  데모
                </span>
              )}
            </div>
            <p className="text-sm text-[#8B95A1] mt-1">
              {source === 'live'
                ? '실 Meta 연동 · 라이브 지표'
                : '목표·예산·성과를 한 창구에서 (Mock 기반 데모)'}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] overflow-hidden text-sm">
              <button
                onClick={() => setView('table')}
                className={`px-3 py-1.5 ${view === 'table' ? 'bg-[#3182F6] text-white' : 'text-[#8B95A1]'}`}
              >
                테이블
              </button>
              <button
                onClick={() => setView('cards')}
                className={`px-3 py-1.5 ${view === 'cards' ? 'bg-[#3182F6] text-white' : 'text-[#8B95A1]'}`}
              >
                카드
              </button>
            </div>
            <Link
              href="/manage/campaigns/new"
              className="px-3 py-1.5 bg-[#3182F6] text-white text-sm font-medium rounded-lg hover:bg-[#1B6EEB]"
            >
              + 새 캠페인
            </Link>
          </div>
        </div>

        {busy && <p className="text-sm text-[#8B95A1] py-20 text-center">불러오는 중…</p>}
        {error && (
          <p className="text-sm text-red-500 py-20 text-center" role="alert">
            {error}
          </p>
        )}

        {!busy && !error && campaigns.length > 0 && (
          <div className="space-y-4">
            {view === 'table' ? (
              <CampaignTable campaigns={campaigns} selected={selected} onSelect={setSelected} />
            ) : (
              <CampaignCards campaigns={campaigns} selected={selected} onSelect={setSelected} />
            )}
          </div>
        )}

        {selected && detail && (
          <CampaignDetailModal detail={detail} source={source} onClose={() => setSelected(null)} />
        )}

        <p className="mt-6 text-[11px] text-[#B0B8C1]">
          {source === 'live'
            ? '실데이터 · Meta 라이브 · CVR/ROAS는 전환 추적 전이라 미측정 · 금액 KRW'
            : '⚠ Mock 기반 데모 · 노출/지출은 일중 곡선 모델 기반 · "예측 CTR" 등 실측 환산 없음 · 금액 KRW'}
        </p>
      </div>
    </AppLayout>
  );
}
