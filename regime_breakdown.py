# regime_breakdown.py
"""
بررسی اینکه آیا Win Rate و بازده سیگنال‌ها بسته به رژیم کل بازار در روز
صدور سیگنال (ستون regime در daily_predictions: bull/bear/neutral) فرق
می‌کند - برای تست فرضیه‌ی «باخت‌ها در روزهای رژیم منفی بیشترند».

نحوه‌ی اجرا:
    python regime_breakdown.py
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

    by_regime = {}

    for i in range(len(dates) - 1):
        d0, d1 = dates[i], dates[i + 1]
        cur.execute(
            f"""
            SELECT t.symbol, t.pressure_score, t.regime, t.market_return,
                   t1.close_change_pct AS actual
            FROM daily_predictions t
            JOIN daily_predictions t1 ON t.symbol = t1.symbol AND t1.date = ?
            WHERE t.date = ? AND t.symbol IN ({placeholders})
            """,
            (d1, d0, *SYMBOLS),
        )
        for row in cur.fetchall():
            if (row["pressure_score"] or 0) < SIGNAL_THRESHOLD:
                continue
            regime = row["regime"] or "نامشخص"
            by_regime.setdefault(regime, []).append(row["actual"] or 0.0)

    conn.close()

    print("=" * 70)
    print("📊 عملکرد سیگنال‌ها (فشار>=65) بر اساس رژیم بازار در روز صدور سیگنال")
    print("=" * 70)
    print(f"{'رژیم':12s} | {'تعداد':>6s} | {'Win Rate':>9s} | {'میانگین بازده':>14s}")
    print("-" * 70)
    for regime, rets in sorted(by_regime.items(), key=lambda x: -len(x[1])):
        n = len(rets)
        win = sum(1 for r in rets if r > 0)
        wr = win / n * 100
        avg = sum(rets) / n
        print(f"{regime:12s} | {n:6d} | {wr:8.1f}% | {avg:+13.2f}%")

    print("\nنکته: اگه Win Rate رژیم 'bear' به‌وضوح پایین‌تر از بقیه باشه،")
    print("یعنی حتی سیگنال قوی روی یک نماد هم در روزهای منفی کل بازار کمتر قابل‌اعتماده.")


if __name__ == "__main__":
    run()