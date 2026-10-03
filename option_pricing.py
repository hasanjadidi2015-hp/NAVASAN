# option_pricing.py
import math
from typing import Dict, Any

# نرخ بهره بدون ریسک سالانه در ایران (تقریباً ۳۰٪)
RISK_FREE_RATE = 0.30

def _norm_cdf(x: float) -> float:
    """تابع توزیع تراکمی نرمال استاندارد."""
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0

def black_scholes_call(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """محاسبه قیمت منصفانه قرارداد کال با مدل بلک-شولز."""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return max(0.0, S - K)
    
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    
    call_price = S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    return max(0.0, call_price)

def calculate_implied_volatility(market_price: float, S: float, K: float, T: float, r: float = RISK_FREE_RATE) -> float:
    """محاسبه نوسان ضمنی (Implied Volatility - IV) با روش تنصیف (Bisection)."""
    if T <= 0 or market_price <= 0 or S <= 0 or K <= 0:
        return 0.0
    
    intrinsic_value = max(0.0, S - K)
    if market_price <= intrinsic_value:
        return 0.01
    
    low_sigma = 0.01
    high_sigma = 3.0
    
    for _ in range(30):
        mid_sigma = (low_sigma + high_sigma) / 2.0
        price = black_scholes_call(S, K, T, r, mid_sigma)
        
        if abs(price - market_price) < 1.0:
            return mid_sigma
        
        if price < market_price:
            low_sigma = mid_sigma
        else:
            high_sigma = mid_sigma
            
    return (low_sigma + high_sigma) / 2.0

def evaluate_option_contract(
    stock_price: float,
    strike_price: float,
    days_to_expire: int,
    option_market_price: float,
    is_call: bool = True,
    historical_volatility: float = 0.35
) -> Dict[str, Any]:
    """
    تحلیل کامل ارزش، حباب ترس (IV Crush)، نقطه سه‌به‌سر سهم و ذوب زمانی (Theta).
    """
    if stock_price <= 0 or strike_price <= 0 or days_to_expire <= 0 or option_market_price <= 0:
        return {
            "fair_price": 0,
            "bubble_pct": 0,
            "iv_pct": 0,
            "status": "داده نامعتبر",
            "status_class": "text-muted",
            "breakeven_stock": 0,
            "breakeven_move_pct": 0,
            "iv_crush_risk": False,
            "theta_hazard": False,
            "sl_price": 0,
            "tp1_price": 0,
        }
    
    T = days_to_expire / 365.0
    r = RISK_FREE_RATE
    
    # ۱. محاسبه نوسان ضمنی (IV)
    iv = calculate_implied_volatility(option_market_price, stock_price, strike_price, T, r)
    
    # ۲. محاسبه قیمت منصفانه (Fair Value)
    fair_price = black_scholes_call(stock_price, strike_price, T, r, max(0.25, historical_volatility))
    
    # ۳. محاسبه درصد حباب
    bubble_pct = ((option_market_price - fair_price) / fair_price) * 100.0 if fair_price > 0 else 0.0
        
    # ۴. محاسبه نقطه سه‌به‌سر واقعی سهم (Break-Even Stock Price)
    if is_call:
        breakeven_stock = strike_price + option_market_price
        breakeven_move_pct = ((breakeven_stock - stock_price) / stock_price) * 100.0
    else:
        breakeven_stock = strike_price - option_market_price
        breakeven_move_pct = ((stock_price - breakeven_stock) / stock_price) * 100.0

    # ۵. بررسی ریسک‌های کلیدی مقاله (IV Crush & Theta Hazard)
    iv_crush_risk = (iv * 100.0) >= 65.0 or bubble_pct >= 35.0
    theta_hazard = days_to_expire <= 15

    # ۶. تعیین برچسب وضعیت حباب و ریسک
    if iv_crush_risk:
        status = "⚠️ ریسک تخلیه حباب ترس (IV Crush)"
        status_class = "text-red"
    elif bubble_pct < -10.0:
        status = "💎 ارزان / زیر ارزش ذاتی"
        status_class = "text-green"
    elif theta_hazard:
        status = "⏱️ ذوب زمانی بالا (Theta High)"
        status_class = "text-red"
    else:
        status = "✅ قیمت منصفانه"
        status_class = "text-green"
        
    # ۷. سطوح حد ضرر و حد سود اختصاصی پریمیوم آپشن
    sl_price = int(round(option_market_price * 0.85))    # حد ضرر ۱۵٪-
    tp1_price = int(round(option_market_price * 1.25))   # هدف اول ۲۵٪+
    
    return {
        "fair_price": int(round(fair_price)),
        "bubble_pct": round(bubble_pct, 1),
        "iv_pct": round(iv * 100.0, 1),
        "status": status,
        "status_class": status_class,
        "breakeven_stock": int(round(breakeven_stock)),
        "breakeven_move_pct": round(breakeven_move_pct, 1),
        "iv_crush_risk": iv_crush_risk,
        "theta_hazard": theta_hazard,
        "sl_price": sl_price,
        "tp1_price": tp1_price,
    }