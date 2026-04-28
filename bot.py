import os
import json
import random
import logging
import re
import asyncio
import sys
import subprocess
from datetime import datetime, timedelta

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatPermissions
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    CommandHandler
)
from telegram.request import HTTPXRequest

# ====================== DATABASE ======================
from database import db

try:
    from playwright.async_api import async_playwright
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "playwright"])
    from playwright.async_api import async_playwright

try:
    subprocess.run(["playwright", "install", "chromium"], check=False)
except Exception:
    pass

TOKEN = "8641381095:AAE1uHoBHObu34tQsTe3hQ1zL4wEPSZgvzU"
OWNER_ID = 5679520675
VERSION = "2.2 (PostgreSQL + Glaz)"

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    stream=sys.stdout
)

# Временные словари (пока оставляем в памяти)
warns = {}
work_timers = {}
duel_sessions = {}


def parse_admin_request(text):
    parts = text.split("\n")
    cmd = parts[0].lower().strip()
    reason = parts[1] if len(parts) > 1 else "Не указана"

    if "навсегда" in cmd:
        return 31536000 * 99, "навсегда", reason

    match = re.search(r"(\d+)\s*([мчд])", cmd)
    if not match:
        return None, None, reason

    val, unit = int(match.group(1)), match.group(2)
    mult = {"м": 60, "ч": 3600, "д": 86400}.get(unit, 3600)
    label = {"м": "мин.", "ч": "час(ов)", "д": "дн."}.get(unit, "")
    return val * mult, f"{val} {label}", reason


DEAD_MARKERS = [
    "room not found", "комната не найдена", "this room does not exist",
    "invalid room", "комнаты не существует", "комнаты, в которую ты пытаешься войти, больше нет",
    "в которую ты пытаешься войти, больше нет", "больше нет",
    "room no longer exists", "the room you are trying to enter no longer exists", "does not exist"
]

EYE_NICK = "KryloxaEye"


async def get_body_text(page):
    try:
        return (await page.locator("body").inner_text(timeout=5000)).lower()
    except Exception:
        return ""


def is_dead_text(text):
    if not text:
        return False
    low = str(text).lower()
    return any(marker in low for marker in DEAD_MARKERS)


def find_players_in_object(obj):
    player_keys = {"players", "users", "members", "participants", "online", "peoples", "people"}
    name_keys = {"name", "nick", "nickname", "username", "player", "user", "login"}

    def list_looks_like_players(items):
        if not isinstance(items, list):
            return False
        if len(items) == 0:
            return True
        good = 0
        checked = 0
        for item in items[:30]:
            checked += 1
            if isinstance(item, dict):
                keys = {str(k).lower() for k in item.keys()}
                if keys & name_keys or {"id", "avatar", "photo", "score", "status"} & keys:
                    good += 1
            elif isinstance(item, str) and 0 < len(item.strip()) <= 32:
                good += 1
        return checked > 0 and good >= max(1, checked // 2)

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                lk = str(k).lower()
                if lk in player_keys and isinstance(v, list) and list_looks_like_players(v):
                    return len(v)
            for v in x.values():
                found = walk(v)
                if found is not None:
                    return found
        elif isinstance(x, list):
            if list_looks_like_players(x) and 1 <= len(x) <= 50:
                return len(x)
            for item in x:
                found = walk(item)
                if found is not None:
                    return found
        return None
    return walk(obj)


def extract_player_count_from_ws(messages):
    best = None
    combined = "\n".join(messages).lower()
    bot_seen = EYE_NICK.lower() in combined

    for raw in messages:
        if not raw:
            continue
        raw = str(raw).strip()
        candidates = [raw]
        json_part = re.search(r"(\{.*\}|\[.*\])", raw, re.DOTALL)
        if json_part:
            candidates.append(json_part.group(1))

        for candidate in candidates:
            try:
                data = json.loads(candidate)
            except Exception:
                continue
            count = find_players_in_object(data)
            if count is not None and 0 <= count <= 50:
                best = max(best or 0, count)

    if best is None:
        return None, bot_seen
    if bot_seen:
        best = max(0, best - 1)
    return best, bot_seen


async def count_players_dom_fallback(page):
    try:
        await asyncio.sleep(3)
        containers = ["[class*='players']", "[class*='Players']", "[class*='participants']", "[class*='Participants']", "[class*='room']"]
        for container in containers:
            block = page.locator(container).first
            if await block.count() > 0:
                items = block.locator("div, li, span")
                count = await items.count()
                names = set()
                for i in range(min(count, 60)):
                    try:
                        el = items.nth(i)
                        if await el.is_visible(timeout=200):
                            t = (await el.inner_text(timeout=300)).strip()
                            if 1 <= len(t) <= 32 and "\n" not in t:
                                bad_words = ["join", "войти", "игрок", "комната", "room", "start", "начать", "ok"]
                                if not any(w in t.lower() for w in bad_words):
                                    names.add(t)
                    except Exception:
                        pass
                if names:
                    count = len(names)
                    if EYE_NICK in names:
                        count -= 1
                    return max(0, count)
        return None
    except Exception:
        return None


async def check_dead_room(page):
    try:
        await asyncio.sleep(1)
        body = await get_body_text(page)
        if is_dead_text(body):
            return True
        for marker in DEAD_MARKERS:
            try:
                if await page.locator(f"text=/{re.escape(marker)}/i").first.is_visible(timeout=600):
                    return True
            except Exception:
                pass
        return False
    except Exception:
        return False


async def debug_page_state(page, prefix="[GLAZ]"):
    try:
        logging.info(f"{prefix} FINAL URL: {page.url}")
        title = await page.title()
        logging.info(f"{prefix} TITLE: {title}")
        body = await page.locator("body").inner_text(timeout=5000)
        logging.info(f"{prefix} BODY TEXT FIRST 1200:\n{body[:1200]}")
        await page.screenshot(path="glaz_debug.png", full_page=True)
        logging.info(f"{prefix} SCREENSHOT SAVED: glaz_debug.png")
    except Exception as e:
        logging.info(f"{prefix} ERROR: {e}")


async def choose_character(page):
    try:
        logging.info("[GLAZ] CHARACTER SELECT START")
        selectors = ["[class*='character']","[class*='Character']","[class*='avatar']","[class*='Avatar']","[class*='skin']","[class*='Skin']","img","canvas","svg"]
        for selector in selectors:
            try:
                items = page.locator(selector)
                total = await items.count()
                for i in range(min(total, 80)):
                    try:
                        el = items.nth(i)
                        if not await el.is_visible(timeout=250): continue
                        box = await el.bounding_box()
                        if not box: continue
                        x = box.get("x", 0)
                        y = box.get("y", 0)
                        w = box.get("width", 0)
                        h = box.get("height", 0)
                        if 25 <= w <= 300 and 25 <= h <= 300 and y < 650:
                            await el.click(force=True)
                            logging.info(f"[GLAZ] CHARACTER CLICKED DOM: {selector} #{i}")
                            await asyncio.sleep(0.7)
                            return True
                    except Exception:
                        pass
            except Exception:
                pass

        points = [(640, 250),(580, 250),(700, 250),(640, 300),(580, 300),(700, 300),(640, 350),(580, 350),(700, 350)]
        for x, y in points:
            try:
                await page.mouse.click(x, y)
                logging.info(f"[GLAZ] CHARACTER CLICKED COORD: {x},{y}")
                await asyncio.sleep(0.35)
            except Exception:
                pass
        return True
    except Exception as e:
        logging.info(f"[GLAZ] CHARACTER ERROR: {e}")
        return False


async def click_join_button(page):
    try:
        join_btn = page.locator("button:has-text('ВОЙТИ'), button:has-text('JOIN'), strong:has-text('ВОЙТИ'), strong:has-text('JOIN'), text=/join/i, text=/войти/i").first
        if await join_btn.is_visible(timeout=5000):
            await join_btn.click(force=True)
            logging.info("[GLAZ] JOIN CLICKED BY LOCATOR")
            return True
    except Exception:
        pass

    try:
        clicked = await page.evaluate("""
            () => {
                const wanted = ['ВОЙТИ', 'JOIN'];
                const all = Array.from(document.querySelectorAll('button, strong, div, span, a'));
                for (const el of all) {
                    const txt = (el.innerText || el.textContent || '').trim().toUpperCase();
                    if (wanted.some(w => txt.includes(w))) {
                        el.click();
                        return true;
                    }
                }
                return false;
            }
        """)
        if clicked:
            logging.info("[GLAZ] JOIN CLICKED BY JS")
            return True
    except Exception:
        pass

    try:
        await page.keyboard.press("Enter")
        logging.info("[GLAZ] JOIN BY ENTER")
        return True
    except Exception:
        return False


async def check_gartic_link(url, count_mode=False):
    ws_messages = []
    async with async_playwright() as p:
        browser = None
        try:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
            )
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                locale="ru-RU"
            )
            await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            page = await context.new_page()

            def on_ws(ws):
                def save_received(payload):
                    try:
                        if isinstance(payload, bytes):
                            payload = payload.decode("utf-8", errors="ignore")
                        ws_messages.append(str(payload)[:20000])
                    except:
                        pass
                ws.on("framereceived", save_received)

            page.on("websocket", on_ws)
            page.on("console", lambda msg: logging.info(f"[BROWSER CONSOLE] {msg.text}"))

            logging.info(f"Глаз проверяет ссылку: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(7)
            await debug_page_state(page, "[GLAZ BEFORE JOIN]")

            if await check_dead_room(page):
                return "❌ Глаз: Ссылка мертва (Комната закрыта)."

            final_url = page.url.lower().rstrip("/")
            if final_url in ["https://garticphone.com", "https://garticphone.com/ru", "http://garticphone.com", "http://garticphone.com/ru"]:
                return "❌ Глаз: Это не комната (редирект на главную)."

            if not count_mode:
                return "⚠️ Глаз: Ссылка похожа на комнату. Используй статус+"

            # === Вход в комнату ===
            input_box = page.locator("input[type='text'], input[placeholder], input").first
            await input_box.click(force=True)
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await input_box.fill(EYE_NICK)

            await page.evaluate("""(nick) => {
                const inputs = document.querySelectorAll('input');
                const inp = inputs[0];
                if (inp) {
                    inp.value = nick;
                    inp.dispatchEvent(new Event('input', {bubbles: true}));
                    inp.dispatchEvent(new Event('change', {bubbles: true}));
                }
            }""", EYE_NICK)

            await asyncio.sleep(1)
            await choose_character(page)
            await asyncio.sleep(1)
            await click_join_button(page)
            await asyncio.sleep(4)

            for _ in range(15):
                await asyncio.sleep(1)
                if await check_dead_room(page):
                    return "❌ Глаз: Ссылка мертва (Комната закрыта)."
                ws_count, bot_seen = extract_player_count_from_ws(ws_messages)
                if ws_count is not None:
                    return f"✅ Глаз v3: Ссылка жива!\n👥 Игроков без меня: {ws_count}\n📡 Метод: WebSocket"

            dom_count = await count_players_dom_fallback(page)
            if dom_count is not None:
                return f"✅ Глаз v3: Ссылка жива!\n👥 Игроков без меня: {dom_count}\n📋 Метод: DOM"

            return "✅ Глаз v3: Ссылка жива (не удалось точно посчитать игроков)"

        except Exception as e:
            logging.error(f"Ошибка Глаза: {e}")
            return "⚠️ Глаз: Ошибка проверки"
        finally:
            if browser:
                await browser.close()


# ====================== ОБРАБОТЧИКИ ======================
async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    raw = update.message.text
    text = raw.lower().strip()
    user = update.effective_user
    reply = update.message.reply_to_message
    cid = update.effective_chat.id

    await db.ensure_user(user.id)   # Важно!

    if text in ["статус", "статус+"]:
        if reply and reply.text:
            match = re.search(r"(https?://garticphone\.com/[^\s]+)", reply.text)
            if match:
                url = match.group(1)
                if text == "статус":
                    msg = await update.message.reply_text("👁 Глаз проверяет...")
                    result = await check_gartic_link(url, count_mode=False)
                else:
                    msg = await update.message.reply_text("👁 Глаз v3 входит...")
                    result = await check_gartic_link(url, count_mode=True)

                try:
                    await msg.edit_text(result)
                except:
                    await update.message.reply_text(result)
                return

    if text in ["баланс", "б"]:
        balance = "∞ (Owner)" if user.id == OWNER_ID else f"{await db.get_balance(user.id)} KLC"
        await update.message.reply_text(f"💰 Ваш баланс: {balance}")
        return

    if text == "обо мне" or (text == "инфа" and reply):
        target = reply.from_user if (text == "инфа" and reply) else user
        await db.ensure_user(target.id)
        balance = "∞ (Owner)" if target.id == OWNER_ID else f"{await db.get_balance(target.id)} KLC"
        rank_str = await get_rank_str(target.id)

        await update.message.reply_text(
            f"👤 Профиль {target.first_name}:\n"
            f"🆔 ID: `{target.id}`\n"
            f"⭐️ Ранг: {rank_str}\n"
            f"💰 Баланс: {balance}\n"
            f"⚠️ Варны: {warns.get(target.id, 0)}/3\n"
            f"Версия: {VERSION}",
            parse_mode="Markdown"
        )
        return

    if text.startswith("промо "):
        code = text.split(" ", 1)[1].strip()
        if await db.use_promo(code, user.id):
            await update.message.reply_text(f"✅ Промокод `{code}` активирован!")
        else:
            await update.message.reply_text("❌ Промокод недействителен или уже использован.")
        return

    if text == "работа":
        if update.effective_chat.type != "private":
            await update.message.reply_text("Работа только в ЛС!")
            return
        now = datetime.now()
        if user.id in work_timers and (now - work_timers[user.id]).seconds < 30:
            left = 30 - (now - work_timers[user.id]).seconds
            await update.message.reply_text(f"Жди {left} сек.")
            return
        gain = random.randint(50, 150)
        await db.update_balance(user.id, gain)
        work_timers[user.id] = now
        await update.message.reply_text(f"⛏ Заработано {gain} KLC!")
        return

    # Дуэль, админка и остальное пока оставил как было (будем дорабатывать постепенно)
    # ... (твой оригинальный код рулетки, on_call и т.д. можно добавить позже)

    if text == "рулетка" and reply:
        await update.message.reply_text("Дуэль пока на доработке")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🤖 Krilox Bot v{VERSION} запущен!\nБаза данных подключена")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Команды:\n/status\n/баланс\n/промо\n/работа\n/magaz")


async def magaz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("Снять мут (1000)", callback_data="shop_unmute")],
        [InlineKeyboardButton("Снять варн (500)", callback_data="shop_unwarn")]
    ]
    await update.message.reply_text("🛒 Магазин", reply_markup=InlineKeyboardMarkup(kb))


# ====================== ЗАПУСК ======================
if __name__ == "__main__":
    print("=" * 55)
    print(f"🤖 Kryloxa Bot v{VERSION} запускается...")
    print("=" * 55)

    async def main():
        await db.connect()

        request_config = HTTPXRequest(connect_timeout=30, read_timeout=30)

        app = ApplicationBuilder().token(TOKEN).request(request_config).build()

        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", help_cmd))
        app.add_handler(CommandHandler("magaz", magaz))

        app.add_handler(CallbackQueryHandler(on_call))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

        print("[OK] Бот успешно запущен с PostgreSQL")

        try:
            await app.run_polling(drop_pending_updates=True)
        finally:
            await db.close()

    asyncio.run(main())
