// 이용약관 — 공개 정적 페이지(https://clickme.co.kr/terms)
import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = { title: '이용약관 | ClickMe' };

const h2 = 'text-lg font-bold text-[#191F28] mt-8 mb-2';
const p = 'text-sm leading-relaxed text-[#4E5968] mb-2';
const li = 'text-sm leading-relaxed text-[#4E5968] ml-5 list-disc';

export default function TermsPage() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <h1 className="text-2xl font-bold text-[#191F28]">이용약관</h1>
      <p className="mt-1 text-xs text-[#8B95A1]">시행일 2026-07-03</p>

      <h2 className={h2}>제1조 (목적)</h2>
      <p className={p}>
        본 약관은 ClickMe(이하 “회사”)가 제공하는 광고 시뮬레이션·생성·관리 서비스(이하
        “서비스”)의 이용 조건과 회사·이용자 간 권리·의무를 정합니다.
      </p>

      <h2 className={h2}>제2조 (계정)</h2>
      <ul className="mb-2">
        <li className={li}>계정은 관리자가 생성·발급하며, 이용자는 자신의 계정 정보를 안전하게 관리해야 합니다.</li>
        <li className={li}>계정의 부정 사용으로 발생한 문제에 대해 회사는 고의·과실이 없는 한 책임지지 않습니다.</li>
      </ul>

      <h2 className={h2}>제3조 (서비스 내용)</h2>
      <ul className="mb-2">
        <li className={li}>AI 가상 소비자 기반 광고 반응 시뮬레이션 및 결과 리포트</li>
        <li className={li}>광고 개선 시안 자동 생성</li>
        <li className={li}>Meta 등 외부 광고 플랫폼 연동을 통한 성과 조회·비교·관리</li>
      </ul>

      <h2 className={h2}>제4조 (시뮬레이션 결과의 성격)</h2>
      <p className={p}>
        시뮬레이션 결과는 실측이 아닌 AI 기반 상대 지표(탐색적 신호)이며, 실제 광고 성과를
        보장하지 않습니다. 집행 의사결정의 참고 자료로만 활용해야 하며, 이에 따른 최종 판단과
        책임은 이용자에게 있습니다.
      </p>

      <h2 className={h2}>제5조 (외부 플랫폼 연동)</h2>
      <p className={p}>
        이용자는 자신이 적법한 권한을 가진 광고 계정만 연동해야 합니다. 연동된 플랫폼(Meta 등)의
        정책 위반으로 발생하는 불이익은 이용자 책임이며, 회사는 연동 토큰을 암호화해 관리합니다.
      </p>

      <h2 className={h2}>제6조 (금지 행위)</h2>
      <ul className="mb-2">
        <li className={li}>타인의 계정·데이터에 대한 무단 접근</li>
        <li className={li}>서비스의 역설계, 비정상적 대량 호출 등 운영을 방해하는 행위</li>
        <li className={li}>법령 또는 공서양속에 반하는 광고 소재의 제작·집행</li>
      </ul>

      <h2 className={h2}>제7조 (책임의 한계)</h2>
      <p className={p}>
        회사는 천재지변, 외부 플랫폼(Meta 등) 장애, 이용자 귀책 사유로 인한 서비스 중단·손해에
        대해 책임지지 않습니다.
      </p>

      <h2 className={h2}>제8조 (약관의 변경)</h2>
      <p className={p}>
        회사는 약관을 개정할 수 있으며, 개정 시 본 페이지에 사전 공지합니다. 개정 후에도 서비스를
        계속 이용하면 변경에 동의한 것으로 봅니다.
      </p>

      <p className="mt-10 text-sm">
        <Link href="/privacy" className="text-[#3182F6] underline">
          개인정보처리방침
        </Link>
        {' · '}
        <Link href="/data-deletion" className="text-[#3182F6] underline">
          데이터 삭제 안내
        </Link>
      </p>
    </main>
  );
}
