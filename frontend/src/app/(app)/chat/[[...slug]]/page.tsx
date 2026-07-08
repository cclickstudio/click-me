'use client';

// /chat — 채팅 워크스페이스(좌: 세션 사이드바 / 우: 대화). 좌측 컨텍스트 패널과 결합하지 않는다.
import ChatWorkspace from '@/components/chat/ChatWorkspace';

export default function ChatRoutePage() {
  return <ChatWorkspace />;
}
