# debug_keys.py
from collector import fetch_market_watch_data
import json

raw = fetch_market_watch_data()
print(f"تعداد کل آیتم‌ها: {len(raw)}")

if raw:
    first = raw[0]
    print("\n===== کلیدهای موجود در اولین نماد =====")
    print(list(first.keys()))
    print("\n===== نمونه کامل اولین نماد (JSON) =====")
    print(json.dumps(first, ensure_ascii=False, indent=2)[:2000])
else:
    print("لیست خالی برگشت!")