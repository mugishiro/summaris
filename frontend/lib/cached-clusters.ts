import { unstable_cache } from 'next/cache';

import { fetchClusterSummaries } from './api-client';
import { CLUSTER_SUMMARIES_TAG } from './cache-tags';

const CACHE_KEY = ['cluster-summaries'];

export const getCachedClusterSummaries = unstable_cache(
  async () => fetchClusterSummaries(),
  CACHE_KEY,
  {
    revalidate: 120,
    tags: [CLUSTER_SUMMARIES_TAG],
  }
);

export { CLUSTER_SUMMARIES_TAG as CACHE_TAG };
