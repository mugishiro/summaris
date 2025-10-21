'use client';

import Link from 'next/link';
import { useMemo } from 'react';

import type { ClusterSummary } from '../lib/types';
import { SourceCredits } from './source-credits';

function formatRelative(dateIso: string): string {
  const date = new Date(dateIso);
  const diff = Date.now() - date.getTime();
  const minutes = Math.round(diff / 60000);
  if (minutes < 1) return 'たった今';
  if (minutes < 60) return `${minutes}分前`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}時間前`;
  const days = Math.round(hours / 24);
  return `${days}日前`;
}

export function ClusterCard({ cluster }: { cluster: ClusterSummary }) {
  const relative = useMemo(() => formatRelative(cluster.updatedAt), [cluster.updatedAt]);
  const summary = cluster.summaryLong?.trim();
  return (
    <article className="flex flex-col gap-4 rounded-xl border border-slate-800 bg-slate-900/40 p-5 shadow-sm shadow-slate-950/40 transition hover:border-sky-500/40">
      <Link
        href={`/cluster/${cluster.id}`}
        className="line-clamp-2 break-words text-lg font-semibold text-slate-100 hover:text-sky-200"
      >
        {cluster.headline}
      </Link>
      <p className="break-words text-sm leading-relaxed text-slate-300">
        {summary && summary.length > 0 ? summary : '要約はまだ生成されていません。'}
      </p>
      <div className="flex flex-col gap-2 text-sm text-slate-400">
        <p className="text-xs">更新: {relative}</p>
      <SourceCredits sources={cluster.sources} primaryHeadline={cluster.headline} />
      </div>
    </article>
  );
}
