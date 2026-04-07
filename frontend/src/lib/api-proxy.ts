import { NextRequest, NextResponse } from 'next/server';

export const API_BASE = process.env.BWS_API_URL || 'http://localhost:8005';

type RouteContext = { params: Promise<Record<string, string>> };

interface ProxyOptions {
  errorMessage?: string;
  wrapSuccess?: boolean;
}

interface PostProxyOptions extends ProxyOptions {
  /** true = always forward body, 'optional' = forward only if content-type is JSON */
  forwardBody?: boolean | 'optional';
}

async function resolvePath(
  template: string,
  params: Promise<Record<string, string>>
): Promise<string> {
  const resolved = await params;
  return template.replace(/\{(\w+)\}/g, (_, key) => resolved[key] ?? '');
}

function errorJson(error: unknown, fallback: string) {
  const message = error instanceof Error ? error.message : fallback;
  return NextResponse.json({ success: false, error: message }, { status: 500 });
}

function notOkJson(data: Record<string, unknown>, status: number, fallback: string) {
  return NextResponse.json(
    { success: false, error: (data.detail as string) || fallback },
    { status }
  );
}

export function proxyGet(backendPath: string, opts: ProxyOptions = {}) {
  const { errorMessage = 'Request failed', wrapSuccess = false } = opts;

  return async function GET(
    _request: NextRequest,
    context?: RouteContext
  ) {
    try {
      const path =
        backendPath.includes('{') && context
          ? await resolvePath(backendPath, context.params)
          : backendPath;
      const res = await fetch(`${API_BASE}${path}`);
      const data = await res.json();

      if (!res.ok) return notOkJson(data, res.status, errorMessage);
      return NextResponse.json(wrapSuccess ? { success: true, data } : data);
    } catch (error) {
      return errorJson(error, errorMessage);
    }
  };
}

export function proxyPost(backendPath: string, opts: PostProxyOptions = {}) {
  const {
    errorMessage = 'Request failed',
    wrapSuccess = false,
    forwardBody = false,
  } = opts;

  return async function POST(
    request: NextRequest,
    context?: RouteContext
  ) {
    try {
      const path =
        backendPath.includes('{') && context
          ? await resolvePath(backendPath, context.params)
          : backendPath;

      let body: string | undefined;
      if (forwardBody === 'optional') {
        const ct = request.headers.get('content-type');
        if (ct?.includes('application/json')) {
          body = JSON.stringify(await request.json());
        }
      } else if (forwardBody) {
        body = JSON.stringify(await request.json());
      }

      const res = await fetch(`${API_BASE}${path}`, {
        method: 'POST',
        headers: body ? { 'Content-Type': 'application/json' } : {},
        body,
      });
      const data = await res.json();

      if (!res.ok) return notOkJson(data, res.status, errorMessage);
      return NextResponse.json(wrapSuccess ? { success: true, data } : data);
    } catch (error) {
      return errorJson(error, errorMessage);
    }
  };
}

export function proxyPut(backendPath: string, opts: ProxyOptions = {}) {
  const { errorMessage = 'Request failed' } = opts;

  return async function PUT(
    request: NextRequest,
    context?: RouteContext
  ) {
    try {
      const path =
        backendPath.includes('{') && context
          ? await resolvePath(backendPath, context.params)
          : backendPath;
      const body = JSON.stringify(await request.json());
      const res = await fetch(`${API_BASE}${path}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body,
      });
      const data = await res.json();

      if (!res.ok) return notOkJson(data, res.status, errorMessage);
      return NextResponse.json(data);
    } catch (error) {
      return errorJson(error, errorMessage);
    }
  };
}

export function proxyDelete(backendPath: string, opts: ProxyOptions = {}) {
  const { errorMessage = 'Request failed' } = opts;

  return async function DELETE(
    _request: NextRequest,
    context?: RouteContext
  ) {
    try {
      const path =
        backendPath.includes('{') && context
          ? await resolvePath(backendPath, context.params)
          : backendPath;
      const res = await fetch(`${API_BASE}${path}`, { method: 'DELETE' });
      const data = await res.json();

      if (!res.ok) return notOkJson(data, res.status, errorMessage);
      return NextResponse.json(data);
    } catch (error) {
      return errorJson(error, errorMessage);
    }
  };
}
