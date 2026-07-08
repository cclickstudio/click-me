// 섹션 헤더 통일 프리미티브 — title·description·우측 action 슬롯 + 본문.
import * as React from 'react';
import { cn } from '@/lib/utils';

interface SectionProps extends Omit<React.HTMLAttributes<HTMLElement>, 'title'> {
  title?: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  /** 헤더 여백/크기. */
  size?: 'sm' | 'md';
}

export function Section({
  title,
  description,
  action,
  size = 'md',
  className,
  children,
  ...props
}: SectionProps) {
  return (
    <section className={cn('space-y-4', className)} {...props}>
      {(title || action) && (
        <div className='flex items-end justify-between gap-4'>
          <div className='space-y-1'>
            {title && (
              <h2
                className={cn(
                  'font-bold tracking-tight text-ink',
                  size === 'sm' ? 'text-base' : 'text-lg'
                )}
              >
                {title}
              </h2>
            )}
            {description && (
              <p className='text-sm text-ink-secondary'>{description}</p>
            )}
          </div>
          {action && <div className='shrink-0'>{action}</div>}
        </div>
      )}
      {children}
    </section>
  );
}
