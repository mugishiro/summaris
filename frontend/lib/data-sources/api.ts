import type { ClusterSummary } from '../types';
import { CLUSTER_SUMMARIES_TAG } from '../cache-tags';
import {
  clusterDetailResponseSchema,
  clusterListResponseSchema,
  clusterSummarySchema,
  type ClusterSummarySchema,
} from '../schemas';
import { ClusterDataError } from '../errors';

const API_BASE_URL =
  process.env.NEWS_API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  '';

const CLUSTERS_ENDPOINT =
  process.env.NEWS_API_CLUSTERS_ENDPOINT ?? '/clusters';

const DEFAULT_REVALIDATE_SECONDS = 300;

function ensureStraitsTimesLink(url?: string | null): string | undefined {
  if (!url) {
    return undefined;
  }
  try {
    const parsed = new URL(url);
    if (!parsed.hostname.toLowerCase().endsWith('straitstimes.com')) {
      return url;
    }
    let updated = false;
    if (!parsed.searchParams.has('utm_source')) {
      parsed.searchParams.set('utm_source', 'rss');
      updated = true;
    }
    if (!parsed.searchParams.has('utm_medium')) {
      parsed.searchParams.set('utm_medium', 'referral');
      updated = true;
    }
    return updated ? parsed.toString() : url;
  } catch {
    return url;
  }
}

function mapSchemaCluster(cluster: ClusterSummarySchema): ClusterSummary {
  const {
    summaryLong,
    headlineJa,
    factCheckStatus,
    languages,
    detailStatus,
    detailRequestedAt,
    detailReadyAt,
    detailExpiresAt,
    detailFailedAt,
    detailFailureReason,
    sources,
    createdAt,
    updatedAt,
    ...rest
  } = cluster;

  const normalisedSummaryLong =
    typeof summaryLong === 'string' && summaryLong.trim().length > 0
      ? summaryLong
      : undefined;

  const resolvedCreatedAt = createdAt ?? updatedAt ?? new Date().toISOString();
  const resolvedUpdatedAt = updatedAt ?? resolvedCreatedAt;

  return {
    ...rest,
    summaryLong: normalisedSummaryLong,
    headlineJa: headlineJa ?? undefined,
    factCheckStatus: factCheckStatus ?? undefined,
    languages: languages ?? undefined,
    detailStatus: detailStatus ?? undefined,
    detailRequestedAt: detailRequestedAt ?? undefined,
    detailReadyAt: detailReadyAt ?? undefined,
    detailExpiresAt: detailExpiresAt ?? undefined,
    detailFailedAt: detailFailedAt ?? undefined,
    detailFailureReason: detailFailureReason ?? undefined,
    createdAt: resolvedCreatedAt,
    updatedAt: resolvedUpdatedAt,
    sources: sources.map((source) => {
      const resolvedArticleUrl =
        ensureStraitsTimesLink(source.articleUrl ?? source.url ?? undefined) ??
        undefined;
      const resolvedUrl = resolvedArticleUrl ?? source.url ?? undefined;
      return {
        ...source,
        url: resolvedUrl,
        articleUrl: resolvedArticleUrl,
        articleTitle:
          source.articleTitle ?? (typeof rest.headline === 'string' ? rest.headline : undefined),
        siteUrl: source.siteUrl ?? undefined,
      };
    }),
  };
}

function buildApiUrl(path: string): string {
  if (!API_BASE_URL) {
    throw new ClusterDataError('API base URL is not configured', [
      { source: 'api', message: 'API base URL is not configured' },
    ]);
  }
  const base = API_BASE_URL.endsWith('/') ? API_BASE_URL : `${API_BASE_URL}/`;
  const trimmedPath = path.startsWith('/') ? path.slice(1) : path;
  return `${base}${trimmedPath}`;
}

type NextFetchInit = RequestInit & { next?: { revalidate?: number } };

export function isApiConfigured(): boolean {
  return Boolean(API_BASE_URL);
}

export async function fetchClustersViaApi(
  init?: NextFetchInit
): Promise<ClusterSummary[]> {
  if (!API_BASE_URL) {
    throw new ClusterDataError('API base URL is not configured', [
      { source: 'api', message: 'API base URL is not configured' },
    ]);
  }

  const url = buildApiUrl(CLUSTERS_ENDPOINT);

  const { headers: initHeaders, cache: initCache, ...otherInit } = init ?? {};
  const requestInit: NextFetchInit = {
    ...otherInit,
    headers: {
      Accept: 'application/json',
      ...(initHeaders ?? {}),
    },
    cache: initCache ?? 'default',
  };
  if (requestInit.cache === 'no-store') {
    if (requestInit.next) {
      delete requestInit.next;
    }
  } else {
    const existingTags = Array.isArray(requestInit.next?.tags)
      ? (requestInit.next!.tags as string[])
      : [];
    const mergedTags = existingTags.includes(CLUSTER_SUMMARIES_TAG)
      ? existingTags
      : [...existingTags, CLUSTER_SUMMARIES_TAG];
    requestInit.next = {
      ...(requestInit.next ?? {}),
      revalidate: requestInit.next?.revalidate ?? DEFAULT_REVALIDATE_SECONDS,
      tags: mergedTags,
    };
  }

  const response = await fetch(url, requestInit);

  if (!response.ok) {
    throw new Error(
      `Failed to fetch clusters: ${response.status} ${response.statusText}`
    );
  }

  const raw = await response.json();
  const parsed = clusterListResponseSchema.safeParse(raw);
  if (!parsed.success) {
    throw new ClusterDataError('クラスタ一覧レスポンスの検証に失敗しました。', [
      {
        source: 'api',
        message: parsed.error.message,
      },
    ]);
  }

  const payload = parsed.data;
  const clusters = Array.isArray(payload) ? payload : payload.clusters ?? [];

  return clusters.map(mapSchemaCluster);
}

export async function fetchClusterDetailViaApi(
  id: string,
  init?: NextFetchInit
): Promise<ClusterSummary | null> {
  if (!API_BASE_URL) {
    throw new ClusterDataError('API base URL is not configured', [
      { source: 'api', message: 'API base URL is not configured' },
    ]);
  }

  const trimmed =
    CLUSTERS_ENDPOINT === '/'
      ? 'clusters'
      : CLUSTERS_ENDPOINT.replace(/^\//, '').replace(/\/+$/, '') || 'clusters';

  const detailPath = `${trimmed}/${encodeURIComponent(id)}`;
  const url = buildApiUrl(detailPath);

  const requestInit: NextFetchInit = {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(init?.headers ?? {}),
    },
  };

  const isNoStore = requestInit.cache === 'no-store';

  if (!requestInit.next && !isNoStore) {
    requestInit.next = { revalidate: DEFAULT_REVALIDATE_SECONDS };
  }
  if (!requestInit.cache) {
    requestInit.cache = 'default';
  } else if (isNoStore && requestInit.next) {
    delete requestInit.next;
  }

  const response = await fetch(url, requestInit);

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    throw new Error(
      `Failed to fetch cluster ${id}: ${response.status} ${response.statusText}`
    );
  }

  if (response.status === 204) {
    return null;
  }

  const raw = await response.json();
  if (raw == null) {
    return null;
  }

  const parsed = clusterDetailResponseSchema.safeParse(raw);
  if (!parsed.success) {
    throw new ClusterDataError('クラスタ詳細レスポンスの検証に失敗しました。', [
      {
        source: 'api',
        message: parsed.error.message,
      },
    ]);
  }

  const payload = parsed.data;

  if (Array.isArray((payload as { clusters?: ClusterSummary[] }).clusters)) {
    const list = (payload as { clusters?: ClusterSummary[] }).clusters ?? [];
    const match = list.find((cluster) => cluster.id === id);
    return match ? mapSchemaCluster(clusterSummarySchema.parse(match)) : null;
  }

  if ((payload as { cluster?: ClusterSummary | null }).cluster !== undefined) {
    const cluster = (payload as { cluster?: ClusterSummary | null }).cluster;
    return cluster ? mapSchemaCluster(clusterSummarySchema.parse(cluster)) : null;
  }

  if ((payload as { data?: ClusterSummary | null }).data !== undefined) {
    const cluster = (payload as { data?: ClusterSummary | null }).data;
    return cluster ? mapSchemaCluster(clusterSummarySchema.parse(cluster)) : null;
  }

  if ((payload as ClusterSummarySchema).id) {
    return mapSchemaCluster(clusterSummarySchema.parse(payload as ClusterSummarySchema));
  }

  return null;
}

export async function fetchClusterDetailFreshViaApi(
  id: string
): Promise<ClusterSummary | null> {
  return fetchClusterDetailViaApi(id, {
    cache: 'no-store',
  });
}
