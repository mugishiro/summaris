import 'server-only';

import type { ClusterSummary } from './types';
import { fetchMockClusters } from './mock-data';
import {
  fetchDynamoClusters,
  isDynamoConfigured,
} from './dynamodb-clusters';
import {
  fetchClusterDetailFreshViaApi,
  fetchClusterDetailViaApi,
  fetchClustersViaApi,
  isApiConfigured,
} from './data-sources/api';
import {
  ClusterDataError,
  type DataSourceFailure,
  type DataSourceKind,
} from './errors';

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

type FetchResult = {
  data: ClusterSummary[] | null;
  failures: DataSourceFailure[];
  attemptedSources: DataSourceKind[];
};

async function fetchFromConfiguredSources(): Promise<FetchResult> {
  const failures: DataSourceFailure[] = [];
  const dataSources: Array<{ source: DataSourceKind; loader: () => Promise<ClusterSummary[]> }> =
    [];

  const dynamoAvailable = isDynamoConfigured();
  const apiAvailable = isApiConfigured();

  if (dynamoAvailable) {
    dataSources.push({
      source: 'dynamodb',
      loader: () => fetchDynamoClusters(),
    });
  }

  if (apiAvailable) {
    dataSources.push({ source: 'api', loader: () => fetchClustersViaApi() });
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

  if (isApiConfigured()) {
    try {
      const cluster = await fetchClusterDetailViaApi(id);
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

  if (isApiConfigured()) {
    try {
      const cluster = await fetchClusterDetailFreshViaApi(id);
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
