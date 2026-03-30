import { type NextRequest, NextResponse } from 'next/server';

const API_BASE = process.env.BWS_API_URL || 'http://localhost:8005';

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ txnId: string }> }
) {
  try {
    const { txnId } = await params;
    const res = await fetch(
      `${API_BASE}/api/portfolio/transactions/${txnId}`
    );
    const data = await res.json();

    if (!res.ok) {
      return NextResponse.json(
        { success: false, error: data.detail || 'Transaction not found' },
        { status: res.status }
      );
    }

    return NextResponse.json(data);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : 'Failed to fetch transaction';
    return NextResponse.json(
      { success: false, error: message },
      { status: 500 }
    );
  }
}

export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ txnId: string }> }
) {
  try {
    const { txnId } = await params;
    const res = await fetch(
      `${API_BASE}/api/portfolio/transactions/${txnId}`,
      { method: 'DELETE' }
    );
    const data = await res.json();

    if (!res.ok) {
      return NextResponse.json(
        { success: false, error: data.detail || 'Failed to delete' },
        { status: res.status }
      );
    }

    return NextResponse.json(data);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : 'Failed to delete transaction';
    return NextResponse.json(
      { success: false, error: message },
      { status: 500 }
    );
  }
}
