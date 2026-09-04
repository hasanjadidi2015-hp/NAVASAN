from flask import Flask, render_template_string, request
import sqlite3
import engine
import backtest

app = Flask(__name__)

RAHAVARD_STYLE_TEMPLATE = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>تحلیگر حرفه‌ای بورس - {{ symbol }}</title>
    <style>
        body { font-family: Tahoma, sans-serif; background-color: #eef2f5; margin: 0; padding: 15px; color: #333; }
        .main-container { max-width: 1250px; margin: auto; background: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        .header-box { background: #1e293b; color: white; padding: 15px 20px; border-radius: 6px; display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
        .header-box h1 { margin: 0; font-size: 20px; }
        .search-form input { padding: 8px 12px; border-radius: 4px; border: none; width: 140px; font-family: Tahoma; }
        .search-form button { padding: 8px 15px; background: #3b82f6; color: white; border: none; border-radius: 4px; cursor: pointer; font-family: Tahoma; }
        
        .ai-banner { background: linear-gradient(135deg, #3b82f6, #1d4ed8); color: white; padding: 15px 20px; border-radius: 6px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; }
        .ai-banner h2 { margin: 0; font-size: 18px; }
        .ai-banner .badge { background: #f59e0b; color: #000; padding: 5px 12px; border-radius: 20px; font-weight: bold; font-size: 14px; }

        .dashboard-grid { display: grid; grid-template-columns: 2fr 1.2fr 1.2fr; gap: 15px; margin-bottom: 20px; }
        @media (max-width: 900px) { .dashboard-grid { grid-template-columns: 1fr; } }

        .panel { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 15px; }
        .panel h3 { margin-top: 0; font-size: 15px; color: #1e293b; border-bottom: 2px solid #cbd5e1; padding-bottom: 8px; }

        .data-table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 13px; }
        .data-table th, .data-table td { padding: 8px; text-align: center; border-bottom: 1px solid #e2e8f0; }
        .data-table th { background: #e2e8f0; color: #334155; }

        .row-item { display: flex; justify-content: space-between; padding: 7px 0; border-bottom: 1px dashed #e2e8f0; font-size: 13px; }
        .row-item span:last-child { font-weight: bold; color: #0f172a; }
        
        .positive { color: #16a34a; font-weight: bold; }
        .negative { color: #dc2626; font-weight: bold; }
        .backtest-section { background: #f1f5f9; padding: 15px; border-radius: 6px; margin-top: 20px; }
    </style>
</head>
<body>
    <div class="main-container">
        
        <div class="header-box">
            <h1>نماد معاملاتی: {{ symbol }} (تاریخ داده: {{ date_str }})</h1>
            <form class="search-form" method="GET" action="/">
                <input type="text" name="symbol" value="{{ symbol }}" placeholder="نام نماد...">
                <button type="submit">جستجو</button>
            </form>
        </div>

        <!-- بخش پیش‌بینی هوشمند فردا (هدف اصلی پروژه) -->
        <div class="ai-banner">
            <div>
                <h2>پیش‌بینی هوشمند وضعیت سهم برای روز معاملاتی بعد</h2>
                <p style="margin: 5px 0 0 0; font-size: 13px; opacity: 0.9;">بر اساس قدرت حقیقی‌ها، حجم صف و فواصل قیمتی</p>
            </div>
            <div class="badge">{{ prediction_label }} (امتیاز: {{ prediction_score }})</div>
        </div>

        <div class="dashboard-grid">
            <div class="panel">
                <h3>وضعیت قیمت و معاملات</h3>
                <div class="row-item"><span>آخرین قیمت:</span> <span>{{ close }}</span></div>
                <div class="row-item"><span>قیمت پایانی:</span> <span>{{ final }}</span></div>
                <div class="row-item"><span>بیشترین / کمترین روز:</span> <span>{{ high }} / {{ low }}</span></div>
                <div class="row-item"><span>حجم معاملات:</span> <span>{{ "{:,}".format(volume|int) }}</span></div>
                <div class="row-item"><span>ارزش معاملات:</span> <span>{{ "{:,}".format(value|int) }} ریال</span></div>
                <div class="row-item"><span>فاصله تا سقف روز:</span> <span class="negative">{{ distance_to_high_pct }}%</span></div>
            </div>

            <div class="panel">
                <h3>سرانه و قدرت خرید حقیقی</h3>
                <div class="row-item"><span>قدرت خرید به فروشنده:</span> <span class="{{ 'positive' if buyer_power >= 1 else 'negative' }}">{{ buyer_power }}</span></div>
                <div class="row-item"><span>سرانه خرید حقیقی:</span> <span>{{ buy_per_capita }} ریال</span></div>
                <div class="row-item"><span>سرانه فروش حقیقی:</span> <span>{{ sell_per_capita }} ریال</span></div>
                <div class="row-item"><span>تعداد خریدار حقیقی:</span> <span>{{ real_buyer_count }} نفر</span></div>
                <div class="row-item"><span>تعداد فروشنده حقیقی:</span> <span>{{ real_seller_count }} نفر</span></div>
            </div>

            <div class="panel">
                <h3>وضعیت صف و عرضه و تقاضا</h3>
                <div class="row-item"><span>حجم صف خرید:</span> <span class="positive">{{ "{:,}".format(buy_queue_vol|int) }}</span></div>
                <div class="row-item"><span>حجم صف فروش:</span> <span class="negative">{{ "{:,}".format(sell_queue_vol|int) }}</span></div>
                <div class="row-item"><span>نسبت صف خرید/فروش:</span> <span>{{ queue_ratio }}</span></div>
            </div>
        </div>

        <div class="backtest-section">
            <h3>نتایج بک‌تست استراتژی روی نماد {{ symbol }}</h3>
            <div style="display: flex; justify-content: space-around; margin-bottom: 10px; font-size: 14px;">
                <span><strong>تعداد کل معاملات:</strong> {{ bt.total_trades }}</span>
                <span><strong>نرخ پیروزی (Win Rate):</strong> {{ bt.win_rate }}%</span>
                <span><strong>بازدهی تجمیعی:</strong> {{ bt.total_return }}%</span>
            </div>
            
            <table class="data-table">
                <tr>
                    <th>تاریخ ورود</th>
                    <th>تاریخ خروج</th>
                    <th>قیمت ورود</th>
                    <th>قیمت خروج</th>
                    <th>بازدهی</th>
                </tr>
                {% for t in bt.trades %}
                <tr>
                    <td>{{ t.entry_date }}</td>
                    <td>{{ t.exit_date }}</td>
                    <td>{{ t.entry_price }}</td>
                    <td>{{ t.exit_price }}</td>
                    <td class="{{ 'positive' if t.win else 'negative' }}">{{ t.return_pct }}%</td>
                </tr>
                {% endfor %}
            </table>
        </div>

    </div>
</body>
</html>
"""

def get_data_from_db(symbol):
    try:
        conn = sqlite3.connect('ahram_v2.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT date, close, final, high, low, volume, value,
                   buy_queue_vol, sell_queue_vol, queue_ratio,
                   real_buyer_count, real_seller_count, buy_per_capita, sell_per_capita,
                   buyer_power, distance_to_high_pct, prediction_label, prediction_score
            FROM daily_features WHERE symbol = ? ORDER BY id DESC LIMIT 1
        ''', (symbol,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {
                "date_str": row[0],
                "close": row[1],
                "final": row[2],
                "high": row[3],
                "low": row[4],
                "volume": row[5],
                "value": row[6],
                "buy_queue_vol": row[7],
                "sell_queue_vol": row[8],
                "queue_ratio": row[9],
                "real_buyer_count": row[10],
                "real_seller_count": row[11],
                "buy_per_capita": f"{int(row[12]):,}" if row[12] else "0",
                "sell_per_capita": f"{int(row[13]):,}" if row[13] else "0",
                "buyer_power": row[14],
                "distance_to_high_pct": row[15],
                "prediction_label": row[16],
                "prediction_score": row[17]
            }
    except Exception as e:
        print(f"DB Error: {e}")
    return None

@app.route('/')
def dashboard():
    symbol = request.args.get('symbol', 'اهرم')
    engine.evaluate_and_predict(symbol)
    
    data = get_data_from_db(symbol)
    if not data:
        data = {
            "date_str": "-", "close": 0, "final": 0, "high": 0, "low": 0,
            "volume": 0, "value": 0, "buy_queue_vol": 0, "sell_queue_vol": 0,
            "queue_ratio": 0, "real_buyer_count": 0, "real_seller_count": 0,
            "buy_per_capita": "0", "sell_per_capita": "0", "buyer_power": 0,
            "distance_to_high_pct": 0, "prediction_label": "نامشخص", "prediction_score": 0
        }
    
    data["symbol"] = symbol
    
    try:
        from pytse_client import Ticker
        ticker = Ticker(symbol)
        bt_results = backtest.run_backtest(ticker.history)
        data["bt"] = bt_results
    except Exception as e:
        data["bt"] = {"total_trades": 0, "win_rate": 0.0, "total_return": 0.0, "trades": []}
        
    return render_template_string(RAHAVARD_STYLE_TEMPLATE, **data)

if __name__ == '__main__':
    engine.init_db()
    app.run(host='127.0.0.1', port=5000, debug=True)