# ml_engine.py
import os
import sqlite3
import warnings
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression

warnings.filterwarnings("ignore")

DB_NAME = "market_history.db"


def load_training_data():
  """بارگذاری و ساخت مجموعه داده‌های آموزش (Dataset) از دیتابیس ۲۰ روزه."""
  if not os.path.exists(DB_NAME):
    return None, None

  conn = sqlite3.connect(DB_NAME)

  # خواندن داده‌های روز T و تطبیق با روز T+1
  query = """
    SELECT 
        t.symbol, t.date,
        t.buyer_power, t.buyer_capita, t.seller_capita,
        t.pressure_raw, t.alpha_market, t.alpha_industry,
        t.vol_to_float, t.queue_to_float, t.endgame_score,
        t.body_pct, t.upper_wick_pct, t.lower_wick_pct, t.clv,
        t.last_vs_close_pct, t.gap_pct, t.vol_vs_avg,
        t1.close_change_pct AS next_return,
        t1.is_buy_queue AS next_is_queue
    FROM daily_predictions t
    JOIN daily_predictions t1 ON t.symbol = t1.symbol 
        AND t1.date = (
            SELECT MIN(date) FROM daily_predictions WHERE date > t.date
        )
    WHERE t.buyer_power IS NOT NULL AND t1.close_change_pct IS NOT NULL
    """

  try:
    df = pd.read_sql(query, conn)
    conn.close()
  except Exception as e:
    conn.close()
    return None, None

  if len(df) < 15:
    return None, None

  # تمیزکاری داده‌ها
  feature_cols = [
      "buyer_power",
      "buyer_capita",
      "seller_capita",
      "pressure_raw",
      "alpha_market",
      "alpha_industry",
      "vol_to_float",
      "queue_to_float",
      "endgame_score",
      "body_pct",
      "upper_wick_pct",
      "lower_wick_pct",
      "clv",
      "last_vs_close_pct",
      "gap_pct",
      "vol_vs_avg",
  ]

  X = df[feature_cols].fillna(0)

  # ساخت متغیرهای هدف (Targets)
  y_pos = (df["next_return"] > 0).astype(int)
  y_p2 = (df["next_return"] >= 2.0).astype(int)
  y_p4 = (df["next_return"] >= 4.0).astype(int)
  y_queue = (df["next_is_queue"] == 1) | (df["next_return"] >= 4.8)
  y_queue = y_queue.astype(int)

  targets = {
      "pos": y_pos,
      "p2": y_p2,
      "p4": y_p4,
      "queue": y_queue,
  }

  return X, targets


class NavasanjML:

  def __init__(self):
    self.models = {}
    self.is_trained = False
    self.sample_count = 0

  def train(self):
    X, targets = load_training_data()
    if X is None or len(X) < 15:
      self.is_trained = False
      return False

    self.sample_count = len(X)
    for target_name, y in targets.items():
      # استفاده از RandomForest همزمان با LogisticRegression برای پایداری
      model = LogisticRegression(C=1.0, max_iter=500)
      model.fit(X, y)
      self.models[target_name] = model

    self.is_trained = True
    return True

  def predict_probabilities(self, row_dict: dict) -> dict:
    """محاسبه احتمالات ریاضی فردا برای یک نماد مشخص."""
    if not self.is_trained:
      return {
          "p_pos": None,
          "p_2pct": None,
          "p_4pct": None,
          "p_queue": None,
          "ml_ready": False,
      }

    feature_cols = [
        "buyer_power",
        "buyer_capita",
        "seller_capita",
        "pressure_raw",
        "alpha_market",
        "alpha_industry",
        "vol_to_float",
        "queue_to_float",
        "endgame_score",
        "body_pct",
        "upper_wick_pct",
        "lower_wick_pct",
        "clv",
        "last_vs_close_pct",
        "gap_pct",
        "vol_vs_avg",
    ]

    features = []
    for col in feature_cols:
      val = row_dict.get(col, 0)
      features.append(float(val if val is not None else 0))

    X_single = np.array([features])

    try:
      p_pos = self.models["pos"].predict_proba(X_single)[0][1] * 100
      p_2pct = self.models["p2"].predict_proba(X_single)[0][1] * 100
      p_4pct = self.models["p4"].predict_proba(X_single)[0][1] * 100
      p_queue = self.models["queue"].predict_proba(X_single)[0][1] * 100

      return {
          "p_pos": round(p_pos, 1),
          "p_2pct": round(p_2pct, 1),
          "p_4pct": round(p_4pct, 1),
          "p_queue": round(p_queue, 1),
          "ml_ready": True,
          "sample_count": self.sample_count,
      }
    except Exception:
      return {
          "p_pos": None,
          "p_2pct": None,
          "p_4pct": None,
          "p_queue": None,
          "ml_ready": False,
      }