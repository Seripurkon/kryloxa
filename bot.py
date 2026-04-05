import os
import json
import random
import logging
import re
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import (
    ApplicationBuilder, ContextTypes, MessageHandler, filters, 
    CallbackQueryHandler, CommandHandler, ConversationHandler
)
from telegram.request import HTTPXRequest

# --- НАСТРОЙКИ ---
TOKEN = "8641381095:AAH44UdW5z66BkX0rO5qKHOcdESAoghso_g"
OWNER_ID = 5679520675
TESTER_ID = 782585931
HELPER_ID = 8475300408

# Реквизиты и данные магазина
CARD_NUMBER = "2202 2084 1533 2171"
SUPPORT_BOT_NAME = "kryloxaHelper_bot"
MIN_WITHDRAW_KLC = 4000 

ECONOMY_FILE = "economy.json"
RANKS_FILE = "ranks.json"
PROMOS_FILE = "promos.json" 
ACTIVATED_PROMOS_FILE = "activated_promos.json"
DONATORS_FILE = "donators.json"
BOT_VERSION = "1.1.1"

# Состояния для промокода
PROMO_NAME, PROMO_TIME, PROMO_REWARD = range(3)

# Настройки Казино
SLOTS_SYMBOLS = ["🍋", "🍒", "🔔", "💎", "7️⃣"]
SLOTS_WEIGHTS = [50, 30, 15, 4.9, 0.1] 
MIN_BET_SLOTS = 500
CURRENCY_RATE = 0.06 
MAX_DAILY_WITHDRAW = 10000

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ БАЗЫ ---
def load_json(filename, default):
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {int(k) if isinstance(k, str) and k.isdigit() else k: v for k, v in data.items()}
        except: return default
    return default

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def decline_word(number, titles):
    cases = [2, 0, 1, 1, 1, 2]
    return titles[0 if number % 100 > 4 and number % 100 < 20 else cases[min(number % 10, 5)]]

def parse_kryloxa_time(text):
    text = text.lower().strip()
    if "навсегда" in text: return -1, "навсегда 💀"
    match = re.search(r"(\d+)\s*([мчдг])", text)
    if not match: return None, None
    amount = int(match.group(1))
    unit = match.group(2)
    if unit == 'м': return amount * 60, f"{amount} {decline_word(amount, ['минуту', 'минуты', 'минут'])}"
    if unit == 'ч': return amount * 3600, f"{amount} {decline_word(amount, ['час', 'часа', 'часов'])}"
    if unit == 'д': return amount * 86400, f"{amount} {decline_word(amount, ['день', 'дня', 'дней'])}"
    if unit == 'г': return amount * 31536000, f"{amount} {decline_word(amount, ['год', 'года', 'лет'])}"
    return None, None

# Загрузка данных
user_ranks = load_json(RANKS_FILE, {OWNER_ID: 4, TESTER_ID: 4, HELPER_ID: -1})
user_balance = load_json(ECONOMY_FILE, {})
active_promos = load_json(PROMOS_FILE, {})
used_promo_db = load_json(ACTIVATED_PROMOS_FILE, {}) 
donators = load_json(DONATORS_FILE, [])

warns = {}
roulette_games = {}
daily_stats = {}
bonus_timers = {}
work_timers = {}
withdraw_requests = {}

# --- ЛОГИКА ЭКОНОМИКИ ---
def get_user_stats(u_id):
    if u_id not in user_balance:
        user_balance[u_id] = {"main": 500, "bonus": 0}
    if isinstance(user_balance[u_id], int):
        old_val = user_balance[u_id]
        user_balance[u_id] = {"main": old_val, "bonus": 0}
        save_json(ECONOMY_FILE, user_balance)
    return user_balance[u_id]

def update_balance(u_id, amount, b_type="main"):
    if u_id == OWNER_ID and amount < 0: return 
    stats = get_user_stats(u_id)
    stats[b_type] += amount
    if stats[b_type] < 0: stats[b_type] = 0
    save_json(ECONOMY_FILE, user_balance)

def get_rank(user_id):
    if user_id == OWNER_ID: return 4
    return user_ranks.get(user_id, 0)

# --- КОМАНДЫ БОТА ---
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Kryloxa System запущена! Напиши /help для списка команд.")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        f"📜 **СПИСОК КОМАНД ({BOT_VERSION})**\n\n"
        "🕹 **Меню:** /start, /help, /donate, /magaz\n"
        "💰 **Экономика:** баланс (б), бонус, тп, обо мне\n"
        "🎰 **Казино:** `слоты [ставка]`, `вывод [сумма] [карта]`\n"
        "⚒ **Заработок:** напиши 'работа' (в ЛС бота)\n"
        "🎫 **Промо:** `Промо: [код]`\n"
        "🛡 **Модер:** инфа, молчи, скажи, бан, варн"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def donate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "<b>🏦 Официальный обменник KLC</b>\n\n"
        "💳 <b>Реквизиты (нажми для копирования):</b>\n"
        f"<code>{CARD_NUMBER}</code>\n\n"
        "💵 <b>Прайс KLC:</b>\n"
        "• 📦 5,000 KLC — 300₽\n"
        "• 💼 10,000 KLC — 550₽\n\n"
        f"⚠️ После оплаты пишите в @{SUPPORT_BOT_NAME} для зачисления."
    )
    kb = [[InlineKeyboardButton("📥 Прислать чек", url=f"https://t.me/{SUPPORT_BOT_NAME}")],
          [InlineKeyboardButton("📤 Оформить вывод", url=f"https://t.me/{SUPPORT_BOT_NAME}")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def show_profile(update: Update, user):
    u_id = user.id
    rank = str(get_rank(u_id))
    stats = get_user_stats(u_id)
    bal_main = "∞" if u_id == OWNER_ID else stats['main']
    text = (
        f"👤 Профиль {user.first_name}:\n"
        f"🆔 ID: `{u_id}`\n"
        f"⭐️ Ранг: {rank}\n"
        f"💳 Чистый: {bal_main} KLC\n"
        f"🎁 Бонус: {stats['bonus']} KLC\n"
        f"⚠️ Варны: {warns.get(u_id, 0)}/3"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def magaz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    stats = get_user_stats(user.id)
    bal = "∞" if user.id == OWNER_ID else (stats['main'] + stats['bonus'])
    text = f"🛒 **Kryloxa Shop**\n💰 Общий баланс: {bal} KLC\nВыберите услугу:"
    kb = [[InlineKeyboardButton("🚫 Снять мут (1000 KLC)", callback_data="buy_unmute")],
          [InlineKeyboardButton("⚠️ Снять варн (500 KLC)", callback_data="buy_unwarn")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def work_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return await update.message.reply_text("❌ Команда 'работа' только в ЛС бота!")
    kb = [[InlineKeyboardButton("⚒ Начать смену", callback_data="do_work")]]
    await update.message.reply_text("🏭 Нажми кнопку, чтобы получить бонусные KLC:", reply_markup=InlineKeyboardMarkup(kb))

# --- КАЗИНО И ИГРЫ ---
async def run_slots(u_id, bet):
    stats = get_user_stats(u_id)
    total = stats["main"] + stats["bonus"]
    if total < bet: return "❌ Мало KLC!", False
    if stats["bonus"] >= bet: update_balance(u_id, -bet, "bonus")
    else:
        rem = bet - stats["bonus"]
        update_balance(u_id, -stats["bonus"], "bonus"); update_balance(u_id, -rem, "main")
    res = [random.choices(SLOTS_SYMBOLS, weights=SLOTS_WEIGHTS)[0] for _ in range(3)]
    win = 0
    if res[0] == res[1] == res[2]:
        win = bet * 200 if res[0] == "7️⃣" else (bet * 25 if res[0] == "💎" else bet * 10)
    elif (res[0] == res[1] or res[1] == res[2] or res[0] == res[2]) and random.random() > 0.6:
        win = int(bet * 1.5)
    if win > 0:
        update_balance(u_id, win, "main")
        return f"🎰 `[ {res[0]} | {res[1]} | {res[2]} ]` \n\n✅ **ВИН!** +{win} KLC (в чистый)", True
    return f"🎰 `[ {res[0]} | {res[1]} | {res[2]} ]` \n\n❌ **Мимо!**", True

def get_slots_kb(bet):
    return InlineKeyboardMarkup([[InlineKeyboardButton("🎰 Снова", callback_data=f"c_spin_{bet}")],
                                 [InlineKeyboardButton("🛑 Стоп", callback_data="c_stop")]])

# --- ОБРАБОТКА CALLBACK ---
async def all_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    u_id = q.from_user.id
    
    if q.data == "do_work":
        now = datetime.now()
        last = work_timers.get(u_id)
        if last and now < last + timedelta(seconds=30):
            return await q.answer(f"⏳ Жди {int((last+timedelta(seconds=30)-now).total_seconds())} сек.", show_alert=True)
        update_balance(u_id, 50, "bonus"); work_timers[u_id] = now
        await q.answer("🎁 +50 Бонусных KLC!"); await q.edit_message_text("⚒ Смена отработана! +50 KLC.")

    elif q.data.startswith("buy_"):
        stats = get_user_stats(u_id); total = stats["main"] + stats["bonus"]
        cost = 1000 if q.data == "buy_unmute" else 500
        if u_id == OWNER_ID or total >= cost:
            if stats["bonus"] >= cost: update_balance(u_id, -cost, "bonus")
            else: rem = cost - stats["bonus"]; update_balance(u_id, -stats["bonus"], "bonus"); update_balance(u_id, -rem, "main")
            if q.data == "buy_unmute":
                try: await context.bot.restrict_chat_member(q.message.chat_id, u_id, permissions=ChatPermissions(can_send_messages=True))
                except: pass
            elif q.data == "buy_unwarn": warns[u_id] = max(0, warns.get(u_id, 0) - 1)
            await q.answer("✅ Готово!", show_alert=True)
        else: await q.answer("❌ Недостаточно средств!", show_alert=True)

    elif q.data.startswith("c_spin_"):
        bet = int(q.data.split("_")[2])
        txt, ok = await run_slots(u_id, bet)
        await q.edit_message_text(txt, reply_markup=get_slots_kb(bet) if ok else None, parse_mode="Markdown")
    
    elif q.data == "c_stop": await q.edit_message_text("🛑 Игра завершена.")

# --- ПРОМОКОДЫ ---
async def promo_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return ConversationHandler.END
    await update.message.reply_text("1) Имя промокода?"); return PROMO_NAME

async def promo_get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['temp_promo_name'] = update.message.text.strip()
    await update.message.reply_text("2) Время действия? (Напр: 1д, 5ч)"); return PROMO_TIME

async def promo_get_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    seconds, _ = parse_kryloxa_time(update.message.text)
    if not seconds: return PROMO_TIME
    context.user_data['temp_promo_expire'] = (datetime.now() + timedelta(seconds=seconds)).isoformat()
    await update.message.reply_text("3) Награда (KLC)?"); return PROMO_REWARD

async def promo_get_reward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        reward = int(update.message.text); name = context.user_data['temp_promo_name']
        active_promos[name] = {"reward": reward, "expire": context.user_data['temp_promo_expire']}
        save_json(PROMOS_FILE, active_promos); await update.message.reply_text(f"✅ Промокод {name} создан!"); return ConversationHandler.END
    except: return PROMO_REWARD

# --- ГЛАВНЫЙ ТЕКСТОВЫЙ ОБРАБОТЧИК ---
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    text = update.message.text.lower(); user = update.effective_user; stats = get_user_stats(user.id)
    
    if text.startswith("промо:"):
        code = text.replace("промо:", "").strip()
        if code in active_promos:
            if user.id in used_promo_db.get(code, []): return await update.message.reply_text("❌ Ты уже активировал это!")
            data = active_promos[code]
            if datetime.now() < datetime.fromisoformat(data['expire']):
                update_balance(user.id, data['reward'], "bonus")
                used_promo_db.setdefault(code, []).append(user.id); save_json(ACTIVATED_PROMOS_FILE, used_promo_db)
                await update.message.reply_text(f"🎫 Промокод активирован! +{data['reward']} Бонусных KLC")
            else: await update.message.reply_text("❌ Срок действия истек.")
    
    elif text in ["баланс", "б"]:
        bal = "∞" if user.id == OWNER_ID else stats['main']
        await update.message.reply_text(f"💰 {user.first_name}:\n💳 Чистый: {bal} KLC\n🎁 Бонусный: {stats['bonus']} KLC")
    
    elif text == "бонус":
        now = datetime.now()
        if user.id in bonus_timers and now < bonus_timers[user.id] + timedelta(days=1):
            return await update.message.reply_text("❌ Бонус раз в 24 часа!")
        amt = random.randint(150, 600); update_balance(user.id, amt, "bonus")
        bonus_timers[user.id] = now; await update.message.reply_text(f"🎁 Твой бонус: +{amt} KLC")

    elif text == "обо мне": await show_profile(update, user)

# --- ЗАПУСК ---
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).request(HTTPXRequest(connect_timeout=30, read_timeout=30)).build()
    
    promo_conv = ConversationHandler(
        entry_points=[CommandHandler("createpm", promo_start)],
        states={
            PROMO_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, promo_get_name)],
            PROMO_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, promo_get_time)],
            PROMO_REWARD: [MessageHandler(filters.TEXT & ~filters.COMMAND, promo_get_reward)],
        },
        fallbacks=[]
    )

    app.add_handler(promo_conv)
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("donate", donate_cmd))
    app.add_handler(CommandHandler("shop", donate_cmd))
    app.add_handler(CommandHandler("magaz", magaz_cmd))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^[Рр]абота$"), work_command))
    app.add_handler(CallbackQueryHandler(all_callbacks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    print(f"Kryloxa System v{BOT_VERSION} ЗАПУЩЕН!")
    app.run_polling(drop_pending_updates=True)
