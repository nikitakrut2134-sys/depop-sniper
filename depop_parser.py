# depop_parser.py
import logging
import math
from typing import List, Dict, Any, Optional
from curl_cffi.requests import AsyncSession
from config import USD_TO_RUB_RATE, ADDITIONAL_RUB, STOP_WORDS

def convert_to_rub(usd_price: float) -> int:
    """Пересчитывает долларовую цену в рубли по формуле: (Цена * 88) + 200 с округлением вверх."""
    rub_exact = (usd_price * USD_TO_RUB_RATE) + ADDITIONAL_RUB
    return math.ceil(rub_exact)

async def fetch_depop_new_listings(session: AsyncSession, query: str) -> List[Dict[str, Any]]:
    """Парсит товары через официальный API Depop с полным обходом Cloudflare через отпечаток Chrome."""
    url = "https://webapi.depop.com/api/v1/search/products/"
    
    params = {
        "q": query,
        "sort": "newest",
        "limit": 20
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://www.depop.com",
        "Referer": f"https://www.depop.com/search/?q={query.replace(' ', '%20')}"
    }

    try:
        # impersonate="chrome124" заставляет сервер думать, что запрос отправлен из чистого браузера Chrome
        response = await session.get(
            url, 
            params=params, 
            headers=headers, 
            impersonate="chrome124", 
            timeout=20
        )
        
        if response.status_code == 200:
            data = response.json()
            return data.get("products", [])
        else:
            logging.warning(f"[{query}] Depop API вернул статус: {response.status_code}")
            return []
            
    except Exception as e:
        logging.error(f"[{query}] Ошибка запроса к Depop API: {e}")
        return []

def filter_and_format_item(item: Dict[str, Any], target_config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Проверяет лот на соответствие фильтрам по цене, размеру и стоп-словам."""
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
        size_matched = any(ts.lower() in size_str.lower() for ts in target_sizes)
        if not size_matched:
            return None

    slug = item.get("slug")
    if not slug:
        return None
    
    item_url = f"https://www.depop.com/products/{slug}/"
    
    pictures = item.get("pictures", [])
    photo_url = pictures[0][0].get("url") if pictures and pictures[0] else None

    price_rub = convert_to_rub(price_usd)

    return {
        "id": item.get("id"),
        "title": slug.replace("-", " ").title(),
        "brand": item.get("brandName", "Без бренда"),
        "price_usd": price_usd,
        "price_rub": price_rub,
        "size": size_str,
        "category": target_config.get("category", "разное"),
        "query": target_config.get("query"),
        "url": item_url,
        "photo_url": photo_url,
        "description": item.get("description", "Без описания.")[:150]
    }