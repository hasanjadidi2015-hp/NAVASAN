from engine import init_db, evaluate_and_predict

print("--- در حال راه‌اندازی دیتابیس ---")
init_db()

print("--- تست اجرای موتور پردازش برای نماد فملی ---")
success = evaluate_and_predict("فملی")

if success:
    print("موفقیت‌آمیز بود! داده‌ها در جدول ذخیره شدند.")
else:
    print("اجرا با خطا مواجه شد. لاگ‌ها را بررسی کنید.")