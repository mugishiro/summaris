import 'server-only';

import type { ClusterSummary } from './types';
import { fetchMockClusters } from './mock-data';
import {
  fetchDynamoClusters,
  isDynamoConfigured,
} from './dynamodb-clusters';
import {
  clusterDetailResponseSchema,
  clusterListResponseSchema,
  clusterSummarySchema,
  type ClusterSummarySchema,
} from './schemas';

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
        articleTitle: source.articleTitle ?? (typeof rest.headline === 'string' ? rest.headline : undefined),
        siteUrl: source.siteUrl ?? undefined,
      };
    }),
  };
}

export type DataSourceKind = 'api' | 'dynamodb';

export type DataSourceFailure = {
  source: DataSourceKind;
  message: string;
};

export class ClusterDataError extends Error {
  readonly failures: DataSourceFailure[];

  constructor(message: string, failures: DataSourceFailure[]) {
    super(message);
    this.name = 'ClusterDataError';
    this.failures = failures;
  }
}

const API_BASE_URL =
  process.env.NEWS_API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  '';

const CLUSTERS_ENDPOINT =
  process.env.NEWS_API_CLUSTERS_ENDPOINT ?? '/clusters';

const DEFAULT_REVALIDATE_SECONDS = 300;

function buildApiUrl(path: string): string {
  if (!API_BASE_URL) {
    throw new ClusterDataError('API base URL is not configured', [
      { source: 'api', message: 'API base URL is not configured' },
    ]);
  }
  const base = API_BASE_URL.endsWith('/')
    ? API_BASE_URL
    : `${API_BASE_URL}/`;
  const trimmedPath = path.startsWith('/')
    ? path.slice(1)
    : path;
  return `${base}${trimmedPath}`;
}

interface ClusterApiResponse {
  clusters: ClusterSummary[];
}

function normaliseError(error: unknown): Error {
  if (error instanceof Error) {
    return error;
  }

  if (typeof error === 'string') {
    return new Error(error);
  }

  try {
    return new Error(JSON.stringify(error));
  } catch {
    return new Error(String(error));
  }
}

function buildClusterDetailPath(id: string): string {
  const trimmed =
    CLUSTERS_ENDPOINT === '/'
      ? 'clusters'
      : CLUSTERS_ENDPOINT.replace(/^\//, '').replace(/\/+$/, '') || 'clusters';

  return `${trimmed}/${encodeURIComponent(id)}`;
}

async function requestClusters(
  init?: RequestInit & { next?: { revalidate?: number } }
): Promise<ClusterSummary[]> {
  if (!API_BASE_URL) {
    throw new ClusterDataError('API base URL is not configured', [
      { source: 'api', message: 'API base URL is not configured' },
    ]);
  }

  const url = buildApiUrl(CLUSTERS_ENDPOINT);

  const { headers: initHeaders, cache: initCache, ...otherInit } = init ?? {};
  const requestInit: RequestInit = {
    ...otherInit,
    headers: {
      Accept: 'application/json',
      ...(initHeaders ?? {}),
    },
    cache: initCache ?? 'no-store',
  };

  const requestInitRecord = requestInit as Record<string, unknown>;
  if ('next' in requestInitRecord) {
    delete requestInitRecord.next;
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
  const clusters = Array.isArray(payload)
    ? payload
    : payload.clusters ?? [];

  return clusters.map(mapSchemaCluster);
}

interface ClusterApiDetailResponse {
  cluster?: ClusterSummary | null;
  data?: ClusterSummary | null;
}

async function requestClusterDetail(
  id: string,
  init?: RequestInit & { next?: { revalidate?: number } }
): Promise<ClusterSummary | null> {
  if (!API_BASE_URL) {
    throw new ClusterDataError('API base URL is not configured', [
      { source: 'api', message: 'API base URL is not configured' },
    ]);
  }

  const detailPath = buildClusterDetailPath(id);
  const url = buildApiUrl(detailPath);

  const requestInit: RequestInit & { next?: { revalidate?: number } } = {
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

  if (Array.isArray((payload as ClusterApiResponse).clusters)) {
    const list = (payload as ClusterApiResponse).clusters;
    const match = list.find((cluster) => cluster.id === id);
    return match ? mapSchemaCluster(clusterSummarySchema.parse(match)) : null;
  }

  if ((payload as ClusterApiDetailResponse).cluster !== undefined) {
    const cluster = (payload as ClusterApiDetailResponse).cluster;
    return cluster ? mapSchemaCluster(clusterSummarySchema.parse(cluster)) : null;
  }

  if ((payload as ClusterApiDetailResponse).data !== undefined) {
    const cluster = (payload as ClusterApiDetailResponse).data;
    return cluster ? mapSchemaCluster(clusterSummarySchema.parse(cluster)) : null;
  }

  if ((payload as ClusterSummarySchema).id) {
    return mapSchemaCluster(clusterSummarySchema.parse(payload as ClusterSummarySchema));
  }

  return null;
}

async function requestClusterDetailFresh(id: string): Promise<ClusterSummary | null> {
  return requestClusterDetail(id, {
    cache: 'no-store',
  });
}

type FetchResult = {
  data: ClusterSummary[] | null;
  failures: DataSourceFailure[];
  attemptedSources: DataSourceKind[];
};

async function fetchFromConfiguredSources(): Promise<FetchResult> {
  const failures: DataSourceFailure[] = [];
  const dataSources: Array<{ source: DataSourceKind; loader: () => Promise<ClusterSummary[]> }> =
    [];

  if (API_BASE_URL) {
    dataSources.push({ source: 'api', loader: () => requestClusters() });
  }

  if (isDynamoConfigured()) {
    dataSources.push({
      source: 'dynamodb',
      loader: () => fetchDynamoClusters(),
    });
  }

  if (dataSources.length === 0) {
    return { data: null, failures, attemptedSources: [] };
  }

  const attemptedSources: DataSourceKind[] = [];

  for (let index = 0; index < dataSources.length; index += 1) {
    const { source, loader } = dataSources[index];
    attemptedSources.push(source);

    try {
      const clusters = await loader();
      if (clusters.length === 0 && index < dataSources.length - 1) {
        console.warn(
          `Data source "${source}" returned 0 clusters; trying next fallback.`
        );
        continue;
      }
      return { data: clusters, failures, attemptedSources };
    } catch (unknownError) {
      const error = normaliseError(unknownError);
      console.error(`Failed to fetch clusters via ${source}`, error);
      failures.push({
        source,
        message: error.message,
      });
    }
  }

  return { data: null, failures, attemptedSources };
}

export async function fetchClusterSummaries(): Promise<ClusterSummary[]> {
  const { data, failures, attemptedSources } =
    await fetchFromConfiguredSources();

  if (data) {
    return data;
  }

  if (attemptedSources.length > 0) {
    throw new ClusterDataError('クラスタデータの取得に失敗しました。', failures);
  }

  return fetchMockClusters();
}

export async function fetchClusterSummariesStrict(): Promise<ClusterSummary[]> {
  const { data, failures, attemptedSources } =
    await fetchFromConfiguredSources();

  if (data) {
    return data;
  }

  if (attemptedSources.length === 0) {
    throw new ClusterDataError('クラスタデータソースが構成されていません。', []);
  }

  throw new ClusterDataError('クラスタデータの取得に失敗しました。', failures);
}

export async function fetchClusterById(id: string): Promise<ClusterSummary | null> {
  const failures: DataSourceFailure[] = [];

  if (API_BASE_URL) {
    try {
      const cluster = await requestClusterDetail(id);
      if (cluster !== null) {
        return cluster;
      }
      return null;
    } catch (unknownError) {
      const error = normaliseError(unknownError);
      console.error(`Failed to load cluster ${id} via API`, error);
      failures.push({
        source: 'api',
        message: error.message,
      });
    }
  }

  if (isDynamoConfigured()) {
    try {
      const clusters = await fetchDynamoClusters();
      const match = clusters.find((cluster) => cluster.id === id);
      if (match) {
        return match;
      }
    } catch (unknownError) {
      const error = normaliseError(unknownError);
      console.error(`Failed to load cluster ${id} via DynamoDB`, error);
      failures.push({
        source: 'dynamodb',
        message: error.message,
      });
    }
  }

  const clusters = await fetchMockClusters();
  const match = clusters.find((cluster) => cluster.id === id) ?? null;

  if (!match && failures.length > 0) {
    throw new ClusterDataError('クラスタデータの取得に失敗しました。', failures);
  }

  return match;
}

export async function fetchClusterByIdFresh(id: string): Promise<ClusterSummary | null> {
  const failures: DataSourceFailure[] = [];

  if (API_BASE_URL) {
    try {
      const cluster = await requestClusterDetailFresh(id);
      if (cluster !== null) {
        return cluster;
      }
      return null;
    } catch (unknownError) {
      const error = normaliseError(unknownError);
      console.error(`Failed to load cluster ${id} via API (fresh)`, error);
      failures.push({
        source: 'api',
        message: error.message,
      });
    }
  }

  if (isDynamoConfigured()) {
    try {
      const clusters = await fetchDynamoClusters();
      const match = clusters.find((cluster) => cluster.id === id);
      if (match) {
        return match;
      }
    } catch (unknownError) {
      const error = normaliseError(unknownError);
      console.error(`Failed to load cluster ${id} via DynamoDB (fresh fallback)`, error);
      failures.push({
        source: 'dynamodb',
        message: error.message,
      });
    }
  }

  const clusters = await fetchMockClusters();
  const match = clusters.find((cluster) => cluster.id === id) ?? null;

  if (!match && failures.length > 0) {
    throw new ClusterDataError('クラスタデータの取得に失敗しました。', failures);
  }

  return match;
}
