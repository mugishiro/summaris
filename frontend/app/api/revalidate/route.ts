import { revalidatePath, revalidateTag } from 'next/cache';
import { NextRequest, NextResponse } from 'next/server';

type RevalidatePayload = {
  paths?: string[] | string;
  tags?: string[] | string;
  secret?: string;
};

const HEADER_TOKEN = 'x-revalidate-token';
const DEFAULT_PATH = '/';
const MAX_TARGETS = 20;
const RATE_LIMIT_MAX = 10;
const RATE_LIMIT_WINDOW_MS = 60_000;

type RateBucket = {
  count: number;
  resetAt: number;
};

const rateLimitBuckets = new Map<string, RateBucket>();

function normaliseToArray(value: RevalidatePayload['paths'] | RevalidatePayload['tags']): string[] {
  if (!value) {
    return [];
  }
  if (Array.isArray(value)) {
    return value
      .filter((entry): entry is string => typeof entry === 'string')
      .map((entry) => entry.trim())
      .filter((entry) => entry.length > 0);
  }
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed ? [trimmed] : [];
  }
  return [];
}

function getConfiguredSecret(): string | null {
  const secret = process.env.REVALIDATE_SECRET ?? '';
  return secret.length > 0 ? secret : null;
}

function isAuthorised(req: NextRequest, body: RevalidatePayload): boolean {
  const configuredSecret = getConfiguredSecret();

  // Allow bypass when no secret configured (e.g., local dev)
  if (!configuredSecret) {
    return true;
  }

  const headerSecret = req.headers.get(HEADER_TOKEN);
  if (headerSecret && headerSecret === configuredSecret) {
    return true;
  }

  if (body.secret && body.secret === configuredSecret) {
    return true;
  }

  const urlSecret = req.nextUrl.searchParams.get('secret');
  if (urlSecret && urlSecret === configuredSecret) {
    return true;
  }

  return false;
}

function normalisePath(path: string): string {
  return path.startsWith('/') ? path : `/${path}`;
}

function prepareTargets(payload: RevalidatePayload) {
  const paths = Array.from(new Set(normaliseToArray(payload.paths).map(normalisePath)));
  const tags = Array.from(new Set(normaliseToArray(payload.tags)));

  return { paths, tags };
}

function resolveClientKey(req: NextRequest) {
  const forwarded = req.headers.get('x-forwarded-for');
  if (forwarded) {
    return forwarded.split(',')[0]?.trim() || forwarded;
  }
  const realIp = req.headers.get('x-real-ip');
  if (realIp) {
    return realIp.trim();
  }
  return req.ip ?? 'unknown';
}

function checkRateLimit(key: string): boolean {
  const now = Date.now();
  const bucket = rateLimitBuckets.get(key);
  if (!bucket || bucket.resetAt <= now) {
    rateLimitBuckets.set(key, { count: 1, resetAt: now + RATE_LIMIT_WINDOW_MS });
    return true;
  }
  if (bucket.count >= RATE_LIMIT_MAX) {
    return false;
  }
  bucket.count += 1;
  return true;
}

export async function POST(req: NextRequest) {
  let payload: RevalidatePayload = {};

  if (req.headers.get('content-type')?.includes('application/json')) {
    try {
      payload = (await req.json()) as RevalidatePayload;
    } catch (error) {
      return NextResponse.json(
        { message: 'Invalid JSON payload', error: error instanceof Error ? error.message : String(error) },
        { status: 400 },
      );
    }
  }

  if (!isAuthorised(req, payload)) {
    return NextResponse.json({ message: 'Invalid revalidation token' }, { status: 401 });
  }

  const clientKey = resolveClientKey(req);
  if (!checkRateLimit(clientKey)) {
    console.warn('Revalidate rate-limit exceeded', { clientKey });
    return NextResponse.json({ message: 'Too many revalidation requests' }, { status: 429 });
  }

  const { paths, tags } = prepareTargets(payload);

  if (paths.length === 0 && tags.length === 0) {
    paths.push(DEFAULT_PATH);
  }

  if (paths.length + tags.length > MAX_TARGETS) {
    return NextResponse.json(
      { message: `Too many revalidation targets (max ${MAX_TARGETS})` },
      { status: 400 }
    );
  }

  const revalidatedPaths: string[] = [];
  const revalidatedTags: string[] = [];

  try {
    for (const path of paths) {
      revalidatePath(path);
      revalidatedPaths.push(path);
    }
    for (const tag of tags) {
      revalidateTag(tag);
      revalidatedTags.push(tag);
    }
    console.info('Revalidated targets', {
      paths: revalidatedPaths,
      tags: revalidatedTags,
      skippedPaths: paths.filter((path) => !revalidatedPaths.includes(path)),
      skippedTags: tags.filter((tag) => !revalidatedTags.includes(tag)),
    });
  } catch (error) {
    console.error('Failed to trigger revalidation', error);
    return NextResponse.json(
      { message: 'Failed to trigger revalidation', error: error instanceof Error ? error.message : String(error) },
      { status: 500 },
    );
  }

  return NextResponse.json(
    {
      revalidated: {
        paths: revalidatedPaths,
        tags: revalidatedTags,
      },
      skipped: {
        paths: paths.filter((path) => !revalidatedPaths.includes(path)),
        tags: tags.filter((tag) => !revalidatedTags.includes(tag)),
      },
    },
    { status: 200 },
  );
}

export const dynamic = 'force-dynamic';
