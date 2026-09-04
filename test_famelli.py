import requests

def test_tsetmc_famelli():
    symbol = "فملی"
    print(f"--- در حال دریافت داده‌های واقعی برای نماد: {symbol} ---")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'http://www.tsetmc.com/'
    }
    
    # استفاده از API مدرن TSETMC برای جستجوی دقیق نماد و کد شناسایی (InsCode)
    search_url = f"https://cdn.tsetmc.com/api/Instrument/GetInstrumentInfo/4634855739771144"
    
    # دریافت اطلاعات حقیقی و حقوقی از طریق API جدید (ClientType API)
    client_url = "https://cdn.tsetmc.com/api/ClientType/GetClientTypeData/4634855739771144"
    
    real_buyer_count, real_seller_count = 0, 0
    real_buy_val, real_sell_val = 0.0, 0.0
    target_date = ""

    try:
        response = requests.get(client_url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            # بررسی ساختار JSON بازگشتی از سرور جدید بورس
            client_types = data.get('clientTypes', [])
            if client_types:
                # برداشتن آخرین رکورد معاملاتی (جدیدترین روز)
                last_record = client_types[-1]
                target_date = str(last_record.get('deven', ''))
                
                real_buyer_count = int(last_record.get('buyCountI', 0))
                real_seller_count = int(last_record.get('sellCountI', 0))
                
                # مقادیر بر حسب ریال یا حجم ضربدر قیمت
                real_buy_val = float(last_record.get('buyValI', 0))
                real_sell_val = float(last_record.get('sellValI', 0))
    except Exception as e:
        print(f"خطا در اتصال به API جدید TSETMC: {e}")

    print(f"\n--- آخرین آمار معاملاتی معتبر (تاریخ: {target_date}) ---")
    print(f"تعداد خریدار حقیقی: {real_buyer_count:,}")
    print(f"تعداد فروشنده حقیقی: {real_seller_count:,}")
    print(f"ارزش خرید حقیقی: {real_buy_val:,.0f} ریال")
    print(f"ارزش فروش حقیقی: {real_sell_val:,.0f} ریال")

    if real_buyer_count > 0 and real_seller_count > 0:
        buy_per_capita = real_buy_val / real_buyer_count
        sell_per_capita = real_sell_val / real_seller_count
        buyer_power = round(buy_per_capita / (sell_per_capita + 1e-6), 2)

        print(f"\nسرانه خرید حقیقی: {buy_per_capita:,.0f} ریال")
        print(f"سرانه فروش حقیقی: {sell_per_capita:,.0f} ریال")
        print(f"قدرت خرید به فروشنده: {buyer_power}")
    else:
        print("\nمقادیر دریافت شده صفر است. لطفاً اتصال اینترنت یا وضعیت دسترسی به سورس را بررسی کنید.")

if __name__ == "__main__":
    test_tsetmc_famelli()