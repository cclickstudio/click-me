'use client';

// 캠페인 클릭 시 뜨는 상세보기 모달 — 배경/ESC로 닫기. CampaignDetail을 오버레이로 감싼다.
import { useEffect } from 'react';
import type { CampaignDetail as Detail, CampaignSource } from './types';
import { CampaignDetail } from './CampaignDetail';

export function CampaignDetailModal({
  detail,
  source,
  onClose,
}: {
  detail: Detail;
  source?: CampaignSource;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="bg-white dark:bg-[#1C2333] rounded-2xl shadow-xl w-full max-w-3xl max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-[#E5E8EB] dark:border-[#2D3748] sticky top-0 bg-white dark:bg-[#1C2333] z-10">
          <span className="font-bold text-[#191F28] dark:text-[#F2F4F6]">캠페인 상세</span>
          <button
            onClick={onClose}
            aria-label="닫기"
            className="text-[#8B95A1] hover:text-[#191F28] dark:hover:text-[#F2F4F6] text-lg leading-none px-1"
          >
            ✕
          </button>
        </div>
        <div className="p-4">
          <CampaignDetail detail={detail} source={source} />
        </div>
      </div>
    </div>
  );
}
