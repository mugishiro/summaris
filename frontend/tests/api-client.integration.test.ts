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
      const status = cluster.detailStatus ?? 'partial';
      expect(['ready', 'stale', 'pending', 'partial', 'failed']).toContain(status);
      if (status === 'ready' || status === 'stale') {
        expect(typeof cluster.summaryLong).toBe('string');
        expect((cluster.summaryLong ?? '').trim().length).toBeGreaterThan(0);
      } else {
        expect(cluster.summaryLong === undefined || cluster.summaryLong === '').toBe(true);
      }
    }
  }, 15000);

  test('fetchClusterById resolves a single cluster', async () => {
    const clusters = await fetchClusterSummariesStrict();
    const target = clusters[0];
    const detail = await fetchClusterById(target.id);
    expect(detail).not.toBeNull();
    expect(detail?.id).toBe(target.id);
    const status = detail?.detailStatus ?? 'partial';
    if (status === 'ready' || status === 'stale') {
      expect(typeof detail?.summaryLong).toBe('string');
      expect((detail?.summaryLong ?? '').trim().length).toBeGreaterThan(0);
    } else {
      const summary = detail?.summaryLong;
      expect(summary === undefined || summary === '').toBe(true);
    }
  }, 15000);
});
