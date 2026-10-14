# live_tracker.py
"""
رصد زنده دقایق پایانی بازار
پیش‌فرض: ۱۲:۰۰ تا ۱۲:۳۵ — هر ۵ دقیقه یک Snapshot
"""
import datetime
import sqlite3
import time

from collector import fetch_enriched_target_data, normalize_fa

DB_NAME = "market_history.db"

# ساعت بازار ایران (قابل تغییر)
START_HOUR, START_MIN = 11, 45
END_HOUR, END_MIN = 12, 40
INTERVAL_SEC = 5 * 60  # هر ۵ دقیقه


def init_snapshot_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS intraday_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            time TEXT,
            ts TEXT,
            symbol TEXT,
            last_price REAL,
            close_price REAL,
            volume REAL,
            buy_q_vol REAL,
            sell_q_vol REAL,
            buy_q_price REAL,
            sell_q_price REAL,
            buyer_power REAL,
            buyer_capita REAL,
            seller_capita REAL,
            real_buy_share REAL,
            buy_count_i REAL,
            sell_count_i REAL,
            last_change_pct REAL,
            close_change_pct REAL,
            UNIQUE(date, time, symbol)
        )
        """
    )
    conn.commit()
    conn.close()


def _f(v, d=0.0):
    try:
        return float(v if v is not None else d)
    except Exception:
        return float(d)


def capture_once() -> int:
    """یک اسنپ‌شات از همه نمادهای هدف."""
    init_snapshot_db()
    raw, _regime = fetch_enriched_target_data(max_workers=6)
    if not raw:
        print("❌ اسنپ‌شات خالی — دیتا نیامد")
        return 0

    now = datetime.datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")
    ts = now.strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    saved = 0

    for item in raw:
        try:
            symbol = normalize_fa(item.get("lva", ""))
            if not symbol:
                continue

            yesterday = _f(item.get("py"))
            close_price = _f(item.get("pcl"))
            last_price = _f(item.get("pf"))
            if last_price <= 0:
                last_price = _f(item.get("pDrCotVal"))
            if last_price <= 0:
                last_price = close_price

            volume = _f(item.get("qtj"))
            if volume <= 0:
                volume = _f(item.get("qTotTran5J"))

            best = item.get("_best") or {}
            buy_q_vol = _f(best.get("buy_q_vol"))
            sell_q_vol = _f(best.get("sell_q_vol"))
            buy_q_price = _f(best.get("buy_q_price"))
            sell_q_price = _f(best.get("sell_q_price"))

            ct = item.get("_ct") or {}
            buy_i_vol = _f(ct.get("buy_i_vol"))
            sell_i_vol = _f(ct.get("sell_i_vol"))
            buy_i_val = _f(ct.get("buy_i_val"))
            sell_i_val = _f(ct.get("sell_i_val"))
            buy_count_i = _f(ct.get("buy_count_i"))
            sell_count_i = _f(ct.get("sell_count_i"))

            total_real = buy_i_vol + sell_i_vol
            real_buy_share = (buy_i_vol / total_real * 100) if total_real > 0 else 50.0

            buyer_capita = seller_capita = 0.0
            if buy_count_i > 0 and buy_i_val > 0:
                buyer_capita = buy_i_val / (buy_count_i * 10_000_000)
            elif buy_count_i > 0 and buy_i_vol > 0 and last_price > 0:
                buyer_capita = (buy_i_vol * last_price) / (buy_count_i * 10_000_000)

            if sell_count_i > 0 and sell_i_val > 0:
                seller_capita = sell_i_val / (sell_count_i * 10_000_000)
            elif sell_count_i > 0 and sell_i_vol > 0 and last_price > 0:
                seller_capita = (sell_i_vol * last_price) / (sell_count_i * 10_000_000)

            buyer_power = (
                (buyer_capita / seller_capita)
                if seller_capita > 0
                else (2.0 if buyer_capita > 0 else 1.0)
            )

            last_change_pct = ((last_price - yesterday) / yesterday * 100) if yesterday > 0 else 0
            close_change_pct = ((close_price - yesterday) / yesterday * 100) if yesterday > 0 else 0

            cur.execute(
                """
                INSERT OR REPLACE INTO intraday_snapshots (
                    date, time, ts, symbol,
                    last_price, close_price, volume,
                    buy_q_vol, sell_q_vol, buy_q_price, sell_q_price,
                    buyer_power, buyer_capita, seller_capita, real_buy_share,
                    buy_count_i, sell_count_i, last_change_pct, close_change_pct
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    date_str, time_str, ts, symbol,
                    last_price, close_price, volume,
                    buy_q_vol, sell_q_vol, buy_q_price, sell_q_price,
                    buyer_power, buyer_capita, seller_capita, real_buy_share,
                    buy_count_i, sell_count_i, last_change_pct, close_change_pct,
                ),
            )
            saved += 1
        except Exception:
            continue

    conn.commit()
    conn.close()
    print(f"✅ Snapshot {date_str} {time_str} | {saved} نماد ذخیره شد")
    return saved


def within_window(now: datetime.datetime) -> bool:
    start = now.replace(hour=START_HOUR, minute=START_MIN, second=0, microsecond=0)
    end = now.replace(hour=END_HOUR, minute=END_MIN, second=0, microsecond=0)
    return start <= now <= end


def run_live_loop():
    print("=" * 60)
    print("📡 Navasanj Live Tracker | رصد دقایق پایانی")
    print(f"⏱ بازه: {START_HOUR:02d}:{START_MIN:02d} تا {END_HOUR:02d}:{END_MIN:02d}")
    print(f"🔁 فاصله: هر {INTERVAL_SEC // 60} دقیقه")
    print("=" * 60)

    last_slot = None
    # اگر خارج از بازه اجرا شد، حداقل یک اسنپ‌شات تستی بگیر
    now = datetime.datetime.now()
    if not within_window(now):
        print("⚠️ الان خارج از بازه پایانی بازار هستی.")
        print("یک Snapshot تستی همین الان گرفته می‌شود...")
        capture_once()
        print("برای رصد واقعی، این فایل را قبل از ۱۲:۰۰ اجرا کن و باز بگذار.")
        return

    print("🟢 داخل بازه — شروع پایش...")
    while True:
        now = datetime.datetime.now()
        if not within_window(now):
            print("🏁 پایان بازه پایانی بازار.")
            break

        # اسلات ۵ دقیقه‌ای: 12:00, 12:05, ...
        slot_min = (now.minute // 5) * 5
        slot = f"{now.hour:02d}:{slot_min:02d}"
        if slot != last_slot:
            print(f"\n📸 گرفتن اسنپ‌شات اسلات {slot} ...")
            try:
                capture_once()
            except Exception as e:
                print(f"❌ خطا در اسنپ‌شات: {e}")
            last_slot = slot

        time.sleep(20)


if __name__ == "__main__":
    run_live_loop()