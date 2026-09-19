# per_symbol_stats.py
"""
شکستن آمار Win Rate / میانگین بازده به تفکیک هر نماد، برای بررسی اینکه آیا
یک نماد خاص (مثل خساپا) واقعاً نسبت به بقیه ضعیف‌تر عمل می‌کند یا این فقط
نوسان طبیعی نمونه‌ی کوچک است.

نحوه‌ی اجرا:
    python per_symbol_stats.py
"""

import sqlite3

DB_NAME = "market_history.db"
SYMBOLS = ("اهرم", "شستا", "وبملت", "ذوب", "فملی", "شپنا", "خساپا")
SIGNAL_THRESHOLD = 65


def run():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT DISTINCT date FROM daily_predictions ORDER BY date ASC")
    dates = [r[0] for r in cur.fetchall()]
    placeholders = ",".join("?" * len(SYMBOLS))

    per_symbol = {s: [] for s in SYMBOLS}

    for i in range(len(dates) - 1):
        d0, d1 = dates[i], dates[i + 1]
        cur.execute(
            f"""
            SELECT t.symbol, t.pressure_score, t1.close_change_pct AS actual
            FROM daily_predictions t
            JOIN daily_predictions t1 ON t.symbol = t1.symbol AND t1.date = ?
            WHERE t.date = ? AND t.symbol IN ({placeholders})
            """,
            (d1, d0, *SYMBOLS),
        )
        for row in cur.fetchall():
            if (row["pressure_score"] or 0) >= SIGNAL_THRESHOLD:
                per_symbol[row["symbol"]].append(row["actual"] or 0.0)

    conn.close()

    print("=" * 70)
    print("📊 آمار هر نماد (فقط سیگنال‌های فشار >= 65)")
    print("=" * 70)
    print(f"{'نماد':10s} | {'تعداد':>6s} | {'Win Rate':>9s} | {'میانگین بازده':>14s}")
    print("-" * 70)

    summary = []
    for sym in SYMBOLS:
        rets = per_symbol[sym]
        if not rets:
            print(f"{sym:10s} | {'0':>6s} | {'-':>9s} | {'-':>14s}")
            continue
        n = len(rets)
        win = sum(1 for r in rets if r > 0)
        wr = win / n * 100
        avg = sum(rets) / n
        summary.append((sym, n, wr, avg))
        print(f"{sym:10s} | {n:6d} | {wr:8.1f}% | {avg:+13.2f}%")

    print("\nنکته: با n کم (کمتر از ۱۰-۱۵)، تفاوت‌ها هنوز می‌تونن نویز آماری باشن،")
    print("نه لزوماً ضعف واقعی اون نماد.")


if __name__ == "__main__":
    run()