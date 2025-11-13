import { Head } from "$fresh/runtime.ts";
import QueueDiagnosticsDashboard from "../islands/QueueDiagnosticsDashboard.tsx";

export default function QueuePage() {
  return (
    <>
      <Head>
        <title>Queue Diagnostics - LEGO Price Tracker</title>
      </Head>
      <div class="min-h-screen bg-base-200 p-4 lg:p-8">
        <div class="max-w-7xl mx-auto">
          {/* Header */}
          <div class="mb-6">
            <div class="text-sm breadcrumbs">
              <ul>
                <li>
                  <a href="/">Home</a>
                </li>
                <li>Queue Diagnostics</li>
              </ul>
            </div>
            <h1 class="text-3xl lg:text-4xl font-bold text-base-content mt-2">
              Queue Diagnostics
            </h1>
            <p class="text-base-content/70 mt-2">
              Comprehensive monitoring and diagnostics for the scraping queue
              system
            </p>
          </div>

          {/* Data Sources Documentation */}
          <div class="mb-6">
            <div class="collapse collapse-arrow bg-base-100 shadow-lg">
              <input type="checkbox" />
              <div class="collapse-title text-xl font-medium">
                📚 Data Sources & Scraping Documentation
              </div>
              <div class="collapse-content">
                <div class="prose max-w-none">
                  <p class="text-base-content/80 mb-4">
                    This system integrates multiple data sources to provide comprehensive LEGO set information.
                    Below is a detailed breakdown of each source, what data is collected, and how it's used.
                  </p>

                  {/* Summary Table */}
                  <div class="overflow-x-auto mb-6">
                    <table class="table table-zebra table-sm">
                      <thead>
                        <tr>
                          <th>Data Type</th>
                          <th>Primary Source</th>
                          <th>Frequency</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr>
                          <td>Historical Pricing</td>
                          <td>Bricklink</td>
                          <td>2-5 min intervals</td>
                        </tr>
                        <tr>
                          <td>Volume/Transactions</td>
                          <td>Bricklink</td>
                          <td>2-5 min intervals</td>
                        </tr>
                        <tr>
                          <td>Retirement Tracking</td>
                          <td>BrickRanker</td>
                          <td>Monthly (30 days)</td>
                        </tr>
                        <tr>
                          <td>Set Metadata</td>
                          <td>WorldBricks</td>
                          <td>Quarterly (90 days)</td>
                        </tr>
                        <tr>
                          <td>Year Released</td>
                          <td>WorldBricks</td>
                          <td>Quarterly (90 days)</td>
                        </tr>
                        <tr>
                          <td>Community Discussions</td>
                          <td>Reddit</td>
                          <td>5-10 sec intervals</td>
                        </tr>
                        <tr>
                          <td>Investment Metrics</td>
                          <td>BrickEconomy</td>
                          <td>Manual only</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>

                  {/* Bricklink */}
                  <div class="card bg-base-200 shadow-sm mb-4">
                    <div class="card-body">
                      <h3 class="card-title text-lg">🧱 Bricklink</h3>
                      <p class="text-sm text-base-content/70 mb-2">
                        <strong>Source:</strong> <code>https://www.bricklink.com/v2/catalog/catalogitem.page?S=[SET_NUMBER]</code>
                      </p>
                      <p class="text-sm mb-2">
                        <strong>Database Tables:</strong> <code>bricklink_items</code>, <code>bricklink_price_history</code>, <code>bricklink_volume_history</code>
                      </p>

                      <div class="text-sm">
                        <strong>Data Collected:</strong>
                        <ul class="list-disc list-inside ml-2 mt-1">
                          <li>Item metadata (title, weight, image URL)</li>
                          <li>Historical pricing data (4 categories):
                            <ul class="list-circle list-inside ml-4">
                              <li>6-month new condition prices</li>
                              <li>6-month used condition prices</li>
                              <li>Current new condition prices</li>
                              <li>Current used condition prices</li>
                            </ul>
                          </li>
                          <li>Volume metrics per category: times_sold, total_lots, total_qty, min_price, avg_price, qty_avg_price, max_price</li>
                        </ul>
                      </div>

                      <div class="mockup-code text-xs mt-2">
                        <pre><code>{`// Example Data Structure
{
  "title": "Death Star™",
  "weight": "18500.00",
  "imageUrl": "https://img.bricklink.com/...",
  "priceHistory": {
    "sixMonthNew": {
      "times_sold": 1234,
      "total_qty": 2500,
      "avg_price": 549.99,
      "min_price": 499.99,
      "max_price": 699.99
    }
  }
}`}</code></pre>
                      </div>

                      <div class="badge badge-info mt-2">Rate Limit: Max 15 requests/hour</div>
                    </div>
                  </div>

                  {/* BrickRanker */}
                  <div class="card bg-base-200 shadow-sm mb-4">
                    <div class="card-body">
                      <h3 class="card-title text-lg">📅 BrickRanker</h3>
                      <p class="text-sm text-base-content/70 mb-2">
                        <strong>Source:</strong> <code>https://brickranker.com/retirement-tracker</code>
                      </p>
                      <p class="text-sm mb-2">
                        <strong>Database Table:</strong> <code>brickranker_retirement_items</code>
                      </p>

                      <div class="text-sm">
                        <strong>Data Collected:</strong>
                        <ul class="list-disc list-inside ml-2 mt-1">
                          <li>Set number and name</li>
                          <li>Year released</li>
                          <li>Expected retirement date</li>
                          <li>"Retiring Soon" flag</li>
                          <li>Theme categorization</li>
                        </ul>
                      </div>

                      <div class="mockup-code text-xs mt-2">
                        <pre><code>{`// Example Data Structure
{
  "setNumber": "75192",
  "name": "Millennium Falcon",
  "yearReleased": 2017,
  "retirementDate": "2024-12-31",
  "retiringSoon": true,
  "theme": "Star Wars"
}`}</code></pre>
                      </div>

                      <div class="badge badge-warning mt-2">Batch scraping: All themes processed monthly</div>
                    </div>
                  </div>

                  {/* WorldBricks */}
                  <div class="card bg-base-200 shadow-sm mb-4">
                    <div class="card-body">
                      <h3 class="card-title text-lg">🌍 WorldBricks</h3>
                      <p class="text-sm text-base-content/70 mb-2">
                        <strong>Source:</strong> <code>https://www.worldbricks.com/en/instructions-number/[range]/lego-set/[setNumber]-[name].html</code>
                      </p>
                      <p class="text-sm mb-2">
                        <strong>Database Table:</strong> <code>worldbricks_sets</code>
                      </p>

                      <div class="text-sm">
                        <strong>Data Collected:</strong>
                        <ul class="list-disc list-inside ml-2 mt-1">
                          <li>Set number and name</li>
                          <li>Detailed description</li>
                          <li>Year released (HIGH PRIORITY)</li>
                          <li>Parts count</li>
                          <li>Dimensions (W×D×H)</li>
                          <li>Image URL</li>
                        </ul>
                      </div>

                      <div class="mockup-code text-xs mt-2">
                        <pre><code>{`// Example Data Structure
{
  "setNumber": "10189",
  "name": "Taj Mahal",
  "description": "The beauty and...",
  "yearReleased": 2008,
  "yearRetired": null,
  "partsCount": 5923,
  "dimensions": "58.2 x 48 x 14.9 cm",
  "imageUrl": "https://worldbricks.com/..."
}`}</code></pre>
                      </div>

                      <div class="badge badge-success mt-2">Updated quarterly (every 90 days)</div>
                    </div>
                  </div>

                  {/* Reddit */}
                  <div class="card bg-base-200 shadow-sm mb-4">
                    <div class="card-body">
                      <h3 class="card-title text-lg">💬 Reddit</h3>
                      <p class="text-sm text-base-content/70 mb-2">
                        <strong>Source:</strong> <code>https://www.reddit.com/r/lego/search.json?q=[SET_NUMBER]</code>
                      </p>
                      <p class="text-sm mb-2">
                        <strong>Database Table:</strong> <code>reddit_search_results</code>
                      </p>

                      <div class="text-sm">
                        <strong>Data Collected:</strong>
                        <ul class="list-disc list-inside ml-2 mt-1">
                          <li>Post titles and content</li>
                          <li>Authors and timestamps</li>
                          <li>Scores and comment counts</li>
                          <li>Post URLs and permalinks</li>
                          <li>Subreddits: r/lego, r/legostarwars, r/legotechnic, etc.</li>
                        </ul>
                      </div>

                      <div class="mockup-code text-xs mt-2">
                        <pre><code>{`// Example Data Structure
{
  "title": "Just finished building 10189!",
  "author": "brickfan123",
  "score": 542,
  "num_comments": 87,
  "created_utc": 1699564800,
  "permalink": "/r/lego/comments/...",
  "subreddit": "lego"
}`}</code></pre>
                      </div>

                      <div class="badge badge-primary mt-2">Unauthenticated API access</div>
                    </div>
                  </div>

                  {/* BrickEconomy */}
                  <div class="card bg-base-200 shadow-sm mb-4">
                    <div class="card-body">
                      <h3 class="card-title text-lg">📊 BrickEconomy</h3>
                      <p class="text-sm text-base-content/70 mb-2">
                        <strong>Source:</strong> <code>https://www.brickeconomy.com/set/[SET_NUMBER]</code>
                      </p>
                      <p class="text-sm mb-2">
                        <strong>Status:</strong> <span class="badge badge-warning">Manual parsing only (not automated)</span>
                      </p>

                      <div class="text-sm">
                        <strong>Data Extracted:</strong>
                        <ul class="list-disc list-inside ml-2 mt-1">
                          <li>Retail price (MSRP)</li>
                          <li>Market value (new/sealed and used)</li>
                          <li>Growth percentages (overall, annual, 90-day)</li>
                          <li>Investment forecasts (1-year, 5-year)</li>
                          <li>Pieces, minifigs, minifigs value, PPP (price per piece)</li>
                          <li>Theme and subtheme</li>
                          <li>Release and retirement dates</li>
                          <li>Quick buy prices (eBay, Amazon, StockX, Bricklink)</li>
                          <li>UPC/EAN codes</li>
                        </ul>
                      </div>

                      <div class="mockup-code text-xs mt-2">
                        <pre><code>{`// Example Data Structure
{
  "msrp": 799.99,
  "marketValue": 1299.99,
  "usedValue": 899.99,
  "overallGrowth": "62.5%",
  "annualGrowth": "15.2%",
  "forecast1Year": 1450.00,
  "forecast5Year": 2100.00,
  "pieces": 5923,
  "minifigs": 0,
  "ppp": 0.135
}`}</code></pre>
                      </div>

                      <div class="badge badge-error mt-2">Not currently in queue system</div>
                    </div>
                  </div>

                  {/* Additional Notes */}
                  <div class="alert alert-info mt-4">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" class="stroke-current shrink-0 w-6 h-6">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                    </svg>
                    <div>
                      <h4 class="font-bold">Integration Notes</h4>
                      <ul class="text-sm list-disc list-inside">
                        <li>No automated data merging between sources currently</li>
                        <li>Each source maintains its own database table</li>
                        <li>Cross-referencing possible via set numbers</li>
                        <li>Images are downloaded and stored locally with deduplication</li>
                        <li>All scrapers implement circuit breaker pattern and exponential backoff</li>
                      </ul>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Dashboard */}
          <QueueDiagnosticsDashboard />
        </div>
      </div>
    </>
  );
}
