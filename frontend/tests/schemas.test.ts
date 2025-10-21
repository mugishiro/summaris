import { describe, expect, test } from 'vitest';

import { clusterDetailResponseSchema, clusterListResponseSchema } from '../lib/schemas';

describe('cluster schemas', () => {
  test('parses a valid list response', () => {
    const sample = {
      clusters: [
        {
          id: 'sample',
          headline: 'Sample Headline',
          headlineJa: 'サンプル見出し',
          summary: 'Sample summary text',
          summaryLong: 'Longer sample summary for verification',
          updatedAt: '2025-10-17T00:00:00Z',
          importance: 'high',
          diffPoints: ['point'],
          topics: ['topic'],
          detailStatus: 'ready',
          factCheckStatus: 'pending',
          languages: ['日本語'],
          sources: [
            {
              id: 'source-1',
              name: 'Source Name',
              url: 'https://example.com',
            },
          ],
        },
      ],
    };

    const parsed = clusterListResponseSchema.parse(sample);
    expect(parsed).toBeDefined();
  });

  test('rejects invalid cluster', () => {
    const invalid = {
      clusters: [
        {
          id: '',
          headline: 'Missing ID',
        },
      ],
    };

    expect(() => clusterListResponseSchema.parse(invalid)).toThrowError();
  });

  test('parses detail wrapper response', () => {
    const sample = {
      cluster: {
        id: 'detail',
        headline: 'Detail Headline',
        summary: 'Detail summary',
        updatedAt: '2025-10-17T00:00:00Z',
        importance: 'medium',
        diffPoints: [],
        topics: [],
        sources: [
          {
            id: 'source-1',
            name: 'Source Name',
          },
        ],
      },
    };

    const parsed = clusterDetailResponseSchema.parse(sample);
    expect(parsed).toBeDefined();
  });
});
