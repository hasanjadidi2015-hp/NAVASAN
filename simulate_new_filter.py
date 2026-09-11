# simulate_new_filter.py
"""
این اسکریپت فقط می‌خواند (Read-Only) و هیچ تغییری در دیتابیس یا سیستم زنده
نمی‌دهد. هدفش اینه که قبل از فعال کردن فیلتر جدید "رشد بی‌پشتوانه" (خریدار
ضعیف بدون صف خرید)، اثرش رو روی داده‌های قبلاً ذخیره‌شده بسنجیم.

قانون شبیه‌سازی‌شده:
    اگر buyer_power < 0.70 و is_buy_queue=False بود، پرسشور نهایی (pressure_score)
    را به سقف 65 محدود کن (مثل همون رفتار "تله گاوی" فعلی، ولی مستقل از صف خرید).

نحوه‌ی اجرا:
    python simulate_new_filter.py
"""

import sqlite3

DB_NAME = "market_history.db"
SYMBOLS = ("اهرم", "شستا", "وبملت", "ذوب", "فملی", "شپنا", "خساپا")
BUYER_POWER_THRESHOLD = 0.70
CAP_SCORE = 60


def run():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT DISTINCT date FROM daily_predictions ORDER BY date ASC")
    dates = [r[0] for r in cur.fetchall()]
    placeholders = ",".join("?" * len(SYMBOLS))

    print("مقایسه‌ی سیگنال‌های فعلی (فشار≥۶۵) با سیگنال‌های شبیه‌سازی‌شده بعد از فیلتر «رشد بی‌پشتوانه»")
    print("=" * 88)

    orig_total = orig_win = 0
    orig_sum = 0.0
    new_total = new_win = 0
    new_sum = 0.0
    changed = []

    for i in range(len(dates) - 1):
        d0, d1 = dates[i], dates[i + 1]
        cur.execute(
            f"""
            SELECT t.symbol, t.pressure_score, t.buyer_power, t.is_buy_queue,
                   t.candle_label, t1.close_change_pct AS actual
            FROM daily_predictions t
            JOIN daily_predictions t1 ON t.symbol = t1.symbol AND t1.date = ?
            WHERE t.date = ? AND t.symbol IN ({placeholders})
            """,
            (d1, d0, *SYMBOLS),
        )
        for row in cur.fetchall():
            p = row["pressure_score"] or 0
            actual = row["actual"] or 0.0
            bp = row["buyer_power"]

            unsupported = (bp is not None and bp < BUYER_POWER_THRESHOLD and not row["is_buy_queue"])
            new_p = min(p, CAP_SCORE) if unsupported else p

            orig_signal = p >= 65
            new_signal = new_p >= 65

            if orig_signal:
                orig_total += 1
                orig_sum += actual
                if actual > 0:
                    orig_win += 1
            if new_signal:
                new_total += 1
                new_sum += actual
                if actual > 0:
                    new_win += 1

            if orig_signal != new_signal:
                changed.append((d0, row["symbol"], p, new_p, actual, unsupported))

    conn.close()

    print("\n📊 قبل از فیلتر جدید (وضعیت فعلی):")
    if orig_total:
        print(f"  n={orig_total} | Win Rate={orig_win / orig_total * 100:.1f}% | میانگین بازده={orig_sum / orig_total:+.2f}%")
    else:
        print("  سیگنالی نبود.")

    print("\n📊 بعد از اعمال فیلتر «رشد بی‌پشتوانه»:")
    if new_total:
        print(f"  n={new_total} | Win Rate={new_win / new_total * 100:.1f}% | میانگین بازده={new_sum / new_total:+.2f}%")
    else:
        print("  سیگنالی نبود.")

    print("\n🔄 سیگنال‌هایی که وضعیتشون (سیگنال / غیرسیگنال) تغییر کرد:")
    if not changed:
        print("  هیچ سیگنالی تغییر نکرد - یعنی این قانون روی این ۶ روز اصلاً اثری نداشته.")
    for d, sym, p_old, p_new, actual, unsup in changed:
        tag = "✅ درست بود که حذف شد" if actual < 0 else "⚠️ این یکی برنده بود و از دست رفت"
        print(f"  {d} | {sym:8s} | P قدیم={p_old:3d} -> P جدید={p_new:3d} | بازده واقعی={actual:+.2f}% | {tag}")


if __name__ == "__main__":
    run()