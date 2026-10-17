# backtest_puts_v2.py
"""
نسخه‌ی دقیق‌تر بک‌تست خرید پوت. تفاوت‌ها با نسخه‌ی اول:
  1) روند ریزشی به ۳ سطح (ملایم / متوسط / شدید) تقسیم شده تا ببینیم هرچی روند ریزشی‌تر،
     خرید پوت بهتر جواب می‌ده یا نه.
  2) توی هر دسته، موفقیت سیگنال PUT با «موفقیت پایه‌ی همه‌ی سهم‌ها در همون دسته» مقایسه می‌شه
     (چون توی بازار خیلی ریزشی، حتی سهم‌های بی‌سیگنال هم بیشتر افت می‌کنن).
  3) سیگنال «PUT آماده‌باش» (قوی) از «PUT محتاط» جدا شده.
  4) تعداد روزهای مجزا و سهم ۳ روز برتر از کل موفقیت‌ها گزارش می‌شه؛ چون سیگنال‌های یک روز
     مستقل از هم نیستن (مثلاً ۱۸ پوت هم‌زمان توی یه روز ریزشی).

فقط می‌خونه، چیزی توی دیتابیس تغییر نمی‌ده.

اجرا:
    python backtest_puts_v2.py
"""

import sqlite3

DB_NAME = "market_history.db"

SUCCESS_DROP = -1.8   # موفقیت خریدار پوت: افت سهم فردا <= این مقدار
TREND_DAYS = 5
MIN_TREND_POINTS = 3

# مرز دسته‌ها بر اساس مجموع بازده شاخص در TREND_DAYS روز آخر (به درصد)
BUCKETS = [
    ("ریزشی شدید   (≤ -3.0)", None, -3.0),
    ("ریزشی متوسط  (-3.0 تا -1.5)", -3.0, -1.5),
    ("ریزشی ملایم  (-1.5 تا -0.5)", -1.5, -0.5),
    ("رنج          (-0.5 تا +0.5)", -0.5, 0.5),
    ("صعودی        (≥ +0.5)", 0.5, None),
]


def bucket_of(trend):
    if trend is None:
        return None
    for name, lo, hi in BUCKETS:
        if (lo is None or trend > lo) and (hi is None or trend <= hi):
            return name
    return None


def top3_share(dates_hits):
    """سهم ۳ روز برتر از کل موفقیت‌ها. dates_hits: {date: تعداد موفقیت}"""
    total = sum(dates_hits.values())
    if total == 0:
        return None
    top = sorted(dates_hits.values(), reverse=True)[:3]
    return sum(top) / total * 100


def main():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT DISTINCT date FROM daily_predictions ORDER BY date ASC")
    dates = [r[0] for r in cur.fetchall()]
    if len(dates) < 4:
        print("❌ داده‌ی کافی نیست.")
        return
    next_date = {d: dates[i + 1] for i, d in enumerate(dates[:-1])}

    cur.execute("SELECT date, AVG(market_return) AS mr FROM daily_predictions GROUP BY date")
    mr = {r["date"]: (r["mr"] if r["mr"] is not None else 0.0) for r in cur.fetchall()}
    trend = {}
    for i, d in enumerate(dates):
        window = dates[max(0, i - TREND_DAYS + 1): i + 1]
        trend[d] = sum(mr[x] for x in window) if len(window) >= MIN_TREND_POINTS else None

    cur.execute("SELECT date, symbol, close_change_pct FROM daily_predictions")
    chg = {(r["date"], r["symbol"]): r["close_change_pct"] for r in cur.fetchall()}

    cur.execute(
        "SELECT date, symbol, option_label FROM daily_predictions WHERE option_label LIKE '%PUT%'"
    )
    puts = cur.fetchall()
    conn.close()

    if not puts:
        print("❌ هیچ ردیف با برچسب PUT توی دیتابیس پیدا نشد.")
        return

    # پایه: همه‌ی ردیف‌ها (هر سهم، هر روز) که روز بعد دارن
    base = {name: [0, 0] for name, _, _ in BUCKETS}  # [تعداد، موفقیت]
    for (d, s), _c in chg.items():
        nd = next_date.get(d)
        cls = bucket_of(trend.get(d))
        if not nd or cls is None or (nd, s) not in chg or chg[(nd, s)] is None:
            continue
        base[cls][0] += 1
        if chg[(nd, s)] <= SUCCESS_DROP:
            base[cls][1] += 1

    # سیگنال‌های PUT
    grp = {name: [] for name, _, _ in BUCKETS}          # تغییر فردا
    days = {name: {} for name, _, _ in BUCKETS}         # روز -> تعداد موفقیت
    by_label = {}                                       # برچسب -> [تعداد، موفقیت، مجموع تغییر]
    skipped = 0
    for r in puts:
        d, s, lab = r["date"], r["symbol"], r["option_label"] or ""
        nd = next_date.get(d)
        cls = bucket_of(trend.get(d))
        if not nd or cls is None or (nd, s) not in chg or chg[(nd, s)] is None:
            skipped += 1
            continue
        x = chg[(nd, s)]
        grp[cls].append(x)
        days[cls][d] = days[cls].get(d, 0) + (1 if x <= SUCCESS_DROP else 0)
        key = "PUT آماده‌باش" if "آماده" in lab else "PUT محتاط" if "محتاط" in lab else "PUT (سایر)"
        rec = by_label.setdefault(key, [0, 0, 0.0])
        rec[0] += 1
        rec[1] += 1 if x <= SUCCESS_DROP else 0
        rec[2] += x

    print("=" * 96)
    print(f"📉 بک‌تست خرید پوت - نسخه‌ی دقیق | موفقیت = افت سهم فردا ≤ {SUCCESS_DROP}٪")
    print("=" * 96)
    print(f"{'روند ۵ روزه‌ی شاخص':32s} | {'سیگنال':>6s} | {'روز':>4s} | {'موفقیت':>7s} | {'پایه':>6s} | {'برتری':>7s} | {'میانگین فردا':>12s} | {'سهم ۳ روز برتر':>14s}")
    print("-" * 96)
    for name, _, _ in BUCKETS:
        arr = grp[name]
        b_n, b_h = base[name]
        base_rate = (b_h / b_n * 100) if b_n else None
        if not arr:
            print(f"{name:32s} | {0:6d} | {0:4d} | {'-':>7s} | {(f'{base_rate:.1f}%' if base_rate is not None else '-'):>6s} | {'-':>7s} | {'-':>12s} | {'-':>14s}")
            continue
        hit = sum(1 for x in arr if x <= SUCCESS_DROP)
        rate = hit / len(arr) * 100
        lift = f"{rate - base_rate:+.1f}" if base_rate is not None else "-"
        share = top3_share(days[name])
        share_txt = f"{share:.0f}%" if share is not None else "-"
        print(f"{name:32s} | {len(arr):6d} | {len(days[name]):4d} | {rate:6.1f}% | {base_rate:5.1f}% | {lift:>7s} | {sum(arr) / len(arr):+11.2f}% | {share_txt:>14s}")
    print("-" * 96)
    print("برتری = موفقیت سیگنال PUT منهای موفقیت پایه (همه‌ی سهم‌ها) در همون دسته، به واحد درصد.")
    print("سهم ۳ روز برتر = چند درصد از موفقیت‌ها فقط از ۳ روز بوده (هرچه بالاتر، نتیجه به چند روز خاص وابسته‌تره).")

    print("\n" + "=" * 60)
    print("🏷  به تفکیک نوع سیگنال PUT (همه‌ی روندها با هم)")
    print("=" * 60)
    for key, (n, h, tot) in sorted(by_label.items()):
        print(f"{key:14s} | {n:4d} سیگنال | موفقیت {h / n * 100:5.1f}% | میانگین فردا {tot / n:+.2f}%")

    if skipped:
        print(f"\nℹ️ {skipped} سیگنال PUT بدون روز بعد یا بدون روند کافی کنار گذاشته شد.")
    print("\nنکته: دسته‌ای که تعداد «روز»ش کمتر از ۸-۱۰ باشه، حتی اگه سیگنالش زیاد باشه، قابل‌اتکا نیست.")


if __name__ == "__main__":
    main()