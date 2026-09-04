# collector.py
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Tuple

import requests

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.tsetmc.com/",
    "Origin": "https://www.tsetmc.com",
    "Accept-Language": "fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def normalize_fa(text: str) -> str:
    if not text:
        return ""
    text = str(text).strip()
    text = text.replace("ي", "ی").replace("ك", "ک")
    text = text.replace("\u200c", " ").replace("\u200b", " ")
    return " ".join(text.split())


RAW_TARGETS = {
    "خبهمن", "خساپا", "خودرو", "وبصادر", "وبملت", "وتجارت",
    "اطلس", "اهرم", "توان", "جوانه", "جوانه کوچک", "دارونو",
    "طعام", "موج", "ذوب", "فملی", "اخابر", "بساما",
    "تاصیکو", "شستا", "شپنا", "فزر", "طلا", "کهربا",
}
TARGET_SYMBOLS = {normalize_fa(s) for s in RAW_TARGETS}

FREE_FLOAT_PCT_FALLBACK = {
    "فملی": 22.0, "ذوب": 35.0, "خودرو": 28.0, "خساپا": 30.0, "خبهمن": 25.0,
    "وبملت": 25.0, "وتجارت": 30.0, "وبصادر": 30.0, "شستا": 20.0, "شپنا": 20.0,
    "اخابر": 20.0, "تاصیکو": 25.0, "بساما": 40.0, "فزر": 25.0, "دارونو": 30.0,
    "اهرم": 100.0, "توان": 100.0, "موج": 100.0, "طلا": 100.0, "کهربا": 100.0,
    "اطلس": 100.0, "طعام": 100.0, "جوانه": 100.0, "جوانه کوچک": 100.0,
}


def safe_parse_tsetmc_response(raw_text: str, symbol: str = "") -> Any:
    if not raw_text or not str(raw_text).strip():
        return {}
    text = str(raw_text).strip()
    if text.startswith("\ufeff"):
        text = text[1:]
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        obj, _ = json.JSONDecoder().raw_decode(text)
        return obj
    except json.JSONDecodeError:
        pass
    match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    return {}


def _f(val, default=0.0) -> float:
    try:
        if val is None or val == "":
            return float(default)
        return float(val)
    except (TypeError, ValueError):
        return float(default)


def _get(d: dict, *keys, default=None):
    if not isinstance(d, dict):
        return default
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    lower_map = {str(k).lower(): k for k in d.keys()}
    for k in keys:
        real = lower_map.get(str(k).lower())
        if real is not None and d[real] is not None:
            return d[real]
    return default


def fetch_raw_market_watch() -> List[Dict[str, Any]]:
    url = (
        "https://cdn.tsetmc.com/api/ClosingPrice/GetMarketWatch?"
        "market=0&industrialGroup=&paperTypes%5B0%5D=1&paperTypes%5B1%5D=2"
        "&paperTypes%5B2%5D=3&paperTypes%5B3%5D=4&paperTypes%5B4%5D=5"
        "&paperTypes%5B5%5D=6&paperTypes%5B6%5D=7&paperTypes%5B7%5D=8"
        "&paperTypes%5B8%5D=9&showAll=true"
    )
    try:
        logger.info("دریافت Market Watch...")
        r = SESSION.get(url, timeout=20)
        if r.status_code != 200:
            logger.error(f"MarketWatch status={r.status_code}")
            return []
        data = safe_parse_tsetmc_response(r.text, "MarketWatch")
        rows = []
        if isinstance(data, dict):
            rows = data.get("marketwatch", []) or []
        logger.info(f"کل نمادها: {len(rows)}")
        return rows if isinstance(rows, list) else []
    except requests.exceptions.RequestException as e:
        logger.error(f"خطای MarketWatch: {e}")
        return []


def fetch_index_returns() -> Dict[str, float]:
    result = {"market_return_pct": 0.0, "equal_weight_return_pct": 0.0, "index_ok": False}
    urls = [
        "https://cdn.tsetmc.com/api/Index/GetIndexB1LastAll/All/1",
        "https://cdn.tsetmc.com/api/Index/GetIndexB1LastAll/All/0",
    ]
    for url in urls:
        try:
            r = SESSION.get(url, timeout=12)
            if r.status_code != 200:
                continue
            data = safe_parse_tsetmc_response(r.text, "Index")
            rows = []
            if isinstance(data, dict):
                rows = data.get("indexB1") or data.get("indexB1Last") or data.get("index") or []
            elif isinstance(data, list):
                rows = data
            if not isinstance(rows, list):
                continue

            market_ret = equal_ret = None
            for row in rows:
                if not isinstance(row, dict):
                    continue
                name = normalize_fa(str(_get(row, "lVal30", "xNamNIvJIdx_DIns", "name", default="")))
                last_i = _f(_get(row, "xDrNivJIdx004", "last", default=0))
                prev_i = _f(_get(row, "xPhNivJIdx004", "yesterday", "py", default=0))
                ch = _f(_get(row, "xVarIdxJEncP", "changePercent", "pc", default=0))
                if prev_i > 0 and last_i > 0 and abs(ch) < 1e-12:
                    ch = ((last_i - prev_i) / prev_i) * 100
                if "هم وزن" in name or "هم‌وزن" in name or "هموزن" in name:
                    equal_ret = ch
                if "شاخص کل" in name and "فرابورس" not in name and "هم" not in name:
                    market_ret = ch
                if name == "شاخص کل":
                    market_ret = ch
            if market_ret is not None:
                result["market_return_pct"] = round(market_ret, 3)
                result["index_ok"] = True
            if equal_ret is not None:
                result["equal_weight_return_pct"] = round(equal_ret, 3)
                result["index_ok"] = True
            if result["index_ok"]:
                return result
        except Exception as e:
            logger.warning(f"index error: {e}")
    return result


def compute_market_regime(all_items: List[Dict[str, Any]], index_info: Dict[str, float]) -> Dict[str, Any]:
    returns = []
    pos = neg = flat = 0
    buy_q_like = sell_q_like = 0
    industry_returns: Dict[str, List[float]] = {}

    for item in all_items:
        symbol = normalize_fa(item.get("lva", ""))
        name = str(item.get("lvc", ""))
        if (
            not symbol or symbol.startswith("ض") or symbol.startswith("ط")
            or "اخزا" in symbol or "اختيار" in name or "اختیار" in name
        ):
            continue
        py = _f(item.get("py"))
        pcl = _f(item.get("pcl"))
        if py <= 0 or pcl <= 0:
            continue
        ret = ((pcl - py) / py) * 100
        returns.append(ret)
        if ret >= 0.2: pos += 1
        elif ret <= -0.2: neg += 1
        else: flat += 1
        if ret >= 4.5: buy_q_like += 1
        if ret <= -4.5: sell_q_like += 1
        ind = str(item.get("cGrValCot") or "UNK").strip() or "UNK"
        industry_returns.setdefault(ind, []).append(ret)

    n = max(1, pos + neg + flat)
    avg_ret = sum(returns) / len(returns) if returns else 0.0
    breadth = (pos / n) * 100.0

    market_return = index_info.get("market_return_pct") or 0.0
    equal_return = index_info.get("equal_weight_return_pct") or 0.0
    if not index_info.get("index_ok"):
        market_return = avg_ret
        equal_return = avg_ret

    score = 0
    score += 2 if market_return >= 0.7 else 1 if market_return >= 0.15 else -2 if market_return <= -0.7 else -1 if market_return <= -0.15 else 0
    score += 2 if equal_return >= 0.7 else 1 if equal_return >= 0.15 else -2 if equal_return <= -0.7 else -1 if equal_return <= -0.15 else 0
    score += 2 if breadth >= 60 else 1 if breadth >= 52 else -2 if breadth <= 35 else -1 if breadth <= 45 else 0
    if buy_q_like > sell_q_like * 1.5: score += 1
    if sell_q_like > buy_q_like * 1.5: score -= 1

    if score >= 3:
        regime, multiplier, label = "bull", 1.15, "بازار مثبت / ریسک‌پذیر 🟢"
    elif score <= -3:
        regime, multiplier, label = "bear", 0.75, "بازار منفی / ریسک‌گریز 🔴"
    else:
        regime, multiplier, label = "neutral", 1.0, "بازار خنثی / متعادل ⚪"

    industry_avg = {k: (sum(v) / len(v) if v else 0.0) for k, v in industry_returns.items()}
    return {
        "market_return_pct": round(market_return, 3),
        "equal_weight_return_pct": round(equal_return, 3),
        "avg_stock_return_pct": round(avg_ret, 3),
        "breadth_pos_pct": round(breadth, 2),
        "pos_count": pos, "neg_count": neg, "flat_count": flat,
        "buy_queue_like": buy_q_like, "sell_queue_like": sell_q_like,
        "regime": regime, "regime_label": label, "market_multiplier": multiplier,
        "industry_avg": industry_avg, "sample_size": len(returns),
    }


def _empty_ct() -> Dict[str, float]:
    return {
        "buy_i_vol": 0.0, "sell_i_vol": 0.0, "buy_n_vol": 0.0, "sell_n_vol": 0.0,
        "buy_i_val": 0.0, "sell_i_val": 0.0, "buy_count_i": 0.0, "sell_count_i": 0.0,
    }


def normalize_client_type(ct: Dict[str, Any]) -> Dict[str, float]:
    if not isinstance(ct, dict):
        return _empty_ct()
    return {
        "buy_i_vol": _f(_get(ct, "buy_I_Volume", "Buy_I_Volume", "buy_I_Vol", "BuyIVolume", "buyIVolume", default=0)),
        "sell_i_vol": _f(_get(ct, "sell_I_Volume", "Sell_I_Volume", "sell_I_Vol", "SellIVolume", "sellIVolume", default=0)),
        "buy_n_vol": _f(_get(ct, "buy_N_Volume", "Buy_N_Volume", "buy_N_Vol", "BuyNVolume", default=0)),
        "sell_n_vol": _f(_get(ct, "sell_N_Volume", "Sell_N_Volume", "sell_N_Vol", "SellNVolume", default=0)),
        "buy_i_val": _f(_get(ct, "buy_I_Value", "Buy_I_Value", "buy_I_Val", "BuyIValue", default=0)),
        "sell_i_val": _f(_get(ct, "sell_I_Value", "Sell_I_Value", "sell_I_Val", "SellIValue", default=0)),
        "buy_count_i": _f(_get(ct, "buy_CountI", "Buy_CountI", "buy_Count_I", "BuyCountI", "buyCountI", default=0)),
        "sell_count_i": _f(_get(ct, "sell_CountI", "Sell_CountI", "sell_Count_I", "SellCountI", "sellCountI", default=0)),
    }


def _parse_client_type_aspx(text: str) -> Dict[str, Dict[str, float]]:
    """
    فرمت خام tsetmc قدیمی:
    ins,Buy_CountI,Buy_CountN,Buy_I_Volume,Buy_N_Volume,Sell_CountI,Sell_CountN,
    Sell_I_Volume,Sell_N_Volume;
    """
    result: Dict[str, Dict[str, float]] = {}
    raw = (text or "").strip()
    if not raw:
        return result

    chunks = raw.replace("\n", ";").split(";")
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = [p.strip() for p in chunk.split(",")]
        if len(parts) < 9:
            continue
        ins = parts[0]
        if not re.match(r"^\d+$", ins):
            continue

        ct = _empty_ct()
        try:
            ct["buy_count_i"] = _f(parts[1])
            # parts[2] = buy_count_n
            ct["buy_i_vol"] = _f(parts[3])
            ct["buy_n_vol"] = _f(parts[4])
            ct["sell_count_i"] = _f(parts[5])
            # parts[6] = sell_count_n
            ct["sell_i_vol"] = _f(parts[7])
            ct["sell_n_vol"] = _f(parts[8])
            if len(parts) >= 13:
                ct["buy_i_val"] = _f(parts[9])
                ct["sell_i_val"] = _f(parts[11])
        except Exception:
            continue

        if any(v > 0 for v in ct.values()):
            result[ins] = ct
    return result


def fetch_client_type_all() -> Dict[str, Dict[str, float]]:
    """دریافت یکجا از endpoint ASPX (حجم + تعداد)."""
    result: Dict[str, Dict[str, float]] = {}

    old_urls = [
        "https://www.tsetmc.com/tsev2/data/ClientTypeAll.aspx",
        "http://www.tsetmc.com/tsev2/data/ClientTypeAll.aspx",
        "https://old.tsetmc.com/tsev2/data/ClientTypeAll.aspx",
    ]
    for url in old_urls:
        try:
            r = SESSION.get(url, timeout=20)
            logger.info(f"ClientTypeAll ASPX status={r.status_code} len={len(r.text or '')}")
            if r.status_code != 200:
                continue
            parsed = _parse_client_type_aspx(r.text)
            if parsed:
                logger.info(f"ClientTypeAll ASPX رکورد: {len(parsed)}")
                return parsed
        except Exception as e:
            logger.warning(f"ClientTypeAll ASPX error: {e}")
    return result


def fetch_client_type_one(ins_code: str) -> Dict[str, float]:
    """دریافت تکی حقیقی/حقوقی - این endpoint شامل تعداد خریدار/فروشنده هم هست."""
    if not ins_code:
        return _empty_ct()

    urls = [
        f"https://cdn.tsetmc.com/api/ClientType/GetClientType/{ins_code}/1/0",
        f"https://cdn.tsetmc.com/api/ClientType/GetClientType/{ins_code}/0/0",
        f"http://cdn.tsetmc.com/api/ClientType/GetClientType/{ins_code}/1/0",
    ]

    for url in urls:
        try:
            r = SESSION.get(url, timeout=10)
            if r.status_code != 200:
                continue
            data = safe_parse_tsetmc_response(r.text, ins_code)
            if not isinstance(data, dict):
                continue

            # ساختار جدید: {"clientType": {...}}
            ct_raw = data.get("clientType")
            if not isinstance(ct_raw, dict):
                # گاهی خود ریشه
                ct_raw = data

            ct = normalize_client_type(ct_raw)
            if any(v > 0 for v in ct.values()):
                return ct
        except Exception:
            continue

    return _empty_ct()


def merge_client_type(bulk: Dict[str, float], one: Dict[str, float]) -> Dict[str, float]:
    """ترکیب دیتای ASPX (حجم دقیق) با API تکی (تعداد)."""
    out = _empty_ct()
    for k in out.keys():
        # اولویت: هرکدام غیرصفر است
        b = bulk.get(k, 0) if bulk else 0
        o = one.get(k, 0) if one else 0
        out[k] = b if b > 0 else o
        # اگر هر دو دارن، bulk (ASPX) دقیق‌تر است برای حجم؛ one برای تعداد
        if k in ("buy_count_i", "sell_count_i"):
            out[k] = o if o > 0 else b
    return out


def fetch_best_limits(ins_code: str) -> Dict[str, float]:
    out = {
        "buy_q_vol": 0.0, "sell_q_vol": 0.0,
        "buy_q_price": 0.0, "sell_q_price": 0.0,
        "buy_q_count": 0.0, "sell_q_count": 0.0,
    }
    if not ins_code:
        return out
    url = f"https://cdn.tsetmc.com/api/BestLimits/{ins_code}"
    try:
        r = SESSION.get(url, timeout=8)
        if r.status_code != 200:
            return out
        data = safe_parse_tsetmc_response(r.text, ins_code)
        rows = []
        if isinstance(data, dict):
            rows = data.get("bestLimits") or data.get("bestLimit") or []
        if not isinstance(rows, list) or not rows:
            return out

        row1 = None
        for row in rows:
            if not isinstance(row, dict):
                continue
            n = int(_f(_get(row, "number", "n", "rid", default=-1)))
            if n == 1:
                row1 = row
                break
            if row1 is None:
                row1 = row
        if not isinstance(row1, dict):
            return out

        out["buy_q_price"] = _f(_get(row1, "pMeDem", "pmd", "buyPrice", default=0))
        out["buy_q_vol"] = _f(_get(row1, "qTitMeDem", "qmd", "buyVol", default=0))
        out["buy_q_count"] = _f(_get(row1, "zOrdMeDem", "buyCount", default=0))
        out["sell_q_price"] = _f(_get(row1, "pMeOf", "pmo", "sellPrice", default=0))
        out["sell_q_vol"] = _f(_get(row1, "qTitMeOf", "qmo", "sellVol", default=0))
        out["sell_q_count"] = _f(_get(row1, "zOrdMeOf", "sellCount", default=0))
        return out
    except Exception:
        return out


def fetch_instrument_info(ins_code: str) -> Dict[str, Any]:
    if not ins_code:
        return {}
    url = f"https://cdn.tsetmc.com/api/Instrument/GetInstrumentInfo/{ins_code}"
    try:
        r = SESSION.get(url, timeout=8)
        if r.status_code != 200:
            return {}
        data = safe_parse_tsetmc_response(r.text, ins_code)
        if isinstance(data, dict):
            return data.get("instrumentInfo") or data
        return {}
    except Exception:
        return {}


def extract_share_stats(info: Dict[str, Any], symbol: str) -> Tuple[float, float, float]:
    if not isinstance(info, dict):
        info = {}
    instrument = info.get("instrument") if isinstance(info.get("instrument"), dict) else {}
    sector = info.get("sector") if isinstance(info.get("sector"), dict) else {}

    total_shares = 0.0
    for src in (info, instrument, sector):
        for k in ("zTitad", "totalShares", "shareCount"):
            v = _f(src.get(k))
            if v > 10_000:
                total_shares = v
                break
        if total_shares > 0:
            break

    ff_pct = 0.0
    ff_shares_direct = 0.0
    for src in (info, instrument, sector):
        for k in ("zTEF", "freeFloat", "FreeFloat", "floatPercent", "freeFloatPercent"):
            v = _f(src.get(k))
            if 0 < v <= 100:
                ff_pct = v
                break
            if v > 1000:
                ff_shares_direct = v
                break
        if ff_pct > 0 or ff_shares_direct > 0:
            break

    if ff_pct <= 0:
        ff_pct = float(FREE_FLOAT_PCT_FALLBACK.get(symbol, 0.0))

    if ff_shares_direct > 0:
        ff_shares = ff_shares_direct
    elif total_shares > 0 and ff_pct > 0:
        ff_shares = total_shares * (ff_pct / 100.0)
    else:
        ff_shares = 0.0

    return ff_shares, ff_pct, total_shares


def _queue_from_marketwatch_item(item: Dict[str, Any]) -> Dict[str, float]:
    out = {"buy_q_vol": 0.0, "sell_q_vol": 0.0, "buy_q_price": 0.0, "sell_q_price": 0.0}
    blds = item.get("blDs") or []
    if blds and isinstance(blds, list) and isinstance(blds[0], dict):
        row = blds[0]
        out["buy_q_price"] = _f(row.get("pmd"))
        out["buy_q_vol"] = _f(row.get("qmd") or row.get("zmd"))
        out["sell_q_price"] = _f(row.get("pmo"))
        out["sell_q_vol"] = _f(row.get("qmo") or row.get("zmo"))
    if out["buy_q_vol"] <= 0:
        out["buy_q_vol"] = _f(item.get("qd1") or item.get("zmd"))
        out["buy_q_price"] = _f(item.get("pd1") or item.get("pmd") or out["buy_q_price"])
    if out["sell_q_vol"] <= 0:
        out["sell_q_vol"] = _f(item.get("qo1") or item.get("zmo"))
        out["sell_q_price"] = _f(item.get("po1") or item.get("pmo") or out["sell_q_price"])
    return out


def _enrich_one(
    item: Dict[str, Any],
    regime_info: Dict[str, Any],
    bulk_client_map: Dict[str, Dict[str, float]],
) -> Dict[str, Any]:
    ins_code = str(item.get("insCode", "")).strip()
    symbol = normalize_fa(item.get("lva", ""))
    industry = str(item.get("cGrValCot") or "UNK").strip() or "UNK"

    # 🎯 دیتای حقیقی/حقوقی از دو منبع ترکیب می‌شود:
    # 1. bulk (ASPX): حجم و ارزش دقیق
    # 2. one (API تکی): تعداد خریدار/فروشنده
    bulk_ct = bulk_client_map.get(ins_code, _empty_ct())
    one_ct = fetch_client_type_one(ins_code)
    ct = merge_client_type(bulk_ct, one_ct)

    info = fetch_instrument_info(ins_code)
    ff_shares, ff_pct, total_shares = extract_share_stats(info, symbol)

    best = fetch_best_limits(ins_code)
    mwq = _queue_from_marketwatch_item(item)
    if best["buy_q_vol"] <= 0 and best["sell_q_vol"] <= 0:
        best["buy_q_vol"] = mwq["buy_q_vol"]
        best["sell_q_vol"] = mwq["sell_q_vol"]
        best["buy_q_price"] = mwq["buy_q_price"]
        best["sell_q_price"] = mwq["sell_q_price"]

    item = dict(item)
    item["_ct"] = ct
    item["_best"] = best
    item["_freeFloatShares"] = ff_shares
    item["_freeFloatPct"] = ff_pct
    item["_totalShares"] = total_shares
    item["_insCode"] = ins_code
    item["_symbol"] = symbol
    item["_industry"] = industry
    item["_industry_return_pct"] = float(regime_info.get("industry_avg", {}).get(industry, 0.0))
    item["_regime"] = regime_info

    if symbol in {"فملی", "اهرم", "طلا", "خودرو", "ذوب", "وبملت"}:
        logger.info(
            f"[{symbol}] BUY: vol={ct['buy_i_vol']:.0f} val={ct['buy_i_val']:.0f} count={ct['buy_count_i']:.0f} | "
            f"SELL: vol={ct['sell_i_vol']:.0f} val={ct['sell_i_val']:.0f} count={ct['sell_count_i']:.0f}"
        )
    return item


def fetch_enriched_target_data(max_workers: int = 6) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    all_items = fetch_raw_market_watch()
    if not all_items:
        return [], {}

    index_info = fetch_index_returns()
    regime_info = compute_market_regime(all_items, index_info)
    logger.info(
        f"رژیم={regime_info.get('regime_label')} | "
        f"کل={regime_info.get('market_return_pct')}% | "
        f"هم‌وزن={regime_info.get('equal_weight_return_pct')}% | "
        f"عرض={regime_info.get('breadth_pos_pct')}%"
    )

    # یکجا بگیر: حجم و ارزش
    bulk_client_map = fetch_client_type_all()
    logger.info(f"ClientType bulk map = {len(bulk_client_map)} نماد")

    targets = []
    for item in all_items:
        if normalize_fa(item.get("lva", "")) in TARGET_SYMBOLS:
            targets.append(item)
    logger.info(f"هدف: {len(targets)} / {len(TARGET_SYMBOLS)}")

    enriched: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = [ex.submit(_enrich_one, it, regime_info, bulk_client_map) for it in targets]
        for fut in as_completed(futs):
            try:
                enriched.append(fut.result())
            except Exception as e:
                logger.warning(f"enrich error: {e}")
    return enriched, regime_info