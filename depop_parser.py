# depop_parser.py
import logging
import math
from typing import List, Dict, Any, Optional
from curl_cffi.requests import AsyncSession
from bs4 import BeautifulSoup
from config import USD_TO_RUB_RATE, ADDITIONAL_RUB, STOP_WORDS

def convert_to_rub(usd_price: float) -> int:
    rub_exact = (usd_price * USD_TO_RUB_RATE) + ADDITIONAL_RUB
    return math.ceil(rub_exact)

async def fetch_depop_new_listings(session: AsyncSession, query: str) -> List[Dict[str, Any]]:
    """Парсит веб-страницу поиска Depop напрямую через HTML-карточки с обходом блокировки."""
    formatted_query = query.replace(' ', '%20')
    url = f"https://www.depop.com/search/?q={formatted_query}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://www.depop.com/"
    }

    try:
        response = await session.get(
            url, 
            headers=headers, 
            impersonate="chrome120", 
            timeout=25,
            follow_redirects=True
        )
        
        if response.status_code != 200:
            logging.warning(f"[{query}] Веб-версия вернула статус: {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        products = []
        
        # Ищем карточки товаров в HTML-структуре сайта
        cards = soup.select('a[href*="/products/"]')
        
        seen_ids = set()
        for card in cards[:15]:
            href = card.get('href', '')
            if '/products/' not in href:
                continue
            
            slug = href.split('/products/')[-1].strip('/')
            if not slug or slug in seen_ids:
                continue
            seen_ids.add(slug)

            # Вытаскиваем картинку и текст для цены
            photo_url = None
            img_tag = card.find('img')
            if img_tag:
                photo_url = img_tag.get('src')

            card_text = card.get_text()
            
            # Пробуем найти цену в долларах через регулярное выражение
            import re
            price_usd = 25.0  # Дефолт на случай, если верстка изменилась
            price_match = re.search(r'\$(\d+(?:\.\d+)?)', card_text)
            if price_match:
                price_usd = float(price_match.group(1))

            price_rub = convert_to_rub(price_usd)

            products.append({
                "id": slug,
                "title": slug.replace("-", " ").title(),
                "brand": "Depop",
                "price_usd": price_usd,
                "price_rub": price_rub,
                "size": "Уточняйте",
                "category": "разное",
                "query": query,
                "url": f"https://www.depop.com/products/{slug}/",
                "photo_url": photo_url,
                "description": card_text[:150]
            })

        return products
            
    except Exception as e:
        logging.error(f"[{query}] Ошибка HTML-парсера: {e}")
        return []

def filter_and_format_item(item: Dict[str, Any], target_config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    description = item.get("description", "").lower()
    if any(sw in description for sw in STOP_WORDS):
        return None

    price_usd = item.get("price_usd", 0)
    max_price = target_config.get("max_price_usd")
    
    if max_price and price_usd > max_price:
        return None
    if price_usd <= 0:
        return None

    return item