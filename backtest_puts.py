# backtest_puts.py
"""
سیگنال‌های PUT داشبورد (برچسب‌های «PUT آماده‌باش» و «PUT محتاط») رو بر اساس
«روند چندروزه‌ی کل بازار» دسته‌بندی می‌کنه و نشون می‌ده خرید پوت توی هر دسته
(بازار ریزشی / رنج / صعودی) چقدر موفق بوده.

موفقیت = افت سهم در روز بعد حداقل SUCCESS_DROP درصد (مثل معیار +1.8٪ برای کال، ولی برعکس).
روند بازار = مجموع بازده شاخص کل در TREND_DAYS روز کاری آخر (تا همون روز سیگنال).

فقط می‌خونه، چیزی توی دیتابیس تغییر نمی‌ده.

اجرا:
    python backtest_puts.py
"""

import sqlite3

DB_NAME = "market_history.db"

SUCCESS_DROP = -1.8   # موفقیت خریدار پوت: افت سهم فردا <= این مقدار
TREND_DAYS = 5        # تعداد روز کاری برای محاسبه‌ی روند شاخص
DOWN_TH = -0.5        # مجموع بازده شاخص <= این مقدار => روند ریزشی
UP_TH = 0.5           # مجموع بازده شاخص >= این مقدار => روند صعودی (بین این دو => رنج)
MIN_TREND_POINTS = 3  # حداقل تعداد روز لازم برای تعیین روند


def classify(trend):
    if trend is None:
        return None
    if trend <= DOWN_TH:
        return "ریزشی"
    if trend >= UP_TH:
        return "صعودی"
    return "رنج"


def main():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT DISTINCT date FROM daily_predictions ORDER BY date ASC")
    dates = [r[0] for r in cur.fetchall()]
    if len(dates) < 3:
        print("❌ داده‌ی کافی نیست.")
        return
    next_date = {d: dates[i + 1] for i, d in enumerate(dates[:-1])}

    # بازده شاخص کل هر روز (ستون market_return، برای همه‌ی نمادهای یک روز یکسانه)
    cur.execute("SELECT date, AVG(market_return) AS mr FROM daily_predictions GROUP BY date")
    mr = {r["date"]: (r["mr"] if r["mr"] is not None else 0.0) for r in cur.fetchall()}

    trend = {}
    for i, d in enumerate(dates):
        window = dates[max(0, i - TREND_DAYS + 1): i + 1]
        trend[d] = sum(mr[x] for x in window) if len(window) >= MIN_TREND_POINTS else None

    valid_trends = [v for v in trend.values() if v is not None]
    if valid_trends:
        print(f"ℹ️ دامنه‌ی روند {TREND_DAYS} روزه‌ی شاخص توی داده‌ها: از {min(valid_trends):+.2f}٪ تا {max(valid_trends):+.2f}٪")
        print(f"   (ریزشی ≤ {DOWN_TH:+.1f}٪ | رنج بین این دو | صعودی ≥ {UP_TH:+.1f}٪)\n")

    # بازده فردای هر نماد
    cur.execute("SELECT date, symbol, close_change_pct FROM daily_predictions")
    chg = {(r["date"], r["symbol"]): r["close_change_pct"] for r in cur.fetchall()}

    # سیگنال‌های PUT
    cur.execute(
        "SELECT date, symbol, pressure_score, option_label FROM daily_predictions "
        "WHERE option_label LIKE '%PUT%'"
    )
    puts = cur.fetchall()
    mode = "برچسب PUT داشبورد"
    if not puts:
        cur.execute(
            "SELECT date, symbol, pressure_score, option_label FROM daily_predictions "
            "WHERE pressure_score <= 30"
        )
        puts = cur.fetchall()
        mode = "جایگزین: فشار ≤ ۳۰ (برچسب PUT توی دیتابیس پیدا نشد)"
    conn.close()

    # پایه‌ی مقایسه: چند درصد از کل ردیف‌ها فردا حداقل SUCCESS_DROP افت کردن
    base_n = base_hit = 0
    for (d, s), c in chg.items():
        nd = next_date.get(d)
        if nd and (nd, s) in chg and chg[(nd, s)] is not None:
            base_n += 1
            if chg[(nd, s)] <= SUCCESS_DROP:
                base_hit += 1

    groups = {}
    skipped = 0
    for r in puts:
        d, s = r["date"], r["symbol"]
        nd = next_date.get(d)
        cls = classify(trend.get(d))
        if not nd or (nd, s) not in chg or chg[(nd, s)] is None or cls is None:
            skipped += 1
            continue
        groups.setdefault(cls, []).append(chg[(nd, s)])

    print("=" * 70)
    print(f"📉 بک‌تست خرید پوت (سیگنال‌ها: {mode})")
    print(f"   موفقیت = افت سهم فردا ≤ {SUCCESS_DROP}٪")
    print("=" * 70)
    print(f"{'روند بازار':10s} | {'تعداد':>6s} | {'موفقیت':>8s} | {'میانگین تغییر فردا':>18s}")
    print("-" * 70)
    total_n = total_hit = 0
    for cls in ("ریزشی", "رنج", "صعودی"):
        arr = groups.get(cls, [])
        if not arr:
            print(f"{cls:10s} | {0:6d} | {'-':>8s} | {'-':>18s}")
            continue
        hit = sum(1 for x in arr if x <= SUCCESS_DROP)
        total_n += len(arr)
        total_hit += hit
        print(f"{cls:10s} | {len(arr):6d} | {hit / len(arr) * 100:7.1f}% | {sum(arr) / len(arr):+17.2f}%")
    print("-" * 70)
    if total_n:
        print(f"{'کل':10s} | {total_n:6d} | {total_hit / total_n * 100:7.1f}% |")
    if base_n:
        print(f"\nپایه‌ی مقایسه (همه‌ی نمادها، همه‌ی روزها): {base_hit / base_n * 100:.1f}٪ افت ≤ {SUCCESS_DROP}٪ در روز بعد")
        print("   (اگه موفقیت پوت از این عدد بالاتر نباشه، سیگنال PUT از شانس بهتر نیست)")
    if skipped:
        print(f"\nℹ️ {skipped} سیگنال PUT بدون روز بعد یا بدون روند کافی کنار گذاشته شد.")
    print("\nنکته: هر دسته‌ای که تعدادش کمتر از ۱۰-۱۵ باشه، هنوز قابل‌اتکا نیست.")


if __name__ == "__main__":
    main()