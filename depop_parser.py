# depop_parser.py
import logging
import math
from typing import List, Dict, Any, Optional
from curl_cffi.requests import AsyncSession
from config import USD_TO_RUB_RATE, ADDITIONAL_RUB, STOP_WORDS

def convert_to_rub(usd_price: float) -> int:
    """Пересчитывает долларовую цену в рубли."""
    rub_exact = (usd_price * USD_TO_RUB_RATE) + ADDITIONAL_RUB
    return math.ceil(rub_exact)

async def fetch_depop_new_listings(session: AsyncSession, query: str) -> List[Dict[str, Any]]:
    """Парсит товары черезэмуляцию поискового бота Googlebot для обхода блокировок дата-центров."""
    url = "https://webapi.depop.com/api/v1/search/products/"
    
    params = {
        "q": query,
        "sort": "newest",
        "limit": 20
    }

    # Маскируемся под поискового робота Googlebot, чтобы Cloudflare пропускал запросы без проверки
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "X-Forwarded-For": "8.8.8.8",
        "Referer": "https://www.google.com/"
    }

    try:
        response = await session.get(
            url, 
            params=params, 
            headers=headers, 
            impersonate="chrome120", 
            timeout=25
        )
        
        if response.status_code == 200:
            data = response.json()
            return data.get("products", [])
        else:
            logging.warning(f"[{query}] Depop API вернул статус: {response.status_code}")
            return []
            
    except Exception as e:
        logging.error(f"[{query}] Ошибка запроса: {e}")
        return []

def filter_and_format_item(item: Dict[str, Any], target_config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Фильтрует и форматирует лот."""
    description = item.get("description", "").lower()
    if any(sw in description for sw in STOP_WORDS):
        return None

    price_info = item.get("price", {})
    price_usd = float(price_info.get("priceAmount", 0))
    max_price = target_config.get("max_price_usd")
    
    if max_price and price_usd > max_price:
        return None
    if price_usd <= 0:
        return None

    raw_sizes = item.get("sizes", [])
    size_str = str(raw_sizes[0]).upper() if raw_sizes else "Уточняйте"
    target_sizes = target_config.get("sizes", [])
    
    if target_sizes:
        if not any(ts.lower() in size_str.lower() for ts in target_sizes):
            return None

    slug = item.get("slug")
    if not slug:
        return None
    
    pictures = item.get("pictures", [])
    photo_url = pictures[0][0].get("url") if pictures and pictures[0] else None

    return {
        "id": item.get("id"),
        "title": slug.replace("-", " ").title(),
        "brand": item.get("brandName", "Без бренда"),
        "price_usd": price_usd,
        "price_rub": convert_to_rub(price_usd),
        "size": size_str,
        "category": target_config.get("category", "разное"),
        "query": target_config.get("query"),
        "url": f"https://www.depop.com/products/{slug}/",
        "photo_url": photo_url,
        "description": item.get("description", "Без описания.")[:150]
    }