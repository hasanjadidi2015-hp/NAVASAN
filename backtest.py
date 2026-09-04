# backtest.py
import os
import sqlite3
from collections import defaultdict

DB_NAME = "market_history.db"


def run_backtest():
    if not os.path.exists(DB_NAME):
        print("❌ فایل market_history.db پیدا نشد. اول dashboard را چند روز اجرا کن.")
        return

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='daily_predictions'")
    if not cur.fetchone():
        print("❌ جدول daily_predictions وجود ندارد.")
        conn.close()
        return

    cur.execute("SELECT DISTINCT date FROM daily_predictions ORDER BY date ASC")
    dates = [r[0] for r in cur.fetchall()]
    print(f"📅 تعداد روزهای ذخیره‌شده: {len(dates)}")
    if len(dates) < 2:
        print("⚠️ برای بک‌تست حداقل ۲ روز معاملاتی لازم است.")
        print("هر روز بعد از بازار: python dashboard_generator.py")
        conn.close()
        return

    # تشخیص ستون endgame
    cols = {r[1] for r in cur.execute("PRAGMA table_info(daily_predictions)").fetchall()}
    has_endgame = "endgame_score" in cols

    buckets = {
        "pressure>=80": [],
        "pressure_65_79": [],
        "pressure_50_64": [],
        "pressure<50": [],
    }
    if has_endgame:
        buckets["endgame>=65 & pressure>=65"] = []
        buckets["endgame<=35"] = []

    print("\n" + "=" * 64)
    print("📊 بک‌تست روزبه‌روز (سیگنال روز T  →  بازدهی واقعی روز T+1)")
    print("=" * 64)

    total = win = 0
    sum_ret = 0.0

    for i in range(len(dates) - 1):
        d0, d1 = dates[i], dates[i + 1]
        if has_endgame:
            sql = """
                SELECT t.symbol, t.prediction, t.pressure_score, t.endgame_score,
                       t1.close_change_pct
                FROM daily_predictions t
                JOIN daily_predictions t1
                  ON t.symbol = t1.symbol AND t1.date = ?
                WHERE t.date = ?
            """
        else:
            sql = """
                SELECT t.symbol, t.prediction, t.pressure_score, 50,
                       t1.close_change_pct
                FROM daily_predictions t
                JOIN daily_predictions t1
                  ON t.symbol = t1.symbol AND t1.date = ?
                WHERE t.date = ?
            """
        cur.execute(sql, (d1, d0))
        rows = cur.fetchall()
        if not rows:
            continue

        print(f"\n🗓 {d0} → نتیجه در {d1}")
        day_signals = 0
        for symbol, pred, pressure, endgame, actual in rows:
            pressure = pressure or 0
            endgame = endgame or 50
            actual = actual or 0.0

            # همه نمونه‌ها برای آمار bucket
            sample = actual
            if pressure >= 80:
                buckets["pressure>=80"].append(sample)
            elif pressure >= 65:
                buckets["pressure_65_79"].append(sample)
            elif pressure >= 50:
                buckets["pressure_50_64"].append(sample)
            else:
                buckets["pressure<50"].append(sample)

            if has_endgame:
                if endgame >= 65 and pressure >= 65:
                    buckets["endgame>=65 & pressure>=65"].append(sample)
                if endgame <= 35:
                    buckets["endgame<=35"].append(sample)

            # سیگنال معاملاتی: فشار بالا
            if pressure < 65:
                continue

            day_signals += 1
            total += 1
            sum_ret += actual
            ok = actual > 0
            if ok:
                win += 1
            mark = "✅" if ok else "❌"
            eg_txt = f" | EG={endgame}" if has_endgame else ""
            print(
                f"  {mark} {symbol:10s} | P={pressure:3.0f}{eg_txt} | "
                f"بازده فردا={actual:+.2f}% | {pred}"
            )

        if day_signals == 0:
            print("  (سیگنال قوی با فشار≥65 نبود)")

    print("\n" + "=" * 64)
    print("🎯 خلاصه عملکرد سیگنال‌های فشار ≥ ۶۵")
    print("=" * 64)
    if total > 0:
        print(f"تعداد سیگنال: {total}")
        print(f"Win Rate (بازده فردا > 0): {win / total * 100:.1f}%")
        print(f"میانگین بازده فردا: {sum_ret / total:+.2f}%")
    else:
        print("سیگنالی برای ارزیابی نبود.")

    print("\n" + "=" * 64)
    print("📦 دقت بر اساس سطح امتیاز (همه نمونه‌ها)")
    print("=" * 64)
    for name, arr in buckets.items():
        if not arr:
            print(f"{name:32s} | n=0")
            continue
        wr = sum(1 for x in arr if x > 0) / len(arr) * 100
        avg = sum(arr) / len(arr)
        print(f"{name:32s} | n={len(arr):3d} | Win={wr:5.1f}% | AvgRet={avg:+.2f}%")

    conn.close()
    print("\nنکته: با افزایش روزهای ذخیره، آمار قابل‌اعتمادتر می‌شود (هدف: ۱۰–۲۰ روز).")


if __name__ == "__main__":
    run_backtest()