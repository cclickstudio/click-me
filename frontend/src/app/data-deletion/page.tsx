// 데이터 삭제 안내 — Meta 앱 심사 필수 URL(사용자 데이터 삭제 방법 고지): https://clickme.co.kr/data-deletion
import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = { title: '데이터 삭제 안내 | ClickMe' };

const h2 = 'text-lg font-bold text-[#191F28] mt-8 mb-2';
const p = 'text-sm leading-relaxed text-[#4E5968] mb-2';
const li = 'text-sm leading-relaxed text-[#4E5968] ml-5 list-decimal';

export default function DataDeletionPage() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <h1 className="text-2xl font-bold text-[#191F28]">데이터 삭제 안내</h1>
      <p className="mt-1 text-xs text-[#8B95A1]">Data Deletion Instructions</p>

      <p className={`${p} mt-6`}>
        ClickMe는 Meta(Facebook·Instagram) 연동을 통해 광고 계정 식별자, 액세스 토큰(암호화
        저장), 광고 성과 집계 데이터를 처리합니다. 아래 방법으로 언제든지 연동과 데이터 삭제를
        요청할 수 있습니다.
      </p>

      <h2 className={h2}>방법 1 — 서비스 내 연동 해제</h2>
      <ul className="mb-2">
        <li className={li}>ClickMe 로그인 → 광고 매니지먼트 → 연동 메뉴로 이동합니다.</li>
        <li className={li}>연결된 Meta 계정의 연결 해제를 요청합니다.</li>
        <li className={li}>해제 시 저장된 액세스 토큰과 연동 정보는 지체 없이 삭제됩니다.</li>
      </ul>

      <h2 className={h2}>방법 2 — Facebook 설정에서 앱 제거</h2>
      <ul className="mb-2">
        <li className={li}>Facebook 설정 → 앱 및 웹사이트로 이동합니다.</li>
        <li className={li}>목록에서 ClickMe를 찾아 제거합니다.</li>
        <li className={li}>제거 시 ClickMe의 접근 권한이 즉시 무효화됩니다.</li>
      </ul>

      <h2 className={h2}>방법 3 — 이메일 삭제 요청</h2>
      <p className={p}>
        rkdrudrn1031@gmail.com 으로 “데이터 삭제 요청”과 함께 계정 정보(로그인 ID 또는 연동한
        광고 계정 ID)를 보내주세요. 접수 후 영업일 기준 7일 이내에 관련 데이터를 삭제하고 결과를
        회신합니다.
      </p>

      <h2 className={h2}>삭제되는 데이터</h2>
      <ul className="mb-2 list-disc">
        <li className="text-sm leading-relaxed text-[#4E5968] ml-5 list-disc">Meta 액세스 토큰 및 연동 식별 정보</li>
        <li className="text-sm leading-relaxed text-[#4E5968] ml-5 list-disc">해당 계정으로 수집된 광고 성과 조회 캐시</li>
        <li className="text-sm leading-relaxed text-[#4E5968] ml-5 list-disc">요청 시 계정 정보 일체(법령상 보존 의무 항목 제외)</li>
      </ul>

      <p className="mt-10 text-sm">
        <Link href="/privacy" className="text-[#3182F6] underline">
          개인정보처리방침
        </Link>
        {' · '}
        <Link href="/terms" className="text-[#3182F6] underline">
          이용약관
        </Link>
      </p>
    </main>
  );
}
