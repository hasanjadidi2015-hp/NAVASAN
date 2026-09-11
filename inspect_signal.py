# inspect_signal.py
"""
بررسی دقیق یک سیگنال خاص (یک نماد در یک روز مشخص) با نمایش تمام
ستون‌های ذخیره‌شده در daily_predictions - برای فهمیدن چرا یک سیگنال
با وجود فشار بالا، فردا نتیجه‌ی برعکس داده است.

نحوه‌ی اجرا:
    python inspect_signal.py <تاریخ> <نماد>

مثال:
    python inspect_signal.py 2026-09-08 خساپا
"""

import sqlite3
import sys

DB_NAME = "market_history.db"


def inspect(date_str: str, symbol: str):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM daily_predictions WHERE date = ? AND symbol = ?",
        (date_str, symbol),
    )
    row = cur.fetchone()
    if not row:
        print(f"❌ رکوردی برای {symbol} در تاریخ {date_str} پیدا نشد.")
        conn.close()
        return

    print(f"\n{'=' * 60}")
    print(f"🔍 جزئیات کامل سیگنال: {symbol} | {date_str}")
    print(f"{'=' * 60}")
    for key in row.keys():
        print(f"  {key:24s} : {row[key]}")

    # برای مقایسه، بقیه‌ی نمادهای همون روز رو هم کنار هم نشون بده
    print(f"\n{'=' * 60}")
    print(f"📊 مقایسه با بقیه‌ی نمادهای همون روز ({date_str})")
    print(f"{'=' * 60}")
    cur.execute(
        """
        SELECT symbol, pressure_score, endgame_score, buyer_power,
               alpha_market, is_buy_queue, candle_label, option_label
        FROM daily_predictions
        WHERE date = ?
        ORDER BY pressure_score DESC
        """,
        (date_str,),
    )
    for r in cur.fetchall():
        marker = " <== همین سیگنال" if r["symbol"] == symbol else ""
        print(
            f"  {r['symbol']:8s} | P={r['pressure_score']:3d} | EG={r['endgame_score']:3d} | "
            f"Power={r['buyer_power']:.2f} | Alpha={r['alpha_market']:+.2f}% | "
            f"BuyQ={bool(r['is_buy_queue'])} | {r['candle_label']}{marker}"
        )

    conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("استفاده: python inspect_signal.py <تاریخ> <نماد>")
        print("مثال:   python inspect_signal.py 2026-09-08 خساپا")
        sys.exit(1)
    inspect(sys.argv[1], sys.argv[2])