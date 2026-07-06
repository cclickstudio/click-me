// 개인정보처리방침 — 공개 정적 페이지(Meta 앱 심사 필수 URL: https://clickme.co.kr/privacy)
import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = { title: '개인정보처리방침 | ClickMe' };

const h2 = 'text-lg font-bold text-[#191F28] mt-8 mb-2';
const p = 'text-sm leading-relaxed text-[#4E5968] mb-2';
const li = 'text-sm leading-relaxed text-[#4E5968] ml-5 list-disc';

export default function PrivacyPage() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <h1 className="text-2xl font-bold text-[#191F28]">개인정보처리방침</h1>
      <p className="mt-1 text-xs text-[#8B95A1]">시행일 2026-07-03</p>

      <p className={`${p} mt-6`}>
        ClickMe(이하 “회사”)는 광고 시뮬레이션·생성·관리 서비스를 제공하며, 이용자의 개인정보를
        중요하게 생각하고 「개인정보 보호법」 등 관련 법령을 준수합니다.
      </p>

      <h2 className={h2}>1. 수집하는 개인정보 항목</h2>
      <ul className="mb-2">
        <li className={li}>계정 정보: 이름, 로그인 ID, 이메일, 연락처(관리자가 계정을 생성하며 자가가입은 없습니다)</li>
        <li className={li}>Meta(Facebook·Instagram) 연동 정보: 광고 계정 ID, 페이지·Instagram 자산 식별자, 액세스 토큰(암호화 저장)</li>
        <li className={li}>광고 성과 데이터: 노출·클릭·지출 등 Meta Marketing API로 조회되는 집계 지표</li>
        <li className={li}>서비스 이용 기록: 접속 로그, 시뮬레이션·생성 이용 내역</li>
      </ul>

      <h2 className={h2}>2. 이용 목적</h2>
      <ul className="mb-2">
        <li className={li}>서비스 제공 — 광고 성과 조회·비교·관리, 시뮬레이션·시안 생성</li>
        <li className={li}>계정 관리 및 조직(팀) 단위 접근 제어</li>
        <li className={li}>서비스 품질 개선 및 오류 대응</li>
      </ul>

      <h2 className={h2}>3. 보유 및 이용 기간</h2>
      <p className={p}>
        개인정보는 수집·이용 목적 달성 시(계정 삭제, Meta 연동 해제 등) 지체 없이 파기합니다. 단,
        관련 법령에 따라 보존이 필요한 경우 해당 기간 동안 보관합니다.
      </p>

      <h2 className={h2}>4. 제3자 제공 및 처리 위탁</h2>
      <p className={p}>
        회사는 이용자의 동의 없이 개인정보를 제3자에게 제공하지 않습니다. 서비스 운영을 위해
        클라우드 인프라(AWS)에 처리를 위탁하며, 위탁 시 관련 법령에 따라 안전하게 관리합니다.
      </p>

      <h2 className={h2}>5. Meta 플랫폼 데이터</h2>
      <p className={p}>
        Meta 연동 시 받는 액세스 토큰은 AES-256으로 암호화해 저장하며, 광고 성과 조회·관리
        목적에만 사용합니다. 연동 해제 또는 데이터 삭제 요청 방법은{' '}
        <Link href="/data-deletion" className="text-[#3182F6] underline">
          데이터 삭제 안내
        </Link>
        를 참고하세요.
      </p>

      <h2 className={h2}>6. 이용자의 권리</h2>
      <p className={p}>
        이용자는 언제든지 자신의 개인정보 열람·정정·삭제·처리정지를 요청할 수 있습니다. 요청은
        아래 연락처 또는 서비스 내 문의 기능으로 접수해 주세요.
      </p>

      <h2 className={h2}>7. 문의처</h2>
      <p className={p}>개인정보 보호 책임: ClickMe 운영팀 · 이메일 rkdrudrn1031@gmail.com</p>

      <p className="mt-10 text-xs text-[#B0B8C1]">
        본 방침은 서비스 변경에 따라 개정될 수 있으며, 개정 시 본 페이지에 게시합니다.
      </p>
      <p className="mt-4 text-sm">
        <Link href="/terms" className="text-[#3182F6] underline">
          이용약관
        </Link>
        {' · '}
        <Link href="/data-deletion" className="text-[#3182F6] underline">
          데이터 삭제 안내
        </Link>
      </p>
    </main>
  );
}
