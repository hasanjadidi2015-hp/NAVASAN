# dashboard_generator.py
import datetime
import os
import re
import sqlite3
import webbrowser

from collector import TARGET_SYMBOLS, fetch_enriched_target_data, normalize_fa
from ml_engine import NavasanjML
from option_pricing import evaluate_option_contract

DB_NAME = "market_history.db"


def _f(val, default=0.0) -> float:
  try:
    if val is None:
      return float(default)
    return float(val)
  except (TypeError, ValueError):
    return float(default)


def jalali_to_gregorian(jy: int, jm: int, jd: int) -> tuple[int, int, int]:
  jy += 1595
  days = -355668 + (365 * jy) + (jy // 33) * 8 + ((jy % 33) + 3) // 4 + jd
  if jm < 7:
    days += (jm - 1) * 31
  else:
    days += (jm - 7) * 30 + 186
  gy = 400 * (days // 146097)
  days %= 146097
  if days > 36524:
    days -= 1
    gy += 100 * (days // 36524)
    days %= 36524
    if days >= 365:
      days += 1
  gy += 4 * (days // 1461)
  days %= 1461
  if days > 365:
    gy += (days - 1) // 365
    days = (days - 1) % 365
  gd = days + 1
  sal_a = [
      0,
      31,
      29 if (gy % 4 == 0 and gy % 100 != 0) or (gy % 400 == 0) else 28,
      31,
      30,
      31,
      30,
      31,
      31,
      30,
      31,
      30,
      31,
  ]
  gm = 0
  for i in range(1, 13):
    if gd <= sal_a[i]:
      gm = i
      break
    gd -= sal_a[i]
  return gy, gm, gd


def get_days_to_expiration(lvc_text: str) -> int:
  if not lvc_text:
    return 30
  match = re.search(
      r"(1[34]\d{2})[/\.-](0?[1-9]|1[0-2])[/\.-](0?[1-9]|[12]\d|3[01])",
      lvc_text,
  )
  if not match:
    return 30
  try:
    jy, jm, jd = int(match.group(1)), int(match.group(2)), int(match.group(3))
    gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
    expire_date = datetime.date(gy, gm, gd)
    today = datetime.date.today()
    return (expire_date - today).days
  except Exception:
    return 30


OPTION_PREFIX_MAP = {
    "اهرم": ("ضهرم", "طهرم", ["اهرم", "هرم"]),
    "فملی": ("ضملی", "طملی", ["فملی", "فملي", "ملی", "ملي"]),
    "وبملت": ("ضملت", "طملت", ["وبملت", "ملت"]),
    "شستا": ("ضستا", "طستا", ["شستا", "ستا"]),
    "شپنا": ("ضپنا", "طپنا", ["شپنا", "پنا"]),
    "خساپا": ("ضسپا", "طسپا", ["خساپا", "ساپا", "سپا"]),
    "خودرو": ("ضخود", "طخود", ["خودرو", "خودر", "خود"]),
    "ذوب": ("ضذوب", "طذوب", ["ذوب"]),
    "خبهمن": ("ضهمن", "طهمن", ["خبهمن", "بهمن", "همن"]),
    "تاصیکو": ("ضتاس", "طتاس", ["تاصیکو", "تاصيكو", "صیکو", "تاس"]),
    "وبصادر": ("ضصاد", "طصاد", ["وبصادر", "صادر", "صاد"]),
    "وتجارت": ("ضجار", "طجار", ["وتجارت", "تجارت", "تجار", "جار"]),
    "فزر": ("ضفذر", "طفذر", ["فزر", "فذر", "پویا", "پويا", "زرکان", "زركان"]),
    "دارونو": ("ضدرو", "طدور", ["دارونو", "دارو", "درو", "دور"]),
    "اطلس": ("ضاطلس", "طاطلس", ["اطلس"]),
    "موج": ("ضموج", "طموج", ["موج"]),
}


def find_best_real_option_contract(
    all_market_items: list,
    underlying_symbol: str,
    signal_type: str,
    stock_price: float,
) -> dict | None:
  if not all_market_items or not underlying_symbol:
    return None

  is_call = "CALL" in signal_type
  norm_underlying = normalize_fa(underlying_symbol)

  prefix_tuple = OPTION_PREFIX_MAP.get(norm_underlying)
  lva_prefixes, lvc_keywords = [], [norm_underlying]

  if prefix_tuple:
    prefix = prefix_tuple[0] if is_call else prefix_tuple[1]
    lva_prefixes.append(normalize_fa(prefix))
    lvc_keywords = [normalize_fa(kw) for kw in prefix_tuple[2]]

  p_char = "ض" if is_call else "ط"
  lva_prefixes.append(p_char + norm_underlying)
  candidates = []

  for item in all_market_items:
    lva = normalize_fa(item.get("lva", "")).replace("ذ", "ز")
    lvc = normalize_fa(item.get("lvc", "")).replace("ذ", "ز")

    is_opt_type = (
        ("ض" in lva
         or "اختيارخ" in lvc
         or "اختيار خ" in lvc
         or "خرید" in lvc
         or "خريد" in lvc)
        if is_call
        else (
            "ط" in lva
            or "اختيارف" in lvc
            or "اختيار ف" in lvc
            or "فروش" in lvc
        )
    )
    if not is_opt_type:
      continue

    match = any(
        pfx.replace("ذ", "ز") and lva.startswith(pfx.replace("ذ", "ز"))
        for pfx in lva_prefixes
    )
    if not match:
      match = any(
          kw.replace("ذ", "ز")
          and (kw.replace("ذ", "ز") in lvc or kw.replace("ذ", "ز") in lva)
          for kw in lvc_keywords
      )
    if not match:
      continue

    dte = get_days_to_expiration(item.get("lvc", ""))
    if dte < 1 or dte > 180:
      continue

    price = 0.0
    for p_key in [
        "pDrCotVal",
        "pcl",
        "pf",
        "pdv",
        "pmd",
        "pmo",
        "pd1",
        "po1",
        "py",
    ]:
      p_val = _f(item.get(p_key))
      if p_val > 0:
        price = p_val
        break

    if price <= 10:
      continue

    volume = _f(item.get("qtj", item.get("qTotTran5J")))

    strike = 0.0
    match_strike = re.search(r"-(\d+)-", lvc)
    if match_strike:
      strike = _f(match_strike.group(1))
    if strike <= 0:
      strike = stock_price * 1.05 if is_call else stock_price * 0.95

    candidates.append({
        "symbol": item.get("lva", ""),
        "name": item.get("lvc", ""),
        "price": price,
        "strike": strike,
        "volume": volume,
        "dte": dte,
    })

  if not candidates:
    return None

  candidates.sort(
      key=lambda x: (
          x["volume"] > 0,
          x["volume"],
          -abs(x["strike"] - stock_price),
      ),
      reverse=True,
  )
  return candidates[0]


def option_decision(row: dict) -> dict:
  p = _f(row.get("pressure_score"))
  power = _f(row.get("buyer_power"), 1.0)
  alpha = _f(row.get("alpha_market"))
  eg = int(row.get("endgame_score") or 50)
  snaps = int(row.get("snap_count") or 0)
  label_candle = str(row.get("candle_label") or "")
  is_buy_q = bool(row.get("is_buy_queue"))
  is_sell_q = bool(row.get("is_sell_queue"))

  bull_trap = ("تله گاوی" in label_candle) or (is_buy_q and power < 0.85)
  bear_accum = ("جمع‌آوری" in label_candle) or (is_sell_q and power > 1.2)
  eg_weak = snaps >= 2 and eg <= 35
  eg_strong = snaps >= 2 and eg >= 65

  if (not bull_trap) and p >= 75 and power >= 1.30 and not eg_weak and alpha >= 0:
    return {
        "option_label": "CALL آماده‌باش 🟢🟢",
        "option_class": "opt-call-strong",
        "option_reason": "فشار+قدرت هم‌جهت صعودی",
    }
  if (not bull_trap) and p >= 78 and power >= 1.20 and eg_strong:
    return {
        "option_label": "CALL آماده‌باش 🟢🟢",
        "option_class": "opt-call-strong",
        "option_reason": "فشار بالا + شتاب پایان بازار",
    }
  if (not bull_trap) and p >= 68 and power >= 1.15 and not eg_weak:
    return {
        "option_label": "CALL محتاط 🟢",
        "option_class": "opt-call-soft",
        "option_reason": "صعودی با کیفیت متوسط",
    }
  if (
      (not bull_trap)
      and p >= 70
      and power >= 1.00
      and alpha >= 0.5
      and not eg_weak
  ):
    return {
        "option_label": "CALL محتاط 🟢",
        "option_class": "opt-call-soft",
        "option_reason": "فشار خوب ولی قدرت متوسط",
    }
  if (not bear_accum) and p <= 30 and power <= 0.80 and not eg_strong:
    return {
        "option_label": "PUT آماده‌باش 🔴🔴",
        "option_class": "opt-put-strong",
        "option_reason": "فشار+قدرت هم‌جهت نزولی",
    }
  if (not bear_accum) and p <= 28 and is_sell_q and power <= 0.90:
    return {
        "option_label": "PUT آماده‌باش 🔴🔴",
        "option_class": "opt-put-strong",
        "option_reason": "صف فروش + فشار خیلی ضعیف",
    }
  if (not bear_accum) and p <= 38 and power <= 0.90 and not eg_strong:
    return {
        "option_label": "PUT محتاط 🔴",
        "option_class": "opt-put-soft",
        "option_reason": "نزول محتمل با ریسک برگشت",
    }
  if (not bear_accum) and p <= 40 and power <= 0.85 and alpha <= -0.5:
    return {
        "option_label": "PUT محتاط 🔴",
        "option_class": "opt-put-soft",
        "option_reason": "ضعیف‌تر از بازار + خریدار کم‌قدرت",
    }
  if bull_trap:
    return {
        "option_label": "NO TRADE ⚪",
        "option_class": "opt-no",
        "option_reason": "تله گاوی / صف بی‌کیفیت",
    }
  if bear_accum and p <= 45:
    return {
        "option_label": "NO TRADE ⚪",
        "option_class": "opt-no",
        "option_reason": "احتمال جمع‌آوری در منفی",
    }

  return {
      "option_label": "NO TRADE ⚪",
      "option_class": "opt-no",
      "option_reason": "سیگنال قاطی/ضعیف برای آپشن",
  }


def init_db():
  conn = sqlite3.connect(DB_NAME)
  cur = conn.cursor()
  cur.execute("""
        CREATE TABLE IF NOT EXISTS daily_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT, symbol TEXT, last_price INTEGER, close_price INTEGER,
            close_change_pct REAL, buyer_power REAL, buyer_capita REAL, seller_capita REAL,
            pressure_score INTEGER, pressure_raw INTEGER, alpha_market REAL, alpha_industry REAL,
            vol_to_float REAL, queue_to_float REAL, endgame_score INTEGER, endgame_label TEXT,
            market_return REAL, regime TEXT, prediction TEXT, is_buy_queue INTEGER,
            open_price REAL, high_price REAL, low_price REAL, body_pct REAL,
            upper_wick_pct REAL, lower_wick_pct REAL, clv REAL, dist_close_high_pct REAL,
            last_vs_close_pct REAL, gap_pct REAL, intraday_range_pct REAL, vol_vs_avg REAL,
            candle_label TEXT, volume REAL, option_label TEXT, option_reason TEXT,
            UNIQUE(date, symbol)
        )
    """)
  conn.commit()
  conn.close()


def get_avg_volume(symbol: str, lookback: int = 20) -> float:
  if not os.path.exists(DB_NAME):
    return 0.0
  try:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    today = datetime.date.today().strftime("%Y-%m-%d")
    cur.execute(
        """
            SELECT volume FROM daily_predictions
            WHERE symbol = ? AND date < ? AND volume IS NOT NULL AND volume > 0
            ORDER BY date DESC LIMIT ?
            """,
        (symbol, today, lookback),
    )
    rows = [r[0] for r in cur.fetchall() if r and r[0]]
    conn.close()
    return sum(rows) / len(rows) if rows else 0.0
  except Exception:
    return 0.0


def compute_candle_features(
    item, last_price, close_price, yesterday, volume
) -> dict:
  day_open = _f(item.get("pf"))
  day_high = _f(item.get("pmx"))
  day_low = _f(item.get("pmn"))

  if day_open <= 0:
    day_open = yesterday if yesterday > 0 else close_price
  if day_high <= 0:
    day_high = max(day_open, close_price, last_price)
  if day_low <= 0:
    vals = [x for x in [day_open, close_price, last_price] if x > 0]
    day_low = min(vals) if vals else 0

  day_high = max(day_high, day_open, close_price, last_price)
  positives = [x for x in [day_open, close_price, last_price, day_low] if x > 0]
  if positives:
    day_low = min(day_low if day_low > 0 else min(positives), min(positives))

  rng = day_high - day_low
  if rng <= 0:
    rng = max(abs(close_price - day_open), abs(last_price - close_price), 1.0)

  body = abs(close_price - day_open)
  upper_wick = max(0.0, day_high - max(day_open, close_price))
  lower_wick = max(0.0, min(day_open, close_price) - day_low)

  body_pct = body / rng * 100.0
  upper_wick_pct = upper_wick / rng * 100.0
  lower_wick_pct = lower_wick / rng * 100.0
  clv = ((close_price - day_low) - (day_high - close_price)) / rng
  close_loc = (close_price - day_low) / rng
  dist_close_high_pct = (
      ((day_high - close_price) / day_high * 100.0) if day_high > 0 else 0.0
  )
  last_vs_close_pct = (
      ((last_price - close_price) / close_price * 100.0) if close_price > 0 else 0.0
  )
  gap_pct = ((day_open - yesterday) / yesterday * 100.0) if yesterday > 0 else 0.0
  intraday_range_pct = (rng / day_open * 100.0) if day_open > 0 else 0.0
  is_bullish = close_price >= day_open

  if body_pct >= 60 and is_bullish and upper_wick_pct <= 15:
    candle_label = "🟢 بدنه بلند صعودی"
  elif body_pct >= 60 and (not is_bullish) and lower_wick_pct <= 15:
    candle_label = "🔴 بدنه بلند نزولی"
  elif lower_wick_pct >= 40 and body_pct <= 35 and close_loc >= 0.6:
    candle_label = "🔨 چکش / رد کف"
  elif upper_wick_pct >= 40 and body_pct <= 35 and close_loc <= 0.4:
    candle_label = "⭐ شوتینگ‌استار / رد سقف"
  elif body_pct <= 20:
    candle_label = "⚪ دوجی / بی‌تصمیمی"
  elif is_bullish and close_loc >= 0.75 and upper_wick_pct <= 20:
    candle_label = "🟢 بستن نزدیک سقف"
  elif (not is_bullish) and close_loc <= 0.25:
    candle_label = "🔴 بستن نزدیک کف"
  else:
    candle_label = "⬆️ کندل صعودی" if is_bullish else "⬇️ کندل نزولی"

  return {
      "open_price": day_open,
      "high_price": day_high,
      "low_price": day_low,
      "body_pct": round(body_pct, 2),
      "upper_wick_pct": round(upper_wick_pct, 2),
      "lower_wick_pct": round(lower_wick_pct, 2),
      "clv": round(clv, 3),
      "close_loc": round(close_loc, 3),
      "dist_close_high_pct": round(dist_close_high_pct, 2),
      "last_vs_close_pct": round(last_vs_close_pct, 2),
      "gap_pct": round(gap_pct, 2),
      "intraday_range_pct": round(intraday_range_pct, 2),
      "is_bullish_candle": is_bullish,
      "candle_label": candle_label,
  }


def candle_pressure_boost(c: dict, vol_vs_avg: float) -> float:
  boost = 0.0
  if c["clv"] >= 0.7:
    boost += 10
  elif c["clv"] >= 0.4:
    boost += 5
  elif c["clv"] <= -0.7:
    boost -= 10
  elif c["clv"] <= -0.4:
    boost -= 5

  if (
      c["is_bullish_candle"]
      and c["upper_wick_pct"] <= 15
      and c["body_pct"] >= 45
  ):
    boost += 8
  if (
      (not c["is_bullish_candle"])
      and c["lower_wick_pct"] <= 15
      and c["body_pct"] >= 45
  ):
    boost -= 8

  if c["lower_wick_pct"] >= 40 and c["body_pct"] <= 35 and c["clv"] >= 0.3:
    boost += 6
  if c["upper_wick_pct"] >= 40 and c["body_pct"] <= 35 and c["clv"] <= -0.2:
    boost -= 6

  if c["dist_close_high_pct"] <= 0.4 and c["is_bullish_candle"]:
    boost += 5
  elif c["dist_close_high_pct"] >= 3.0 and not c["is_bullish_candle"]:
    boost -= 3

  if c["last_vs_close_pct"] >= 0.5:
    boost += 5
  elif c["last_vs_close_pct"] <= -0.5:
    boost -= 5

  if 0.3 <= c["gap_pct"] <= 2.5:
    boost += 3
  elif c["gap_pct"] <= -1.5:
    boost -= 3

  if vol_vs_avg >= 2.5:
    boost += 10
  elif vol_vs_avg >= 1.5:
    boost += 6
  elif vol_vs_avg >= 1.1:
    boost += 3
  elif 0 < vol_vs_avg <= 0.5:
    boost -= 4

  if (
      c["dist_close_high_pct"] <= 0.6
      and c["upper_wick_pct"] <= 18
      and vol_vs_avg >= 1.4
      and c["is_bullish_candle"]
  ):
    boost += 8
  return boost


def load_endgame_features(date_str: str | None = None) -> dict:
  date_str = date_str or datetime.date.today().strftime("%Y-%m-%d")
  out = {}
  if not os.path.exists(DB_NAME):
    return out
  conn = sqlite3.connect(DB_NAME)
  cur = conn.cursor()
  try:
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND"
        " name='intraday_snapshots'"
    )
    if not cur.fetchone():
      conn.close()
      return out
    cur.execute(
        """
            SELECT symbol, time, last_price, volume, buy_q_vol, sell_q_vol,
                   buyer_power, buyer_capita, real_buy_share, last_change_pct
            FROM intraday_snapshots
            WHERE date = ? ORDER BY symbol ASC, time ASC
            """,
        (date_str,),
    )
    rows = cur.fetchall()
  except Exception:
    conn.close()
    return out
  conn.close()

  by_sym = {}
  for r in rows:
    by_sym.setdefault(r[0], []).append({
        "time": r[1],
        "last_price": _f(r[2]),
        "volume": _f(r[3]),
        "buy_q_vol": _f(r[4]),
        "sell_q_vol": _f(r[5]),
        "buyer_power": _f(r[6]),
        "buyer_capita": _f(r[7]),
        "real_buy_share": _f(r[8]),
    })

  for sym, snaps in by_sym.items():
    if len(snaps) < 2:
      out[sym] = {
          "endgame_score": 50,
          "endgame_label": "داده ناکافی ⚪",
          "snap_count": len(snaps),
      }
      continue

    first, last = snaps[0], snaps[-1]
    delta_buy_q = last["buy_q_vol"] - first["buy_q_vol"]
    delta_sell_q = last["sell_q_vol"] - first["sell_q_vol"]
    delta_power = last["buyer_power"] - first["buyer_power"]
    delta_capita = last["buyer_capita"] - first["buyer_capita"]
    delta_share = last["real_buy_share"] - first["real_buy_share"]
    delta_vol = last["volume"] - first["volume"]
    delta_price_pct = (
        ((last["last_price"] - first["last_price"]) / first["last_price"]) * 100
        if first["last_price"] > 0
        else 0.0
    )

    score = 50.0
    q_chg = (
        delta_buy_q / max(first["buy_q_vol"], 1) * 100
        if first["buy_q_vol"] > 0
        else (100 if delta_buy_q > 0 else (-50 if delta_buy_q < 0 else 0))
    )

    if q_chg >= 40:
      score += 16
    elif q_chg >= 15:
      score += 10
    elif q_chg >= 5:
      score += 5
    elif q_chg <= -40:
      score -= 16
    elif q_chg <= -15:
      score -= 10
    elif q_chg <= -5:
      score -= 5

    if delta_sell_q < 0 and abs(delta_sell_q) > first["sell_q_vol"] * 0.1:
      score += 6
    elif delta_sell_q > first["sell_q_vol"] * 0.2:
      score -= 6

    if delta_power >= 0.3:
      score += 12
    elif delta_power >= 0.1:
      score += 6
    elif delta_power <= -0.3:
      score -= 12
    elif delta_power <= -0.1:
      score -= 6

    if delta_capita >= 5:
      score += 8
    elif delta_capita >= 2:
      score += 4
    elif delta_capita <= -5:
      score -= 8

    if delta_share >= 5:
      score += 6
    elif delta_share <= -5:
      score -= 6

    if delta_price_pct >= 0.8:
      score += 10
    elif delta_price_pct >= 0.2:
      score += 5
    elif delta_price_pct <= -0.8:
      score -= 10
    elif delta_price_pct <= -0.2:
      score -= 5

    if first["volume"] > 0:
      vol_grow = delta_vol / first["volume"] * 100
      if vol_grow >= 20:
        score += 5
      elif vol_grow >= 8:
        score += 2

    score = max(0.0, min(100.0, score))
    s = int(round(score))
    if s >= 80:
      label = "🚀 تقاضای انفجاری"
    elif s >= 65:
      label = "⬆️ در حال قوی‌شدن"
    elif s <= 20:
      label = "💥 ریزش تقاضا"
    elif s <= 35:
      label = "⬇️ در حال ضعیف‌شدن"
    else:
      label = "➡️ ثابت / خنثی"
    out[sym] = {
        "endgame_score": s,
        "endgame_label": label,
        "snap_count": len(snaps),
    }
  return out


def save_to_db(analyzed_data: list, regime_info: dict):
  init_db()
  conn = sqlite3.connect(DB_NAME)
  cur = conn.cursor()
  today_str = datetime.date.today().strftime("%Y-%m-%d")
  saved = 0
  for item in analyzed_data:
    try:
      cur.execute(
          """
                INSERT OR REPLACE INTO daily_predictions (
                    date, symbol, last_price, close_price, close_change_pct,
                    buyer_power, buyer_capita, seller_capita,
                    pressure_score, pressure_raw, alpha_market, alpha_industry,
                    vol_to_float, queue_to_float, endgame_score, endgame_label,
                    market_return, regime, prediction, is_buy_queue,
                    open_price, high_price, low_price,
                    body_pct, upper_wick_pct, lower_wick_pct, clv,
                    dist_close_high_pct, last_vs_close_pct, gap_pct,
                    intraday_range_pct, vol_vs_avg, candle_label, volume,
                    option_label, option_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
          (
              today_str,
              item["symbol"],
              item["last_price"],
              item["close_price"],
              item["close_change_pct"],
              item["buyer_power"],
              item["buyer_capita"],
              item["seller_capita"],
              item["pressure_score"],
              item["pressure_raw"],
              item["alpha_market"],
              item["alpha_industry"],
              item["vol_to_float"],
              item["queue_to_float"],
              item.get("endgame_score", 50),
              item.get("endgame_label", ""),
              regime_info.get("market_return_pct", 0.0),
              regime_info.get("regime", "neutral"),
              item["prediction"],
              1 if item["is_buy_queue"] else 0,
              item.get("open_price", 0),
              item.get("high_price", 0),
              item.get("low_price", 0),
              item.get("body_pct", 0),
              item.get("upper_wick_pct", 0),
              item.get("lower_wick_pct", 0),
              item.get("clv", 0),
              item.get("dist_close_high_pct", 0),
              item.get("last_vs_close_pct", 0),
              item.get("gap_pct", 0),
              item.get("intraday_range_pct", 0),
              item.get("vol_vs_avg", 0),
              item.get("candle_label", ""),
              item.get("volume", 0),
              item.get("option_label", ""),
              item.get("option_reason", ""),
          ),
      )
      saved += 1
    except Exception:
      pass
  conn.commit()
  conn.close()
  print(f"💾 {saved} ردیف ذخیره شد ({today_str}).")


def analyze_tomorrow_status(
    item: dict,
    regime_info: dict,
    endgame_map: dict,
    ml_engine: NavasanjML,
    all_market_items: list,
) -> dict | None:
  try:
    symbol = normalize_fa(item.get("lva", ""))
    name = str(item.get("lvc", "")).strip()
    if not symbol:
      return None

    yesterday = _f(item.get("py"))
    close_price = _f(item.get("pcl"))
    last_price = _f(item.get("pDrCotVal"))
    if last_price <= 0:
      last_price = _f(item.get("pdv"))
    if last_price <= 0:
      last_price = close_price

    max_limit = _f(item.get("pMax"))
    min_limit = _f(item.get("pMin"))
    day_high = _f(item.get("pmx"))
    if yesterday > 0:
      if max_limit <= 0:
        max_limit = yesterday * 1.05
      if min_limit <= 0:
        min_limit = yesterday * 0.95

    volume = _f(item.get("qtj"))
    if volume <= 0:
      volume = _f(item.get("qTotTran5J"))
    if yesterday <= 0 or close_price <= 0:
      return None

    last_change_pct = ((last_price - yesterday) / yesterday) * 100
    close_change_pct = ((close_price - yesterday) / yesterday) * 100

    candle = compute_candle_features(
        item, last_price, close_price, yesterday, volume
    )
    avg_vol = get_avg_volume(symbol, 20)
    vol_vs_avg = (volume / avg_vol) if avg_vol > 0 else 0.0
    c_boost = candle_pressure_boost(candle, vol_vs_avg)

    best = item.get("_best") or {}
    buy_q_vol = _f(best.get("buy_q_vol"))
    sell_q_vol = _f(best.get("sell_q_vol"))
    buy_q_price = _f(best.get("buy_q_price"))
    sell_q_price = _f(best.get("sell_q_price"))

    queue_ratio = 0.0
    if sell_q_vol > 0:
      queue_ratio = buy_q_vol / sell_q_vol
    elif buy_q_vol > 0:
      queue_ratio = 10.0

    ct = item.get("_ct") or {}
    buy_i_vol = _f(ct.get("buy_i_vol"))
    sell_i_vol = _f(ct.get("sell_i_vol"))
    buy_i_val = _f(ct.get("buy_i_val"))
    sell_i_val = _f(ct.get("sell_i_val"))
    buy_count_i = _f(ct.get("buy_count_i"))
    sell_count_i = _f(ct.get("sell_count_i"))

    total_real = buy_i_vol + sell_i_vol
    real_buy_share = (
        (buy_i_vol / total_real * 100) if total_real > 0 else 50.0
    )

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
    net_real_vol = buy_i_vol - sell_i_vol
    count_ratio = (
        (buy_count_i / sell_count_i)
        if sell_count_i > 0
        else (2.0 if buy_count_i > 0 else 1.0)
    )

    ff_shares = _f(item.get("_freeFloatShares"))
    total_shares = _f(item.get("_totalShares"))
    denom = ff_shares if ff_shares > 0 else total_shares
    vol_to_float = (volume / denom * 100.0) if denom > 0 else 0.0
    queue_to_float = (buy_q_vol / denom * 100.0) if denom > 0 else 0.0

    tick_pct = candle["last_vs_close_pct"]
    dist_to_high_pct = candle["dist_close_high_pct"]

    is_buy_queue = (
        (max_limit > 0 and last_price >= max_limit * 0.998)
        or (max_limit > 0 and buy_q_vol > 0 and buy_q_price >= max_limit * 0.998)
        or last_change_pct >= 4.8
    )
    is_sell_queue = (
        (min_limit > 0 and last_price <= min_limit * 1.002)
        or (
            min_limit > 0
            and sell_q_vol > 0
            and sell_q_price <= min_limit * 1.002
        )
        or last_change_pct <= -4.8
    )

    market_ret = _f(regime_info.get("market_return_pct"))
    industry_ret = _f(item.get("_industry_return_pct"))
    alpha_market = close_change_pct - market_ret
    alpha_industry = close_change_pct - industry_ret

    pressure = 50.0

    if buyer_power >= 3.0:
      pressure += 22
    elif buyer_power >= 2.0:
      pressure += 15
    elif buyer_power >= 1.2:
      pressure += 8
    elif buyer_power <= 0.5:
      pressure -= 22
    elif buyer_power <= 0.75:
      pressure -= 14
    elif buyer_power < 0.95:
      pressure -= 7

    if real_buy_share >= 65:
      pressure += 11
    elif real_buy_share >= 55:
      pressure += 6
    elif real_buy_share <= 35:
      pressure -= 11
    elif real_buy_share <= 45:
      pressure -= 6

    if count_ratio >= 1.4:
      pressure += 4
    elif count_ratio <= 0.7:
      pressure -= 4

    is_bull_trap = False
    if is_buy_queue:
      if buyer_power < 0.85:
        pressure -= 12
        is_bull_trap = True
        candle["candle_label"] += " ⚠️ تله گاوی"
      else:
        pressure += 12

    if is_sell_queue:
      if buyer_power > 1.2:
        pressure += 5
        candle["candle_label"] += " 🎣 جمع‌آوری"
      else:
        pressure -= 12

    if queue_ratio >= 3 and not is_bull_trap:
      pressure += 7
    elif queue_ratio >= 1.5 and not is_bull_trap:
      pressure += 4
    elif 0 < queue_ratio <= 0.4:
      pressure -= 7

    if tick_pct >= 0.8:
      pressure += 9
    elif tick_pct >= 0.2:
      pressure += 4
    elif tick_pct <= -0.8:
      pressure -= 9
    elif tick_pct <= -0.2:
      pressure -= 5

    if day_high >= max_limit * 0.995 and close_change_pct > 0:
      pressure += 8
    elif dist_to_high_pct <= 1.0 and close_change_pct > 0:
      pressure += 5

    if vol_to_float >= 8:
      pressure += 10
    elif vol_to_float >= 4:
      pressure += 7
    elif vol_to_float >= 2:
      pressure += 4

    if queue_to_float >= 3 and not is_bull_trap:
      pressure += 8
    elif queue_to_float >= 1.5 and not is_bull_trap:
      pressure += 5
    elif queue_to_float >= 0.7 and not is_bull_trap:
      pressure += 3

    if alpha_market >= 2.0:
      pressure += 10
    elif alpha_market >= 1.0:
      pressure += 6
    elif alpha_market >= 0.4:
      pressure += 3
    elif alpha_market <= -2.0:
      pressure -= 10
    elif alpha_market <= -1.0:
      pressure -= 6

    if alpha_industry >= 1.5:
      pressure += 6
    elif alpha_industry >= 0.6:
      pressure += 3
    elif alpha_industry <= -1.5:
      pressure -= 6

    if volume > 0 and total_real > 0:
      net_ratio = net_real_vol / volume
      if net_ratio >= 0.2:
        pressure += 7
      elif net_ratio >= 0.05:
        pressure += 3
      elif net_ratio <= -0.2:
        pressure -= 7
      elif net_ratio <= -0.05:
        pressure -= 3

    pressure += c_boost

    eg = endgame_map.get(symbol) or {
        "endgame_score": 50,
        "endgame_label": "بدون‌اسنپ‌شات ⚪",
        "snap_count": 0,
    }
    endgame_score = int(eg.get("endgame_score", 50))
    endgame_label = eg.get("endgame_label", "بدون‌اسنپ‌شات ⚪")
    if eg.get("snap_count", 0) >= 2:
      if endgame_score >= 80:
        pressure += 12
      elif endgame_score >= 65:
        pressure += 7
      elif endgame_score <= 20:
        pressure -= 12
      elif endgame_score <= 35:
        pressure -= 7
      else:
        pressure += (endgame_score - 50) * 0.08

    pressure_raw = int(round(max(0.0, min(100.0, pressure))))
    if is_bull_trap and pressure_raw > 65:
      pressure_raw = 65

    mult = _f(regime_info.get("market_multiplier"), 1.0)
    pressure_score = int(
        round(max(0.0, min(100.0, 50.0 + (pressure_raw - 50.0) * mult)))
    )

    if pressure_score >= 80 or (
        is_buy_queue and pressure_score >= 68 and not is_bull_trap
    ):
      prediction, status_class = (
          "صف خرید محتمل / بسیار پرتقاضا 🟢🟢",
          "status-buy-queue",
      )
    elif pressure_score >= 60:
      prediction, status_class = "مثبت و صعودی 🟢", "status-positive"
    elif pressure_score <= 20 or (is_sell_queue and pressure_score <= 35):
      prediction, status_class = (
          "صف فروش محتمل / پرعرضه 🔴🔴",
          "status-sell-queue",
      )
    elif pressure_score <= 40:
      prediction, status_class = "منفی و نزولی 🔴", "status-negative"
    else:
      prediction, status_class = "متعادل / رنج ⚪", "status-neutral"

    row = {
        "symbol": symbol,
        "name": name,
        "last_price": int(last_price),
        "close_price": int(close_price),
        "last_change_pct": round(last_change_pct, 2),
        "close_change_pct": round(close_change_pct, 2),
        "volume": int(volume),
        "buy_q_vol": int(buy_q_vol),
        "sell_q_vol": int(sell_q_vol),
        "buyer_power": round(buyer_power, 2),
        "buyer_capita": round(buyer_capita, 2),
        "seller_capita": round(seller_capita, 2),
        "real_buy_share": round(real_buy_share, 1),
        "vol_to_float": round(vol_to_float, 3),
        "queue_to_float": round(queue_to_float, 3),
        "alpha_market": round(alpha_market, 2),
        "alpha_industry": round(alpha_industry, 2),
        "open_price": int(candle["open_price"]),
        "high_price": int(candle["high_price"]),
        "low_price": int(candle["low_price"]),
        "body_pct": candle["body_pct"],
        "upper_wick_pct": candle["upper_wick_pct"],
        "lower_wick_pct": candle["lower_wick_pct"],
        "clv": candle["clv"],
        "dist_close_high_pct": candle["dist_close_high_pct"],
        "last_vs_close_pct": candle["last_vs_close_pct"],
        "gap_pct": candle["gap_pct"],
        "intraday_range_pct": candle["intraday_range_pct"],
        "vol_vs_avg": round(vol_vs_avg, 2),
        "candle_label": candle["candle_label"],
        "candle_boost": round(c_boost, 1),
        "pressure_raw": pressure_raw,
        "pressure_score": pressure_score,
        "endgame_score": endgame_score,
        "endgame_label": endgame_label,
        "snap_count": int(eg.get("snap_count", 0)),
        "prediction": prediction,
        "status_class": status_class,
        "is_buy_queue": is_buy_queue,
        "is_sell_queue": is_sell_queue,
        "has_real_data": total_real > 0 or buy_count_i > 0,
        "has_queue_data": (buy_q_vol > 0 or sell_q_vol > 0),
    }

    # 🤖 محاسبه احتمالات ریاضی توسط هوش مصنوعی (ML)
    ml_preds = ml_engine.predict_probabilities(row)
    row.update(ml_preds)

    od = option_decision(row)
    row.update(od)

    # 🔍 جستجوی واقعی و زنده بهترین قرارداد اختیار معامله (ذخیره حجم معامله جهت رتبه‌بندی)
    real_opt = find_best_real_option_contract(
        all_market_items, symbol, row["option_label"], last_price
    )
    if real_opt and real_opt["price"] > 0:
      is_call_type = "CALL" in row["option_label"]
      opt_eval = evaluate_option_contract(
          stock_price=last_price,
          strike_price=real_opt["strike"],
          days_to_expire=real_opt["dte"],
          option_market_price=real_opt["price"],
          is_call=is_call_type,
          historical_volatility=0.35,
      )
      row["opt_real_symbol"] = f"{real_opt['symbol']} ({real_opt['dte']}d)"
      row["opt_real_price"] = int(real_opt["price"])
      row["opt_real_volume"] = int(real_opt["volume"])  # 🎯 ذخیره حجم زنده
      row["opt_bubble_status"] = opt_eval["status"]
      row["opt_bubble_class"] = opt_eval["status_class"]
      row["opt_breakeven_stock"] = opt_eval["breakeven_stock"]
      row["opt_breakeven_move_pct"] = opt_eval["breakeven_move_pct"]
      row["opt_sl"] = opt_eval["sl_price"]
      row["opt_tp1"] = opt_eval["tp1_price"]
    else:
      row["opt_real_symbol"] = "قرارداد فعال یافت نشد"
      row["opt_real_price"] = 0
      row["opt_real_volume"] = 0
      row["opt_bubble_status"] = "—"
      row["opt_bubble_class"] = "text-muted"
      row["opt_breakeven_stock"] = 0
      row["opt_breakeven_move_pct"] = 0
      row["opt_sl"] = 0
      row["opt_tp1"] = 0

    return row
  except Exception:
    return None


def generate_daily_bulletin(analyzed_data: list, regime_info: dict) -> str:
  """موتور هوشمند ساخت تیتر اصلی — رتبه‌بندی فوق‌العاده دقیق بر اساس 'حجم نقدشوندگی زنده اختیار معامله'."""
  if not analyzed_data:
    return ""

  valid_candidates = []

  # ۱. استخراج نمادهای دارای سیگنال قوی، قیمت معتبر و حجم معاملات زنده بالا
  for item in analyzed_data:
    opt_class = item.get("option_class", "")
    opt_price = item.get("opt_real_price", 0)
    opt_vol = item.get("opt_real_volume", 0)
    opt_symbol = item.get("opt_real_symbol", "")
    is_iv_crush = "IV Crush" in item.get("opt_bubble_status", "")

    # 🛑 فیلتر سخت‌گیرانه نقدشوندگی: حتماً دارای معامله زنده و قیمت معتبر بالای ۵۰ ریال
    if opt_class in ("opt-call-strong", "opt-put-strong"):
      if (
          opt_price >= 50
          and opt_vol > 0
          and not is_iv_crush
          and "یافت نشد" not in opt_symbol
      ):
        valid_candidates.append(item)

  # ۲. اگر سیگنال قوی نبود، بررسی سیگنال‌های محتاط بسیار پرقدرت
  if not valid_candidates:
    for item in analyzed_data:
      opt_class = item.get("option_class", "")
      opt_price = item.get("opt_real_price", 0)
      opt_vol = item.get("opt_real_volume", 0)
      opt_symbol = item.get("opt_real_symbol", "")
      is_iv_crush = "IV Crush" in item.get("opt_bubble_status", "")

      if (
          opt_class in ("opt-call-soft", "opt-put-soft")
          and item.get("pressure_score", 0) >= 75
      ):
        if (
            opt_price >= 50
            and opt_vol > 0
            and not is_iv_crush
            and "یافت نشد" not in opt_symbol
        ):
          valid_candidates.append(item)

  # ۳. اگر هیچ معامله نقدشونده‌ای پیدا نشد 👈 صادر کردن دستور NO TRADE
  if not valid_candidates:
    return """
        <div style="background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); border: 2px solid #ef4444; border-radius: 16px; padding: 20px; margin-bottom: 24px; box-shadow: 0 10px 25px -5px rgba(239, 68, 68, 0.25);">
            <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 8px;">
                <span style="font-size: 28px;">⛔</span>
                <h2 style="margin: 0; color: #f87171; font-size: 20px; font-weight: 800;">دستورالعمل معامله فردا: هیچ معامله‌ای انجام ندهید! (NO TRADE)</h2>
            </div>
            <p style="margin: 0; color: #cbd5e1; font-size: 13.5px; line-height: 1.7;">
                بررسی تمام الزامات سیستم نشان می‌دهد بازار فردا دارای سیگنال هم‌جهت با نقدشوندگی عالی و حباب منصفانه نیست. برای حفظ سرمایه، پیشنهاد می‌شود فردا <strong>دست نگه دارید</strong> و هیچ موقعیت جدیدی در اختیار معامله اتخاذ نکنید.
            </p>
        </div>
        """

  # 🎯 مرتب‌سازی نهایی بر اساس حجم زنده معاملات آپشن (پرحجم‌ترین نماد مثل اهرم، خودرو، فملی برنده می‌شود!)
  valid_candidates.sort(
      key=lambda x: (x.get("opt_real_volume", 0), x.get("pressure_score", 0)),
      reverse=True,
  )
  top_target = valid_candidates[0]

  is_call = "CALL" in top_target["option_label"]
  badge_bg = "rgba(34,197,94,0.2)" if is_call else "rgba(239,68,68,0.2)"
  badge_border = "#22c55e" if is_call else "#ef4444"
  badge_color = "#4ade80" if is_call else "#f87171"
  action_type_fa = "خرید اختیار خرید (CALL)" if is_call else "خرید اختیار فروش (PUT)"

  ml_p2 = top_target.get("p_2pct", 0)
  ml_txt = (
      f"احتمال سود +۲٪ فردا: {ml_p2}%"
      if top_target.get("ml_ready")
      else "احتمال صعود بالا"
  )

  return f"""
    <div style="background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); border: 2px solid {badge_border}; border-radius: 16px; padding: 20px; margin-bottom: 24px; box-shadow: 0 10px 25px -5px rgba(0,0,0,0.5);">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; border-bottom: 1px solid #334155; padding-bottom: 12px; margin-bottom: 14px;">
            <div style="display: flex; align-items: center; gap: 10px;">
                <span style="font-size: 26px;">🎯</span>
                <div>
                    <span style="font-size: 12px; color: #94a3b8; font-weight: 600;">دستورالعمل اجرایی معامله فردا (ویژه معامله‌گر):</span>
                    <h2 style="margin: 2px 0 0 0; color: #38bdf8; font-size: 19px; font-weight: 800;">
                        {action_type_fa} روی نماد <span style="color:#facc15;">{top_target['symbol']}</span>
                    </h2>
                </div>
            </div>
            <div style="background: {badge_bg}; border: 1px solid {badge_border}; color: {badge_color}; padding: 6px 16px; border-radius: 20px; font-weight: 800; font-size: 13px;">
                {top_target['option_label']}
            </div>
        </div>

        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; background: #0f172a; padding: 14px; border-radius: 12px; border: 1px solid #334155;">
            <div>
                <span style="color: #94a3b8; font-size: 11px; display: block;">نماد دقیق قرارداد اختیار:</span>
                <strong style="color: #facc15; font-size: 15px;">{top_target.get('opt_real_symbol', '—')}</strong>
            </div>
            <div>
                <span style="color: #94a3b8; font-size: 11px; display: block;">قیمت زنده پریمیوم:</span>
                <strong style="color: #f8fafc; font-size: 14px;">{top_target.get('opt_real_price', 0):,} ریال</strong>
            </div>
            <div>
                <span style="color: #94a3b8; font-size: 11px; display: block;">حد ضرر (SL) / حد سود (TP1):</span>
                <strong style="color: #f87171; font-size: 13px;">SL: {top_target.get('opt_sl', 0):,}</strong> | <strong style="color: #4ade80; font-size: 13px;">TP1: {top_target.get('opt_tp1', 0):,}</strong>
            </div>
            <div>
                <span style="color: #94a3b8; font-size: 11px; display: block;">قدرت خریدار / هوش مصنوعی:</span>
                <strong style="color: #38bdf8; font-size: 13px;">قدرت: {top_target['buyer_power']} | {ml_txt}</strong>
            </div>
        </div>

        <div style="margin-top: 12px; font-size: 12px; color: #cbd5e1; line-height: 1.7;">
            📌 <strong>دستورالعمل سفارش‌گذاری ساعت ۰۹:۰۰ فردا:</strong> نماد <strong style="color:#facc15;">{top_target.get('opt_real_symbol', '')}</strong> را در کارگزاری جستجو کنید. در ۳۰ دقیقه اول بازار، اگر سهم پایه ({top_target['symbol']}) صفر تابلو یا منفی کوچک داد، با رعایت حدضرر {top_target.get('opt_sl', 0):,} ریال وارد شوید.
        </div>
    </div>
    """


def generate_html_dashboard(analyzed_data: list, regime_info: dict):
  counts = {
      "CALL آماده‌باش 🟢🟢": 0,
      "CALL محتاط 🟢": 0,
      "NO TRADE ⚪": 0,
      "PUT محتاط 🔴": 0,
      "PUT آماده‌باش 🔴🔴": 0,
  }
  for x in analyzed_data:
    counts[x.get("option_label", "NO TRADE ⚪")] = (
        counts.get(x.get("option_label", "NO TRADE ⚪"), 0) + 1
    )

  ml_status_text = "🤖 هوش مصنوعی (ML): در حال جمع‌آوری داده"
  if analyzed_data and analyzed_data[0].get("ml_ready"):
    sample_cnt = analyzed_data[0].get("sample_count", 0)
    ml_status_text = f"🤖 هوش مصنوعی (ML): فعال و آموزش‌دیده روی {sample_cnt} نمونه تاریخی"

  bulletin_html = generate_daily_bulletin(analyzed_data, regime_info)

  cards_html = ""
  for item in analyzed_data:
    p_class = "text-green" if item["last_change_pct"] >= 0 else "text-red"
    power = item["buyer_power"]
    power_class = (
        "text-green" if power >= 1.2 else ("text-red" if power < 0.85 else "")
    )
    a_class = (
        "text-green"
        if item["alpha_market"] >= 0.4
        else ("text-red" if item["alpha_market"] <= -0.4 else "")
    )

    if item["has_queue_data"]:
      if item["is_buy_queue"] and item["buy_q_vol"] > 0:
        queue_info = (
            f"<span class='text-green'>خرید {item['buy_q_vol']:,}</span>"
        )
      elif item["is_sell_queue"] and item["sell_q_vol"] > 0:
        queue_info = (
            f"<span class='text-red'>فروش {item['sell_q_vol']:,}</span>"
        )
      else:
        queue_info = f"{item['buy_q_vol']:,} / {item['sell_q_vol']:,}"
    else:
      queue_info = "—"

    capita_txt = (
        f"{item['buyer_capita']}م / {item['seller_capita']}م"
        if item["has_real_data"]
        else "—"
    )

    if item.get("ml_ready"):
      ml_html = f"""
            <div class="ml-box">
                <div><span class="lbl">مثبت:</span> <strong style="color:#4ade80;">{item['p_pos']}%</strong></div>
                <div><span class="lbl">+۲٪ سود:</span> <strong style="color:#38bdf8;">{item['p_2pct']}%</strong></div>
                <div><span class="lbl">+۴٪ سود:</span> <strong style="color:#facc15;">{item['p_4pct']}%</strong></div>
                <div><span class="lbl">صف خرید:</span> <strong style="color:#f87171;">{item['p_queue']}%</strong></div>
            </div>
            """
    else:
      ml_html = '<div class="ml-box text-muted">نیازمند داده‌های بیشتر...</div>'

    opt_sym_txt = item.get("opt_real_symbol", "نامشخص")
    opt_price_txt = (
        f"{item['opt_real_price']:,} ریال"
        if item.get("opt_real_price", 0) > 0
        else "—"
    )
    be_move_sign = "+" if item.get("opt_breakeven_move_pct", 0) >= 0 else ""
    be_html = (
        f"سربه‌سر سهم: {item.get('opt_breakeven_stock', 0):,}"
        f" ({be_move_sign}{item.get('opt_breakeven_move_pct', 0)}%)"
        if item.get("opt_breakeven_stock", 0) > 0
        else ""
    )

    opt_details_html = f"""
        <div style="font-size:10.5px; margin-top:4px; line-height:1.5;">
            🎯 <strong style="color:#facc15;">نماد: {opt_sym_txt}</strong> ({opt_price_txt})<br/>
            حباب/ریسک: <span class="{item['opt_bubble_class']}">{item['opt_bubble_status']}</span><br/>
            <span style="color:#cbd5e1;">{be_html}</span><br/>
            <span style="color:#f87171;">SL: {item['opt_sl']:,}</span> | 
            <span style="color:#4ade80;">TP1: {item['opt_tp1']:,}</span>
        </div>
        """

    cards_html += f"""
        <div class="stock-card" data-status="{item['status_class']}" data-option="{item['option_class']}">
            <div class="card-header">
                <div>
                    <span class="sym-title">{item['symbol']}</span>
                    <span class="text-muted" style="margin-right:6px; font-size:11px;">{item['name']}</span>
                </div>
                <span class="badge {item['status_class']}">{item['prediction']}</span>
            </div>

            <div class="opt-banner {item['option_class']}">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span class="opt-badge">{item['option_label']}</span>
                    <span style="font-size:11px; opacity:0.9;">{item['option_reason']}</span>
                </div>
                {opt_details_html}
            </div>

            {ml_html}

            <div class="metrics-grid">
                <div class="metric-item">
                    <span class="lbl">آخرین قیمت</span>
                    <span class="val">{item['last_price']:,} <small class="{p_class}">({item['last_change_pct']}%)</small></span>
                </div>
                <div class="metric-item">
                    <span class="lbl">قدرت خریدار</span>
                    <span class="val {power_class}">{item['buyer_power']}</span>
                </div>
                <div class="metric-item">
                    <span class="lbl">سرانه (خ/ف)</span>
                    <span class="val">{capita_txt}</span>
                </div>
                <div class="metric-item">
                    <span class="lbl">فشار خرید</span>
                    <div class="pressure-wrap" style="margin-top:3px;"><div class="pressure-bar" style="width:{item['pressure_score']}%"></div><span>{item['pressure_score']}</span></div>
                </div>
                <div class="metric-item">
                    <span class="lbl">Alpha بازار</span>
                    <span class="val {a_class}">{item['alpha_market']:+.2f}%</span>
                </div>
                <div class="metric-item">
                    <span class="lbl">روند پایانی</span>
                    <span class="val">{item['endgame_label']} <small class="text-muted">(EG:{item['endgame_score']})</small></span>
                </div>
                <div class="metric-item">
                    <span class="lbl">کندل روز</span>
                    <span class="val">{item['candle_label']} <small class="text-muted">(CLV:{item['clv']:+.2f})</small></span>
                </div>
                <div class="metric-item">
                    <span class="lbl">وضعیت صف</span>
                    <span class="val">{queue_info}</span>
                </div>
            </div>
        </div>
        """

  html = f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Navasanj | دیده‌بان هوشمند کارتی</title>
  <link href="https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/Vazirmatn-font-face.css" rel="stylesheet" />
  <style>
    * {{ box-sizing:border-box; font-family:Vazirmatn,sans-serif; }}
    body {{ background:#0f172a; color:#f8fafc; margin:0; padding:20px; }}
    .header {{ display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap; border-bottom:1px solid #334155; padding-bottom:14px; align-items:center; }}
    .title {{ font-size:22px; font-weight:800; color:#38bdf8; }}
    .regime,.summary {{ background:#1e293b; border:1px solid #334155; border-radius:12px; padding:12px 16px; margin:14px 0; display:flex; gap:16px; flex-wrap:wrap; font-size:13px; }}
    .controls {{ display:flex; gap:10px; margin:16px 0 20px; flex-wrap:wrap; }}
    .search-box {{ padding:10px 14px; border-radius:8px; border:1px solid #334155; background:#1e293b; color:#fff; width:260px; }}
    .filter-btn {{ padding:8px 14px; border-radius:8px; border:none; background:#334155; color:#fff; cursor:pointer; font-weight:600; font-size:12px; transition:0.2s; }}
    .filter-btn.active,.filter-btn:hover {{ background:#0284c7; }}

    .cards-grid {{ display:grid; grid-template-columns:repeat(auto-fill, minmax(360px, 1fr)); gap:16px; }}
    .stock-card {{ background:#1e293b; border:1px solid #334155; border-radius:12px; padding:16px; display:flex; flex-direction:column; gap:12px; box-shadow:0 4px 6px -1px rgba(0,0,0,0.3); transition:transform 0.2s, border-color 0.2s; }}
    .stock-card:hover {{ transform:translateY(-2px); border-color:#0284c7; }}
    .card-header {{ display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #334155; padding-bottom:10px; }}
    .sym-title {{ font-size:18px; font-weight:800; color:#38bdf8; }}

    .opt-banner {{ border-radius:8px; padding:10px 12px; border:1px solid #334155; }}
    .opt-call-strong {{ background:rgba(34,197,94,.15); border-color:#22c55e; }}
    .opt-call-soft {{ background:rgba(56,189,248,.15); border-color:#0ea5e9; }}
    .opt-put-strong {{ background:rgba(239,68,68,.15); border-color:#ef4444; }}
    .opt-put-soft {{ background:rgba(249,115,22,.15); border-color:#f97316; }}
    .opt-no {{ background:rgba(148,163,184,.1); border-color:#64748b; }}
    .opt-badge {{ font-size:11px; font-weight:800; padding:2px 8px; border-radius:10px; background:rgba(255,255,255,0.1); }}

    .ml-box {{ background:#0f172a; border-radius:8px; padding:8px 12px; font-size:11px; display:grid; grid-template-columns:1fr 1fr; gap:6px; border:1px solid #334155; }}
    .ml-box .lbl {{ color:#94a3b8; }}

    .metrics-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; font-size:12px; background:#0f172a; padding:10px; border-radius:8px; }}
    .metric-item {{ display:flex; flex-direction:column; gap:2px; }}
    .metric-item .lbl {{ color:#94a3b8; font-size:10.5px; }}
    .metric-item .val {{ font-weight:700; color:#f8fafc; }}

    .bold {{ font-weight:700; }}
    .text-muted {{ color:#94a3b8; }}
    .text-green {{ color:#4ade80; }}
    .text-red {{ color:#f87171; }}
    .badge {{ padding:4px 8px; border-radius:12px; font-size:10.5px; font-weight:700; }}
    .status-buy-queue {{ background:rgba(34,197,94,.2); color:#4ade80; border:1px solid #22c55e; }}
    .status-positive {{ background:rgba(56,189,248,.2); color:#38bdf8; }}
    .status-neutral {{ background:rgba(148,163,184,.2); color:#cbd5e1; }}
    .status-negative {{ background:rgba(249,115,22,.2); color:#fb923c; }}
    .status-sell-queue {{ background:rgba(239,68,68,.2); color:#f87171; border:1px solid #ef4444; }}

    .pressure-wrap {{ position:relative; width:100%; height:16px; background:#334155; border-radius:8px; overflow:hidden; display:inline-block; }}
    .pressure-bar {{ position:absolute; right:0; top:0; bottom:0; background:#22c55e; }}
    .pressure-wrap span {{ position:relative; z-index:1; font-size:10px; font-weight:800; display:flex; height:100%; align-items:center; justify-content:center; color:#fff; }}
  </style>
</head>
<body>
  <div class="header">
    <div class="title">🤖 Navasanj — دیده‌بان هوشمند + تیتر دستورالعمل اجرایی فردا</div>
    <div style="color:#38bdf8; font-weight:bold; font-size:13px;">{ml_status_text}</div>
  </div>

  <div class="regime">
    <div>رژیم: <b>{regime_info.get('regime_label','')}</b></div>
    <div>شاخص: <b>{regime_info.get('market_return_pct',0):+.2f}%</b></div>
    <div>هم‌وزن: <b>{regime_info.get('equal_weight_return_pct',0):+.2f}%</b></div>
    <div>ضریب: <b>×{regime_info.get('market_multiplier',1)}</b></div>
  </div>

  <div class="summary">
    <div>CALL قوی: <b style="color:#4ade80">{counts.get('CALL آماده‌باش 🟢🟢',0)}</b></div>
    <div>CALL محتاط: <b style="color:#38bdf8">{counts.get('CALL محتاط 🟢',0)}</b></div>
    <div>NO TRADE: <b>{counts.get('NO TRADE ⚪',0)}</b></div>
    <div>PUT محتاط: <b style="color:#fb923c">{counts.get('PUT محتاط 🔴',0)}</b></div>
    <div>PUT قوی: <b style="color:#f87171">{counts.get('PUT آماده‌باش 🔴🔴',0)}</b></div>
  </div>

  {bulletin_html}

  <div class="controls">
    <input id="searchInput" class="search-box" placeholder="🔍 جستجوی نماد..." onkeyup="filterCards()" />
    <button class="filter-btn active" onclick="setOpt('all')">همه</button>
    <button class="filter-btn" onclick="setOpt('opt-call-strong')">CALL آماده‌باش</button>
    <button class="filter-btn" onclick="setOpt('opt-call-soft')">CALL محتاط</button>
    <button class="filter-btn" onclick="setOpt('opt-no')">NO TRADE</button>
    <button class="filter-btn" onclick="setOpt('opt-put-soft')">PUT محتاط</button>
    <button class="filter-btn" onclick="setOpt('opt-put-strong')">PUT آماده‌باش</button>
  </div>

  <div class="cards-grid" id="cardsGrid">
    {cards_html}
  </div>

  <script>
    let currentOpt = 'all';
    function setOpt(v){{
      currentOpt = v;
      document.querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active'));
      event.target.classList.add('active');
      filterCards();
    }}
    function filterCards(){{
      const search = document.getElementById('searchInput').value.toLowerCase();
      document.querySelectorAll('.stock-card').forEach(card=>{{
        const text = card.innerText.toLowerCase();
        const opt = card.getAttribute('data-option');
        const okSearch = text.includes(search);
        const okOpt = currentOpt === 'all' || opt === currentOpt;
        card.style.display = (okSearch && okOpt) ? 'flex' : 'none';
      }});
    }}
  </script>
</body>
</html>"""

  out = "market_forecast_dashboard.html"
  with open(out, "w", encoding="utf-8") as f:
    f.write(html)
  path = os.path.abspath(out)
  webbrowser.open(f"file://{path}")
  print(f"✅ داشبورد جدید با تیتر دستورالعمل فردا بروزرسانی شد: {path}")


def main():
  print("🚀 Navasanj | ساخت داشبورد با تیتر دستورالعمل اصلی...")

  ml_engine = NavasanjML()
  trained = ml_engine.train()

  enriched_targets, regime_info, all_market_items = fetch_enriched_target_data(
      max_workers=6
  )
  if not enriched_targets:
    print("❌ دیتا نیامد")
    return

  endgame_map = load_endgame_features()
  analyzed = []
  for item in enriched_targets:
    res = analyze_tomorrow_status(
        item, regime_info, endgame_map, ml_engine, all_market_items
    )
    if res:
      analyzed.append(res)

  rank = {
      "opt-call-strong": 0,
      "opt-put-strong": 1,
      "opt-call-soft": 2,
      "opt-put-soft": 3,
      "opt-no": 4,
  }
  analyzed.sort(
      key=lambda x: (rank.get(x.get("option_class"), 9), -x["pressure_score"])
  )

  save_to_db(analyzed, regime_info)
  generate_html_dashboard(analyzed, regime_info)


if __name__ == "__main__":
  main()