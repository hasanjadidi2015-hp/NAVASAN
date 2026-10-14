# find_duplicate_days.py
"""
روزهایی که توی daily_predictions ثبت شدن ولی در واقع تکرار قیمت‌های روز قبلی
هستن (مثلاً اجرای dashboard_generator.py در پنجشنبه/جمعه یا روز تعطیل رسمی،
وقتی بازار بسته‌ست و Market Watch همون قیمت‌های آخرین روز کاری رو برمی‌گردونه) رو پیدا می‌کنه.

چرا مهمه: بک‌تست «سیگنال روز T» رو با ستون close_change_pct «روز بعد ثبت‌شده» مقایسه می‌کنه.
اگه ردیف روز بعد تکراریه، به‌جای بازده فردا، بازده همون روز T مقایسه می‌شه
(نشت اطلاعات از آینده) و نتیجه‌ی بک‌تست الکی خوب می‌شه.

اجرا:
    python find_duplicate_days.py            # فقط گزارش می‌ده، چیزی تغییر نمی‌کنه
    python find_duplicate_days.py --delete   # بعد از گرفتن بک‌آپ، ردیف‌های تکراری رو حذف می‌کنه
"""

import datetime
import shutil
import sqlite3
import sys

DB_NAME = "market_history.db"
MIN_COMMON_SYMBOLS = 5      # حداقل تعداد نماد مشترک برای مقایسه
DUPLICATE_RATIO = 0.90      # اگه ≥۹۰٪ نمادها دقیقاً قیمت پایانی و درصد تغییر یکسان داشتن => تکراری
WEEKDAYS_FA = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]


def load_day(cur, date_str):
    cur.execute(
        "SELECT symbol, close_price, close_change_pct FROM daily_predictions WHERE date = ?",
        (date_str,),
    )
    return {r[0]: (r[1], r[2]) for r in cur.fetchall()}


def main():
    do_delete = "--delete" in sys.argv

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT date FROM daily_predictions ORDER BY date ASC")
    dates = [r[0] for r in cur.fetchall()]
    print(f"📅 تعداد روزهای ثبت‌شده: {len(dates)}\n")

    flagged = []
    for prev, cur_date in zip(dates, dates[1:]):
        a = load_day(cur, prev)
        b = load_day(cur, cur_date)
        common = [s for s in b if s in a]
        if len(common) < MIN_COMMON_SYMBOLS:
            continue
        same = sum(1 for s in common if a[s] == b[s])
        ratio = same / len(common)
        if ratio >= DUPLICATE_RATIO:
            wd = WEEKDAYS_FA[datetime.date.fromisoformat(cur_date).weekday()]
            flagged.append((cur_date, wd, prev, same, len(common)))

    if not flagged:
        print("✅ هیچ روز تکراری پیدا نشد.")
        conn.close()
        return

    print("⚠️ روزهای مشکوک به تکراری بودن (قیمت‌ها دقیقاً مثل روز قبلشونه):")
    for d, wd, prev, same, n in flagged:
        cur.execute("SELECT COUNT(*) FROM daily_predictions WHERE date = ?", (d,))
        rows = cur.fetchone()[0]
        print(f"  {d} ({wd}) | شبیه {prev} | {same}/{n} نماد یکسان | {rows} ردیف توی دیتابیس")

    if not do_delete:
        print("\nبرای حذف این ردیف‌ها (با بک‌آپ خودکار): python find_duplicate_days.py --delete")
        conn.close()
        return

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = DB_NAME.replace(".db", f"_backup_{stamp}.db")
    conn.close()
    shutil.copy(DB_NAME, backup)
    print(f"\n💾 بک‌آپ گرفته شد: {backup}")

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    total = 0
    for d, _wd, _prev, _same, _n in flagged:
        cur.execute("DELETE FROM daily_predictions WHERE date = ?", (d,))
        total += cur.rowcount
    conn.commit()
    conn.close()
    print(f"🗑 {total} ردیف از daily_predictions حذف شد. حالا python backtest.py رو دوباره بزن.")


if __name__ == "__main__":
    main()