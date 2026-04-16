import { NextRequest, NextResponse } from 'next/server';
import { API_BASE } from '@/lib/api-proxy';

interface Context {
  readonly params: Promise<{ readonly name: string }>;
}

const VALID_TASK_NAME = /^[a-zA-Z0-9_-]+$/;

export async function POST(_request: NextRequest, context: Context) {
  try {
    const { name } = await context.params;
    if (!VALID_TASK_NAME.test(name)) {
      return NextResponse.json(
        { success: false, error: 'Invalid task name' },
        { status: 400 }
      );
    }
    const res = await fetch(
      `${API_BASE}/api/operations/tasks/${encodeURIComponent(name)}/restart`,
      { method: 'POST' }
    );
    const data = await res.json();
    if (!res.ok) {
      return NextResponse.json(
        {
          success: false,
          error: data.detail ?? 'Failed to restart task',
        },
        { status: res.status }
      );
    }
    return NextResponse.json(data);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : 'Failed to connect to API';
    return NextResponse.json(
      { success: false, error: message },
      { status: 500 }
    );
  }
}
