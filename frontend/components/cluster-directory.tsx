'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';

import { useClusterDetails } from '../hooks/use-cluster-details';
import {
  deriveDisplayTitle,
  formatDisplayDate,
  getRegistrationTimestamp,
  groupClustersBySource,
  type SourceGroup,
} from '../lib/cluster-helpers';
import type { ClusterSummary } from '../lib/types';
import { DetailStatusBadge } from './detail-status-badge';
import { SourceCredits } from './source-credits';

type ViewMode = 'today' | 'yesterday' | 'latest';

type ViewOption = {
  label: string;
  key: ViewMode;
};

type SourceCategory = 'all' | 'domestic' | 'europe' | 'middle-east' | 'asia' | 'africa';

type SourceCategoryOption = {
  key: SourceCategory;
  label: string;
};

const SOURCE_CATEGORY_OPTIONS: SourceCategoryOption[] = [
  { key: 'all', label: 'すべて' },
  { key: 'domestic', label: '国内' },
  { key: 'europe', label: '欧州' },
  { key: 'middle-east', label: '中東' },
  { key: 'asia', label: 'アジア' },
  { key: 'africa', label: 'アフリカ' },
];

const SOURCE_CATEGORY_SETS: Record<SourceCategory, ReadonlySet<string>> = {
  all: new Set(),
  domestic: new Set(['nhk-news']),
  europe: new Set(['bbc-world', 'dw-world', 'el-pais']),
  'middle-east': new Set(['al-jazeera-english']),
  asia: new Set(['straits-times', 'times-of-india']),
  africa: new Set(['allafrica-latest']),
};

const VIEW_OPTIONS: ViewOption[] = [
  { label: '今日', key: 'today' },
  { label: '昨日', key: 'yesterday' },
  { label: '取得順', key: 'latest' },
];

type Props = {
  clusters: ClusterSummary[];
};

export function ClusterDirectory({ clusters }: Props) {
  const { normalisedClusters, clusterDetails, ensureDetailSummary, getDetailState } =
    useClusterDetails(clusters);
  const [sourceCategory, setSourceCategory] = useState<SourceCategory>('all');
  const [viewMode, setViewMode] = useState<ViewMode>('today');
  const [activeClusterId, setActiveClusterId] = useState<string | null>(null);
  const filteredClusters = useMemo(() => {
    if (sourceCategory === 'all') {
      return normalisedClusters;
    }
    const allowed = SOURCE_CATEGORY_SETS[sourceCategory];
    return normalisedClusters.filter((cluster) =>
      cluster.sources.some((source) => allowed.has(source.id))
    );
  }, [normalisedClusters, sourceCategory]);

  useEffect(() => {
    if (activeClusterId && !filteredClusters.some((cluster) => cluster.id === activeClusterId)) {
      setActiveClusterId(null);
    }
  }, [filteredClusters, activeClusterId]);
  const baseClusterMap = useMemo(() => {
    const map = new Map<string, ClusterSummary>();
    normalisedClusters.forEach((cluster) => map.set(cluster.id, cluster));
    return map;
  }, [normalisedClusters]);

  const latestClusters = useMemo(() => {
    return [...filteredClusters].sort(
      (a, b) => getRegistrationTimestamp(b) - getRegistrationTimestamp(a)
    );
  }, [filteredClusters]);

  const todayClusters = useMemo(() => {
    const now = new Date();
    const startOfToday = new Date(now);
    startOfToday.setHours(0, 0, 0, 0);
    const startOfTodayMs = startOfToday.getTime();
    const startOfTomorrow = new Date(startOfToday);
    startOfTomorrow.setDate(startOfTomorrow.getDate() + 1);
    const startOfTomorrowMs = startOfTomorrow.getTime();

    return latestClusters.filter((cluster) => {
      const acquiredAtMs = getRegistrationTimestamp(cluster);
      if (acquiredAtMs === 0) {
        return false;
      }
      return acquiredAtMs >= startOfTodayMs && acquiredAtMs < startOfTomorrowMs;
    });
  }, [latestClusters]);

  const yesterdayClusters = useMemo(() => {
    const now = new Date();
    const startOfToday = new Date(now);
    startOfToday.setHours(0, 0, 0, 0);
    const startOfYesterday = new Date(startOfToday);
    startOfYesterday.setDate(startOfYesterday.getDate() - 1);
    const startOfTodayMs = startOfToday.getTime();
    const startOfYesterdayMs = startOfYesterday.getTime();

    return latestClusters.filter((cluster) => {
      const acquiredAtMs = getRegistrationTimestamp(cluster);
      if (acquiredAtMs === 0) {
        return false;
      }
      return acquiredAtMs >= startOfYesterdayMs && acquiredAtMs < startOfTodayMs;
    });
  }, [latestClusters]);

  const todayClustersBySource = useMemo<SourceGroup[]>(() => groupClustersBySource(todayClusters), [todayClusters]);
  const yesterdayClustersBySource = useMemo<SourceGroup[]>(() => groupClustersBySource(yesterdayClusters), [yesterdayClusters]);

  const activeCluster = activeClusterId
    ? clusterDetails[activeClusterId] ?? baseClusterMap.get(activeClusterId) ?? null
    : null;

  const handleOpenCluster = useCallback(
    (clusterId: string) => {
      setActiveClusterId(clusterId);
    },
    [setActiveClusterId]
  );

const renderClusterList = useCallback(
    (clusterList: ClusterSummary[], emptyMessage: string) => (
      <section className="rounded-xl border border-slate-200 bg-white/80 dark:border-slate-800 dark:bg-slate-900/40">
        <div className="border-b border-slate-200 px-4 py-3 text-xs text-slate-600 dark:border-slate-800 dark:text-slate-400">
          該当件数: {clusterList.length} 件
        </div>
        <ul className="max-h-[60vh] overflow-y-auto divide-y divide-slate-200 dark:divide-slate-800">
          {clusterList.length === 0 && (
            <li className="px-4 py-6 text-sm text-slate-600 dark:text-slate-400">{emptyMessage}</li>
          )}
          {clusterList.map((cluster) => {
            const resolvedCluster = clusterDetails[cluster.id] ?? cluster;
            const displayTitle = deriveDisplayTitle(resolvedCluster);
            const primarySource = resolvedCluster.sources[0];
            const siteName = primarySource?.name || '不明';
            const registeredIso =
              resolvedCluster.createdAt ??
              resolvedCluster.detailRequestedAt ??
              resolvedCluster.updatedAt;
            return (
              <li key={cluster.id}>
                <button
                  type="button"
                  onClick={() => handleOpenCluster(cluster.id)}
                  className="flex w-full items-start gap-3 overflow-hidden px-4 py-3 text-left text-sm text-slate-700 transition hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800/60"
                >
                  <div className="flex min-w-0 flex-1 items-start gap-3 overflow-hidden">
                    <div className="min-w-0 flex-1 overflow-hidden">
                      <p className="text-xs text-slate-600 dark:text-slate-400">
                        {formatDisplayDate(registeredIso)} ・ {siteName}
                      </p>
                      <p className="mt-1 truncate font-semibold text-slate-900 dark:text-slate-100">{displayTitle}</p>
                    </div>
                    <DetailStatusBadge
                      status={resolvedCluster.detailStatus}
                      className="shrink-0 whitespace-nowrap"
                    />
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      </section>
    ),
    [clusterDetails, handleOpenCluster]
  );

  const renderSourceGroups = useCallback(
    (groups: SourceGroup[], emptyMessage: string) => (
      <section className="flex flex-col gap-4">
        {groups.map(({ id, label, url, clusters: grouped }) => (
          <div key={id} className="rounded-xl border border-slate-200 bg-white/80 dark:border-slate-800 dark:bg-slate-900/40">
            <header className="flex items-center justify-between gap-4 border-b border-slate-200 px-4 py-3 text-base text-slate-900 dark:border-slate-800 dark:text-slate-100">
              {(() => {
                const resolvedUrl = url || grouped[0]?.sources?.find((s) => s.id === id)?.url;
                if (resolvedUrl) {
                  return (
                    <a
                      href={resolvedUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="max-w-[70%] overflow-hidden truncate text-left font-semibold text-slate-900 underline decoration-sky-500 underline-offset-4 dark:text-slate-100"
                    >
                      {label}
                    </a>
                  );
                }
                return (
                  <span className="max-w-[70%] overflow-hidden truncate text-left font-semibold text-slate-900 dark:text-slate-100">
                    {label}
                  </span>
                );
              })()}
              <span className="text-xs text-slate-500 dark:text-slate-400">{grouped.length} 件</span>
            </header>
            <ul className="max-h-[50vh] overflow-y-auto divide-y divide-slate-200 dark:divide-slate-800">
              {grouped.map((cluster) => {
                const resolvedCluster = clusterDetails[cluster.id] ?? cluster;
                const displayTitle = deriveDisplayTitle(resolvedCluster);
                const registeredIso =
                  resolvedCluster.createdAt ??
                  resolvedCluster.detailRequestedAt ??
                  resolvedCluster.updatedAt;
                return (
                  <li key={`${id}-${cluster.id}`}>
                    <button
                      type="button"
                      onClick={() => handleOpenCluster(cluster.id)}
                      className="flex w-full items-start gap-3 overflow-hidden px-4 py-3 text-left text-sm text-slate-700 transition hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800/60"
                    >
                      <div className="flex min-w-0 flex-1 items-start gap-3 overflow-hidden">
                        <div className="min-w-0 flex-1 overflow-hidden">
                          <p className="text-xs text-slate-600 dark:text-slate-400">{formatDisplayDate(registeredIso)}</p>
                          <p className="mt-1 truncate font-semibold text-slate-900 dark:text-slate-100">{displayTitle}</p>
                        </div>
                        <DetailStatusBadge
                          status={resolvedCluster.detailStatus}
                          className="shrink-0 whitespace-nowrap"
                        />
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
        {groups.length === 0 && (
          <p className="rounded-xl border border-slate-200 bg-white/80 px-4 py-6 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-900/40 dark:text-slate-400">
            {emptyMessage}
          </p>
        )}
      </section>
    ),
    [clusterDetails, handleOpenCluster]
  );

  const activeClusterDetailState = activeCluster
    ? getDetailState(activeCluster)
    : null;

  useEffect(() => {
    if (activeClusterId) {
      const handler = (event: KeyboardEvent) => {
        if (event.key === 'Escape') {
          setActiveClusterId(null);
        }
      };
      document.body.style.overflow = 'hidden';
      window.addEventListener('keydown', handler);
      return () => {
        document.body.style.overflow = '';
        window.removeEventListener('keydown', handler);
      };
    }
    document.body.style.overflow = '';
    return () => {
      document.body.style.overflow = '';
    };
  }, [activeClusterId]);

  return (
    <div className="flex flex-col gap-6">
      <section className="rounded-xl border border-slate-200 bg-white/80 p-3 text-sm dark:border-slate-800 dark:bg-slate-900/40">
        <div className="flex flex-wrap gap-2">
          {SOURCE_CATEGORY_OPTIONS.map((option) => {
            const isActive = sourceCategory === option.key;
            return (
              <button
                key={option.key}
                type="button"
                onClick={() => setSourceCategory(option.key)}
                className={`rounded-full px-4 py-2 text-sm transition ${
                  isActive
                    ? 'bg-emerald-500 text-white shadow'
                    : 'bg-slate-200 text-slate-700 hover:bg-slate-300 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700'
                }`}
              >
                {option.label}
              </button>
            );
          })}
        </div>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white/80 p-3 text-sm dark:border-slate-800 dark:bg-slate-900/40">
        <div className="flex flex-wrap gap-2">
          {VIEW_OPTIONS.map((option) => {
            const isActive = viewMode === option.key;
            return (
              <button
                key={option.key}
                type="button"
                onClick={() => setViewMode(option.key)}
                className={`rounded-full px-4 py-2 text-sm transition ${
                  isActive
                    ? 'bg-sky-500 text-white shadow'
                    : 'bg-slate-200 text-slate-700 hover:bg-slate-300 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700'
                }`}
              >
                {option.label}
              </button>
            );
          })}
        </div>
      </section>

      {viewMode === 'today' &&
        renderSourceGroups(todayClustersBySource, '本日取得されたクラスタは見つかりませんでした。')}

      {viewMode === 'yesterday' &&
        renderSourceGroups(yesterdayClustersBySource, '昨日取得されたクラスタは見つかりませんでした。')}

      {viewMode === 'latest' &&
        renderClusterList(latestClusters, '取得済みのクラスタがまだありません。')}

      {activeCluster && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center bg-slate-900/40 px-4 py-10 backdrop-blur-sm dark:bg-slate-950/70"
          onClick={() => setActiveClusterId(null)}
        >
          <article
            className="relative max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-700 shadow-2xl dark:border-slate-800 dark:bg-slate-900/90 dark:text-slate-200"
            onClick={(event) => event.stopPropagation()}
          >
            <button
              type="button"
              onClick={() => setActiveClusterId(null)}
              aria-label="閉じる"
              className="absolute right-4 top-4 rounded-full bg-slate-200 px-2 py-1 text-sm text-slate-700 transition hover:bg-slate-300 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
            >
              ×
            </button>
            <header className="mb-4 flex flex-col gap-2">
              <h2 className="line-clamp-2 break-words text-xl font-semibold">{deriveDisplayTitle(activeCluster)}</h2>
              <time className="text-xs text-slate-500 dark:text-slate-400">
                {formatDisplayDate(activeCluster.createdAt ?? activeCluster.detailRequestedAt ?? activeCluster.updatedAt)}
              </time>
            </header>
            <section className="flex flex-col gap-6">
              {activeClusterDetailState && (
                <>
                  {!activeClusterDetailState.hasSummary && (
                    <div className="flex flex-wrap items-center gap-3">
                      <button
                        type="button"
                        onClick={() => ensureDetailSummary(activeCluster)}
                        disabled={activeClusterDetailState.isGenerating}
                        className={`rounded-full px-4 py-2 text-sm transition ${
                          activeClusterDetailState.isGenerating
                            ? 'bg-slate-200 text-slate-500 dark:bg-slate-800 dark:text-slate-400'
                            : 'bg-sky-500 text-white hover:bg-sky-600'
                        }`}
                      >
                        <span className="flex items-center gap-2">
                          {activeClusterDetailState.isGenerating && (
                            <span
                              aria-hidden="true"
                              className="inline-flex h-4 w-4 animate-spin rounded-full border-2 border-white/60 border-t-transparent"
                            />
                          )}
                          <span>
                            {activeClusterDetailState.isGenerating ? '要約を生成中…' : '要約を生成'}
                          </span>
                        </span>
                      </button>
                    </div>
                  )}
                  <div className="flex flex-col gap-2">
                    {activeClusterDetailState.detailStatus === 'partial' && (
                      <p className="text-sm text-slate-600 dark:text-slate-400">
                        要約はまだ生成されていません。上のボタンから生成できます。
                      </p>
                    )}
                    {activeClusterDetailState.isError && (
                      <p className="text-sm text-rose-300">
                        要約の生成に失敗しました。
                        {activeClusterDetailState.failureReason && (
                          <span className="ml-1 text-xs">
                            原因: {activeClusterDetailState.failureReason}
                          </span>
                        )}
                        <span className="ml-1">時間をおいて再試行してください。</span>
                      </p>
                    )}
                    {activeClusterDetailState.hasSummary && (
                      <p className="whitespace-pre-wrap break-words leading-relaxed text-slate-800 dark:text-slate-200">
                        {activeClusterDetailState.summary}
                      </p>
                    )}
                  </div>
                </>
              )}
              <SourceCredits
                sources={activeCluster.sources}
                heading="参照記事"
                primaryHeadline={activeCluster.headline}
              />
            </section>
          </article>
        </div>
      )}
    </div>
  );
}
