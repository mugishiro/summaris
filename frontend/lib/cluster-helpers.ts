import type { ClusterSummary } from './types';

const JSON_FENCE_RE = /```(?:json)?\s*({[\s\S]*?})\s*```/i;
const QUOTED_VALUE_RE = (key: string) =>
  new RegExp(`"${key}"\\s*:\\s*"([^"\\\\]*(?:\\\\.[^"\\\\]*)*)"`, 'i');
const ARRAY_VALUE_RE = (key: string) => new RegExp(`"${key}"\\s*:\\s*\\[(.*?)\\]`, 'is');
const JP_TEXT_RE = /[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]/;

type ParsedSummaryPayload = {
  summary?: string;
  summaryLong?: string;
  diffPoints?: string[];
};

export type SourceGroup = {
  id: string;
  label: string;
  url?: string;
  clusters: ClusterSummary[];
};

function containsJapanese(text: string): boolean {
  return /[\u3040-\u30ff\u4e00-\u9faf]/.test(text);
}

export function deriveDisplayTitle(cluster: ClusterSummary): string {
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

export function formatDisplayDate(timestamp?: string): string {
  if (!timestamp) {
    return '';
  }
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return timestamp;
  }
  return date.toLocaleString('ja-JP', { hour12: false });
}

export function toTimestamp(value?: string): number {
  if (!value) {
    return 0;
  }
  const parsed = new Date(value).getTime();
  return Number.isNaN(parsed) ? 0 : parsed;
}

export function getRegistrationTimestamp(cluster: ClusterSummary): number {
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

export function detailStatusPriority(
  status: ClusterSummary['detailStatus'] | undefined
): number {
  switch (status) {
    case 'ready':
      return 4;
    case 'stale':
      return 3;
    case 'failed':
      return 2;
    case 'pending':
      return 1;
    case 'partial':
    default:
      return 0;
  }
}

function groupClustersBySourceInternal(clusters: ClusterSummary[]): SourceGroup[] {
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

  return Array.from(map.values()).map((group) => ({
    ...group,
    url:
      group.url ??
      group.clusters[0]?.sources.find((s) => s.id === group.id)?.siteUrl ??
      group.clusters[0]?.sources.find((s) => s.id === group.id)?.url,
  }));
}

export function groupClustersBySource(clusters: ClusterSummary[]): SourceGroup[] {
  return groupClustersBySourceInternal(clusters).sort((a, b) =>
    a.label.localeCompare(b.label, 'ja')
  );
}

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
  const items = content
    .split(/,(?![^[]*\])/)
    .map((item) =>
      decodeJsonLikeString(item.replace(/^\s*["']?/, '').replace(/["']?\s*$/, ''))
    );
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
    extractQuotedValue(raw, 'summary_long') ?? extractQuotedValue(raw, 'summaryLong');

  const diffPointsFallback =
    extractArrayValue(raw, 'diff_points') ?? extractArrayValue(raw, 'diffPoints');

  if (!summaryLongFallback && !diffPointsFallback) {
    return null;
  }

  return {
    summaryLong: summaryLongFallback ?? undefined,
    diffPoints:
      diffPointsFallback && diffPointsFallback.length > 0 ? diffPointsFallback : undefined,
  };
}

const KNOWN_DETAIL_STATUSES: ReadonlyArray<NonNullable<ClusterSummary['detailStatus']>> = [
  'ready',
  'stale',
  'pending',
  'failed',
  'partial',
];

function normaliseDetailStatus(value?: string | null): ClusterSummary['detailStatus'] {
  if (!value) {
    return 'partial';
  }
  const trimmed = value.trim().toLowerCase();
  return KNOWN_DETAIL_STATUSES.includes(trimmed as NonNullable<ClusterSummary['detailStatus']>)
    ? (trimmed as ClusterSummary['detailStatus'])
    : 'partial';
}

export function normaliseClusterSummary(cluster: ClusterSummary): ClusterSummary {
  const rawStatus = typeof cluster.detailStatus === 'string' ? cluster.detailStatus.trim().toLowerCase() : undefined;
  const detailStatus = normaliseDetailStatus(rawStatus);
  const isReadyStatus = detailStatus === 'ready' || detailStatus === 'stale';
  const payload = extractSummaryPayload(cluster.summaryLong);
  const legacySummary = (cluster as { summary?: string }).summary;

  const extractJapaneseOrEmpty = (value: string | undefined): string | undefined => {
    if (!value) {
      return undefined;
    }
    const trimmed = value.trim();
    if (!trimmed) {
      return undefined;
    }
    const lines = trimmed
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => line.length > 0);
    const japaneseLines = lines.filter((line) => JP_TEXT_RE.test(line));
    if (japaneseLines.length > 0) {
      return japaneseLines.join('\n');
    }
    return trimmed;
  };

  const cleanedStoredLong = firstNonEmpty(stripStructuredArtifacts(cluster.summaryLong));
  const cleanedStoredShort = firstNonEmpty(
    extractQuotedValue(cluster.summaryLong, 'summary'),
    stripStructuredArtifacts(legacySummary)
  );

  const extractedSummaryLong = firstNonEmpty(payload?.summaryLong, payload?.summary);

  const resolvedSummaryLong =
    isReadyStatus
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

  const fallbackFailure =
    resolvedSummaryLong.includes('要約を生成できませんでした') ||
    resolvedSummaryLong.includes('要約は生成されていません');

  const effectiveDetailStatus = fallbackFailure ? 'failed' : detailStatus;
  const effectiveSummary = fallbackFailure ? '' : resolvedSummaryLong;

  const diffPoints =
    payload?.diffPoints && payload.diffPoints.length > 0 ? payload.diffPoints : cluster.diffPoints;

  return {
    ...cluster,
    detailStatus: effectiveDetailStatus,
    summaryLong: effectiveSummary,
    diffPoints,
  };
}
