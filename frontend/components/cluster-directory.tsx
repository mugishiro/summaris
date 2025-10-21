'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';

import type { ClusterSummary } from '../lib/types';
import { SourceCredits } from './source-credits';

type ViewMode = 'today' | 'yesterday' | 'latest';

type ViewOption = {
  label: string;
  key: ViewMode;
};

type SourceGroup = {
  id: string;
  label: string;
  url?: string;
  clusters: ClusterSummary[];
};

const VIEW_OPTIONS: ViewOption[] = [
  { label: '今日', key: 'today' },
  { label: '昨日', key: 'yesterday' },
  { label: '取得順', key: 'latest' },
];

const DETAIL_POLL_INTERVAL_MS = 1500;
const DETAIL_POLL_MAX_ATTEMPTS = 20;

function containsJapanese(text: string): boolean {
  return /[\u3040-\u30ff\u4e00-\u9faf]/.test(text);
}

function deriveDisplayTitle(cluster: ClusterSummary): string {
  const candidate = cluster.headlineJa?.trim();
  if (candidate) {
    return candidate;
  }
  const original = cluster.headline.trim();
  if (containsJapanese(original)) {
    return original;
  }
  const detail = (cluster.summaryLong ?? '').trim();
  if (!detail) {
    return original;
  }
  const sentenceMatch = detail.match(/[^。!?！？]+/);
  if (sentenceMatch && sentenceMatch[0].length > 0) {
    return sentenceMatch[0];
  }
  return detail.length > 0 ? detail : original;
}

function formatDisplayDate(timestamp?: string): string {
  if (!timestamp) {
    return '';
  }
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return timestamp;
  }
  return date.toLocaleString('ja-JP', { hour12: false });
}

function toTimestamp(value?: string): number {
  if (!value) {
    return 0;
  }
  const parsed = new Date(value).getTime();
  return Number.isNaN(parsed) ? 0 : parsed;
}

function getRegistrationTimestamp(cluster: ClusterSummary): number {
  const createdAt = toTimestamp(cluster.createdAt);
  if (createdAt > 0) {
    return createdAt;
  }
  const requestedAt = toTimestamp(cluster.detailRequestedAt);
  if (requestedAt > 0) {
    return requestedAt;
  }
  const publishedAt = toTimestamp(cluster.publishedAt);
  if (publishedAt > 0) {
    return publishedAt;
  }
  return toTimestamp(cluster.updatedAt);
}

const JSON_FENCE_RE = /```(?:json)?\s*({[\s\S]*?})\s*```/i;
const QUOTED_VALUE_RE = (key: string) =>
  new RegExp(`"${key}"\\s*:\\s*"([^"\\\\]*(?:\\\\.[^"\\\\]*)*)"`, 'i');
const ARRAY_VALUE_RE = (key: string) =>
  new RegExp(`"${key}"\\s*:\\s*\\[(.*?)\\]`, 'is');
const JP_TEXT_RE = /[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]/;

function groupClustersBySource(clusters: ClusterSummary[]): SourceGroup[] {
  const map = new Map<string, SourceGroup>();

  clusters.forEach((cluster) => {
    cluster.sources.forEach((source) => {
      const id = source.id || 'unknown';
      const label = source.name?.trim() || id;
      const siteUrl = source.siteUrl || undefined;
      const articleUrl = source.articleUrl || source.url || undefined;
      if (!map.has(id)) {
        map.set(id, {
          id,
          label,
          url: siteUrl || undefined,
          clusters: [],
        });
      }
      const group = map.get(id)!;
      if (!group.url && (siteUrl || articleUrl)) {
        group.url = siteUrl || articleUrl;
      }
      group.clusters.push(cluster);
    });
  });

  return Array.from(map.values())
    .map((group) => ({
      ...group,
      url:
        group.url ??
        group.clusters[0]?.sources.find((s) => s.id === group.id)?.siteUrl ??
        group.clusters[0]?.sources.find((s) => s.id === group.id)?.url,
    }))
    .sort((a, b) => a.label.localeCompare(b.label, 'ja'));
}

type ParsedSummaryPayload = {
  summary?: string;
  summaryLong?: string;
  diffPoints?: string[];
};

function decodeJsonLikeString(raw: string): string {
  try {
    const wrapped = `{"value":"${raw.replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"}`;
    const parsed = JSON.parse(wrapped) as { value: string };
    return parsed.value.trim();
  } catch {
    return raw.replace(/\\n/gi, '\n').replace(/\\"/g, '"').replace(/\\\\/g, '\\').trim();
  }
}

function stripStructuredArtifacts(raw?: string): string {
  if (!raw) {
    return '';
  }
  const withoutFence = raw.replace(JSON_FENCE_RE, '').trim();
  return withoutFence
    .replace(/^Here\s+(?:is|are)\s+the\s+(?:summarized\s+article|summary|summaries).*?:\s*/i, '')
    .replace(/^Here\s+(?:is|are)\s+the\s+diff\s+points.*?:\s*/i, '')
    .trim();
}

function parseStructuredJson(raw?: string): Record<string, unknown> | null {
  if (!raw) {
    return null;
  }
  const trimmed = raw.trim();
  if (!trimmed) {
    return null;
  }
  const fenceMatch = JSON_FENCE_RE.exec(trimmed);
  let candidate: string | null = null;
  if (fenceMatch) {
    candidate = fenceMatch[1];
  } else {
    const firstBrace = trimmed.indexOf('{');
    const lastBrace = trimmed.lastIndexOf('}');
    if (firstBrace >= 0 && lastBrace > firstBrace) {
      candidate = trimmed.slice(firstBrace, lastBrace + 1);
    }
  }
  if (!candidate) {
    return null;
  }
  try {
    const parsed = JSON.parse(candidate);
    return parsed && typeof parsed === 'object' ? (parsed as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

function extractQuotedValue(raw: string | undefined, key: string): string | undefined {
  if (!raw) {
    return undefined;
  }
  const match = QUOTED_VALUE_RE(key).exec(raw);
  if (!match || !match[1]) {
    return undefined;
  }
  return decodeJsonLikeString(match[1]);
}

function extractArrayValue(raw: string | undefined, key: string): string[] | undefined {
  if (!raw) {
    return undefined;
  }
  const match = ARRAY_VALUE_RE(key).exec(raw);
  if (!match || match[1] == null) {
    return undefined;
  }
  const content = match[1].trim();
  if (!content) {
    return [];
  }
  const items = content.split(/,(?![^[]*\])/).map((item) => decodeJsonLikeString(item.replace(/^\s*["']?/, '').replace(/["']?\s*$/, '')));
  return items.filter((item) => item.length > 0);
}

function firstNonEmpty(...candidates: Array<string | undefined>): string | undefined {
  for (const candidate of candidates) {
    if (candidate && candidate.trim().length > 0) {
      return candidate.trim();
    }
  }
  return undefined;
}

function extractSummaryPayload(raw?: string): ParsedSummaryPayload | null {
  if (raw) {
    const summarySectionMatch = raw.match(/\*\*summary_long\*\*\s*:\s*([\s\S]+)/i);
    if (summarySectionMatch) {
      const remainder = summarySectionMatch[1];
      const nextSectionIndex = remainder.search(/\*\*[a-z_]+\*\*\s*:/i);
      const sectionBody = (nextSectionIndex >= 0 ? remainder.slice(0, nextSectionIndex) : remainder).trim();
      const cleanedSummary = sectionBody
        .replace(/^Here\s+is\s+the\s+summary[:：]?\s*/i, '')
        .trim();

      const diffMatch = raw.match(/\*\*diff_points\*\*\s*:\s*([\s\S]+)/i);
      let extractedDiffPoints: string[] | undefined;
      if (diffMatch) {
        const diffRemainder = diffMatch[1];
        const diffNextIndex = diffRemainder.search(/\*\*[a-z_]+\*\*\s*:/i);
        const diffSection = (diffNextIndex >= 0 ? diffRemainder.slice(0, diffNextIndex) : diffRemainder)
          .split(/\r?\n+/)
          .map((line) => line.replace(/^\s*[-*]\s*/, '').trim())
          .filter((line) => line.length > 0);
        if (diffSection.length > 0) {
          extractedDiffPoints = diffSection;
        }
      }

      if (cleanedSummary) {
        return {
          summaryLong: cleanedSummary,
          diffPoints: extractedDiffPoints,
        };
      }
    }
  }

  const parsed = parseStructuredJson(raw);
  if (parsed) {
    const summaryCandidates = [
      typeof parsed.summary === 'string' ? parsed.summary : undefined,
      typeof parsed.summary_long === 'string' ? parsed.summary_long : undefined,
      typeof parsed.summaryLong === 'string' ? parsed.summaryLong : undefined,
    ]
      .map((value) => value?.trim())
      .filter((value) => (value ?? '').length > 0);

    const diffPointsRaw = (parsed.diff_points ?? parsed.diffPoints) as unknown;
    const diffPoints = Array.isArray(diffPointsRaw)
      ? diffPointsRaw.map((point) => String(point).trim()).filter((point) => point.length > 0)
      : undefined;

    return {
      summaryLong: summaryCandidates[1] ?? summaryCandidates[0],
      diffPoints: diffPoints && diffPoints.length > 0 ? diffPoints : undefined,
    };
  }

  const summaryLongFallback =
    extractQuotedValue(raw, 'summary_long') ??
    extractQuotedValue(raw, 'summaryLong');

  const diffPointsFallback =
    extractArrayValue(raw, 'diff_points') ??
    extractArrayValue(raw, 'diffPoints');

  if (!summaryLongFallback && !diffPointsFallback) {
    return null;
  }

  return {
    summaryLong: summaryLongFallback ?? undefined,
    diffPoints: diffPointsFallback && diffPointsFallback.length > 0 ? diffPointsFallback : undefined,
  };
}

function normaliseClusterSummary(cluster: ClusterSummary): ClusterSummary {
  const detailStatus = (cluster.detailStatus ?? 'partial') as ClusterSummary['detailStatus'];
  const isReadyStatus = detailStatus === 'ready' || detailStatus === 'stale';
  const payload =
    extractSummaryPayload(cluster.summaryLong);
  const legacySummary = (cluster as { summary?: string }).summary;

  const extractJapaneseOrEmpty = (value: string | undefined): string | undefined => {
    if (!value) {
      return undefined;
    }
    const trimmed = value.trim();
    if (!trimmed) {
      return undefined;
    }
    const lines = trimmed.split(/\r?\n/).map((line) => line.trim()).filter((line) => line.length > 0);
    const japaneseLines = lines.filter((line) => JP_TEXT_RE.test(line));
    const candidate = japaneseLines.length > 0 ? japaneseLines.join('\n') : trimmed;
    return JP_TEXT_RE.test(candidate) ? candidate : undefined;
  };

  const cleanedStoredLong = firstNonEmpty(
    stripStructuredArtifacts(cluster.summaryLong)
  );
  const cleanedStoredShort = firstNonEmpty(
    extractQuotedValue(cluster.summaryLong, 'summary'),
    stripStructuredArtifacts(legacySummary)
  );

  const extractedSummaryLong = firstNonEmpty(payload?.summaryLong, payload?.summary);

  const resolvedSummaryLong = isReadyStatus
    ? extractJapaneseOrEmpty(
        firstNonEmpty(
          extractedSummaryLong,
          cleanedStoredLong,
          cleanedStoredShort,
          cluster.summaryLong,
          legacySummary
        )
      ) ?? ''
    : '';

  const diffPoints =
    payload?.diffPoints && payload.diffPoints.length > 0
      ? payload.diffPoints
      : cluster.diffPoints;

  return {
    ...cluster,
    detailStatus,
    summaryLong: resolvedSummaryLong,
    diffPoints,
  };
}

type Props = {
  clusters: ClusterSummary[];
};

export function ClusterDirectory({ clusters }: Props) {
  const normalisedClusters = useMemo(
    () => clusters.map((cluster) => normaliseClusterSummary(cluster)),
    [clusters]
  );
  const [viewMode, setViewMode] = useState<ViewMode>('today');
  const [activeClusterId, setActiveClusterId] = useState<string | null>(null);
  const [detailCache, setDetailCache] = useState<Record<string, ClusterSummary>>({});
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [errorClusterId, setErrorClusterId] = useState<string | null>(null);

  const baseClusterMap = useMemo(() => {
    const map = new Map<string, ClusterSummary>();
    normalisedClusters.forEach((cluster) => map.set(cluster.id, cluster));
    return map;
  }, [normalisedClusters]);

  const latestClusters = useMemo(() => {
    return [...normalisedClusters].sort(
      (a, b) => getRegistrationTimestamp(b) - getRegistrationTimestamp(a)
    );
  }, [normalisedClusters]);

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
    ? detailCache[activeClusterId] ?? baseClusterMap.get(activeClusterId) ?? null
    : null;

  const ensureDetailSummary = useCallback(
    async (cluster: ClusterSummary) => {
      const normalisedCluster = normaliseClusterSummary(cluster);
      const cached = detailCache[cluster.id];
      const previousSummary = (cached?.summaryLong ?? normalisedCluster.summaryLong ?? '').trim();
      const previousStatus = (cached?.detailStatus ?? normalisedCluster.detailStatus ?? 'partial') as ClusterSummary['detailStatus'];

      if (loadingId === cluster.id) {
        return;
      }

      setLoadingId(cluster.id);
      setErrorClusterId(null);

      setDetailCache((prev) => ({
        ...prev,
        [cluster.id]: normaliseClusterSummary({
          ...(prev[cluster.id] ?? normalisedCluster),
          detailStatus: 'pending',
          summaryLong: '',
        }),
      }));

      try {
        const ensureResponse = await fetch(`/api/cluster/${cluster.id}/detail`, {
          method: 'POST',
          cache: 'no-store',
        });

        if (!ensureResponse.ok && ensureResponse.status !== 202) {
          throw new Error(`Failed to initiate summary generation (${ensureResponse.status})`);
        }

        let attempts = 0;
        let detailCluster: ClusterSummary | null = null;
        let failedCluster: ClusterSummary | null = null;

        while (attempts < DETAIL_POLL_MAX_ATTEMPTS) {
          const detailResponse = await fetch(`/api/cluster/${cluster.id}/detail`, {
            method: 'GET',
            cache: 'no-store',
          });

          if (detailResponse.status === 404) {
            break;
          }

          if (detailResponse.ok) {
            const payload = (await detailResponse.json()) as unknown;

            const toDetailStatus = (
              value: unknown
            ): ClusterSummary['detailStatus'] | undefined => {
              if (typeof value !== 'string') {
                return undefined;
              }
              const lowered = value.toLowerCase();
              switch (lowered) {
                case 'ready':
                case 'stale':
                case 'pending':
                case 'failed':
                case 'partial':
                  return lowered as ClusterSummary['detailStatus'];
                default:
                  return undefined;
              }
            };

            let payloadStatus: ClusterSummary['detailStatus'] | undefined;
            let clusterPayload: ClusterSummary | null = null;

            if (payload && typeof payload === 'object') {
              const record = payload as Record<string, unknown>;
              payloadStatus =
                toDetailStatus(record.detailStatus) ??
                toDetailStatus(record.status);

              if (record.cluster && typeof record.cluster === 'object') {
                clusterPayload = record.cluster as ClusterSummary;
              } else if (record.data && typeof record.data === 'object') {
                clusterPayload = record.data as ClusterSummary;
              } else if ('id' in record && typeof record.id === 'string') {
                clusterPayload = payload as ClusterSummary;
              }
            }

            if (
              payloadStatus === 'failed' ||
              clusterPayload?.detailStatus === 'failed'
            ) {
              if (attempts === 0) {
                attempts += 1;
                await new Promise((resolve) => setTimeout(resolve, DETAIL_POLL_INTERVAL_MS));
                continue;
              }
              failedCluster = clusterPayload
                ? { ...clusterPayload, detailStatus: 'failed' }
                : {
                    ...(cached ?? normalisedCluster),
                    detailStatus: 'failed',
                  };
              break;
            }

            if (clusterPayload) {
              const derivedStatus =
                toDetailStatus(clusterPayload.detailStatus) ?? payloadStatus ?? null;
              const normalisedPayload = normaliseClusterSummary({
                ...clusterPayload,
                detailStatus: derivedStatus ?? clusterPayload.detailStatus,
              });

              const isReadyState =
                derivedStatus === 'ready' || derivedStatus === 'stale';
              const readySummary = normalisedPayload.summaryLong?.trim() ?? '';
              let candidateDetailCluster: ClusterSummary | null = null;

              setDetailCache((prev) => {
                const previous = prev[cluster.id] ?? normalisedCluster;
                const merged: ClusterSummary = {
                  ...previous,
                  ...normalisedPayload,
                  detailStatus: derivedStatus ?? previous.detailStatus,
                };

                if (isReadyState) {
                  const preferredSummary =
                    readySummary ||
                    (normalisedPayload.summaryLong ?? '').trim() ||
                    (previous.summaryLong ?? '').trim();
                  merged.summaryLong = preferredSummary;
                  candidateDetailCluster = merged;
                } else {
                  merged.summaryLong = previous.summaryLong;
                }

                return {
                  ...prev,
                  [cluster.id]: merged,
                };
              });

              setErrorClusterId(null);

              if (isReadyState) {
                const preferredSummary =
                  readySummary || (normalisedPayload.summaryLong ?? '').trim();
                const summaryUnchanged = preferredSummary === previousSummary;
                const previouslyReady = previousStatus === 'ready' || previousStatus === 'stale';
                if (previouslyReady && summaryUnchanged && attempts < DETAIL_POLL_MAX_ATTEMPTS - 1) {
                  attempts += 1;
                  await new Promise((resolve) => setTimeout(resolve, DETAIL_POLL_INTERVAL_MS));
                  continue;
                }
                detailCluster = candidateDetailCluster ?? normalisedPayload;
                break;
              }
            }
          }

          attempts += 1;
          if (attempts >= DETAIL_POLL_MAX_ATTEMPTS) {
            break;
          }
          await new Promise((resolve) => setTimeout(resolve, DETAIL_POLL_INTERVAL_MS));
        }

        if (failedCluster) {
          setDetailCache((prev) => ({
            ...prev,
            [cluster.id]: normaliseClusterSummary({
              ...failedCluster,
              summaryLong:
                (failedCluster.summaryLong ?? '').trim() ||
                (prev[cluster.id]?.summaryLong ?? normalisedCluster.summaryLong),
            }),
          }));
          setErrorClusterId(cluster.id);
          return;
        }

        if (!detailCluster) {
          console.warn(
            `Detailed summary for ${cluster.id} is still pending after ${DETAIL_POLL_MAX_ATTEMPTS} attempts.`
          );
          return;
        }

        setDetailCache((prev) => ({
          ...prev,
          [cluster.id]: normaliseClusterSummary(detailCluster as ClusterSummary),
        }));
        setErrorClusterId(null);
      } catch (error) {
        console.error('Failed to load detailed summary', error);
        setDetailCache((prev) => ({
          ...prev,
          [cluster.id]: normaliseClusterSummary({
            ...(prev[cluster.id] ?? normalisedCluster),
            detailStatus: 'failed',
          }),
        }));
        setErrorClusterId(cluster.id);
      } finally {
        setLoadingId(null);
      }
    },
    [detailCache, loadingId]
  );

  const handleOpenCluster = useCallback(
    (clusterId: string) => {
      setActiveClusterId(clusterId);
    },
    [setActiveClusterId]
  );

const renderClusterList = useCallback(
    (clusterList: ClusterSummary[], emptyMessage: string) => (
      <section className="rounded-xl border border-slate-800 bg-slate-900/40">
        <div className="border-b border-slate-800 px-4 py-3 text-xs text-slate-500">
          該当件数: {clusterList.length} 件
        </div>
        <ul className="max-h-[60vh] overflow-y-auto divide-y divide-slate-800">
          {clusterList.length === 0 && (
            <li className="px-4 py-6 text-sm text-slate-400">{emptyMessage}</li>
          )}
          {clusterList.map((cluster) => {
            const displayTitle = deriveDisplayTitle(cluster);
            const primarySource = cluster.sources[0];
            const siteName = primarySource?.name || '不明';
            const registeredIso = cluster.createdAt ?? cluster.detailRequestedAt ?? cluster.updatedAt;
            return (
              <li key={cluster.id}>
                <button
                  type="button"
                  onClick={() => handleOpenCluster(cluster.id)}
                  className="flex w-full items-start gap-3 overflow-hidden px-4 py-3 text-left text-sm text-slate-200 transition hover:bg-slate-800/60"
                >
                  <div className="min-w-0 flex-1 overflow-hidden">
                    <p className="text-xs text-slate-500">
                      {formatDisplayDate(registeredIso)} ・ {siteName}
                    </p>
                    <p className="mt-1 truncate font-semibold text-slate-100">{displayTitle}</p>
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      </section>
    ),
    [handleOpenCluster]
  );

  const renderSourceGroups = useCallback(
    (groups: SourceGroup[], emptyMessage: string) => (
      <section className="flex flex-col gap-4">
        {groups.map(({ id, label, url, clusters: grouped }) => (
          <div key={id} className="rounded-xl border border-slate-800 bg-slate-900/40">
            <header className="flex items-center justify-between gap-4 border-b border-slate-800 px-4 py-3 text-base text-slate-100">
              {(() => {
                const resolvedUrl = url || grouped[0]?.sources?.find((s) => s.id === id)?.url;
                if (resolvedUrl) {
                  return (
                    <a
                      href={resolvedUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="max-w-[70%] overflow-hidden truncate text-left font-semibold text-slate-100 underline decoration-sky-500 underline-offset-4"
                    >
                      {label}
                    </a>
                  );
                }
                return (
                  <span className="max-w-[70%] overflow-hidden truncate text-left font-semibold text-slate-100">
                    {label}
                  </span>
                );
              })()}
              <span className="text-xs text-slate-400">{grouped.length} 件</span>
            </header>
            <ul className="max-h-[50vh] overflow-y-auto divide-y divide-slate-800">
              {grouped.map((cluster) => {
                const displayTitle = deriveDisplayTitle(cluster);
                const registeredIso = cluster.createdAt ?? cluster.detailRequestedAt ?? cluster.updatedAt;
                return (
                  <li key={`${id}-${cluster.id}`}>
                    <button
                      type="button"
                      onClick={() => handleOpenCluster(cluster.id)}
                      className="flex w-full items-start gap-3 overflow-hidden px-4 py-3 text-left text-sm text-slate-200 transition hover:bg-slate-800/60"
                    >
                      <div className="min-w-0 flex-1 overflow-hidden">
                        <p className="text-xs text-slate-500">{formatDisplayDate(registeredIso)}</p>
                        <p className="mt-1 truncate font-semibold text-slate-100">{displayTitle}</p>
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
        {groups.length === 0 && (
          <p className="rounded-xl border border-slate-800 bg-slate-900/40 px-4 py-6 text-sm text-slate-400">
            {emptyMessage}
          </p>
        )}
      </section>
    ),
    [handleOpenCluster]
  );

  const getDetailState = useCallback(
    (cluster: ClusterSummary) => {
      const summary = (cluster.summaryLong ?? '').trim();
      const detailStatus = (cluster.detailStatus ?? 'partial') as ClusterSummary['detailStatus'];
      const isReadyStatus = detailStatus === 'ready' || detailStatus === 'stale';
      const hasSummaryContent = summary.length > 0;
      const hasSummary = hasSummaryContent && isReadyStatus;
      const isSummaryMissingAfterReady = isReadyStatus && !hasSummaryContent;
      const isReady = hasSummary;
      const isError = detailStatus === 'failed' || errorClusterId === cluster.id;
      const isGenerating = loadingId === cluster.id || detailStatus === 'pending';

      return {
        summary,
        detailStatus,
        hasSummary,
        isReady,
        isError,
        isGenerating,
        isSummaryMissingAfterReady,
      };
    },
    [errorClusterId, loadingId]
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
      <section className="rounded-xl border border-slate-800 bg-slate-900/40 p-3 text-sm">
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
                    : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
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
          className="fixed inset-0 z-50 flex items-start justify-center bg-slate-950/70 px-4 py-10 backdrop-blur-sm"
          onClick={() => setActiveClusterId(null)}
        >
          <article
            className="relative max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-xl border border-slate-800 bg-slate-900/90 p-6 text-sm text-slate-200 shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <button
              type="button"
              onClick={() => setActiveClusterId(null)}
              aria-label="閉じる"
              className="absolute right-4 top-4 rounded-full bg-slate-800 px-2 py-1 text-sm text-slate-300 transition hover:bg-slate-700"
            >
              ×
            </button>
            <header className="mb-4 flex flex-col gap-2">
              <h2 className="line-clamp-2 break-words text-xl font-semibold">{deriveDisplayTitle(activeCluster)}</h2>
              <time className="text-xs text-slate-500">
                {formatDisplayDate(activeCluster.createdAt ?? activeCluster.detailRequestedAt ?? activeCluster.updatedAt)}
              </time>
            </header>
            <section className="flex flex-col gap-6">
              {activeClusterDetailState && (
                <>
                  <div className="flex flex-wrap items-center gap-3">
                    <button
                      type="button"
                      onClick={() =>
                        ensureDetailSummary(activeCluster)
                      }
                      disabled={activeClusterDetailState.isGenerating}
                      className={`rounded-full px-4 py-2 text-sm transition ${
                        activeClusterDetailState.isGenerating
                          ? 'bg-slate-800 text-slate-400'
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
                            {activeClusterDetailState.isGenerating
                              ? '要約を生成中…'
                              : activeClusterDetailState.detailStatus === 'stale'
                                ? '要約を更新'
                                : activeClusterDetailState.hasSummary
                                  ? '要約を再生成'
                                  : '要約を生成'}
                          </span>
                        </span>
                      </button>
                  </div>
                  {activeClusterDetailState.isError ? (
                    <p className="text-sm text-rose-300">
                      要約の生成に失敗しました。時間をおいて再試行してください。
                    </p>
                  ) : (
                    <div className="flex flex-col gap-2">
                      {activeClusterDetailState.detailStatus === 'partial' && (
                        <p className="text-sm text-slate-400">
                          要約はまだ生成されていません。上のボタンから生成できます。
                        </p>
                      )}
                      {activeClusterDetailState.isSummaryMissingAfterReady &&
                        !activeClusterDetailState.isGenerating && (
                          <p className="text-sm text-rose-300">
                            要約を生成できませんでした。もう一度「要約を生成」を押してください。
                          </p>
                        )}
                      {activeClusterDetailState.detailStatus === 'stale' &&
                        !activeClusterDetailState.isGenerating && (
                          <p className="text-sm text-slate-400">
                            要約を再生成できます。上のボタンをクリックしてください。
                          </p>
                        )}
                      {activeClusterDetailState.hasSummary && (
                        <p className="break-words leading-relaxed text-slate-200 whitespace-pre-wrap">
                          {activeClusterDetailState.summary}
                        </p>
                      )}
                    </div>
                  )}
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
