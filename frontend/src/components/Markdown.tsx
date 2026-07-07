'use client';
// LLM 답변(마크다운)을 채팅 말풍선에 맞게 렌더 — 표·목록·코드·강조를 Tailwind로 스타일.

import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';

export function Markdown({ children }: { children: string }) {
  return (
    <div className="text-sm leading-relaxed [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="mb-2 leading-relaxed">{children}</p>,
          ul: ({ children }) => <ul className="list-disc pl-5 mb-2 space-y-1">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal pl-5 mb-2 space-y-1">{children}</ol>,
          li: ({ children }) => <li className="leading-relaxed">{children}</li>,
          h1: ({ children }) => <h1 className="text-base font-bold mb-2 mt-3">{children}</h1>,
          h2: ({ children }) => <h2 className="text-sm font-bold mb-1.5 mt-3">{children}</h2>,
          h3: ({ children }) => <h3 className="text-sm font-semibold mb-1 mt-2">{children}</h3>,
          strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
          em: ({ children }) => <em className="italic">{children}</em>,
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer" className="text-[#3182F6] underline">
              {children}
            </a>
          ),
          code: ({ className, children }) =>
            className?.includes('language-') ? (
              <code className={className}>{children}</code>
            ) : (
              <code className="px-1 py-0.5 rounded bg-black/5 dark:bg-white/10 text-[0.85em] font-mono">
                {children}
              </code>
            ),
          pre: ({ children }) => (
            <pre className="my-2 p-3 rounded-lg bg-[#0F172A] text-[#E2E8F0] text-[12px] overflow-x-auto">
              {children}
            </pre>
          ),
          table: ({ children }) => (
            <div className="my-2 overflow-x-auto">
              <table className="w-full text-[13px] border-collapse">{children}</table>
            </div>
          ),
          thead: ({ children }) => (
            <thead className="border-b border-line">{children}</thead>
          ),
          th: ({ children }) => <th className="text-left font-semibold px-2 py-1">{children}</th>,
          td: ({ children }) => (
            <td className="px-2 py-1 border-b border-line">{children}</td>
          ),
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-[#D1D6DB] dark:border-[#333D4B] pl-3 my-2 text-[#6B7684] dark:text-[#9CA3AF]">
              {children}
            </blockquote>
          ),
          hr: () => <hr className="my-3 border-line" />,
        } satisfies Components}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
