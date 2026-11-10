# main.py
import asyncio
import logging
from aiogram import Bot
from curl_cffi.requests import AsyncSession
from config import TELEGRAM_TOKEN, CHAT_ID, SEARCH_TARGETS, CHECK_INTERVAL_SECONDS
from depop_parser import fetch_depop_new_listings, filter_and_format_item

# Настройка логирования в консоль
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# Инициализация Telegram-бота
bot = Bot(token=TELEGRAM_TOKEN)

# Множество для хранения уже отправленных ID товаров, чтобы не слать дубликаты
sent_item_ids = set()

async def send_telegram_alert(item: dict):
    """Формирует красивое сообщение и отправляет карточку товара в Telegram."""
    caption = (
        f"🔥 **Новый лот на Depop!**\n\n"
        f"📌 **Название:** {item['title']}\n"
        f"🏷 **Бренд:** {item['brand']}\n"
        f"📏 **Размер:** {item['size']}\n"
        f"💵 **Цена:** ${item['price_usd']:.2f} (~{item['price_rub']} ₽)\n\n"
        f"🔍 *Поиск:* `{item['query']}`\n\n"
        f"[👉 Ссылка на товар]({item['url']})"
    )
    
    photo_url = item.get("photo_url")
    try:
        if photo_url:
            await bot.send_photo(
                chat_id=CHAT_ID, 
                photo=photo_url, 
                caption=caption, 
                parse_mode="Markdown"
            )
        else:
            await bot.send_message(
                chat_id=CHAT_ID, 
                text=caption, 
                parse_mode="Markdown", 
                disable_web_page_preview=False
            )
        logging.info(f"✅ Отправлен в Telegram: {item['title']} ({item['price_rub']} ₽)")
    except Exception as e:
        logging.error(f"❌ Ошибка отправки в Telegram: {e}")

async def process_target(session: AsyncSession, target: dict):
    """Обрабатывает один поисковый запрос из конфига."""
    query = target["query"]
    # Передаем сессию curl_cffi для запроса с отпечатком браузера
    raw_items = await fetch_depop_new_listings(session, query)
    
    if not raw_items:
        return

    # Обрабатываем с конца (от старых к новым), чтобы новые публиковались первыми
    for raw_item in reversed(raw_items):
        item_id = str(raw_item.get("id"))
        if not item_id or item_id in sent_item_ids:
            continue

        # Фильтруем товар по цене, размеру и стоп-словам
        formatted_item = filter_and_format_item(raw_item, target)
        
        if formatted_item:
            sent_item_ids.add(item_id)
            await send_telegram_alert(formatted_item)
            await asyncio.sleep(1) # Небольшая пауза между отправкой сообщений

        # Ограничиваем размер кэша отправленных ID, чтобы не забивать память
        if len(sent_item_ids) > 1000:
            sent_item_ids.clear()

async def monitor_loop():
    """Бесконечный цикл снайпера."""
    logging.info(f"🚀 Снайпер Depop запущен! Проверка каждые {CHECK_INTERVAL_SECONDS // 60} минут.")
    
    # Создаем единую сессию curl_cffi для переиспользования TLS-соединений
    async with AsyncSession() as session:
        while True:
            for target in SEARCH_TARGETS:
                await process_target(session, target)
                await asyncio.sleep(2)  # Пауза между разными поисковыми запросами
            
            logging.info(f"💤 Проверка окончена. Засыпаем на {CHECK_INTERVAL_SECONDS} секунд...")
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)

def main():
    """Точка входа."""
    try:
        asyncio.run(monitor_loop())
    except (KeyboardInterrupt, SystemExit):
        logging.info("🛑 Снайпер остановлен пользователем.")

if __name__ == "__main__":
    main()