'use client';

import type { ClusterSummary } from '../lib/types';

type StatusMeta = {
  label: string;
  className: string;
  spinner?: boolean;
};

const STATUS_META: Record<Exclude<ClusterSummary['detailStatus'], undefined | null>, StatusMeta> = {
  ready: {
    label: 'できた！',
    className: 'bg-emerald-500/90 text-white',
  },
  stale: {
    label: 'ちょっと古い',
    className: 'bg-amber-500/80 text-slate-900',
  },
  pending: {
    label: 'ぐるぐる生成中',
    className: 'bg-sky-500/90 text-white',
    spinner: true,
  },
  failed: {
    label: 'エラーでした',
    className: 'bg-rose-600/90 text-white',
  },
  partial: {
    label: 'まだ未生成',
    className: 'bg-slate-700 text-slate-200',
  },
};

const DEFAULT_META: StatusMeta = {
  label: 'まだ未生成',
  className: 'bg-slate-700 text-slate-200',
};

function resolveMeta(status?: ClusterSummary['detailStatus']): StatusMeta {
  if (!status) {
    return DEFAULT_META;
  }
  return STATUS_META[status] ?? DEFAULT_META;
}

type DetailStatusBadgeProps = {
  status?: ClusterSummary['detailStatus'];
  className?: string;
};

export function DetailStatusBadge({ status, className = '' }: DetailStatusBadgeProps) {
  const meta = resolveMeta(status);
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${meta.className} ${className}`}
    >
      {meta.spinner ? (
        <span
          className="h-1.5 w-1.5 animate-spin rounded-full border border-white/60 border-t-transparent"
          aria-hidden="true"
        />
      ) : (
        <span className="h-1.5 w-1.5 rounded-full bg-current opacity-80" aria-hidden="true" />
      )}
      {meta.label}
    </span>
  );
}
