# Model Tuning & Production Model


## 11 - ML Preprocessing & Hyperparameter Tuning (185 sets)

Tested target transforms, scalers, model architectures, outlier handling, and hyperparameter tuning.

### Preprocessing Findings

| Technique | Impact |
|-----------|--------|
| Log target transform | HURTS (R2 0.265 -> 0.162). GBMs handle skew natively. |
| RobustScaler | Neutral (0.266 vs 0.265). Tree models are scale-invariant. |
| PowerTransformer | Neutral (0.262). |
| Winsorize P5-P95 | Slightly helps raw (+0.038) but unnecessary with tuned model. |

### Hyperparameter Tuning Results

| Config | R2 | Corr | MAE | AUC |
|--------|-----|------|-----|-----|
| Old (d=3, leaf=5, n=100, lr=0.05) | 0.265 | 0.515 | 4.55% | 0.755 |
| d=4, leaf=4, n=150, lr=0.03 | 0.367 | 0.612 | 4.14% | 0.798 |
| d=4, leaf=3, n=150, lr=0.03 | 0.386 | 0.624 | 4.14% | 0.803 |
| **d=4, leaf=6, n=150, lr=0.03** | **0.401** | **0.641** | **4.08%** | **0.813** |

**+0.136 R2 improvement from tuning alone.** The model was under-fitting at depth=3. Depth=4 with leaf=6 (higher regularization) is optimal.

### Key Learnings

1. **Deeper trees + more regularization** is the winning combo. depth=4 lets the model capture more interactions, leaf=6 prevents overfitting.
2. **Slower learning rate** (0.03) with more trees (150) = better generalization.
3. **Very stable** across random seeds (R2 varies by 0.001).
4. **Tree-based models don't need** log transforms, robust scaling, or power transforms.
5. **Linear models fail** on this data (Ridge R2=-0.015, Huber R2=-0.060) -- the relationships are nonlinear.

### Updated Best Model

**GBM (d=4, leaf=6, n=150, lr=0.03) on 185 sets, 12 intrinsic features:**
- LOO R2 = 0.401, Correlation = 0.641, MAE = 4.08%, AUC = 0.813

---

## 12 - Best Model: Tuned GBM + Subtheme + Bayesian Theme (209-214 sets)

Combined all improvements: HP tuning + subtheme features + Bayesian smoothed theme encoding.

### Feature Set (14 features)

| Feature | Perm Importance | Type |
|---------|-----------------|------|
| subtheme_loo | 0.598 | Subtheme LOO growth |
| theme_bayes (alpha=20) | 0.461 | Bayesian smoothed theme growth |
| minifig_density | 0.167 | Intrinsic |
| usd_gbp_ratio | 0.130 | Pricing strategy |
| log_parts | 0.086 | Intrinsic |
| price_per_part | 0.064 | Intrinsic |
| theme_size | 0.055 | Theme metadata |
| review_count | 0.052 | Popularity |
| sub_size | 0.045 | Subtheme metadata |
| Others (mfigs, log_rrp, price_tier, is_licensed, rating) | <0.03 | Various |

### Model Config

GBM: n_estimators=250, max_depth=4, min_samples_leaf=6, learning_rate=0.02

### Validated Results (214 sets)

| Metric | Value |
|--------|-------|
| LOO R2 | 0.337 |
| LOO Correlation | 0.581 |
| LOO MAE | 4.54% |
| LOO AUC | 0.810 |
| 5-fold CV R2 (20 repeats) | 0.188 +/- 0.175 |
| Seed stability | R2 varies by 0.002 |

### Improvement Journey

| Step | n | LOO R2 | AUC | What changed |
|------|---|--------|-----|-------------|
| Exp 05 baseline | 157 | 0.265 | 0.755 | 12 features, d=3 |
| + HP tuning | 185 | 0.401 | 0.813 | d=4, leaf=6, lr=0.02 |
| + subtheme | 209 | 0.444 | 0.801 | subtheme_loo, sub_size |
| + Bayesian theme | 209 | 0.473 | 0.856 | Smoothed target encoding |
| Validated (more data) | 214 | 0.337 | 0.810 | Honest estimate on growing dataset |

### Per-Theme Performance

| Theme | n | MAE | Avg Growth |
|-------|---|-----|-----------|
| Star Wars | 43 | 2.4% | 9.0% |
| Monkie Kid | 10 | 3.1% | 7.8% |
| Super Mario | 9 | 3.2% | 6.6% |
| Holiday & Event | 5 | 3.5% | 3.8% |
| Super Heroes | 27 | 4.2% | 12.5% |
| NINJAGO | 18 | 4.2% | 12.7% |
| Minecraft | 12 | 4.5% | 19.2% |
| Harry Potter | 11 | 4.5% | 13.7% |
| DUPLO | 19 | 6.0% | 11.2% |
| Creator | 6 | 9.1% | 12.0% |
| LEGO Ideas | 6 | 10.9% | 12.1% |
| SPEED CHAMPIONS | 5 | 8.9% | 17.4% |

### Key Insight: Bayesian Smoothing

The alpha=20 Bayesian encoding blends theme mean with global mean: `smoothed = (n * theme_mean + 20 * global_mean) / (n + 20)`. This prevents small themes (Creator n=6, Ideas n=6) from having extreme LOO values that cause overfitting. For large themes (Star Wars n=43), it barely changes the value. This is a classic regularization technique for target encoding.

---
