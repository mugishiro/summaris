import { unstable_cache } from 'next/cache';

import { fetchClusterSummaries } from './api-client';

const CACHE_TAG = 'cluster-summaries';
const CACHE_KEY = ['cluster-summaries'];

export const getCachedClusterSummaries = unstable_cache(
  async () => fetchClusterSummaries(),
  CACHE_KEY,
  {
    revalidate: 120,
    tags: [CACHE_TAG],
  }
);

export { CACHE_TAG };
