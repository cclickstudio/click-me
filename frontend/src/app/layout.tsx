import type { Metadata } from 'next';
import './globals.css';
import ThemeProvider from '@/components/ThemeProvider';
import { AuthProvider } from '@/components/AuthProvider';
import { ProjectProvider } from '@/components/ProjectContext';
import { ChatControllerProvider } from '@/components/chat/ChatController';

export const metadata: Metadata = {
  title: 'Click Me - 광고 관리 파이널 플래너',
  description: '광고를 집행하기 전에, AI 가상 소비자에게 먼저 테스트해보세요.',
  icons: {
    icon: '/logo/logo-mark.png',
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko" data-scroll-behavior="smooth" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var e=document.documentElement;var dt=localStorage.getItem('data-theme')||'blue';e.setAttribute('data-theme',dt);var editor=['monokai','monokai-black','dracula'].indexOf(dt)!==-1;var t=localStorage.getItem('theme');var d=window.matchMedia('(prefers-color-scheme: dark)').matches;if(editor||t==='dark'||(t===null&&d))e.classList.add('dark')}catch(e){}})()`,
          }}
        />
      </head>
      <body className="font-sans">
        <ThemeProvider>
          <AuthProvider>
            <ProjectProvider>
              <ChatControllerProvider>{children}</ChatControllerProvider>
            </ProjectProvider>
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
