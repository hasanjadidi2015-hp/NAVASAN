# fix_live_tracker.py
"""
این اسکریپت فقط یک خط توی live_tracker.py رو اصلاح می‌کنه (خطی که با تغییر collector.py از کار افتاده بود).
قبل از هر تغییری از فایل بک‌آپ می‌گیره (live_tracker.py.bak).

اجرا (داخل پوشه‌ی navasan):
    python fix_live_tracker.py
"""

import os
import shutil

FILE = "live_tracker.py"
OLD = "raw, _regime = fetch_enriched_target_data(max_workers=6)"
NEW = "raw = fetch_enriched_target_data(max_workers=6)[0]"


def main():
    if not os.path.exists(FILE):
        print("❌ فایل live_tracker.py توی این پوشه پیدا نشد.")
        print("   مطمئن شو ترمینال داخل پوشه‌ی navasan باز شده (جلوی خط باید ...\\navasan> نوشته باشه).")
        return

    with open(FILE, encoding="utf-8") as f:
        text = f.read()

    if NEW in text and OLD not in text:
        print("✅ این فایل از قبل اصلاح شده؛ کاری لازم نیست.")
        return

    count = text.count(OLD)
    if count == 0:
        print("⚠️ خط مورد نظر پیدا نشد (شاید فایل تغییر کرده). هیچ‌چیز عوض نشد.")
        print("   این خط‌ها رو برای من بفرست:")
        for i, line in enumerate(text.splitlines(), 1):
            if "fetch_enriched_target_data" in line:
                print(f"   خط {i}: {line.strip()}")
        return

    shutil.copy(FILE, FILE + ".bak")
    with open(FILE, "w", encoding="utf-8") as f:
        f.write(text.replace(OLD, NEW))
    print(f"✅ {count} خط اصلاح شد. نسخه‌ی قبلی توی live_tracker.py.bak نگه داشته شد.")


if __name__ == "__main__":
    main()