# backtest.py
import os
import sqlite3

DB_NAME = "market_history.db"

# حداقل رشد سهم پایه برای اینکه پریمیوم آپشن وارد سود واقعی شود (۱.۸٪)
MIN_STOCK_RETURN_FOR_OPTION_WIN = 1.8


def run_backtest():
  if not os.path.exists(DB_NAME):
    print("❌ فایل market_history.db پیدا نشد.")
    return

  conn = sqlite3.connect(DB_NAME)
  cur = conn.cursor()

  cur.execute(
      "SELECT name FROM sqlite_master WHERE type='table' AND"
      " name='daily_predictions'"
  )
  if not cur.fetchone():
    print("❌ جدول daily_predictions وجود ندارد.")
    conn.close()
    return

  cur.execute("SELECT DISTINCT date FROM daily_predictions ORDER BY date ASC")
  dates = [r[0] for r in cur.fetchall()]
  print(f"📅 تعداد روزهای ذخیره‌شده: {len(dates)}")
  if len(dates) < 2:
    print("⚠️ برای بک‌تست حداقل ۲ روز معاملاتی لازم است.")
    conn.close()
    return

  print("\n" + "=" * 70)
  print(
      "📊 بک‌تست واقع‌بینانه آپشن (سود واقعی پریمیوم نیاز به رشد ≥"
      f" +{MIN_STOCK_RETURN_FOR_OPTION_WIN}% سهم دارد)"
  )
  print("=" * 70)

  total_signals = 0
  option_wins = 0
  total_return = 0.0

  for i in range(len(dates) - 1):
    d0, d1 = dates[i], dates[i + 1]
    sql = """
            SELECT t.symbol, t.prediction, t.pressure_score, t.endgame_score,
                   t1.close_change_pct
            FROM daily_predictions t
            JOIN daily_predictions t1 ON t.symbol = t1.symbol AND t1.date = ?
            WHERE t.date = ? AND t.pressure_score >= 80
        """
    cur.execute(sql, (d1, d0))
    rows = cur.fetchall()
    if not rows:
      continue

    print(f"\n🗓 {d0} → نتیجه واقعی در {d1}:")
    for symbol, pred, pressure, endgame, actual in rows:
      pressure = pressure or 0
      endgame = endgame or 50
      actual = actual or 0.0

      total_signals += 1
      total_return += actual

      # 🎯 برد واقعی آپشن: رشد سهم باید بالای ۱.۸٪ باشد
      is_option_win = actual >= MIN_STOCK_RETURN_FOR_OPTION_WIN

      if is_option_win:
        option_wins += 1
        mark = "✅ سود آپشن"
      else:
        mark = "❌ زیان/سوخت آپشن"

      print(
          f"  {mark} | {symbol:8s} | P={pressure:3d} | EG={endgame:3d} | رشد"
          f" سهم={actual:+5.2f}%"
      )

  print("\n" + "=" * 70)
  print("🎯 خلاصه عملکرد واقعی برای پریمیوم اختیار معامله (P >= 80)")
  print("=" * 70)
  if total_signals > 0:
    win_rate = (option_wins / total_signals) * 100
    avg_ret = total_return / total_signals
    print(f"تعداد کل سیگنال‌ها (P >= 80) : {total_signals}")
    print(
      f"تعداد موفقیت واقعی آپشن    : {option_wins} (رشد سهم ≥"
      f" +{MIN_STOCK_RETURN_FOR_OPTION_WIN}%)"
    )
    print(f"وین‌ریت واقعی سود پریمیوم    : {win_rate:.1f}%")
    print(f"میانگین رشد سهم پایه        : {avg_ret:+5.2f}%")
  else:
    print("هیچ سیگنالی با فشار بالای ۸۰ یافت نشد.")

  conn.close()


if __name__ == "__main__":
  run_backtest()