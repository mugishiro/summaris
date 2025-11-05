'use client';

import type { ClusterSummary } from '../lib/types';

type StatusMeta = {
  label: string;
  className: string;
};

const STATUS_META: Record<Exclude<ClusterSummary['detailStatus'], undefined | null>, StatusMeta> = {
  ready: {
    label: '要約済み',
    className: 'bg-emerald-500/90 text-white',
  },
  stale: {
    label: '要再生成',
    className: 'bg-amber-500/80 text-slate-900',
  },
  pending: {
    label: '生成中',
    className: 'bg-sky-500/90 text-white',
  },
  failed: {
    label: '生成失敗',
    className: 'bg-rose-600/90 text-white',
  },
  partial: {
    label: '未生成',
    className: 'bg-slate-700 text-slate-200',
  },
};

const DEFAULT_META: StatusMeta = {
  label: '未生成',
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
      <span className="h-1.5 w-1.5 rounded-full bg-current opacity-80" aria-hidden="true" />
      {meta.label}
    </span>
  );
}
