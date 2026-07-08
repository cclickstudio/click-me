// 빈 상태 프리미티브 — 아이콘·헤드라인·설명·CTA.
import * as React from 'react';
import { cn } from '@/lib/utils';

interface EmptyStateProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'title'> {
  icon?: React.ReactNode;
  title: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
  ...props
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-line px-6 py-14 text-center',
        className
      )}
      {...props}
    >
      {icon && (
        <div className='flex size-12 items-center justify-center rounded-full bg-surface-1 text-ink-tertiary [&_svg]:size-6'>
          {icon}
        </div>
      )}
      <div className='space-y-1'>
        <p className='text-base font-semibold text-ink'>{title}</p>
        {description && (
          <p className='mx-auto max-w-sm text-sm text-ink-secondary'>{description}</p>
        )}
      </div>
      {action && <div className='mt-1'>{action}</div>}
    </div>
  );
}
