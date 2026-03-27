import { NextRequest, NextResponse } from 'next/server';
import { exec } from 'child_process';
import { promisify } from 'util';
import { writeFile, unlink } from 'fs/promises';
import path from 'path';
import os from 'os';
import crypto from 'crypto';

const execAsync = promisify(exec);

const PROJECT_ROOT = path.resolve(process.cwd(), '..');
const PYTHON = path.join(PROJECT_ROOT, '.venv', 'bin', 'python3');

export async function POST(request: NextRequest) {
  let scriptPath = '';

  try {
    const body = await request.json();
    const { scraperId, url } = body;

    if (!scraperId || !url) {
      return NextResponse.json(
        { success: false, error: 'Missing scraperId or url' },
        { status: 400 }
      );
    }

    if (scraperId !== 'shopee') {
      return NextResponse.json(
        { success: false, error: `Unknown scraper: ${scraperId}` },
        { status: 400 }
      );
    }

    // Validate URL is a shopee.com.my URL
    if (!url.startsWith('https://shopee.com.my/')) {
      return NextResponse.json(
        { success: false, error: 'URL must be a shopee.com.my URL' },
        { status: 400 }
      );
    }

    // Write Python script to a temp file to avoid shell escaping issues
    const scriptId = crypto.randomBytes(8).toString('hex');
    scriptPath = path.join(os.tmpdir(), `bws_scrape_${scriptId}.py`);

    const safeUrl = url.replace(/'/g, "\\'");
    const script = [
      'import asyncio, json, sys',
      `sys.path.insert(0, '${PROJECT_ROOT}')`,
      'from services.shopee.scraper import scrape_shop_page',
      '',
      'async def main():',
      `    result = await scrape_shop_page('${safeUrl}', max_items=200)`,
      '    items = [',
      '        {',
      "            'title': item.title,",
      "            'price_display': item.price_display,",
      "            'sold_count': item.sold_count,",
      "            'rating': item.rating,",
      "            'shop_name': item.shop_name,",
      "            'product_url': item.product_url,",
      "            'image_url': item.image_url,",
      '        }',
      '        for item in result.items',
      '    ]',
      '    print(json.dumps({',
      "        'success': result.success,",
      "        'query': result.query,",
      "        'items': items,",
      "        'error': result.error,",
      '    }))',
      '',
      'asyncio.run(main())'
    ].join('\n');

    await writeFile(scriptPath, script, 'utf-8');

    const { stdout, stderr } = await execAsync(`${PYTHON} ${scriptPath}`, {
      timeout: 600_000, // 10 minute timeout (login may take time)
      cwd: PROJECT_ROOT,
      env: { ...process.env, PYTHONPATH: PROJECT_ROOT }
    });

    if (stderr && !stderr.includes('NotOpenSSLWarning')) {
      console.error('Scraper stderr:', stderr);
    }

    // Find the JSON line in stdout (skip any warnings/print statements)
    const lines = stdout.trim().split('\n');
    const jsonLine = lines.findLast((line) => line.startsWith('{'));

    if (!jsonLine) {
      return NextResponse.json(
        { success: false, error: 'No JSON output from scraper' },
        { status: 500 }
      );
    }

    const result = JSON.parse(jsonLine);
    return NextResponse.json(result);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : 'Scrape execution failed';
    return NextResponse.json(
      { success: false, error: message },
      { status: 500 }
    );
  } finally {
    // Clean up temp script
    if (scriptPath) {
      await unlink(scriptPath).catch(() => {});
    }
  }
}
