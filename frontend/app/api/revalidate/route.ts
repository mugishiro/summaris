import { revalidatePath, revalidateTag } from 'next/cache';
import { NextRequest, NextResponse } from 'next/server';

type RevalidatePayload = {
  paths?: string[] | string;
  tags?: string[] | string;
  secret?: string;
};

const HEADER_TOKEN = 'x-revalidate-token';
const DEFAULT_PATH = '/';

function normaliseToArray<T extends string>(value: T | T[] | undefined): T[] {
  if (!value) return [];
  return Array.isArray(value) ? value : [value];
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

function prepareTargets(payload: RevalidatePayload) {
  const paths = normaliseToArray(payload.paths);
  const tags = normaliseToArray(payload.tags);

  return {
    paths: paths.map((path) => (path.startsWith('/') ? path : `/${path}`)),
    tags,
  };
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

  const { paths, tags } = prepareTargets(payload);

  if (paths.length === 0 && tags.length === 0) {
    paths.push(DEFAULT_PATH);
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
  } catch (error) {
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
