import 'server-only';

import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { DynamoDBDocumentClient, ScanCommand, type ScanCommandInput } from '@aws-sdk/lib-dynamodb';

import type { ClusterSummary } from './types';
import { getSourceMetadata } from './source-catalog';

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

const TABLE_NAME =
  process.env.NEWS_SUMMARY_TABLE_NAME ??
  process.env.SUMMARY_TABLE_NAME ??
  '';

const REGION =
  process.env.NEWS_AWS_REGION ??
  process.env.AWS_REGION ??
  'ap-northeast-1';

const RAW_LIMIT =
  process.env.NEWS_FRONTEND_CLUSTER_LIMIT ??
  process.env.NEXT_PUBLIC_NEWS_FRONTEND_CLUSTER_LIMIT ??
  '';

const PARSED_LIMIT = Number(RAW_LIMIT);
const MAX_RESULTS =
  Number.isFinite(PARSED_LIMIT) && PARSED_LIMIT > 0
    ? PARSED_LIMIT
    : Number.POSITIVE_INFINITY;
const IS_UNLIMITED = MAX_RESULTS === Number.POSITIVE_INFINITY;

let documentClient: DynamoDBDocumentClient | null = null;

function getClient(): DynamoDBDocumentClient {
  if (!documentClient) {
    if (!TABLE_NAME) {
      throw new Error('NEWS_SUMMARY_TABLE_NAME is not configured');
    }

    const client = new DynamoDBClient({
      region: REGION,
    });
    documentClient = DynamoDBDocumentClient.from(client, {
      marshallOptions: {
        removeUndefinedValues: true,
      },
    });
  }
  return documentClient;
}

type RawSummaries = {
  summary?: string;
  summary_long?: string;
  [legacyKey: string]: unknown;
};

type RawSummaryItem = {
  pk?: string;
  sk?: string;
  title?: string;
  link?: string;
  headline_translated?: string;
  detail_status?: string;
  detail_requested_at?: number | string;
  detail_ready_at?: number | string;
  detail_expires_at?: number | string;
  detail_failed_at?: number | string;
  detail_failure_reason?: string;
  created_at?: number;
  updated_at?: number;
  published_at?: string;
  summaries?: RawSummaries;
};

function normaliseId(value: string | undefined, prefix: string) {
  if (!value) {
    return '';
  }
  return value.startsWith(prefix) ? value.slice(prefix.length) : value;
}

function deriveSummaryLong(summaries: RawSummaries | undefined): string {
  if (!summaries) {
    return '';
  }
  const candidates = ['summary_long', 'summary'];
  for (const key of candidates) {
    const raw = summaries[key];
    if (typeof raw === 'string') {
      const trimmed = raw.trim();
      if (trimmed) {
        return trimmed;
      }
    }
  }
  return '';
}

function detectLanguages(summary: string | undefined): string[] | undefined {
  if (!summary) {
    return undefined;
  }
  const hasJapanese = /[\u3040-\u30ff\u4e00-\u9faf]/.test(summary);
  const hasLatin = /[A-Za-z]/.test(summary);
  const languages: string[] = [];

  if (hasJapanese) {
    languages.push('日本語');
  }
  if (hasLatin) {
    languages.push('英語');
  }

  return languages.length > 0 ? languages : undefined;
}

function deriveImportance(
  updatedAt: Date,
  summaryLong: string
): ClusterSummary['importance'] {
  const now = Date.now();
  const ageHours = (now - updatedAt.getTime()) / (1000 * 60 * 60);
  const fallbackSummary = summaryLong.includes('要約を生成できませんでした');

  if (fallbackSummary) {
    return 'low';
  }

  if (ageHours <= 6) {
    return 'high';
  }
  if (ageHours <= 24) {
    return 'medium';
  }

  return 'low';
}

function deriveTopics(sourceId: string): string[] {
  const metadata = getSourceMetadata(sourceId);
  return [...metadata.defaultTopics];
}

function normaliseEpochSeconds(value: unknown): number | undefined {
  if (value === null || value === undefined) {
    return undefined;
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed) {
      return undefined;
    }
    const parsed = Number(trimmed);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return undefined;
}

function formatEpochAsIso(value: unknown): string | undefined {
  const seconds = normaliseEpochSeconds(value);
  if (seconds === undefined || seconds <= 0) {
    return undefined;
  }
  return new Date(seconds * 1000).toISOString();
}

function cleanDetailStatus(
  rawStatus: string | undefined,
  expiresAtSeconds: number | undefined
): ClusterSummary['detailStatus'] | undefined {
  if (!rawStatus) {
    return undefined;
  }
  const status = rawStatus.trim().toLowerCase();
  if (!status) {
    return undefined;
  }
  if (status === 'ready') {
    if (
      typeof expiresAtSeconds === 'number' &&
      Number.isFinite(expiresAtSeconds) &&
      expiresAtSeconds > 0 &&
      expiresAtSeconds * 1000 <= Date.now()
    ) {
      return 'stale';
    }
    return 'ready';
  }
  if (status === 'pending' || status === 'partial' || status === 'failed') {
    return status;
  }
  return undefined;
}

function cleanOptionalText(value: unknown): string | undefined {
  if (value === null || value === undefined) {
    return undefined;
  }
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed.length > 0 ? trimmed : undefined;
  }
  const coerced = String(value).trim();
  return coerced.length > 0 ? coerced : undefined;
}

function marshallItem(raw: RawSummaryItem): ClusterSummary | null {
  const sourceId = normaliseId(raw.pk, 'SOURCE#');
  const itemId = normaliseId(raw.sk, 'ITEM#');
  if (!sourceId || !itemId) {
    return null;
  }

  const summaryLong = deriveSummaryLong(raw.summaries);
  const metadata = getSourceMetadata(sourceId);

  const createdAtSeconds = raw.created_at ?? 0;
  const createdAt = createdAtSeconds
    ? new Date(createdAtSeconds * 1000)
    : new Date();
  const updatedAtSeconds = raw.updated_at ?? raw.created_at ?? 0;
  const updatedAt = updatedAtSeconds
    ? new Date(updatedAtSeconds * 1000)
    : createdAt;
  const detailExpiresAtSeconds = normaliseEpochSeconds(raw.detail_expires_at);
  const detailStatus = cleanDetailStatus(raw.detail_status, detailExpiresAtSeconds);
  let publishedAt: string | undefined;
  if (raw.published_at) {
    const parsed = new Date(raw.published_at);
    if (!Number.isNaN(parsed.getTime())) {
      publishedAt = parsed.toISOString();
    }
  }
  const articleUrl = ensureStraitsTimesLink(raw.link ?? metadata.url ?? undefined);
  const siteUrl = metadata.url ?? undefined;
  const displayUrl = articleUrl ?? siteUrl;

  const isReady = detailStatus === 'ready' || detailStatus === 'stale';
  const summaryLongReady = summaryLong.trim();
  const resolvedSummaryLong = isReady ? summaryLongReady : '';

  return {
    id: itemId,
    headline: raw.title ?? '(タイトル不明)',
    headlineJa: raw.headline_translated ?? undefined,
    summaryLong: resolvedSummaryLong,
    createdAt: createdAt.toISOString(),
    updatedAt: updatedAt.toISOString(),
    publishedAt,
    detailStatus,
    detailRequestedAt: formatEpochAsIso(raw.detail_requested_at),
    detailReadyAt: formatEpochAsIso(raw.detail_ready_at),
    detailExpiresAt: formatEpochAsIso(raw.detail_expires_at),
    detailFailedAt: formatEpochAsIso(raw.detail_failed_at),
    detailFailureReason: cleanOptionalText(raw.detail_failure_reason),
    importance: deriveImportance(updatedAt, resolvedSummaryLong),
    topics: deriveTopics(sourceId),
    languages: detectLanguages(resolvedSummaryLong),
    sources: [
      {
        id: metadata.id,
        name: metadata.name,
        url: displayUrl,
        articleUrl,
        articleTitle: raw.title ?? undefined,
        siteUrl,
      },
    ],
  };
}

export async function fetchDynamoClusters(): Promise<ClusterSummary[]> {
  if (!TABLE_NAME) {
    throw new Error('NEWS_SUMMARY_TABLE_NAME is not configured');
  }

  const client = getClient();
  const items: ClusterSummary[] = [];
  let lastEvaluatedKey: Record<string, unknown> | undefined;

  do {
    const remaining = MAX_RESULTS - items.length;
    if (!IS_UNLIMITED && remaining <= 0) {
      break;
    }

    const commandInput: ScanCommandInput = {
      TableName: TABLE_NAME,
    };
    if (lastEvaluatedKey) {
      commandInput.ExclusiveStartKey = lastEvaluatedKey;
    }

    if (!IS_UNLIMITED) {
      commandInput.Limit = Math.min(50, remaining);
    }

    const response = await client.send(new ScanCommand(commandInput));

    const records = response.Items as RawSummaryItem[] | undefined;
    if (records) {
      for (const record of records) {
        const cluster = marshallItem(record);
        if (cluster) {
          items.push(cluster);
        }
        if (!IS_UNLIMITED && items.length >= MAX_RESULTS) {
          break;
        }
      }
    }

    lastEvaluatedKey = response.LastEvaluatedKey;
  } while (lastEvaluatedKey && (IS_UNLIMITED || items.length < MAX_RESULTS));

  return items.sort(
    (a, b) =>
      new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
  );
}

export function isDynamoConfigured(): boolean {
  return Boolean(TABLE_NAME);
}
