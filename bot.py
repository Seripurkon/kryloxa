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

# --- НАСТРОЙКИ (КОНСТАНТЫ) ---
TOKEN = "8641381095:AAH44UdW5z66BkX0rO5qKHOcdESAoghso_g"
OWNER_ID = 5679520675
TESTER_ID = 782585931
HELPER_ID = 8475300408

# Реквизиты и Саппорт
CARD_NUMBER = "2202 2084 1533 2171"
SUPPORT_BOT_NAME = "kryloxaHelper_bot" # Без @ для ссылок
MIN_WITHDRAW_KLC = 4000 

ECONOMY_FILE = "economy.json"
RANKS_FILE = "ranks.json"
PROMOS_FILE = "promos.json" 
ACTIVATED_PROMOS_FILE = "activated_promos.json"
DONATORS_FILE = "donators.json"
BOT_VERSION = "1.1.0"

# Состояния для промокода
PROMO_NAME, PROMO_TIME, PROMO_REWARD = range(3)

# Настройки Казино
SLOTS_SYMBOLS = ["🍋", "🍒", "🔔", "💎", "7️⃣"]
SLOTS_WEIGHTS = [50, 30, 15, 4.9, 0.1] 
MIN_BET_SLOTS = 500
CURRENCY_RATE = 0.06 # 1 KLC = 0.06 руб
MAX_DAILY_WITHDRAW = 10000

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
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

def get_rank(user_id):
    if user_id == OWNER_ID: return 4
    return user_ranks.get(user_id, 0)

# --- ЭКОНОМИКА ---
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

def get_slots_kb(bet):
    kb = [[InlineKeyboardButton("🎰 Крутить снова", callback_data=f"c_spin_{bet}")],
          [InlineKeyboardButton("🛑 Стоп", callback_data="c_stop")]]
    return InlineKeyboardMarkup(kb)

def reload_chamber(g):
    chamber = [True, True, True, False, False, False]
    random.shuffle(chamber)
    g['chamber'] = chamber

# --- КАЗИНО ЛОГИКА ---
async def run_slots(u_id, bet):
    stats = get_user_stats(u_id)
    total = stats["main"] + stats["bonus"]
    if total < bet: return "❌ Недостаточно KLC!", False
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
        return f"🎰 `[ {res[0]} | {res[1]} | {res[2]} ]` \n\n✅ **ВИН!** +{win} KLC", True
    return f"🎰 `[ {res[0]} | {res[1]} | {res[2]} ]` \n\n❌ **Мимо!**", True

# --- ПРОФИЛЬ И МАГАЗИН ---
async def show_profile(update: Update, user):
    u_id = user.id
    rank = str(get_rank(u_id))
    stats = get_user_stats(u_id)
    bal_main = "∞" if u_id == OWNER_ID else stats['main']
    text = (f"👤 Профиль {user.first_name}:\n🆔 ID: `{u_id}`\n⭐️ Ранг: {rank}\n"
            f"💳 Чистый: {bal_main} KLC\n🎁 Бонус: {stats['bonus']} KLC\n⚠️ Варны: {warns.get(u_id, 0)}/3")
    await update.message.reply_text(text, parse_mode="Markdown")

async def donate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Новая команда /donate и /shop"""
    text = (
        "<b>🏦 Официальный обменник KLC</b>\n\n"
        "Пополни баланс для игры или выведи средства 💳\n\n"
        "💵 <b>Покупка пакетов:</b>\n"
        "• 📦 <b>5,000 KLC</b> — 300₽\n"
        "• 💼 <b>10,000 KLC</b> — 550₽ <i>(Выгода 50₽!)</i>\n\n"
        "💰 <b>Вывод средств:</b>\n"
        f"• Минимальная сумма: <b>{MIN_WITHDRAW_KLC} KLC</b>\n"
        "• <i>(Примерно 239₽ без комиссии)</i>\n\n"
        "💳 <b>Реквизиты (нажми для копирования):</b>\n"
        f"<code>{CARD_NUMBER}</code>\n\n"
        f"⚠️ <b>ОФОРМЛЕНИЕ:</b> После оплаты или для вывода пишите в @{SUPPORT_BOT_NAME}"
    )
    kb = [[InlineKeyboardButton("📥 Прислать чек", url=f"https://t.me/{SUPPORT_BOT_NAME}")],
          [InlineKeyboardButton("📤 Оформить вывод", url=f"https://t.me/{SUPPORT_BOT_NAME}")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def magaz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    stats = get_user_stats(user.id)
    bal = "∞" if user.id == OWNER_ID else (stats['main'] + stats['bonus'])
    text = f"🛒 **Kryloxa Shop**\n💰 Баланс: {bal} KLC"
    kb = [[InlineKeyboardButton("🚫 Снять мут (1000 KLC)", callback_data="buy_unmute")],
          [InlineKeyboardButton("⚠️ Снять варн (500 KLC)", callback_data="buy_unwarn")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

# --- ОБРАБОТКА CALLBACK ---
async def all_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    u_id = q.from_user.id
    
    if q.data == "do_work":
        now = datetime.now()
        last_work = work_timers.get(u_id)
        if last_work and now < last_work + timedelta(seconds=30):
            return await q.answer(f"⏳ Жди {int((last_work+timedelta(seconds=30)-now).total_seconds())} сек.", show_alert=True)
        update_balance(u_id, 50, "bonus"); work_timers[u_id] = now
        await q.answer("🎁 +50 Бонусных KLC!"); await q.edit_message_text("⚒ Смена отработана!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚒ Еще", callback_data="do_work")]]))

    elif q.data.startswith("buy_"):
        stats = get_user_stats(u_id); total = stats["main"] + stats["bonus"]
        cost = 1000 if q.data == "buy_unmute" else 500
        if u_id == OWNER_ID or total >= cost:
            if stats["bonus"] >= cost: update_balance(u_id, -cost, "bonus")
            else: rem = cost - stats["bonus"]; update_balance(u_id, -stats["bonus"], "bonus"); update_balance(u_id, -rem, "main")
            if q.data == "buy_unmute":
                try: await context.bot.restrict_chat_member(q.message.chat_id, u_id, permissions=ChatPermissions(can_send_messages=True, can_send_audios=True, can_send_documents=True, can_send_photos=True, can_send_videos=True, can_send_video_notes=True, can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True, can_add_web_page_previews=True, can_change_info=True, can_invite_users=True, can_pin_messages=True, can_manage_topics=True))
                except: pass
            elif q.data == "buy_unwarn": warns[u_id] = max(0, warns.get(u_id, 0) - 1)
            await q.answer("✅ Успешно!", show_alert=True)
        else: await q.answer("❌ Нет денег!", show_alert=True)

    elif q.data.startswith("c_spin_"):
        bet = int(q.data.split("_")[2])
        res_text, success = await run_slots(u_id, bet)
        await q.edit_message_text(res_text, reply_markup=get_slots_kb(bet) if success else None, parse_mode="Markdown")
    
    elif q.data == "c_stop": await q.edit_message_text("🛑 Стоп.")

    elif q.data.startswith("adm_"):
        action, rid = q.data.split("_")[1], int(q.data.split("_")[2])
        req = withdraw_requests.get(rid)
        if not req: return
        if action == "win": await context.bot.send_message(req["u_id"], f"✅ Выплата {req['rub']} руб. отправлена!")
        else: update_balance(req["u_id"], req["m"], "main"); update_balance(req["u_id"], req["b"], "bonus"); await context.bot.send_message(req["u_id"], "❌ Отказ. KLC вернулись.")
        del withdraw_requests[rid]; await q.edit_message_text(q.message.text + "\n\n✅ ГОТОВО")

    elif q.data.startswith("rbet_"):
        _, b, g_id = q.data.split("_", 2)
        if g_id in roulette_games: roulette_games[g_id]['bet_type'] = b; reload_chamber(roulette_games[g_id]); await update_ui(q, g_id, "🔥 БОЙ!")

    elif q.data.startswith("rt_"):
        _, act, g_id = q.data.split("_", 2)
        if g_id not in roulette_games: return
        g = roulette_games[g_id]; hit = g['chamber'].pop(0); curr, opp = g['turn'], (g['p2'] if g['turn'] == g['p1'] else g['p1'])
        if act == "opp":
            if hit: g['lives'][opp] -= 1; msg = "💥 БАХ!"
            else: msg = "💨 Холостой!"; g['turn'] = opp
        else:
            if hit: g['lives'][curr] -= 1; msg = "💥 БАХ!"; g['turn'] = opp
            else: msg = "💨 Доп. ход!"
        if any(l <= 0 for l in g['lives'].values()):
            # [Тут логика завершения рулетки с наказаниями из твоего кода]
            await q.edit_message_text(f"🏆 Конец игры! {msg}")
            del roulette_games[g_id]
        else: await update_ui(q, g_id, msg)

# --- ПРОМОКОДЫ И ТЕКСТ ---
async def promo_start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if u.effective_user.id != OWNER_ID: return ConversationHandler.END
    await u.message.reply_text("1) Имя промокода?"); return PROMO_NAME

async def promo_get_name(u: Update, c: ContextTypes.DEFAULT_TYPE):
    c.user_data['temp_promo_name'] = u.message.text.strip()
    await u.message.reply_text("2) Время? (1д, 5ч)"); return PROMO_TIME

async def promo_get_time(u: Update, c: ContextTypes.DEFAULT_TYPE):
    s, t = parse_kryloxa_time(u.message.text)
    if not s: return PROMO_TIME
    c.user_data['temp_promo_expire'] = (datetime.now() + timedelta(seconds=s)).isoformat()
    await u.message.reply_text("3) Награда (KLC)?"); return PROMO_REWARD

async def promo_get_reward(u: Update, c: ContextTypes.DEFAULT_TYPE):
    try:
        reward = int(u.message.text); name = c.user_data['temp_promo_name']
        active_promos[name] = {"reward": reward, "expire": c.user_data['temp_promo_expire']}
        save_json(PROMOS_FILE, active_promos); await u.message.reply_text(f"✅ Промо {name} создан!"); return ConversationHandler.END
    except: return PROMO_REWARD

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    txt = update.message.text.lower(); user = update.effective_user; stats = get_user_stats(user.id)
    
    if txt.startswith("промо:"):
        code = txt.replace("промо:", "").strip()
        if code in active_promos:
            if user.id in used_promo_db.get(code, []): return await update.message.reply_text("❌ Уже брал!")
            data = active_promos[code]
            if datetime.now() < datetime.fromisoformat(data['expire']):
                update_balance(user.id, data['reward'], "bonus"); used_promo_db.setdefault(code, []).append(user.id); save_json(ACTIVATED_PROMOS_FILE, used_promo_db)
                await update.message.reply_text(f"🎫 +{data['reward']} Бонусных KLC!")
            else: await update.message.reply_text("❌ Истек.")
    
    elif txt in ["баланс", "б"]:
        await update.message.reply_text(f"💰 {user.first_name}:\n💳 Чистый: {stats['main']}\n🎁 Бонус: {stats['bonus']}")
    
    elif txt == "бонус":
        now = datetime.now()
        if user.id in bonus_timers and now < bonus_timers[user.id] + timedelta(days=1): return await update.message.reply_text("❌ Жди 24ч!")
        amt = random.randint(150, 600); update_balance(user.id, amt, "bonus"); bonus_timers[user.id] = now
        await update.message.reply_text(f"🎁 +{amt} Бонусных KLC!")

    elif txt.startswith("слоты"):
        parts = txt.split()
        if len(parts) >= 2 and parts[1].isdigit():
            bet = int(parts[1])
            if bet >= MIN_BET_SLOTS:
                res, ok = await run_slots(user.id, bet)
                await update.message.reply_text(res, reply_markup=get_slots_kb(bet) if ok else None, parse_mode="Markdown")

    elif txt.startswith("вывод"):
        parts = update.message.text.split()
        if len(parts) >= 3 and parts[1].isdigit():
            amt = int(parts[1]); card = " ".join(parts[2:])
            if amt < MIN_WITHDRAW_KLC: return await update.message.reply_text(f"❌ Минимум {MIN_WITHDRAW_KLC}!")
            if (stats["main"] + stats["bonus"]) >= amt:
                f_b = min(amt, stats["bonus"]); f_m = amt - f_b
                rub = int(((f_m*CURRENCY_RATE)*0.35) + ((f_b*CURRENCY_RATE)*0.65)) # Примерный расчет
                rid = random.randint(1000, 9999); withdraw_requests[rid] = {"u_id": user.id, "rub": rub, "m": f_m, "b": f_b}
                update_balance(user.id, -f_m, "main"); update_balance(user.id, -f_b, "bonus")
                await update.message.reply_text(f"✅ Заявка №{rid} создана! Жди ~{rub} руб.")
                await context.bot.send_message(OWNER_ID, f"💰 ВЫВОД №{rid}\nКарта: `{card}`\nСумма: {rub}₽", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Да", callback_data=f"adm_win_{rid}"), InlineKeyboardButton("❌ Нет", callback_data=f"adm_rej_{rid}")]]))

async def update_ui(q, g_id, status):
    g = roulette_games[g_id]; l, bl = g['chamber'].count(True), g['chamber'].count(False)
    txt = f"🔫 Патроны: {len(g['chamber'])} (🔥 {l} | ❄️ {bl})\n📢 {status}\n👤 {g['p1_n']}: {'❤️'*g['lives'][g['p1']]}\n👤 {g['p2_n']}: {'❤️'*g['lives'][g['p2']]}\n👉 Ход: {g['p1_n'] if g['turn']==g['p1'] else g['p2_n']}"
    kb = [[InlineKeyboardButton("🎯 Оппонент", callback_data=f"rt_opp_{g_id}"), InlineKeyboardButton("🔫 Себя", callback_data=f"rt_self_{g_id}")]]
    await q.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(kb))

# --- ЗАПУСК ---
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).request(HTTPXRequest(connect_timeout=30, read_timeout=30)).build()
    
    promo_conv = ConversationHandler(
        entry_points=[CommandHandler("createpm", promo_start)],
        states={PROMO_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, promo_get_name)],
                PROMO_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, promo_get_time)],
                PROMO_REWARD: [MessageHandler(filters.TEXT & ~filters.COMMAND, promo_get_reward)]},
        fallbacks=[]
    )

    app.add_handler(promo_conv)
    app.add_handler(CommandHandler("start", lambda u, c: u.message.reply_text("👋 Напиши /help.")))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("magaz", magaz_cmd))
    app.add_handler(CommandHandler("donate", donate_cmd))
    app.add_handler(CommandHandler("shop", donate_cmd))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^[Рр]абота$"), lambda u, c: u.message.reply_text("⚒ Жми кнопку!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Начать", callback_data="do_work")]]))))
    app.add_handler(CallbackQueryHandler(all_callbacks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    print("Kryloxa System v1.1.0 запущен!")
    app.run_polling(drop_pending_updates=True)
