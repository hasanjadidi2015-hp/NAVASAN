# simulate_filter_candidates.py
"""
تست چند فرضیه‌ی مختلف برای فیلتر «سیگنال ضعیف/بی‌پشتوانه» روی کل داده‌ی
ذخیره‌شده در daily_predictions، تا به‌جای تنظیم دستی روی ۲-۳ نمونه، با دید
کامل‌تری تصمیم بگیریم. فقط می‌خواند - هیچ تغییری در DB یا سیستم زنده نمی‌دهد.

نحوه‌ی اجرا:
    python simulate_filter_candidates.py
"""

import sqlite3

DB_NAME = "market_history.db"
SYMBOLS = ("اهرم", "شستا", "وبملت", "ذوب", "فملی", "شپنا", "خساپا")
SIGNAL_THRESHOLD = 65
CAP_SCORE = 60


def fetch_signals(cur):
    cur.execute("SELECT DISTINCT date FROM daily_predictions ORDER BY date ASC")
    dates = [r[0] for r in cur.fetchall()]
    placeholders = ",".join("?" * len(SYMBOLS))

    rows = []
    for i in range(len(dates) - 1):
        d0, d1 = dates[i], dates[i + 1]
        cur.execute(
            f"""
            SELECT t.symbol, t.date, t.pressure_score, t.buyer_power, t.is_buy_queue,
                   t.alpha_market, t.alpha_industry, t.vol_vs_avg,
                   t1.close_change_pct AS actual
            FROM daily_predictions t
            JOIN daily_predictions t1 ON t.symbol = t1.symbol AND t1.date = ?
            WHERE t.date = ? AND t.symbol IN ({placeholders})
            """,
            (d1, d0, *SYMBOLS),
        )
        rows.extend(cur.fetchall())
    return rows


def eval_rule(rows, name, condition_fn):
    orig_total = orig_win = 0
    orig_sum = 0.0
    new_total = new_win = 0
    new_sum = 0.0
    removed = []

    for r in rows:
        p = r["pressure_score"] or 0
        actual = r["actual"] or 0.0
        orig_signal = p >= SIGNAL_THRESHOLD
        if orig_signal:
            orig_total += 1
            orig_sum += actual
            if actual > 0:
                orig_win += 1

        flagged = condition_fn(r)
        new_p = min(p, CAP_SCORE) if flagged else p
        new_signal = new_p >= SIGNAL_THRESHOLD

        if new_signal:
            new_total += 1
            new_sum += actual
            if actual > 0:
                new_win += 1

        if orig_signal and not new_signal:
            removed.append((r["date"], r["symbol"], actual))

    print(f"\n📌 قانون: {name}")
    if orig_total:
        print(f"  قبل : n={orig_total:2d} | Win={orig_win / orig_total * 100:5.1f}% | Avg={orig_sum / orig_total:+.2f}%")
    if new_total:
        print(f"  بعد : n={new_total:2d} | Win={new_win / new_total * 100:5.1f}% | Avg={new_sum / new_total:+.2f}%")
    else:
        print("  بعد : هیچ سیگنالی باقی نموند!")
    if removed:
        print("  حذف‌شده‌ها:")
        for d, sym, actual in removed:
            tag = "✅ درست بود که حذف شد" if actual < 0 else "⚠️ برنده بود، از دست رفت"
            print(f"    {d} | {sym:8s} | بازده واقعی={actual:+.2f}% | {tag}")
    else:
        print("  هیچ سیگنالی حذف نشد.")


def run():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    rows = fetch_signals(cur)
    conn.close()

    print("=" * 78)
    print(f"مقایسه‌ی فرضیه‌های مختلف فیلتر روی {len(rows)} رکورد کل (قبل از فیلتر فشار)")
    print("=" * 78)

    # فرضیه‌ی فعلی (زنده در dashboard_generator.py)
    eval_rule(
        rows,
        "فعلی: buyer_power < 0.70 و is_buy_queue=False",
        lambda r: (r["buyer_power"] is not None and r["buyer_power"] < 0.70 and not r["is_buy_queue"]),
    )

    # فرضیه‌ی جدید: آستانه‌ی کمی بالاتر
    eval_rule(
        rows,
        "پیشنهادی: buyer_power < 0.75 و is_buy_queue=False",
        lambda r: (r["buyer_power"] is not None and r["buyer_power"] < 0.75 and not r["is_buy_queue"]),
    )

    # فرضیه‌ی ترکیبی: قدرت متوسط ولی ضعیف‌تر از صنعت خودش
    eval_rule(
        rows,
        "ترکیبی: buyer_power < 0.75 و alpha_industry < 0 و is_buy_queue=False",
        lambda r: (
            r["buyer_power"] is not None
            and r["buyer_power"] < 0.75
            and (r["alpha_industry"] or 0) < 0
            and not r["is_buy_queue"]
        ),
    )

    # فرضیه‌ی ترکیبی: قدرت متوسط + حجم زیر میانگین
    eval_rule(
        rows,
        "ترکیبی: buyer_power < 0.75 و vol_vs_avg < 1.0 و is_buy_queue=False",
        lambda r: (
            r["buyer_power"] is not None
            and r["buyer_power"] < 0.75
            and (r["vol_vs_avg"] or 0) < 1.0
            and not r["is_buy_queue"]
        ),
    )


if __name__ == "__main__":
    run()