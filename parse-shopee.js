const fs = require('fs');
const path = require('path');

function parseShopeeHTML(htmlContent) {
  const products = [];

  // Split by product items - each product is in a shop-search-result-view__item div
  const itemRegex = /<div class="shop-search-result-view__item[^>]*>[\s\S]*?<\/a><\/div><\/div><\/div><\/div>/g;
  const items = htmlContent.match(itemRegex) || [];

  console.log(`Found ${items.length} product items`);

  items.forEach((item, index) => {
    try {
      // Extract product name - look for LEGO and 5-digit code
      let productName = null;

      // Method 1: Find text with "LEGO" and extract full product name
      const legoMatch = item.match(/>(LEGO[^<]*\d{5}[^<]*)</);
      if (legoMatch) {
        productName = legoMatch[1].trim();
      }

      // Fallback: Look for line-clamp-2 div content
      if (!productName) {
        const nameMatch = item.match(/class="line-clamp-2[^>]*>[\s\S]*?<img[^>]*>([^<]*)</);
        if (nameMatch) {
          productName = nameMatch[1].trim();
        }
      }

      // Extract price - find RM followed by numbers
      let price = null;
      const priceMatches = item.match(/RM<\/span><span[^>]*>([0-9,.]+)</);
      if (priceMatches) {
        price = priceMatches[1].replace(',', '');
      }

      // Fallback: Look for any price pattern
      if (!price) {
        const altPriceMatch = item.match(/RM\s*([0-9,.]+)/);
        if (altPriceMatch) {
          price = altPriceMatch[1].replace(',', '');
        }
      }

      // Extract sold units - find number followed by "sold"
      let soldUnits = null;
      const soldMatch = item.match(/>([0-9kK.+,]+)\s*sold</);
      if (soldMatch) {
        soldUnits = soldMatch[1].trim();
      }

      // Only add if we found at least a product name
      if (productName) {
        products.push({
          productName,
          price: price || 'N/A',
          soldUnits: soldUnits || 'N/A'
        });

        console.log(`Product ${index + 1}: ${productName} | RM${price} | ${soldUnits} sold`);
      }

    } catch (error) {
      console.error(`Error parsing item ${index + 1}:`, error.message);
    }
  });

  return products;
}

function parseAllFiles() {
  const files = fs.readdirSync(__dirname)
    .filter(f => f.startsWith('shop-listing-') && f.endsWith('.txt'));

  console.log(`Found ${files.length} shop listing files\n`);

  let allProducts = [];

  files.forEach(file => {
    console.log(`\nParsing ${file}...`);
    const content = fs.readFileSync(path.join(__dirname, file), 'utf-8');
    const products = parseShopeeHTML(content);
    allProducts = allProducts.concat(products);
  });

  return allProducts;
}

function exportToCSV(products, filename = 'shopee-products.csv') {
  const headers = 'Product Name,Price (RM),Units Sold\n';
  const rows = products.map(p =>
    `"${p.productName}",${p.price},"${p.soldUnits}"`
  ).join('\n');

  fs.writeFileSync(filename, headers + rows);
  console.log(`\n✓ Exported ${products.length} products to ${filename}`);
}

// Main execution
console.log('=== Shopee Product Parser ===\n');
const products = parseAllFiles();

console.log(`\n=== Summary ===`);
console.log(`Total products extracted: ${products.length}`);

if (products.length > 0) {
  exportToCSV(products);

  // Show sample
  console.log(`\nFirst 3 products:`);
  products.slice(0, 3).forEach((p, i) => {
    console.log(`${i + 1}. ${p.productName}`);
    console.log(`   Price: RM${p.price} | Sold: ${p.soldUnits}`);
  });
}
