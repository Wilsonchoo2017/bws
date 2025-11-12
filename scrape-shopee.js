const { chromium } = require('playwright');

async function scrapeShopeePrice(url) {
  console.log('Launching browser...');

  const browser = await chromium.launch({
    headless: false, // Set to true for production, false to watch it work
    args: [
      '--disable-blink-features=AutomationControlled',
      '--disable-dev-shm-usage',
      '--no-sandbox',
    ]
  });

  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    viewport: { width: 1920, height: 1080 },
    locale: 'en-MY',
    timezoneId: 'Asia/Kuala_Lumpur',
  });

  // Remove automation indicators
  await context.addInitScript(() => {
    Object.defineProperty(navigator, 'webdriver', {
      get: () => false,
    });
  });

  const page = await context.newPage();

  try {
    console.log('Navigating to Shopee...');
    await page.goto(url, {
      waitUntil: 'domcontentloaded',
      timeout: 30000
    });

    // Wait a bit for anti-bot checks
    console.log('Waiting for page to load...');
    await page.waitForTimeout(3000);

    // Try multiple selectors (Shopee may use different ones)
    const priceSelectors = [
      '[class*="price"]',
      '[data-testid="price"]',
      '.pqTWkA', // Common Shopee class
      'div[class*="product-price"]',
      'span[class*="price"]',
    ];

    console.log('Looking for price...');

    // Take screenshot for debugging
    await page.screenshot({ path: 'shopee-debug.png', fullPage: true });
    console.log('Screenshot saved as shopee-debug.png');

    // Try to find price with various methods
    let priceText = null;

    // Method 1: Direct selector search
    for (const selector of priceSelectors) {
      try {
        await page.waitForSelector(selector, { timeout: 5000 });
        const elements = await page.$$(selector);
        for (const element of elements) {
          const text = await element.textContent();
          if (text && text.includes('RM')) {
            priceText = text.trim();
            console.log(`Found price with selector ${selector}: ${priceText}`);
            break;
          }
        }
        if (priceText) break;
      } catch (e) {
        // Try next selector
      }
    }

    // Method 2: Search all text content containing "RM"
    if (!priceText) {
      console.log('Trying alternative method - searching for RM in page...');
      priceText = await page.evaluate(() => {
        const walker = document.createTreeWalker(
          document.body,
          NodeFilter.SHOW_TEXT,
          null
        );

        let node;
        const prices = [];
        while (node = walker.nextNode()) {
          const text = node.textContent.trim();
          if (text.match(/RM\s*[\d,]+\.?\d*/)) {
            prices.push(text);
          }
        }
        return prices.length > 0 ? prices : null;
      });
    }

    // Method 3: Check page content
    const pageContent = await page.content();
    console.log('\nPage title:', await page.title());

    // Look for JSON data in page
    const jsonData = await page.evaluate(() => {
      const scripts = Array.from(document.querySelectorAll('script'));
      for (const script of scripts) {
        const content = script.textContent;
        if (content.includes('price') && content.includes('{')) {
          try {
            // Try to find JSON objects
            const matches = content.match(/\{[^}]*"price"[^}]*\}/g);
            if (matches) return matches;
          } catch (e) {}
        }
      }
      return null;
    });

    if (jsonData) {
      console.log('\nFound potential price in JSON:', jsonData);
    }

    console.log('\n=== RESULT ===');
    if (priceText) {
      console.log('Price found:', priceText);
    } else {
      console.log('Could not find price. Check shopee-debug.png for details.');
      console.log('The page might require additional interaction or have anti-bot measures.');
    }

    return priceText;

  } catch (error) {
    console.error('Error:', error.message);
    await page.screenshot({ path: 'shopee-error.png' });
    console.log('Error screenshot saved as shopee-error.png');
  } finally {
    await browser.close();
  }
}

// Run the scraper
const url = process.argv[2] || 'https://shopee.com.my/LEGO-Speed-Champions-77244-Mercedes-AMG-F1-W15-Race-Car-(267-Pieces)-i.77251500.29227244818';
scrapeShopeePrice(url);
