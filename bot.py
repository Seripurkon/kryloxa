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

# ====================== ПОДКЛЮЧЕНИЕ БД ======================
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
VERSION = "2.2 (PostgreSQL + Глаз + Дуэли)"

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    stream=sys.stdout
)

# Временные данные для дуэлей и таймеров (оставляем в памяти)
duel_sessions = {}
work_timers = {}


async def get_rank_str(uid):
    """Получение ранга из БД"""
    if uid == OWNER_ID:
        return "4 (Owner)"
    rank = await db.get_rank(uid)
    return "-1 Tester" if rank == -1 else str(rank)


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
    "room not found",
    "комната не найдена",
    "this room does not exist",
    "invalid room",
    "комнаты не существует",
    "комнаты, в которую ты пытаешься войти, больше нет",
    "в которую ты пытаешься войти, больше нет",
    "больше нет",
    "room no longer exists",
    "the room you are trying to enter no longer exists",
    "does not exist"
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

        containers = [
            "[class*='players']",
            "[class*='Players']",
            "[class*='participants']",
            "[class*='Participants']",
            "[class*='room']",
        ]

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
    except Exception:
        pass

    try:
        title = await page.title()
        logging.info(f"{prefix} TITLE: {title}")
    except Exception as e:
        logging.info(f"{prefix} TITLE ERROR: {e}")

    try:
        body = await page.locator("body").inner_text(timeout=5000)
        logging.info(f"{prefix} BODY TEXT FIRST 1200:\n{body[:1200]}")
    except Exception as e:
        logging.info(f"{prefix} BODY ERROR: {e}")

    try:
        await page.screenshot(path="glaz_debug.png", full_page=True)
        logging.info(f"{prefix} SCREENSHOT SAVED: glaz_debug.png")
    except Exception as e:
        logging.info(f"{prefix} SCREENSHOT ERROR: {e}")


async def choose_character(page):
    try:
        logging.info("[GLAZ] CHARACTER SELECT START")

        selectors = [
            "[class*='character']",
            "[class*='Character']",
            "[class*='avatar']",
            "[class*='Avatar']",
            "[class*='skin']",
            "[class*='Skin']",
            "img",
            "canvas",
            "svg"
        ]

        for selector in selectors:
            try:
                items = page.locator(selector)
                total = await items.count()

                for i in range(min(total, 80)):
                    try:
                        el = items.nth(i)

                        if not await el.is_visible(timeout=250):
                            continue

                        box = await el.bounding_box()
                        if not box:
                            continue

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

        points = [
            (640, 250), (580, 250), (700, 250),
            (640, 300), (580, 300), (700, 300),
            (640, 350), (580, 350), (700, 350),
            (520, 300), (760, 300),
            (500, 360), (780, 360),
        ]

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
        join_btn = page.locator(
            "button:has-text('ВОЙТИ'), "
            "button:has-text('JOIN'), "
            "strong:has-text('ВОЙТИ'), "
            "strong:has-text('JOIN'), "
            "text=/join/i, "
            "text=/войти/i"
        ).first

        if await join_btn.is_visible(timeout=5000):
            await join_btn.click(force=True)
            logging.info("[GLAZ] JOIN CLICKED BY LOCATOR")
            return True
    except Exception as e:
        logging.info(f"[GLAZ] JOIN LOCATOR FAILED: {e}")

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
    except Exception as e:
        logging.info(f"[GLAZ] JOIN JS FAILED: {e}")

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
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled"
                ]
            )

            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/123.0.0.0 Safari/537.36"
                ),
                locale="ru-RU"
            )

            await context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            page = await context.new_page()

            def on_ws(ws):
                def save_received(payload):
                    try:
                        if isinstance(payload, bytes):
                            payload = payload.decode("utf-8", errors="ignore")
                        payload = str(payload)
                        if payload:
                            ws_messages.append(payload[:20000])
                            logging.info(f"[WS RECEIVED] {payload[:600]}")
                    except Exception as e:
                        logging.info(f"[WS RECEIVED ERROR] {e}")

                ws.on("framereceived", save_received)

            page.on("websocket", on_ws)
            page.on("console", lambda msg: logging.info(f"[BROWSER CONSOLE] {msg.text}"))

            logging.info(f"Глаз проверяет ссылку: {url}")

            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(7)
            await debug_page_state(page, "[GLAZ BEFORE JOIN]")

            final_url = page.url.lower().rstrip("/")

            if await check_dead_room(page):
                return "❌ Глаз: Ссылка мертва (Комната закрыта)."

            if final_url in [
                "https://garticphone.com",
                "https://garticphone.com/ru",
                "http://garticphone.com",
                "http://garticphone.com/ru"
            ]:
                return "❌ Глаз: Это не комната (редирект на главную)."

            if not count_mode:
                return "⚠️ Глаз: Ссылка похожа на комнату.\nДля точной проверки используй `статус+`."

            input_box = page.locator("input[type='text'], input[placeholder], input").first

            try:
                if not await input_box.is_visible(timeout=9000):
                    await debug_page_state(page, "[GLAZ NO INPUT]")
                    if await check_dead_room(page):
                        return "❌ Глаз: Ссылка мертва (Комната закрыта)."
                    return "⚠️ Глаз: Не нашёл поле входа."
            except Exception:
                await debug_page_state(page, "[GLAZ INPUT ERROR]")
                if await check_dead_room(page):
                    return "❌ Глаз: Ссылка мертва (Комната закрыта)."
                return "⚠️ Глаз: Не нашёл поле входа."

            await input_box.click(force=True)
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await input_box.fill(EYE_NICK)

            try:
                await page.evaluate(
                    """(nick) => {
                        const inputs = Array.from(document.querySelectorAll('input'));
                        const visible = inputs.filter(i => {
                            const r = i.getBoundingClientRect();
                            return r.width > 0 && r.height > 0;
                        });
                        const inp = visible[0] || inputs[0];
                        if (inp) {
                            inp.focus();
                            inp.value = nick;
                            inp.dispatchEvent(new Event('input', { bubbles: true }));
                            inp.dispatchEvent(new Event('change', { bubbles: true }));
                            inp.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));
                        }
                    }""",
                    EYE_NICK
                )
                logging.info("[GLAZ] NICK SET BY FILL + JS EVENTS")
            except Exception as e:
                logging.info(f"[GLAZ] NICK JS SET FAILED: {e}")

            await asyncio.sleep(1)

            await choose_character(page)
            await asyncio.sleep(1)

            await debug_page_state(page, "[GLAZ BEFORE JOIN CLICK]")

            await click_join_button(page)

            await asyncio.sleep(4)
            await debug_page_state(page, "[GLAZ AFTER JOIN CLICK]")

            for _ in range(15):
                await asyncio.sleep(1)

                if await check_dead_room(page):
                    return "❌ Глаз: Ссылка мертва (Комната закрыта)."

                ws_count, bot_seen = extract_player_count_from_ws(ws_messages)
                if ws_count is not None:
                    return f"✅ Глаз v3: Ссылка жива!\n👥 Игроков без меня: {ws_count}\n📡 Метод: WebSocket"

            await debug_page_state(page, "[GLAZ AFTER WAIT]")

            if await check_dead_room(page):
                return "❌ Глаз: Ссылка мертва (Комната закрыта)."

            dom_count = await count_players_dom_fallback(page)
            if dom_count is not None:
                return f"✅ Глаз v3: Ссылка жива!\n👥 Игроков без меня: {dom_count}\n📋 Метод: DOM fallback"

            body_after = await get_body_text(page)
            if EYE_NICK.lower() in body_after.lower() or ws_messages:
                return f"✅ Глаз v3: Ссылка жива!\n👥 Игроков: не смог распарсить.\n📡 WS сообщений: {len(ws_messages)}"

            return "⚠️ Глаз: Не смог подтвердить вход."

        except Exception as e:
            logging.error(f"Ошибка Глаза: {e}")
            return "⚠️ Глаз: Ошибка проверки или тайм-аут сайта."

        finally:
            if browser:
                await browser.close()


async def handle_duel(query, context, gid, striker_id):
    game = duel_sessions.get(gid)

    if not game or striker_id != game["turn"]:
        return

    if not game.get("chamber"):
        if gid in duel_sessions:
            del duel_sessions[gid]
        await query.message.edit_text("🫙 В барабане кончились патроны. Ничья!")
        return

    bullet = game["chamber"].pop(random.randint(0, len(game["chamber"]) - 1))

    if bullet == "🔥":
        game[f"hp{1 if striker_id == game['p1'] else 2}"] -= 1
        effect = "💥 БАБАХ!"
    else:
        effect = "💨 ОСЕЧКА!"

    if game["hp1"] <= 0 or game["hp2"] <= 0 or not game["chamber"]:
        winner_n = game["p2_n"] if game["hp1"] <= 0 else game["p1_n"]
        loser_n = game["p1_n"] if game["hp1"] <= 0 else game["p2_n"]
        loser_id = game["p1"] if game["hp1"] <= 0 else game["p2"]
        winner_id = game["p2"] if game["hp1"] <= 0 else game["p1"]
        chat_id = query.message.chat_id

        res = f"📢 {effect}\n\n🏆 Победил {winner_n}!\n"

        try:
            if game["bet"] == "warn":
                new_warns = await db.update_warns(loser_id, 1)
                res += f"⚠️ {loser_n} получает ВАРН! ({new_warns}/3)"

                if new_warns >= 3:
                    await context.bot.ban_chat_member(chat_id, loser_id)
                    res += f"\n⛔ {loser_n} забанен (3/3 варнов)!"
                    await db.reset_warns(loser_id)

            elif game["bet"] == "ban":
                await context.bot.ban_chat_member(
                    chat_id,
                    loser_id,
                    until_date=datetime.now() + timedelta(days=1)
                )
                res += f"🚫 {loser_n} улетает в бан на 1 день!"

            elif game["bet"] == "mute":
                await context.bot.restrict_chat_member(
                    chat_id,
                    loser_id,
                    ChatPermissions(can_send_messages=False),
                    until_date=datetime.now() + timedelta(days=1)
                )
                res += f"😶 {loser_n} в муте на 1 день!"

            else:
                await db.update_balance(loser_id, -100)
                await db.update_balance(winner_id, 100)
                res += f"💰 {loser_n} теряет 100 KLC!"

        except Exception as e:
            logging.error(f"Дуэль ошибка: {e}")
            res += f"\n🛡 {loser_n} защищён высшими силами!"

        await query.message.edit_text(res)

        if gid in duel_sessions:
            del duel_sessions[gid]

        return

    game["turn"] = game["p2"] if striker_id == game["p1"] else game["p1"]
    turn_n = game["p1_n"] if game["turn"] == game["p1"] else game["p2_n"]

    fires = game["chamber"].count("🔥")
    ices = game["chamber"].count("❄️")

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔫 СТРЕЛЯТЬ", callback_data=f"shot_{gid}_{game['turn']}")]
    ])

    status = (
        f"🎰 Ставка: {game['bet'].upper()}\n"
        f"🔫 Патроны: {len(game['chamber'])} (🔥 {fires} | ❄️ {ices})\n\n"
        f"👤 {game['p1_n']}: {'❤️' * game['hp1']}\n"
        f"👤 {game['p2_n']}: {'❤️' * game['hp2']}\n"
        f"👉 Ход: {turn_n}"
    )

    await query.message.edit_text(f"📢 {effect}\n\n{status}", reply_markup=kb)


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    raw = update.message.text
    text = raw.lower().strip()
    user = update.effective_user
    reply = update.message.reply_to_message
    cid = update.effective_chat.id

    # Регистрируем пользователя в БД
    await db.ensure_user(user.id)

    if text in ["статус", "статус+"]:
        if reply and reply.text:
            match = re.search(r"(https?://garticphone\.com/[^\s]+)", reply.text)

            if match:
                url = match.group(1)

                if text == "статус":
                    msg = await update.message.reply_text("👁 Глаз Крилоксы проверяет комнату без входа...")
                    result = await check_gartic_link(url, count_mode=False)
                else:
                    msg = await update.message.reply_text("👁 Глаз v3 входит, слушает WebSocket и пишет debug-логи...")
                    result = await check_gartic_link(url, count_mode=True)

                try:
                    await msg.edit_text(result, parse_mode="Markdown")
                except Exception:
                    await update.message.reply_text(result, parse_mode="Markdown")

                return

        await update.message.reply_text(
            "⚠️ Ответь командой `статус` или `статус+` на сообщение со ссылкой Gartic Phone.",
            parse_mode="Markdown"
        )
        return

    if text in ["баланс", "б"]:
        if user.id == OWNER_ID:
            balance = "∞ (Owner)"
        else:
            balance = f"{await db.get_balance(user.id)} KLC"
        await update.message.reply_text(f"💰 Ваш баланс: {balance}")
        return

    if text == "обо мне" or (text == "инфа" and reply):
        target = reply.from_user if (text == "инфа" and reply) else user
        await db.ensure_user(target.id)
        
        if target.id == OWNER_ID:
            balance = "∞ (Owner)"
        else:
            balance = f"{await db.get_balance(target.id)} KLC"

        warns_count = await db.get_warns(target.id)
        rank = await db.get_rank(target.id)
        rank_str = "4 (Owner)" if target.id == OWNER_ID else ("-1 Tester" if rank == -1 else str(rank))

        await update.message.reply_text(
            f"👤 Профиль пользователя {target.first_name}:\n"
            f"🆔 ID: `{target.id}`\n"
            f"⭐️ Ранг: {rank_str}\n"
            f"💰 Баланс: {balance}\n"
            f"⚠️ Варны: {warns_count}/3\n"
            f"────────────────\n"
            f"🤖 Версия: {VERSION}",
            parse_mode="Markdown"
        )
        return

    if text.startswith("промо "):
        code = text.split(" ", 1)[1].strip()
        
        if await db.use_promo(code, user.id):
            promo_amount = await db.get_promo_amount(code)
            await update.message.reply_text(f"✅ Промокод `{code}` активирован! +{promo_amount} KLC.", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Такого промокода нет или он уже использован.")
        return

    if text == "работа":
        if update.effective_chat.type != "private":
            await update.message.reply_text("⚒ Работа доступна только в ЛС бота!")
            return

        now = datetime.now()

        if user.id in work_timers and (now - work_timers[user.id]).seconds < 30:
            left = 30 - (now - work_timers[user.id]).seconds
            await update.message.reply_text(f"⏳ Жди {left} сек.")
            return

        gain = random.randint(50, 150)
        await db.update_balance(user.id, gain)
        work_timers[user.id] = now

        await update.message.reply_text(f"⛏ Заработано {gain} KLC!")
        return

    if text == "рулетка" and reply:
        if reply.from_user.id == user.id:
            return

        gid = f"{user.id}_{reply.from_user.id}"
        chamber = ["🔥", "🔥", "❄️", "❄️", "❄️", "❄️"]

        duel_sessions[gid] = {
            "p1": user.id,
            "p1_n": user.first_name,
            "p2": reply.from_user.id,
            "p2_n": reply.from_user.first_name,
            "hp1": 2,
            "hp2": 2,
            "turn": None,
            "chamber": chamber,
            "bet": None
        }

        kb = [
            [
                InlineKeyboardButton("💰 100 KLC", callback_data=f"set_klc_{gid}"),
                InlineKeyboardButton("⚠️ ВАРН", callback_data=f"set_warn_{gid}")
            ],
            [
                InlineKeyboardButton("🚫 БАН 1д", callback_data=f"set_ban_{gid}"),
                InlineKeyboardButton("😶 МУТ 1д", callback_data=f"set_mute_{gid}")
            ]
        ]

        await update.message.reply_text(
            f"🎲 ДУЭЛЬ!\n\n"
            f"👤 {user.first_name} VS {reply.from_user.first_name}\n"
            f"🔫 Барабан: 6 патронов\n\n"
            f"👉 {reply.from_user.first_name}, выбирай ставку:",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    if reply and await db.get_rank(user.id) >= 1:
        target_id = reply.from_user.id
        target_name = reply.from_user.first_name

        if text.startswith("бан"):
            seconds, label, reason = parse_admin_request(raw)

            await context.bot.ban_chat_member(
                cid,
                target_id,
                until_date=datetime.now() + timedelta(seconds=seconds) if seconds else None
            )

            await update.message.reply_text(
                f"🚫 {target_name} забанен ({label if label else 'навсегда'}).\n"
                f"📝 Причина: {reason}"
            )
            return

        if text.startswith("молчи"):
            seconds, label, reason = parse_admin_request(raw)

            await context.bot.restrict_chat_member(
                cid,
                target_id,
                ChatPermissions(can_send_messages=False),
                until_date=datetime.now() + timedelta(seconds=seconds if seconds else 3600)
            )

            await update.message.reply_text(
                f"🤫 {target_name} в муте ({label if label else '1 час'}).\n"
                f"📝 Причина: {reason}"
            )
            return

        if text == "скажи":
            await context.bot.restrict_chat_member(
                cid,
                target_id,
                ChatPermissions(
                    can_send_messages=True,
                    can_send_photos=True,
                    can_send_videos=True,
                    can_send_other_messages=True
                )
            )

            await update.message.reply_text(f"🔊 {target_name} размучен.")
            return

        if text.startswith("варн"):
            _, _, reason = parse_admin_request(raw)

            new_warns = await db.update_warns(target_id, 1)

            if new_warns >= 3:
                await context.bot.ban_chat_member(cid, target_id)
                await update.message.reply_text(
                    f"⛔️ {target_name} забанен (3/3 варнов).\n"
                    f"Причина: {reason}"
                )
                await db.reset_warns(target_id)
            else:
                await update.message.reply_text(
                    f"⚠️ Варн {target_name} ({new_warns}/3).\n"
                    f"Причина: {reason}"
                )

            return


async def on_call(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data

    try:
        await q.answer()
    except Exception:
        pass

    if data.startswith("set_"):
        parts = data.split("_")
        bet = parts[1]
        gid = f"{parts[2]}_{parts[3]}"

        game = duel_sessions.get(gid)

        if not game:
            await q.answer("Игра уже закончилась.", show_alert=True)
            return

        if q.from_user.id != game["p2"]:
            await q.answer("Ставку выбирает второй игрок.", show_alert=True)
            return

        game["bet"] = bet
        game["turn"] = game["p1"]

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔫 СТРЕЛЯТЬ", callback_data=f"shot_{gid}_{game['turn']}")]
        ])

        status = (
            f"🎰 Ставка: {bet.upper()}\n"
            f"🔫 Патроны: 6 (🔥 2 | ❄️ 4)\n\n"
            f"👤 {game['p1_n']}: ❤️❤️\n"
            f"👤 {game['p2_n']}: ❤️❤️\n"
            f"👉 Ход: {game['p1_n']}"
        )

        await q.message.edit_text(status, reply_markup=kb)
        return

    if data.startswith("shot_"):
        parts = data.split("_")
        gid = f"{parts[1]}_{parts[2]}"
        striker = int(parts[3])

        if q.from_user.id != striker:
            await q.answer("Сейчас не твой ход.", show_alert=True)
            return

        await handle_duel(q, context, gid, striker)
        return

    if data.startswith("shop_"):
        uid = q.from_user.id
        await db.ensure_user(uid)

        if data == "shop_unmute":
            if await db.get_balance(uid) >= 1000:
                await db.update_balance(uid, -1000)

                await context.bot.restrict_chat_member(
                    q.message.chat_id,
                    uid,
                    ChatPermissions(
                        can_send_messages=True,
                        can_send_photos=True,
                        can_send_videos=True,
                        can_send_other_messages=True
                    )
                )

                await q.answer("✅ Мут снят!", show_alert=True)
            else:
                await q.answer("❌ Недостаточно KLC.", show_alert=True)

            return

        if data == "shop_unwarn":
            if await db.get_balance(uid) >= 500:
                await db.update_balance(uid, -500)
                new_warns = await db.update_warns(uid, -1)
                await q.answer(f"✅ Варн снят! Теперь варнов: {new_warns}", show_alert=True)
            else:
                await q.answer("❌ Недостаточно KLC.", show_alert=True)

            return


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🤖 Kryloxa Bot v{VERSION} запущен!\n✅ PostgreSQL подключён")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        f"📜 СПИСОК КОМАНД ({VERSION})\n\n"
        "🕹 Меню: /start, /help, /magaz\n"
        "👁 Глаз: статус — без входа; статус+ — WebSocket debug\n"
        "💰 Экономика: баланс, б, обо мне\n"
        "⚒ Фарм: работа — только в ЛС бота\n"
        "🎫 Промо: промо [код]\n"
        "🛡 Модер: инфа, молчи, скажи, бан, варн\n"
        "🎲 Игра: рулетка — ответом на пользователя"
    )

    await update.message.reply_text(text)


async def magaz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("🧼 Снять мут (1000 KLC)", callback_data="shop_unmute")],
        [InlineKeyboardButton("💊 Снять варн (500 KLC)", callback_data="shop_unwarn")]
    ]

    await update.message.reply_text(
        "🛒 Kryloxa Shop",
        reply_markup=InlineKeyboardMarkup(kb)
    )


if __name__ == "__main__":
    print("=" * 45)
    print("🤖 Kryloxa Bot запускается...")
    print(f"Версия: {VERSION}")
    print("=" * 45)

    # Подключаемся к БД
    async def init_db():
        await db.connect()

    asyncio.get_event_loop().run_until_complete(init_db())

    request_config = HTTPXRequest(
        connect_timeout=30,
        read_timeout=30,
        write_timeout=30,
        pool_timeout=30
    )

    app = ApplicationBuilder().token(TOKEN).request(request_config).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("magaz", magaz))

    app.add_handler(CallbackQueryHandler(on_call))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    print("[OK] Бот запущен.")
    app.run_polling(drop_pending_updates=True)
