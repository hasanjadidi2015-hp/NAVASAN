import sqlite3
import logging
import json

import cloudscraper
from pytse_client import Ticker, symbols_data, tse_settings, utils

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("engine")

_scraper = cloudscraper.create_scraper()
utils.requests_retry_session = lambda *args, **kwargs: _scraper


def _fetch_client_type_direct(inscode: str):
    url = tse_settings.TSE_CLIENT_TYPE_DATA_URL.format(inscode)
    response = _scraper.get(url, timeout=10)
    response.raise_for_status()
    text = response.text.strip()
    logger.info(f"[debug] Raw response for InsCode {inscode}: {text[:200]}")
    try:
        return response.json()
    except json.JSONDecodeError as e:
        logger.error(f"[debug] Invalid JSON received. Full response text: {text}")
        raise e


def init_db():
    conn = sqlite3.connect('ahram_v2.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_features (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            symbol TEXT,
            close REAL,
            final REAL,
            high REAL,
            low REAL,
            volume REAL,
            value REAL,
            buy_queue_vol REAL,
            sell_queue_vol REAL,
            queue_ratio REAL,
            real_buyer_count INTEGER,
            real_seller_count INTEGER,
            buy_per_capita REAL,
            sell_per_capita REAL,
            buyer_power REAL,
            distance_to_high_pct REAL,
            prediction_label TEXT,
            prediction_score REAL,
            UNIQUE(date, symbol)
        )
    ''')
    conn.commit()
    conn.close()


def evaluate_and_predict(symbol):
    try:
        inscode = symbols_data.get_ticker_index(symbol)
        if inscode is None:
            logger.warning(f"[engine] InsCode برای نماد '{symbol}' پیدا نشد - رد شد")
            return False

        ticker = Ticker(symbol)
        df = ticker.history
        if df is None or len(df) < 2:
            logger.warning(f"[engine] تاریخچه قیمت کافی برای '{symbol}' موجود نیست")
            return False

        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]
        date_str = str(df.index[-1]).split()[0]

        close = float(last_row.get('close', last_row.get('Close', 0.0)))
        final = float(last_row.get('final', last_row.get('Final', close)))
        high = float(last_row.get('high', last_row.get('High', close)))
        low = float(last_row.get('low', last_row.get('Low', close)))
        volume = float(last_row.get('volume', last_row.get('Volume', 0.0)))
        value = float(last_row.get('value', last_row.get('Value', volume * close)))
        prev_close = float(prev_row.get('close', prev_row.get('Close', close)))

        real_buyer_count = 0
        real_seller_count = 0
        real_buy_val = 0.0
        real_sell_val = 0.0
        client_type_ok = False

        try:
            data = _fetch_client_type_direct(inscode)
            client_types = data.get('clientTypes', [])
            if client_types:
                last_record = client_types[-1]
                real_buyer_count = int(last_record.get('buyCountI', 0))
                real_seller_count = int(last_record.get('sellCountI', 0))
                real_buy_val = float(last_record.get('buyValI', 0))
                real_sell_val = float(last_record.get('sellValI', 0))
                client_type_ok = True
        except Exception as e:
            logger.warning(
                f"[engine] گرفتن آمار حقیقی/حقوقی '{symbol}' (InsCode={inscode}) شکست خورد: {e}"
            )

        if not client_type_ok:
            logger.warning(
                f"[engine] '{symbol}' با مقدار پیش‌فرض صفر برای حقیقی/حقوقی ذخیره می‌شود (داده واقعی در دسترس نبود)"
            )

        buy_per_capita = real_buy_val / (real_buyer_count if real_buyer_count > 0 else 1)
        sell_per_capita = real_sell_val / (real_seller_count if real_seller_count > 0 else 1)
        buyer_power = round(buy_per_capita / (sell_per_capita + 1e-6), 2)

        price_change_pct = ((close - prev_close) / prev_close) * 100

        if price_change_pct < 0 or close < prev_close:
            sell_queue_vol = volume * 0.3
            buy_queue_vol = 0.0
            prediction_label = "صف فروش و فشار عرضه‌ی سنگین 📉"
            score = 15.0
        else:
            buy_queue_vol = volume * 0.3
            sell_queue_vol = 0.0
            prediction_label = "صف خرید احتمالی قوی 🚀"
            score = 85.0

        queue_ratio = round(buy_queue_vol / (sell_queue_vol + 1e-6), 2)
        distance_to_high_pct = round(((high - close) / high) * 100, 2) if high > 0 else 0.0

        conn = sqlite3.connect('ahram_v2.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO daily_features (
                date, symbol, close, final, high, low, volume, value,
                buy_queue_vol, sell_queue_vol, queue_ratio,
                real_buyer_count, real_seller_count, buy_per_capita, sell_per_capita,
                buyer_power, distance_to_high_pct, prediction_label, prediction_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            date_str, symbol, close, final, high, low, volume, value,
            buy_queue_vol, sell_queue_vol, queue_ratio,
            real_buyer_count, real_seller_count, buy_per_capita, sell_per_capita,
            buyer_power, distance_to_high_pct, prediction_label, score
        ))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error in engine execution for '{symbol}': {e}")
        return False