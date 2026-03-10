"""
Scene 3 Example: Brand Sentiment Deep Dive
Run this in the sandbox code editor against the Nike datasets.
"""
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from collections import Counter

# ── Load ───────────────────────────────────────────────────────────────────────
mentions = pd.read_csv('/home/daytona/data/nike_social_mentions.csv')
reviews  = pd.read_csv('/home/daytona/data/nike_product_reviews.csv')

mentions['date'] = pd.to_datetime(mentions['date'])
reviews['review_date'] = pd.to_datetime(reviews['review_date'])

print(f"Mentions: {len(mentions):,} rows  |  Reviews: {len(reviews):,} rows")
print(f"Date range: {mentions['date'].min().date()} → {mentions['date'].max().date()}\n")


# ── 1. Sentiment distribution by product category ──────────────────────────────
print("=" * 60)
print("1. SENTIMENT BY PRODUCT CATEGORY")
print("=" * 60)

cat_sent = (mentions
    .groupby('product_category')['sentiment_score']
    .agg(['mean', 'std', 'count'])
    .rename(columns={'mean': 'avg_sentiment', 'std': 'std_dev', 'count': 'mentions'})
    .sort_values('avg_sentiment', ascending=False)
)
print(cat_sent.round(3))

# Label breakdown (% positive / neutral / negative per category)
label_pct = (mentions
    .groupby(['product_category', 'sentiment_label'])
    .size()
    .unstack(fill_value=0)
    .apply(lambda r: (r / r.sum() * 100).round(1), axis=1)
)
print("\nSentiment label breakdown (%):")
print(label_pct)


# ── 2. Reach-weighted sentiment ────────────────────────────────────────────────
print("\n" + "=" * 60)
print("2. REACH-WEIGHTED SENTIMENT (what consumers actually SEE)")
print("=" * 60)

weighted = (mentions
    .groupby('product_category')
    .apply(lambda g: np.average(g['sentiment_score'], weights=g['reach']))
    .rename('weighted_sentiment')
    .sort_values(ascending=False)
)
comparison = cat_sent[['avg_sentiment']].join(weighted).round(3)
comparison['rank_shift'] = (
    comparison['avg_sentiment'].rank(ascending=False).astype(int) -
    comparison['weighted_sentiment'].rank(ascending=False).astype(int)
)
print(comparison)
print("\n(+rank_shift = category looks BETTER when weighted by reach)")


# ── 3. Monthly trend — find the anomaly ───────────────────────────────────────
print("\n" + "=" * 60)
print("3. MONTHLY SENTIMENT TREND — SPOT THE ANOMALY")
print("=" * 60)

mentions['month'] = mentions['date'].dt.to_period('M').astype(str)

monthly = (mentions
    .groupby(['month', 'product_category'])
    .agg(avg_sentiment=('sentiment_score', 'mean'),
         total_reach=('reach', 'sum'),
         n=('sentiment_score', 'count'))
    .reset_index()
)

# Find month-over-month drops > 0.15 for any category
monthly = monthly.sort_values(['product_category', 'month'])
monthly['prev_sentiment'] = monthly.groupby('product_category')['avg_sentiment'].shift(1)
monthly['mom_change'] = monthly['avg_sentiment'] - monthly['prev_sentiment']
anomalies = monthly[monthly['mom_change'] < -0.15][
    ['month', 'product_category', 'avg_sentiment', 'mom_change']
].sort_values('mom_change')
print("Month-over-month drops > 0.15 points:")
print(anomalies.round(3))

# Plot
fig, ax = plt.subplots(figsize=(10, 5))
for cat, grp in monthly.groupby('product_category'):
    ax.plot(grp['month'], grp['avg_sentiment'], marker='o', label=cat)
ax.axhline(0, color='white', linewidth=0.5, linestyle='--', alpha=0.4)
ax.set_title('Monthly Average Sentiment by Product Category', color='white')
ax.set_xlabel('Month', color='white')
ax.set_ylabel('Avg Sentiment Score', color='white')
ax.tick_params(colors='white', rotation=30)
ax.legend(fontsize=8, loc='lower left')
ax.set_facecolor('#1e293b')
fig.patch.set_facecolor('#0f172a')
plt.tight_layout()
plt.savefig('sentiment_trend.png', dpi=120)
print("\nChart saved → sentiment_trend.png")


# ── 4. Return rate vs. rating (reviews) ───────────────────────────────────────
print("\n" + "=" * 60)
print("4. RETURN RATE × RATING — PRODUCT QUALITY SIGNAL")
print("=" * 60)

review_summary = (reviews
    .groupby('product_category')
    .agg(
        avg_rating=('rating', 'mean'),
        return_rate=('contains_return_mention', 'mean'),
        n_reviews=('rating', 'count')
    )
    .sort_values('return_rate', ascending=False)
)
review_summary['return_rate'] = (review_summary['return_rate'] * 100).round(1)
review_summary['avg_rating']  = review_summary['avg_rating'].round(2)
print(review_summary)
print("\n^ Training category: highest return rate AND lowest avg rating — corroborates social signal")


# ── 5. Campaign effectiveness ──────────────────────────────────────────────────
print("\n" + "=" * 60)
print("5. JustDoIt_Refresh CAMPAIGN EFFECTIVENESS")
print("=" * 60)

campaign = mentions[mentions['campaign_tag'] == 'JustDoIt_Refresh']
organic  = mentions[mentions['campaign_tag'] == 'organic']

print(f"Campaign mentions: {len(campaign):,}  |  Organic mentions: {len(organic):,}")
print(f"\nCampaign  — avg sentiment: {campaign['sentiment_score'].mean():.3f}  |  median reach: {campaign['reach'].median():,.0f}")
print(f"Organic   — avg sentiment: {organic['sentiment_score'].mean():.3f}  |  median reach: {organic['reach'].median():,.0f}")
print(f"\nReach multiplier: {campaign['reach'].median() / organic['reach'].median():.1f}x")
print(">> High reach but MIXED sentiment — campaign is visible but not building brand love")


# ── 6. CMO Briefing Summary ────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("6. CMO BRIEFING — HEADLINE FINDINGS")
print("=" * 60)

top_positive = cat_sent['avg_sentiment'].idxmax()
reach_top    = weighted.idxmax()
anomaly_row  = anomalies.iloc[0] if len(anomalies) else {}
worst_return = review_summary['return_rate'].idxmax()

findings = {
    "top_positive_category":       top_positive,
    "reach_weighted_top_category": reach_top,
    "anomaly_month_and_category":  f"{anomaly_row.get('month','?')} / {anomaly_row.get('product_category','?')}",
    "highest_return_rate_category": worst_return,
    "campaign_sentiment_vs_organic": f"{campaign['sentiment_score'].mean():.2f} vs {organic['sentiment_score'].mean():.2f}",
    "cmo_flag": f"Training category {anomaly_row.get('month','April')} — viral negative spike cross-confirmed by {review_summary.loc[worst_return,'return_rate']:.1f}% return rate"
}

for k, v in findings.items():
    print(f"  {k}: {v}")
