"""
Scene 4 Example: Competitive Benchmarking Sprint
Run this in the sandbox code editor (Scene 3 files also still available).
"""
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# ── Load ───────────────────────────────────────────────────────────────────────
sov   = pd.read_csv('/home/daytona/data/brand_competitive_sov.csv')
comp  = pd.read_csv('/home/daytona/data/nike_competitor_review_sentiment.csv')

# Nike reviews from Scene 3 still in sandbox
nike_rv = pd.read_csv('/home/daytona/data/nike_product_reviews.csv')

sov['week_start'] = pd.to_datetime(sov['week_start'])
comp['review_date'] = pd.to_datetime(comp['review_date'])

print(f"SOV rows: {len(sov):,}  |  Competitor review rows: {len(comp):,}")
print(f"Brands: {sov['brand'].unique().tolist()}\n")


# ── 1. SOV overview — brand × category pivot ──────────────────────────────────
print("=" * 60)
print("1. SHARE-OF-VOICE OVERVIEW (avg % by brand × category)")
print("=" * 60)

sov_pivot = (sov
    .groupby(['brand', 'category'])['sov_percent']
    .mean()
    .unstack()
    .round(1)
)
print(sov_pivot)
print(f"\nNike's WEAKEST category: {sov_pivot.loc['Nike'].idxmin()}  ({sov_pivot.loc['Nike'].min():.1f}%)")
print(f"Nike's STRONGEST category: {sov_pivot.loc['Nike'].idxmax()}  ({sov_pivot.loc['Nike'].max():.1f}%)")


# ── 2. SOV trend in Running — find the challenger ─────────────────────────────
print("\n" + "=" * 60)
print("2. RUNNING SOV TREND + GROWTH SLOPE")
print("=" * 60)

running = sov[sov['category'] == 'Running'].copy()
running['week_num'] = (running['week_start'] - running['week_start'].min()).dt.days / 7

slopes = {}
for brand, grp in running.groupby('brand'):
    grp = grp.sort_values('week_num')
    slope, intercept = np.polyfit(grp['week_num'], grp['sov_percent'], 1)
    slopes[brand] = round(slope, 3)

slopes_df = pd.Series(slopes, name='sov_slope_pp_per_week').sort_values(ascending=False)
print("SOV slope (pp per week) in Running category:")
print(slopes_df)
print(f"\nFastest growing: {slopes_df.idxmax()}  (+{slopes_df.max():.3f} pp/week)")
print(f"Fastest declining: {slopes_df.idxmin()}  ({slopes_df.min():.3f} pp/week)")

# Plot
fig, ax = plt.subplots(figsize=(10, 5))
for brand, grp in running.groupby('brand'):
    grp = grp.sort_values('week_start')
    ax.plot(grp['week_start'], grp['sov_percent'], marker='o', markersize=3, label=brand)
ax.set_title('Running Category — Share of Voice Over Time', color='white')
ax.set_xlabel('Week', color='white')
ax.set_ylabel('SOV (%)', color='white')
ax.tick_params(colors='white', rotation=30)
ax.legend(fontsize=9)
ax.set_facecolor('#1e293b')
fig.patch.set_facecolor('#0f172a')
plt.tight_layout()
plt.savefig('running_sov_trend.png', dpi=120)
print("\nChart saved → running_sov_trend.png")


# ── 3. 18-24 demographic index — the real threat signal ───────────────────────
print("\n" + "=" * 60)
print("3. 18-24 DEMOGRAPHIC INDEX — RUNNING CATEGORY")
print("=" * 60)

run_dem = (running
    .groupby(['brand', running['week_start'].dt.month.rename('month')])
    ['demographic_index_1824']
    .mean()
    .unstack()
    .round(3)
)
print("Avg demographic_index_1824 by brand × month (Running only):")
print(run_dem)

# Jan vs Jun comparison
print("\nJan → Jun shift:")
for brand in run_dem.index:
    jan = run_dem.loc[brand, 1] if 1 in run_dem.columns else None
    jun = run_dem.loc[brand, 6] if 6 in run_dem.columns else None
    if jan and jun:
        arrow = "↑" if jun > jan else "↓"
        print(f"  {brand:<14} {jan:.2f} → {jun:.2f}  {arrow}")

# Brands over-indexed with 18-24 (index > 1.0) in Running
over_indexed = running.groupby('brand')['demographic_index_1824'].mean()
print(f"\nOver-indexed with 18-24 (avg index > 1.0):")
print(over_indexed[over_indexed > 1.0].sort_values(ascending=False).round(3))


# ── 4. Review quality benchmarking ────────────────────────────────────────────
print("\n" + "=" * 60)
print("4. REVIEW QUALITY BENCHMARK — Nike vs Competitors")
print("=" * 60)

# Add Nike to competitor reviews for unified comparison
nike_rv_sub = nike_rv[['product_category', 'rating', 'sentiment_score']].copy()
nike_rv_sub['brand'] = 'Nike'
nike_rv_sub['review_length_words'] = 0   # not tracked for Nike in this dataset

comp_sub = comp[['brand', 'category', 'rating', 'sentiment_score', 'review_length_words']].copy()
comp_sub = comp_sub.rename(columns={'category': 'product_category'})

all_reviews = pd.concat([nike_rv_sub, comp_sub], ignore_index=True)

benchmark = (all_reviews
    .groupby('brand')
    .agg(
        avg_rating=('rating', 'mean'),
        avg_sentiment=('sentiment_score', 'mean'),
        avg_review_length=('review_length_words', lambda x: x[x > 0].mean()),
        n_reviews=('rating', 'count')
    )
    .round(2)
    .sort_values('avg_rating', ascending=False)
)
print(benchmark)
print("\n^ review_length_words = proxy for purchase conviction (longer = more invested buyer)")


# ── 5. Competitive threat matrix ──────────────────────────────────────────────
print("\n" + "=" * 60)
print("5. 2×2 THREAT MATRIX — Running Category")
print("=" * 60)

threat_data = pd.DataFrame({
    'brand':     slopes.keys(),
    'sov_slope': slopes.values(),
    'dem_index': [over_indexed.get(b, 0) for b in slopes.keys()],
})
threat_data['sov_growing']     = threat_data['sov_slope'] > 0
threat_data['dem_overindexed'] = threat_data['dem_index'] > 1.0

def quadrant(row):
    if row['sov_growing'] and row['dem_overindexed']:
        return '🔴 HIGH THREAT  (growing SOV + over-indexed 18-24)'
    elif row['sov_growing'] and not row['dem_overindexed']:
        return '🟡 MONITOR      (growing SOV, but older skew)'
    elif not row['sov_growing'] and row['dem_overindexed']:
        return '🟠 LATENT RISK  (losing SOV but owns 18-24 mindshare)'
    else:
        return '🟢 LOW THREAT   (declining SOV + under-indexed)'

threat_data['quadrant'] = threat_data.apply(quadrant, axis=1)
print(threat_data[['brand','sov_slope','dem_index','quadrant']].to_string(index=False))


# ── 6. Competitive brief ──────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("6. COMPETITIVE BRIEF FOR CMO")
print("=" * 60)

high_threat = threat_data[threat_data['quadrant'].str.startswith('🔴')]
threat_brand = high_threat['brand'].values[0] if len(high_threat) else 'Unknown'

nike_running_sov = sov_pivot.loc['Nike', 'Running'] if 'Running' in sov_pivot.columns else 0
top_comp_rating  = benchmark[benchmark.index != 'Nike']['avg_rating'].max()
nike_rating      = benchmark.loc['Nike', 'avg_rating'] if 'Nike' in benchmark.index else 0

competitive_brief = {
    "nike_running_sov_avg":             f"{nike_running_sov:.1f}%",
    "fastest_growing_competitor":       slopes_df.drop('Nike', errors='ignore').idxmax(),
    "18_24_threat_brand":               threat_brand,
    "nike_review_rating_vs_top_competitor": f"{nike_rating:.2f} vs {top_comp_rating:.2f}",
    "recommended_cmo_action": (
        f"Defensive investment in Running/18-24: {threat_brand} is gaining "
        f"{abs(slopes_df.get(threat_brand, 0)):.2f} pp SOV/week with a rising "
        f"demographic index — address with product storytelling targeting Gen Z runners."
    )
}

for k, v in competitive_brief.items():
    print(f"  {k}: {v}")
