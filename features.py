import pandas as pd
import ta

def calculate_daily_features(df):
    """
    محاسبه ویژگی‌های تکنیکال و روزانه برای یک نماد
    """
    try:
        if df is None or len(df) < 20:
            return None

        # اطمینان از اینکه ایندکس تاریخ است
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)

        df = df.copy()
        df.columns = [str(col).strip().capitalize() for col in df.columns]

        close = float(df['Close'].iloc[-1])
        volume = float(df['Volume'].iloc[-1])
        
        # محاسبه میانگین متحرک حجم (VMA20)
        vma20 = float(df['Volume'].rolling(window=20).mean().iloc[-1])

        # VWAP
        typical_price = (df['High'] + df['Low'] + df['Close']) / 3
        vwap = float((typical_price * df['Volume']).cumsum().iloc[-1] / df['Volume'].cumsum().iloc[-1])

        # RSI
        rsi_series = ta.momentum.rsi(df['Close'], window=14)
        rsi = float(rsi_series.iloc[-1]) if not rsi_series.empty else 50.0

        # ATR
        atr_series = ta.volatility.average_true_range(df['High'], df['Low'], df['Close'], window=14)
        atr = float(atr_series.iloc[-1]) if not atr_series.empty else 0.0

        # Close Location Value (CLV)
        high = float(df['High'].iloc[-1])
        low = float(df['Low'].iloc[-1])
        clv = float(((close - low) - (high - close)) / (high - low)) if (high - low) > 0 else 0.0

        # فیگورهای کندل
        open_p = float(df['Open'].iloc[-1])
        body = abs(close - open_p)
        total_range = high - low if (high - low) > 0 else 1.0
        
        upper_wick = high - max(close, open_p)
        lower_wick = min(close, open_p) - low

        upper_wick_pct = float(upper_wick / total_range)
        lower_wick_pct = float(lower_wick / total_range)
        body_pct = float(body / total_range)

        return {
            "close": close,
            "volume": volume,
            "vma20": vma20,
            "vwap": vwap,
            "rsi": rsi,
            "atr": atr,
            "close_location_value": clv,
            "upper_wick_pct": upper_wick_pct,
            "lower_wick_pct": lower_wick_pct,
            "body_pct": body_pct
        }
    except Exception as e:
        print(f"Error in features calculation: {e}")
        return None