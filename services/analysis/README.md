# Product Analysis System

A comprehensive, extensible SOLID-based analysis system for evaluating LEGO
product investment opportunities.

## Overview

The Product Analysis System provides multi-dimensional scoring and buy/hold/pass
recommendations for LEGO products by analyzing data from multiple sources
including Shopee, ToysRUs, Bricklink, BrickRanker, and Reddit.

## Architecture

The system follows SOLID principles for maximum extensibility and
maintainability:

```
services/analysis/
├── types.ts                     # Core type definitions
├── AnalysisService.ts          # Main orchestrator
├── RecommendationEngine.ts     # Coordinates analyzers and strategies
├── analyzers/
│   ├── BaseAnalyzer.ts         # Abstract base class
│   ├── PricingAnalyzer.ts      # Pricing and margin analysis
│   ├── DemandAnalyzer.ts       # Market demand and sentiment
│   ├── AvailabilityAnalyzer.ts # Stock and retirement urgency
│   └── QualityAnalyzer.ts      # Product quality and trust
└── strategies/
    ├── BaseStrategy.ts              # Strategy base class
    ├── InvestmentFocusStrategy.ts   # Long-term investment
    ├── QuickFlipStrategy.ts         # Fast turnaround resale
    └── BargainHunterStrategy.ts     # Deep discount hunting
```

## Analysis Dimensions

### 1. Pricing Analysis (PricingAnalyzer)

Evaluates pricing competitiveness and profit potential:

- **Discount Depth**: Percentage off retail price
- **Resale Margin**: Current retail vs Bricklink resale prices
- **Price Appreciation**: 6-month price trend analysis
- **Price Volatility**: Price range stability

**Scoring**: 0-100 where higher scores indicate better pricing opportunities.

**Data Sources**:

- Shopee/ToysRUs retail pricing
- Bricklink current and historical resale pricing

### 2. Demand Analysis (DemandAnalyzer)

Evaluates market demand and community interest:

- **Sales Velocity**: Units sold on retail platforms
- **Resale Activity**: Bricklink transaction volume
- **Community Sentiment**: Reddit posts, scores, and engagement
- **Engagement Metrics**: Views, likes, comments

**Scoring**: 0-100 where higher scores indicate stronger demand.

**Data Sources**:

- Shopee sales and engagement metrics
- Bricklink transaction history
- Reddit community discussions

### 3. Availability Analysis (AvailabilityAnalyzer)

Evaluates scarcity and urgency:

- **Retirement Timing**: Days until expected retirement
- **Stock Levels**: Current inventory availability
- **Platform Status**: Active vs delisted products

**Scoring**: 0-100 where higher scores indicate greater urgency/scarcity.

**Data Sources**:

- BrickRanker retirement tracking
- Shopee/ToysRUs stock information

### 4. Quality Analysis (QualityAnalyzer)

Evaluates product and seller quality:

- **Product Ratings**: Star ratings and review counts
- **Seller Trust**: Verified seller badges
- **Brand Authenticity**: Official LEGO verification
- **Theme Popularity**: Premium theme identification

**Scoring**: 0-100 where higher scores indicate higher quality.

**Data Sources**:

- Shopee ratings and seller badges
- Product metadata

## Investment Strategies

### Investment Focus (Default)

**Best for**: Long-term investment portfolios

**Weights**:

- Availability: 40% (retirement timing is critical)
- Pricing: 35% (margins and appreciation)
- Demand: 20% (resale market activity)
- Quality: 5% (assumes LEGO quality)

**Key Metrics**:

- Estimated ROI based on current margins or appreciation trends
- Time horizon based on retirement proximity
- Investment window optimization

### Quick Flip

**Best for**: Fast turnaround resales

**Weights**:

- Demand: 40% (need active buyers)
- Pricing: 35% (current margins matter most)
- Availability: 20% (low stock creates urgency)
- Quality: 5% (speed over perfection)

**Key Metrics**:

- Immediate resale potential
- Quick profit opportunities
- Short time horizons (1-3 months)

### Bargain Hunter

**Best for**: Finding deep discounts on quality products

**Weights**:

- Pricing: 50% (looking for discounts)
- Quality: 25% (want quality products)
- Demand: 15% (want popular items)
- Availability: 10% (not urgency focused)

**Key Metrics**:

- Discount depth
- Value for money
- Quality ratings

## API Endpoints

### Get Product Analysis

```
GET /api/analysis/:productId?strategy=<strategyName>
```

Analyzes a single product with the specified strategy.

**Parameters**:

- `productId` (required): Product ID to analyze
- `strategy` (optional): Strategy name (default: "Investment Focus")

**Response**:

```json
{
  "overall": {
    "value": 85,
    "confidence": 0.87,
    "reasoning": "Strong availability signals. Strong pricing signals.",
    "dataPoints": { ... }
  },
  "dimensions": {
    "pricing": { ... },
    "demand": { ... },
    "availability": { ... },
    "quality": { ... }
  },
  "action": "strong_buy",
  "strategy": "Investment Focus",
  "urgency": "urgent",
  "estimatedROI": 45,
  "timeHorizon": "6-12 months post-retirement",
  "risks": [ ... ],
  "opportunities": [ ... ],
  "analyzedAt": "2025-11-12T..."
}
```

### Batch Analysis

```
POST /api/analysis/batch
Content-Type: application/json

{
  "productIds": ["prod-1", "prod-2", ...],
  "strategy": "Investment Focus"
}
```

Analyzes multiple products in parallel (max 100).

### Get Available Strategies

```
GET /api/analysis/strategies
```

Returns available strategies and analyzer information.

**Response**:

```json
{
  "strategies": [
    {
      "name": "Investment Focus",
      "description": "Identifies sets with best investment potential..."
    },
    ...
  ],
  "analyzers": [
    {
      "name": "Pricing Analyzer",
      "description": "Evaluates price competitiveness..."
    },
    ...
  ]
}
```

## UI Components

### ProductAnalysisCard (Island)

Interactive component displaying full analysis with strategy selector.

```tsx
<ProductAnalysisCard
  productId="prod-123"
  defaultStrategy="Investment Focus"
/>;
```

**Features**:

- Strategy selector dropdown
- Overall score and recommendation badge
- Investment metrics (ROI, time horizon)
- Dimensional score breakdown with reasoning
- Collapsible opportunities and risks
- Real-time loading and error states

### ScoreMeter (Component)

Reusable score visualization component.

```tsx
<ScoreMeter
  score={85}
  label="Overall Score"
  size="lg"
  showValue={true}
/>;
```

**Features**:

- Color-coded based on score (red/yellow/blue/green)
- Three sizes (sm/md/lg)
- Animated progress bar

### RecommendationBadge (Component)

Color-coded action and urgency badges.

```tsx
<RecommendationBadge
  action="strong_buy"
  urgency="urgent"
  size="lg"
/>;
```

**Features**:

- Action: strong_buy, buy, hold, pass
- Urgency: urgent, moderate, low, no_rush
- Color-coded with icons

## Usage Examples

### Basic Usage

```typescript
import { analysisService } from "./services/analysis/AnalysisService.ts";

// Analyze a single product
const recommendation = await analysisService.analyzeProduct(
  "shopee-123",
  "Investment Focus",
);

console.log(`Action: ${recommendation.action}`);
console.log(`Score: ${recommendation.overall.value}/100`);
console.log(`ROI: ${recommendation.estimatedROI}%`);
```

### Batch Analysis

```typescript
const results = await analysisService.analyzeProducts(
  ["prod-1", "prod-2", "prod-3"],
  "Quick Flip",
);

for (const [productId, rec] of results) {
  if (rec.action === "strong_buy") {
    console.log(`${productId}: Strong buy opportunity!`);
  }
}
```

### Demo Page

Visit `/analysis-demo` to see the system in action with sample products.

## Extending the System

### Adding a New Analyzer

1. Create a new analyzer class extending `BaseAnalyzer`:

```typescript
import { BaseAnalyzer } from "./BaseAnalyzer.ts";
import type { AnalysisScore } from "../types.ts";

export class MyCustomAnalyzer extends BaseAnalyzer<MyDataType> {
  constructor() {
    super("My Analyzer", "Description of what it does");
  }

  async analyze(data: MyDataType): Promise<AnalysisScore> {
    // Implement scoring logic
    return {
      value: 75,
      confidence: 0.85,
      reasoning: "Analysis reasoning...",
      dataPoints: {/* raw data */},
    };
  }
}
```

2. Register it in `AnalysisService.ts` constructor.

### Adding a New Strategy

1. Create a new strategy class extending `BaseStrategy`:

```typescript
import { BaseStrategy } from "./BaseStrategy.ts";
import type { DimensionWeights } from "../types.ts";

export class MyCustomStrategy extends BaseStrategy {
  constructor() {
    const weights: DimensionWeights = {
      pricing: 0.30,
      demand: 0.30,
      availability: 0.25,
      quality: 0.15,
    };

    super(
      "My Strategy",
      "Description of when to use this strategy",
      weights,
    );
  }

  // Optionally override interpret() for custom logic
}
```

2. Register it in `AnalysisService.ts` constructor.

### Adding a New Data Source

1. Add new fields to relevant data types in `types.ts`
2. Fetch data in `AnalysisService.buildAnalysisInput()`
3. Incorporate into analyzer scoring logic

## Database Schema

The `productAnalysis` table caches analysis results:

```sql
CREATE TABLE product_analysis (
  id SERIAL PRIMARY KEY,
  product_id VARCHAR(100) NOT NULL,
  strategy VARCHAR(50) NOT NULL,
  overall_score INTEGER NOT NULL,
  confidence INTEGER NOT NULL,
  action VARCHAR(20) NOT NULL,
  urgency VARCHAR(20) NOT NULL,
  dimensional_scores JSONB NOT NULL,
  estimated_roi INTEGER,
  time_horizon VARCHAR(100),
  risks JSONB,
  opportunities JSONB,
  full_recommendation JSONB NOT NULL,
  analyzed_at TIMESTAMP DEFAULT NOW(),
  created_at TIMESTAMP DEFAULT NOW()
);
```

## Testing

Run the development server and visit:

- `/analysis-demo` - Interactive demo with sample products
- Test API endpoints with curl:

```bash
# Single product analysis
curl http://localhost:8000/api/analysis/prod-123?strategy=Investment%20Focus

# Available strategies
curl http://localhost:8000/api/analysis/strategies

# Batch analysis
curl -X POST http://localhost:8000/api/analysis/batch \
  -H "Content-Type: application/json" \
  -d '{"productIds": ["prod-1", "prod-2"], "strategy": "Quick Flip"}'
```

## Performance Considerations

- Analyzers run in parallel for faster analysis
- Consider implementing caching layer for frequently analyzed products
- Batch analysis processes products concurrently
- Database indexes optimize data fetching

## Future Enhancements

- [ ] Implement caching with TTL
- [ ] Add machine learning price prediction
- [ ] Historical trend visualization
- [ ] Email alerts for high-scoring opportunities
- [ ] Portfolio tracking and analytics
- [ ] Comparative analysis across similar products
- [ ] Market segment analysis (by theme, price range)
- [ ] Seasonal adjustment factors
