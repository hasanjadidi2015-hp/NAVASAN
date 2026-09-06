# snapshot_collector.py
"""
این اسکریپت باید جدا از dashboard_generator.py و در طول ساعات معاملاتی
(مثلاً از ۰۸:۵۵ تا ۱۲:۳۰) به‌صورت مداوم روشن بماند و هر چند دقیقه یک‌بار
وضعیت لحظه‌ای هر نماد را در جدول intraday_snapshots ذخیره کند.

بدون این اسنپ‌شات‌ها، تابع load_endgame_features در dashboard_generator.py
هیچ‌وقت داده‌ی کافی برای مقایسه‌ی "اول روز" با "آخر روز" پیدا نمی‌کند و
همیشه مقدار پیش‌فرض endgame_score=50 برمی‌گرداند.

نحوه‌ی اجرا (هر روز صبح، قبل از باز شدن بازار):
    python snapshot_collector.py

اسکریپت خودش تا ساعت پایان بازار (پیش‌فرض ۱۲:۳۰) صبر می‌کند و بعد خودکار
متوقف می‌شود. اگر می‌خواهی به‌صورت خودکار هر روز اجرا شود، آن را در
Windows Task Scheduler برای ساعت ۰۸:۵۵ هر روز کاری زمان‌بندی کن.
"""

import datetime
import sqlite3
import time

from collector import fetch_enriched_target_data, normalize_fa

DB_NAME = "market_history.db"


def _f(val, default=0.0) -> float:
    try:
        if val is None:
            return float(default)
        return float(val)
    except (TypeError, ValueError):
        return float(default)


def init_snapshot_table():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS intraday_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            time TEXT,
            symbol TEXT,
            last_price REAL,
            volume REAL,
            buy_q_vol REAL,
            sell_q_vol REAL,
            buyer_power REAL,
            buyer_capita REAL,
            real_buy_share REAL,
            last_change_pct REAL,
            UNIQUE(date, time, symbol)
        )
        """
    )
    conn.commit()
    conn.close()


def extract_snapshot_row(item: dict) -> dict | None:
    """
    همان منطق محاسبه‌ی buyer_power / buyer_capita / real_buy_share که در
    analyze_tomorrow_status (dashboard_generator.py) استفاده می‌شود، اما
    فقط بخش‌های لازم برای Endgame — بدون محاسبات کندل و فشار.
    """
    try:
        symbol = normalize_fa(item.get("lva", ""))
        if not symbol:
            return None

        yesterday = _f(item.get("py"))
        close_price = _f(item.get("pcl"))
        last_price = _f(item.get("pDrCotVal"))
        if last_price <= 0:
            last_price = _f(item.get("pdv"))
        if last_price <= 0:
            last_price = close_price
        if yesterday <= 0:
            return None

        last_change_pct = ((last_price - yesterday) / yesterday) * 100

        volume = _f(item.get("qtj"))
        if volume <= 0:
            volume = _f(item.get("qTotTran5J"))

        best = item.get("_best") or {}
        buy_q_vol = _f(best.get("buy_q_vol"))
        sell_q_vol = _f(best.get("sell_q_vol"))

        ct = item.get("_ct") or {}
        buy_i_vol = _f(ct.get("buy_i_vol"))
        sell_i_vol = _f(ct.get("sell_i_vol"))
        buy_i_val = _f(ct.get("buy_i_val"))
        sell_i_val = _f(ct.get("sell_i_val"))
        buy_count_i = _f(ct.get("buy_count_i"))
        sell_count_i = _f(ct.get("sell_count_i"))

        total_real = buy_i_vol + sell_i_vol
        real_buy_share = (buy_i_vol / total_real * 100) if total_real > 0 else 50.0

        px = last_price if last_price > 0 else close_price
        buyer_capita = seller_capita = 0.0
        if buy_count_i > 0 and buy_i_val > 0:
            buyer_capita = buy_i_val / (buy_count_i * 10_000_000)
        elif buy_count_i > 0 and buy_i_vol > 0:
            buyer_capita = (buy_i_vol * px) / (buy_count_i * 10_000_000)
        if sell_count_i > 0 and sell_i_val > 0:
            seller_capita = sell_i_val / (sell_count_i * 10_000_000)
        elif sell_count_i > 0 and sell_i_vol > 0:
            seller_capita = (sell_i_vol * px) / (sell_count_i * 10_000_000)

        buyer_power = (
            (buyer_capita / seller_capita)
            if seller_capita > 0
            else (2.0 if buyer_capita > 0 else 1.0)
        )

        return {
            "symbol": symbol,
            "last_price": last_price,
            "volume": volume,
            "buy_q_vol": buy_q_vol,
            "sell_q_vol": sell_q_vol,
            "buyer_power": round(buyer_power, 3),
            "buyer_capita": round(buyer_capita, 3),
            "real_buy_share": round(real_buy_share, 2),
            "last_change_pct": round(last_change_pct, 2),
        }
    except Exception:
        return None


def save_snapshot(rows: list):
    init_snapshot_table()
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    time_str = datetime.datetime.now().strftime("%H:%M:%S")
    saved = 0
    for r in rows:
        try:
            cur.execute(
                """
                INSERT OR REPLACE INTO intraday_snapshots (
                    date, time, symbol, last_price, volume,
                    buy_q_vol, sell_q_vol, buyer_power, buyer_capita,
                    real_buy_share, last_change_pct
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    today_str,
                    time_str,
                    r["symbol"],
                    r["last_price"],
                    r["volume"],
                    r["buy_q_vol"],
                    r["sell_q_vol"],
                    r["buyer_power"],
                    r["buyer_capita"],
                    r["real_buy_share"],
                    r["last_change_pct"],
                ),
            )
            saved += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    print(f"📸 اسنپ‌شات {time_str} — {saved} نماد ذخیره شد.")


def run_once():
    raw, _regime = fetch_enriched_target_data(max_workers=6)
    if not raw:
        print("❌ دیتا نیامد.")
        return
    rows = [extract_snapshot_row(item) for item in raw]
    rows = [r for r in rows if r]
    save_snapshot(rows)


def run_loop(interval_minutes: int = 20, start: str = "08:55", end: str = "12:30"):
    """
    هر interval_minutes دقیقه یک اسنپ‌شات می‌گیرد، فقط بین ساعت start و end.
    این اسکریپت باید صبح قبل از باز شدن بازار اجرا شود و تا پایان بازار روشن بماند.
    """
    print(f"🚀 جمع‌آوری اسنپ‌شات هر {interval_minutes} دقیقه، بین ساعت {start} تا {end}")
    while True:
        now = datetime.datetime.now().strftime("%H:%M")
        if now < start:
            time.sleep(15)
            continue
        if now > end:
            print("⏹ ساعت پایان رسید، جمع‌آوری متوقف شد.")
            break
        run_once()
        time.sleep(interval_minutes * 60)


if __name__ == "__main__":
    run_loop()