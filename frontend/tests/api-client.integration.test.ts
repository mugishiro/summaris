import { beforeAll, describe, expect, test } from 'vitest';

const API_URL =
  process.env.TEST_CONTENT_API_URL ??
  'https://4beowhel9h.execute-api.ap-northeast-1.amazonaws.com/dev/';

let fetchClusterSummariesStrict: typeof import('../lib/api-client').fetchClusterSummariesStrict;
let fetchClusterById: typeof import('../lib/api-client').fetchClusterById;

beforeAll(async () => {
  process.env.NEWS_API_BASE_URL = API_URL;
  process.env.NEXT_PUBLIC_API_BASE_URL = API_URL;
  const client = await import('../lib/api-client');
  fetchClusterSummariesStrict = client.fetchClusterSummariesStrict;
  fetchClusterById = client.fetchClusterById;
});

describe('api-client integration', () => {
  test('fetchClusterSummariesStrict returns clusters from API', async () => {
    const clusters = await fetchClusterSummariesStrict();
    expect(Array.isArray(clusters)).toBe(true);
    expect(clusters.length).toBeGreaterThan(0);
    for (const cluster of clusters) {
      expect(cluster.id).toMatch(/\w/);
      expect(cluster.sources.length).toBeGreaterThan(0);
      expect(cluster.summaryLong).toBeDefined();
      expect(cluster.detailStatus).toBeDefined();
    }
  }, 15000);

  test('fetchClusterById resolves a single cluster', async () => {
    const clusters = await fetchClusterSummariesStrict();
    const target = clusters[0];
    const detail = await fetchClusterById(target.id);
    expect(detail).not.toBeNull();
    expect(detail?.id).toBe(target.id);
    expect(detail?.summaryLong).toBeDefined();
  }, 15000);
});
