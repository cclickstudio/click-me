// 챗 본문 마크다운 렌더 — 굵게·번호목록·문단·줄바꿈을 GFM으로 표시(평문 대신).
// 안전 렌더러: rehype-raw 미사용 → 모델/사용자 출력의 raw HTML은 escape(XSS 방지).
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export default function Markdown({ children }: { children: string }) {
  return (
    <div className="text-sm leading-relaxed [&>*:last-child]:mb-0">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="mb-2">{children}</p>,
          ul: ({ children }) => <ul className="list-disc pl-5 mb-2 space-y-0.5">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal pl-5 mb-2 space-y-0.5">{children}</ol>,
          li: ({ children }) => <li>{children}</li>,
          strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
          a: ({ children, href }) => (
            <a href={href} target="_blank" rel="noreferrer" className="text-[#3182F6] underline">
              {children}
            </a>
          ),
          // inline code — 작은 pill
          code: ({ children }) => (
            <code className="px-1 py-0.5 rounded bg-black/5 dark:bg-white/10 text-[0.85em]">
              {children}
            </code>
          ),
          // code block — 블록 박스. 안쪽 code의 pill은 자식 셀렉터로 리셋해 이중 배경 방지.
          pre: ({ children }) => (
            <pre className="block overflow-x-auto p-3 my-2 rounded-lg bg-black/5 dark:bg-white/10 text-[0.85em] [&_code]:bg-transparent [&_code]:p-0">
              {children}
            </pre>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
