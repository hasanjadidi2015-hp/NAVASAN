# backtest.py
import os
import sqlite3

DB_NAME = "market_history.db"

# فقط این نمادها در بک‌تست در نظر گرفته می‌شوند
SYMBOLS = ("اهرم", "شستا", "وبملت", "ذوب", "فملی", "شپنا", "خساپا")


def compute_stats(returns):
    """
    آمار پیشرفته روی یک لیست بازده (به درصد).
    ترتیب لیست باید زمانی (تاریخ) باشد تا Max Drawdown معنی‌دار باشد.
    """
    if not returns:
        return None

    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]

    win_rate = len(wins) / len(returns) * 100
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    win_loss_ratio = (avg_win / abs(avg_loss)) if avg_loss != 0 else float("inf")

    # منحنی سرمایه فرضی (شروع از ۱۰۰) برای محاسبه‌ی حداکثر افت پیاپی
    equity = 100.0
    peak = equity
    max_dd = 0.0
    for r in returns:
        equity *= (1 + r / 100.0)
        peak = max(peak, equity)
        dd = (peak - equity) / peak * 100
        max_dd = max(max_dd, dd)

    return {
        "n": len(returns),
        "win_rate": win_rate,
        "avg_return": sum(returns) / len(returns),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "win_loss_ratio": win_loss_ratio,
        "max_drawdown": max_dd,
    }


def print_stats_block(title, stats):
    print(f"\n{title}")
    if not stats:
        print("  داده‌ای برای محاسبه نبود.")
        return
    wl_txt = f"{stats['win_loss_ratio']:.2f}" if stats["win_loss_ratio"] != float("inf") else "∞ (بدون ضرر)"
    print(f"  تعداد نمونه       : {stats['n']}")
    print(f"  Win Rate          : {stats['win_rate']:.1f}%")
    print(f"  میانگین بازده     : {stats['avg_return']:+.2f}%")
    print(f"  میانگین سود برنده : {stats['avg_win']:+.2f}%")
    print(f"  میانگین ضرر بازنده: {stats['avg_loss']:+.2f}%")
    print(f"  نسبت سود/ضرر      : {wl_txt}")
    print(f"  حداکثر افت پیاپی  : {stats['max_drawdown']:.2f}%  (روی منحنی سرمایه‌ی فرضی)")


def get_index_benchmark(cur, dates):
    """
    بازده فردای شاخص کل را از ستون market_return همان جدول daily_predictions
    می‌خواند — این ستون از قبل توسط dashboard_generator.py (regime_info) پر می‌شود،
    پس نیازی به جدول یا منبع داده‌ی جداگانه نیست.
    """
    bench_returns = []
    for i in range(len(dates) - 1):
        d1 = dates[i + 1]
        cur.execute(
            "SELECT market_return FROM daily_predictions WHERE date = ? LIMIT 1",
            (d1,),
        )
        row = cur.fetchone()
        if row and row[0] is not None:
            bench_returns.append(row[0])
    return bench_returns


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

    symbol_placeholders = ",".join("?" * len(SYMBOLS))

    print("\n" + "=" * 64)
    print(f"📊 بک‌تست روزبه‌روز (سیگنال روز T  →  بازدهی واقعی روز T+1)  |  نمادها: {', '.join(SYMBOLS)}")
    print("=" * 64)

    total = win = 0
    sum_ret = 0.0
    signal_returns = []  # برای Win/Loss Ratio و Max Drawdown، به ترتیب زمانی

    for i in range(len(dates) - 1):
        d0, d1 = dates[i], dates[i + 1]
        if has_endgame:
            sql = f"""
                SELECT t.symbol, t.prediction, t.pressure_score, t.endgame_score,
                       t1.close_change_pct
                FROM daily_predictions t
                JOIN daily_predictions t1
                  ON t.symbol = t1.symbol AND t1.date = ?
                WHERE t.date = ? AND t.symbol IN ({symbol_placeholders})
            """
        else:
            sql = f"""
                SELECT t.symbol, t.prediction, t.pressure_score, 50,
                       t1.close_change_pct
                FROM daily_predictions t
                JOIN daily_predictions t1
                  ON t.symbol = t1.symbol AND t1.date = ?
                WHERE t.date = ? AND t.symbol IN ({symbol_placeholders})
            """
        cur.execute(sql, (d1, d0, *SYMBOLS))
        rows = cur.fetchall()
        if not rows:
            continue

        print(f"\n🗓 {d0} → نتیجه در {d1}")
        day_signals = 0
        for symbol, pred, pressure, endgame, actual in rows:
            pressure = pressure or 0
            endgame = endgame or 50
            actual = actual or 0.0

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

            if pressure < 65:
                continue

            day_signals += 1
            total += 1
            sum_ret += actual
            signal_returns.append(actual)
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

    # متریک‌های پیشرفته روی همان سیگنال‌ها
    print_stats_block("📈 متریک‌های پیشرفته سیگنال‌های فشار ≥ ۶۵", compute_stats(signal_returns))

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

    # بنچمارک شاخص کل (اگر جدول index_history موجود باشد)
    print("\n" + "=" * 64)
    print("⚖️  مقایسه با بنچمارک (شاخص کل)")
    print("=" * 64)
    bench_returns = get_index_benchmark(cur, dates)
    if not bench_returns:
        print("جدول index_history موجود است ولی داده‌ای برای این بازه ثبت نشده.")
    else:
        bench_avg = sum(bench_returns) / len(bench_returns)
        print(f"میانگین بازده فردای شاخص کل در همین بازه: {bench_avg:+.2f}%  (n={len(bench_returns)})")
        if total > 0:
            alpha = (sum_ret / total) - bench_avg
            print(f"آلفای مدل نسبت به شاخص (میانگین سیگنال منهای میانگین شاخص): {alpha:+.2f}%")

    conn.close()
    print("\nنکته: با افزایش روزهای ذخیره، آمار قابل‌اعتمادتر می‌شود (هدف: ۳۰-۴۰ روز).")


if __name__ == "__main__":
    run_backtest()