"""
Generate synthetic Nike brand analytics datasets for the simulation data challenge.
Run: python generate_nike_datasets.py
Outputs 5 CSVs into this directory.
"""
import numpy as np
import pandas as pd
from datetime import date, timedelta
import random
import os

RNG = np.random.default_rng(42)
random.seed(42)

OUT = os.path.dirname(os.path.abspath(__file__))

# ── helpers ────────────────────────────────────────────────────────────────────

def date_range_days(start="2025-01-01", end="2025-06-30"):
    s = date.fromisoformat(start)
    e = date.fromisoformat(end)
    return [s + timedelta(days=i) for i in range((e - s).days + 1)]

ALL_DAYS = date_range_days()

def clamp(v, lo=-1.0, hi=1.0):
    return float(np.clip(v, lo, hi))

def sentiment_label(score):
    if score >= 0.15:
        return "positive"
    if score <= -0.15:
        return "negative"
    return "neutral"


# ══════════════════════════════════════════════════════════════════════════════
# 1. nike_social_mentions.csv  (~2 400 rows)
# ══════════════════════════════════════════════════════════════════════════════

def make_social_mentions(n=2400):
    platforms   = ["Twitter", "Instagram", "Reddit", "TikTok"]
    platform_w  = [0.35, 0.30, 0.20, 0.15]

    categories  = ["Running", "Basketball", "Training", "Lifestyle",
                   "Jordan Brand", "Sustainability"]

    # base sentiment mean / std per category
    cat_sentiment = {
        "Running":      (0.35, 0.25),
        "Basketball":   (0.28, 0.28),
        "Training":     (0.20, 0.30),   # will get April dip applied
        "Lifestyle":    (0.18, 0.32),
        "Jordan Brand": (0.40, 0.22),
        "Sustainability": (0.05, 0.45), # bimodal - applied separately
    }

    # category volume weights (Running & Jordan Brand get more chatter)
    cat_w = [0.22, 0.18, 0.18, 0.16, 0.18, 0.08]

    campaign_tags = ["organic", "JustDoIt_Refresh", "NikeAir_Max", "NikeFC", "NikeSB"]
    # organic dominates; JustDoIt_Refresh concentrated Feb-Mar
    BASE_CAMP_W   = [0.65, 0.08, 0.10, 0.10, 0.07]

    rows = []
    for i in range(n):
        d    = random.choice(ALL_DAYS)
        platform = RNG.choice(platforms, p=platform_w)
        cat  = RNG.choice(categories, p=cat_w)

        # campaign tag — JustDoIt_Refresh boosted in Feb-Mar
        if d.month in (2, 3):
            camp_w = [0.45, 0.28, 0.10, 0.10, 0.07]
        else:
            camp_w = BASE_CAMP_W
        campaign = RNG.choice(campaign_tags, p=camp_w)

        # sentiment
        if cat == "Sustainability":
            # bimodal: half praise, half greenwashing criticism
            if RNG.random() < 0.45:
                score = clamp(RNG.normal(0.55, 0.15))   # genuine praise
            else:
                score = clamp(RNG.normal(-0.38, 0.18))  # greenwashing criticism
        else:
            mu, sd = cat_sentiment[cat]
            score = clamp(RNG.normal(mu, sd))

        # April 2025 Training anomaly — viral Reddit complaint thread
        if cat == "Training" and d.month == 4:
            if platform == "Reddit":
                score = clamp(RNG.normal(-0.45, 0.20))   # severely negative
            else:
                score = clamp(score - 0.25)              # general bleed-through

        # JustDoIt_Refresh has high reach but mixed/neutral sentiment
        if campaign == "JustDoIt_Refresh":
            reach = int(RNG.integers(8_000, 85_000))
            score = clamp(RNG.normal(0.08, 0.25))        # mixed
        elif platform == "TikTok":
            reach = int(RNG.integers(2_000, 120_000))
        elif platform == "Instagram":
            reach = int(RNG.integers(500, 40_000))
        elif platform == "Twitter":
            reach = int(RNG.integers(50, 15_000))
        else:  # Reddit
            reach = int(RNG.integers(20, 5_000))

        engagement = int(reach * RNG.uniform(0.03, 0.18))
        verified   = bool(RNG.random() < 0.12)

        rows.append({
            "mention_id":          f"SM-{i+1:05d}",
            "platform":            platform,
            "date":                d.isoformat(),
            "product_category":    cat,
            "sentiment_score":     round(score, 4),
            "sentiment_label":     sentiment_label(score),
            "reach":               reach,
            "engagement_count":    engagement,
            "is_verified_account": verified,
            "campaign_tag":        campaign,
        })

    df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    df["mention_id"] = [f"SM-{i+1:05d}" for i in range(len(df))]
    path = os.path.join(OUT, "nike_social_mentions.csv")
    df.to_csv(path, index=False)
    print(f"✓  nike_social_mentions.csv          {len(df):,} rows → {path}")
    return df


# ══════════════════════════════════════════════════════════════════════════════
# 2. nike_product_reviews.csv  (~1 800 rows)
# ══════════════════════════════════════════════════════════════════════════════

PRODUCTS = {
    "Running":      ["Nike Air Zoom Pegasus 41", "Nike Vomero 17", "Nike Invincible 3",
                     "Nike Infinity Run 4", "Nike React Miler 3"],
    "Basketball":   ["Nike LeBron XXII", "Nike Cosmic Unity 3", "Nike Zoom GT Cut 3"],
    "Training":     ["Nike Metcon 9", "Nike Dri-FIT ADV", "Nike React Infinity 4",
                     "Nike Air Max Trainer"],
    "Lifestyle":    ["Nike Air Max 97", "Nike Air Force 1 '07", "Nike Dunk Low"],
    "Jordan Brand": ["Air Jordan 1 Retro High OG", "Air Jordan 4 Retro", "Air Jordan 11 Retro"],
    "Sustainability": ["Nike Forward", "Nike Space Hippie 04", "Nike Crater Impact"],
}

def make_product_reviews(n=1800):
    categories = list(PRODUCTS.keys())
    cat_w      = [0.22, 0.15, 0.22, 0.18, 0.16, 0.07]
    sources    = ["Nike App", "Amazon", "Foot Locker"]
    # Nike App skews higher ratings (brand loyalists self-select)
    source_w   = [0.35, 0.45, 0.20]

    # base rating distributions (mean, std) per category × source
    base_ratings = {
        "Nike App":    {"Running": (4.3, 0.7), "Basketball": (4.1, 0.8),
                        "Training": (3.8, 0.9), "Lifestyle": (4.0, 0.8),
                        "Jordan Brand": (4.5, 0.6), "Sustainability": (4.1, 0.8)},
        "Amazon":      {"Running": (3.9, 0.9), "Basketball": (3.7, 1.0),
                        "Training": (3.2, 1.1), "Lifestyle": (3.6, 0.9),
                        "Jordan Brand": (4.0, 0.8), "Sustainability": (3.8, 0.9)},
        "Foot Locker": {"Running": (4.0, 0.8), "Basketball": (3.9, 0.8),
                        "Training": (3.5, 1.0), "Lifestyle": (3.9, 0.8),
                        "Jordan Brand": (4.3, 0.7), "Sustainability": (3.9, 0.8)},
    }

    # return mention rates per category
    return_rates = {
        "Running": 0.03, "Basketball": 0.06, "Training": 0.12,
        "Lifestyle": 0.05, "Jordan Brand": 0.04, "Sustainability": 0.07,
    }

    # Jordan Brand gets highest helpful votes (engaged community)
    helpful_base = {
        "Running": (5, 20), "Basketball": (3, 15), "Training": (2, 12),
        "Lifestyle": (4, 18), "Jordan Brand": (10, 45), "Sustainability": (3, 14),
    }

    rows = []
    for i in range(n):
        d   = random.choice(ALL_DAYS)
        cat = RNG.choice(categories, p=cat_w)
        src = RNG.choice(sources, p=source_w)
        prd = random.choice(PRODUCTS[cat])

        mu, sd = base_ratings[src][cat]
        # April Training penalty
        if cat == "Training" and d.month == 4:
            mu -= 0.8
        raw_rating = int(np.clip(round(RNG.normal(mu, sd)), 1, 5))

        # sentiment roughly derived from rating
        base_sent = (raw_rating - 3) / 2.5
        score = clamp(RNG.normal(base_sent, 0.2))

        # return mention
        ret_prob = return_rates[cat]
        if cat == "Training" and d.month in (4, 5):
            ret_prob *= 2.2
        contains_return = bool(RNG.random() < ret_prob)

        lo, hi = helpful_base[cat]
        helpful = int(RNG.integers(lo, hi))
        verified = bool(RNG.random() < 0.72)

        rows.append({
            "review_id":               f"REV-{i+1:05d}",
            "product_name":            prd,
            "product_category":        cat,
            "rating":                  raw_rating,
            "review_date":             d.isoformat(),
            "source":                  src,
            "helpful_votes":           helpful,
            "verified_purchase":       verified,
            "contains_return_mention": contains_return,
            "sentiment_score":         round(score, 4),
        })

    df = pd.DataFrame(rows).sort_values("review_date").reset_index(drop=True)
    df["review_id"] = [f"REV-{i+1:05d}" for i in range(len(df))]
    path = os.path.join(OUT, "nike_product_reviews.csv")
    df.to_csv(path, index=False)
    print(f"✓  nike_product_reviews.csv          {len(df):,} rows → {path}")
    return df


# ══════════════════════════════════════════════════════════════════════════════
# 3. nike_brand_tracker_monthly.csv  (72 rows)
# ══════════════════════════════════════════════════════════════════════════════

def make_brand_tracker():
    months   = ["2025-01","2025-02","2025-03","2025-04","2025-05","2025-06"]
    segments = ["18-24", "25-40"]
    metrics  = ["aided_awareness", "brand_consideration", "purchase_intent",
                "nps", "brand_love_score"]

    # base values per metric × segment (Jan baseline)
    base = {
        ("aided_awareness",   "18-24"): 92.1,
        ("aided_awareness",   "25-40"): 89.3,
        ("brand_consideration","18-24"): 68.4,
        ("brand_consideration","25-40"): 64.2,
        ("purchase_intent",   "18-24"): 55.3,
        ("purchase_intent",   "25-40"): 52.1,
        ("nps",               "18-24"): 41.2,
        ("nps",               "25-40"): 44.8,
        ("brand_love_score",  "18-24"): 62.5,
        ("brand_love_score",  "25-40"): 58.9,
    }

    # month-over-month deltas — training recall April dip for 18-24 purchase_intent
    # brand_love climbs steadily for 25-40 (JustDoIt_Refresh resonates with them)
    deltas = {
        ("purchase_intent","18-24"): [0, +1.2, +0.8, -3.5, -0.4, +1.1],  # April dip
        ("brand_love_score","25-40"): [0, +1.4, +1.8, +0.9, +1.3, +1.6], # steady climb
        ("nps","18-24"):              [0, +0.5, +0.3, -1.8, +0.2, +0.9], # echo of April
    }

    rows = []
    for seg in segments:
        for metric in metrics:
            val = base[(metric, seg)]
            for m_idx, month in enumerate(months):
                delta = deltas.get((metric, seg), [0]*6)[m_idx]
                val += delta + RNG.normal(0, 0.3)  # small noise
                rows.append({
                    "month":   month,
                    "metric":  metric,
                    "value":   round(val, 2),
                    "segment": seg,
                })

    df = pd.DataFrame(rows)
    path = os.path.join(OUT, "nike_brand_tracker_monthly.csv")
    df.to_csv(path, index=False)
    print(f"✓  nike_brand_tracker_monthly.csv    {len(df):,} rows → {path}")
    return df


# ══════════════════════════════════════════════════════════════════════════════
# 4. brand_competitive_sov.csv  (~480 rows)
# ══════════════════════════════════════════════════════════════════════════════

def make_competitive_sov():
    # Monday-starting weeks
    weeks = []
    d = date(2025, 1, 6)
    while d <= date(2025, 6, 30):
        weeks.append(d)
        d += timedelta(weeks=1)

    brands     = ["Nike", "Adidas", "New Balance", "On Running", "Hoka"]
    categories = ["Running", "Basketball", "Training", "Lifestyle"]

    # Base SOV per brand × category (must sum to ~100 per cat each week, varies with noise)
    base_sov = {
        # category:   Nike  Adidas  NewBalance  OnRunning  Hoka
        "Running":    [38,   22,     14,          14,        12],
        "Basketball": [54,   26,      5,           4,        11],
        "Training":   [42,   28,     12,           9,         9],
        "Lifestyle":  [34,   31,     16,           9,        10],
    }

    # On Running in Running: demographic_index_1824 climbs from ~0.9 to ~1.4
    # On Running SOV in Running also nudges up over time (trend)
    # Adidas Lifestyle: sentiment spike Feb-Mar (Samba cycle)

    rows = []
    for w_idx, week in enumerate(weeks):
        month = week.month
        frac  = w_idx / max(len(weeks) - 1, 1)   # 0→1 over the period

        for cat in categories:
            raw_sov = list(base_sov[cat])

            # On Running Running SOV grows +0.12% per week
            if cat == "Running":
                on_idx = brands.index("On Running")
                raw_sov[on_idx] += frac * 5.5  # +5.5 pp over period
                # compensate from Nike slightly
                raw_sov[0] -= frac * 2.8

            # Normalise to 100
            total = sum(raw_sov)
            sov_vals = [v / total * 100 for v in raw_sov]

            for b_idx, brand in enumerate(brands):
                sov_pct = round(sov_vals[b_idx] + RNG.normal(0, 0.8), 2)
                vol     = int(RNG.integers(300, 2500) * (sov_vals[b_idx] / 20))

                # base sentiment per brand
                sent_base = {"Nike": 0.22, "Adidas": 0.18, "New Balance": 0.20,
                             "On Running": 0.30, "Hoka": 0.28}[brand]
                # Adidas Lifestyle Feb-Mar Samba bump
                if brand == "Adidas" and cat == "Lifestyle" and month in (2, 3):
                    sent_base += 0.22
                avg_sent = round(clamp(RNG.normal(sent_base, 0.12)), 4)

                # demographic_index_1824 for On Running Running climbs 0.9→1.4
                if brand == "On Running" and cat == "Running":
                    dem_idx = round(0.90 + frac * 0.52 + RNG.normal(0, 0.04), 3)
                elif brand == "Nike" and cat == "Running":
                    dem_idx = round(RNG.normal(1.05, 0.06), 3)   # roughly indexed
                elif brand == "Hoka" and cat == "Running":
                    dem_idx = round(RNG.normal(0.75, 0.08), 3)   # older skew
                else:
                    dem_idx = round(RNG.normal(0.95, 0.10), 3)

                dem_idx = float(np.clip(dem_idx, 0.30, 2.0))

                rows.append({
                    "week_start":            week.isoformat(),
                    "brand":                 brand,
                    "category":              cat,
                    "sov_percent":           max(sov_pct, 0.5),
                    "mention_volume":        vol,
                    "avg_sentiment":         avg_sent,
                    "demographic_index_1824": dem_idx,
                })

    df = pd.DataFrame(rows)
    path = os.path.join(OUT, "brand_competitive_sov.csv")
    df.to_csv(path, index=False)
    print(f"✓  brand_competitive_sov.csv         {len(df):,} rows → {path}")
    return df


# ══════════════════════════════════════════════════════════════════════════════
# 5. nike_competitor_review_sentiment.csv  (~800 rows)
# ══════════════════════════════════════════════════════════════════════════════

COMP_PRODUCTS = {
    "Adidas": {
        "Running":      ["Adidas Ultraboost 23", "Adidas Solarboost 5", "Adidas Adizero Adios 8"],
        "Basketball":   ["Adidas D.O.N. Issue 5", "Adidas Harden Vol. 7"],
        "Training":     ["Adidas Powerlift 5", "Adidas Dropset 3"],
        "Lifestyle":    ["Adidas Samba OG", "Adidas Gazelle Bold", "Adidas Forum Low"],
    },
    "New Balance": {
        "Running":      ["New Balance Fresh Foam X 1080v13", "NB FuelCell SuperComp Elite v4"],
        "Basketball":   ["New Balance TWO WXY v4"],
        "Training":     ["New Balance Minimus TR v3", "NB Fresh Foam Roav 2"],
        "Lifestyle":    ["New Balance 990v6", "New Balance 550"],
    },
    "On Running": {
        "Running":      ["On Cloudmonster 2", "On Cloudsurfer 7", "On Cloudstratus 4"],
        "Basketball":   [],
        "Training":     ["On Cloudflow 4", "On Roger Pro 2"],
        "Lifestyle":    ["On Cloud 5", "On Cloudnova"],
    },
    "Hoka": {
        "Running":      ["Hoka Clifton 9", "Hoka Bondi 8", "Hoka Speedgoat 5"],
        "Basketball":   [],
        "Training":     ["Hoka Kawana 2", "Hoka Transport"],
        "Lifestyle":    ["Hoka Ora Primo", "Hoka Rincon 3"],
    },
}

def make_competitor_reviews(n=800):
    sources = ["Amazon", "Foot Locker", "Brand App"]
    source_w = [0.55, 0.30, 0.15]

    categories = ["Running", "Basketball", "Training", "Lifestyle"]
    cat_w      = [0.35, 0.10, 0.25, 0.30]

    # brand rating tendencies
    brand_rating_adj = {
        "Adidas": 0.0, "New Balance": +0.15, "On Running": +0.35, "Hoka": +0.30,
    }

    rows = []
    brand_list = list(COMP_PRODUCTS.keys())
    # weight: On Running & Hoka get proportionally more reviews (they're trending)
    brand_w = [0.30, 0.25, 0.25, 0.20]

    for i in range(n):
        brand = RNG.choice(brand_list, p=brand_w)
        cat   = RNG.choice(categories, p=cat_w)
        # skip empty product lists
        while not COMP_PRODUCTS[brand].get(cat):
            cat = RNG.choice(categories, p=cat_w)

        prd = random.choice(COMP_PRODUCTS[brand][cat])
        d   = random.choice(ALL_DAYS)
        src = RNG.choice(sources, p=source_w)

        adj = brand_rating_adj[brand]
        raw = int(np.clip(round(RNG.normal(3.8 + adj, 0.8)), 1, 5))

        score = clamp(RNG.normal((raw - 3) / 2.5, 0.18))

        # On Running reviews tend to be longer (premium buyers, more expressive)
        if brand == "On Running":
            length = int(RNG.integers(60, 220))
        elif brand == "New Balance":
            length = int(RNG.integers(40, 160))
        else:
            length = int(RNG.integers(25, 140))

        rows.append({
            "brand":               brand,
            "product_name":        prd,
            "category":            cat,
            "rating":              raw,
            "review_date":         d.isoformat(),
            "source":              src,
            "sentiment_score":     round(score, 4),
            "review_length_words": length,
        })

    df = pd.DataFrame(rows).sort_values("review_date").reset_index(drop=True)
    path = os.path.join(OUT, "nike_competitor_review_sentiment.csv")
    df.to_csv(path, index=False)
    print(f"✓  nike_competitor_review_sentiment.csv {len(df):,} rows → {path}")
    return df


# ══════════════════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("Generating Nike simulation datasets...\n")
    sm  = make_social_mentions()
    rv  = make_product_reviews()
    bt  = make_brand_tracker()
    sov = make_competitive_sov()
    cr  = make_competitor_reviews()

    print("\n── Quick sanity checks ───────────────────────────────────────────")

    # Social mentions: April Training should be most negative month for Training
    sm["date"] = pd.to_datetime(sm["date"])
    sm["month"] = sm["date"].dt.month
    training_monthly = (sm[sm["product_category"] == "Training"]
                        .groupby("month")["sentiment_score"].mean())
    april_score = training_monthly.get(4, None)
    print(f"  Training category Apr sentiment:  {april_score:.3f}  (expect < 0.00)")

    # Sustainability should be bimodal (std > 0.35)
    sust_std = sm[sm["product_category"] == "Sustainability"]["sentiment_score"].std()
    print(f"  Sustainability sentiment std:      {sust_std:.3f}  (expect > 0.35)")

    # On Running Running demographic_index_1824: Jun avg > Jan avg
    on_run = sov[(sov["brand"] == "On Running") & (sov["category"] == "Running")].copy()
    on_run["week_start"] = pd.to_datetime(on_run["week_start"])
    on_run["month"] = on_run["week_start"].dt.month
    jan_idx = on_run[on_run["month"] == 1]["demographic_index_1824"].mean()
    jun_idx = on_run[on_run["month"] == 6]["demographic_index_1824"].mean()
    print(f"  On Running 18-24 index Jan→Jun:   {jan_idx:.2f} → {jun_idx:.2f}  (expect ~0.9 → ~1.4)")

    # Training return rate should exceed Running
    training_ret = rv[rv["product_category"] == "Training"]["contains_return_mention"].mean()
    running_ret  = rv[rv["product_category"] == "Running"]["contains_return_mention"].mean()
    print(f"  Return mention rate Train vs Run:  {training_ret:.1%} vs {running_ret:.1%}  (expect Training > 8%)")

    print("\nAll done. 5 CSV files written to:", OUT)
