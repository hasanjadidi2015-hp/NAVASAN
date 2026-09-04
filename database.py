import sqlite3

def init_db():
    conn = sqlite3.connect('ahram_v2.db')
    cursor = conn.cursor()
    
    # جدول ذخیره وضعیت نمادها و ویژگی‌های استخراج‌شده در پایان روز
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_features (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            symbol TEXT,
            close REAL,
            volume REAL,
            vma20 REAL,
            vwap REAL,
            rsi REAL,
            atr REAL,
            close_location_value REAL,
            upper_wick_pct REAL,
            lower_wick_pct REAL,
            body_pct REAL,
            market_regime TEXT,
            industry_strength REAL,
            UNIQUE(date, symbol)
        )
    ''')
    
    # جدول ثبت پیش‌بینی‌ها و مقایسه با نتیجه واقعی روز بعد (برای ارزیابی و مدل‌سازی)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS prediction_journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            symbol TEXT,
            score REAL,
            p_positive REAL,
            p_plus2 REAL,
            p_buy_queue REAL,
            next_day_return REAL,
            next_day_high REAL,
            next_day_buy_queue INTEGER,
            is_evaluated INTEGER DEFAULT 0,
            prediction_correct INTEGER
        )
    ''')
    
    conn.commit()
    conn.close()
    print("Database V2 initialized successfully.")

if __name__ == '__main__':
    init_db()