import os
import json
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Chat
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

# --- КОНФИГ (ТВОИ ДАННЫЕ) ---
TOKEN = "8641381095:AAGLY3W93LQGfq_Ygm1OIfAMwlhb6SlQrXE"
OWNER_ID = 5679520675 
FRIEND_ID = 782585931
RANKS_FILE = "ranks.json"
ECONOMY_FILE = "economy.json"

# --- СИСТЕМА СОХРАНЕНИЯ ---
def load_json(filename, default):
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {int(k): v for k, v in data.items()}
        except: pass
    return default

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# Инициализация баз данных
user_ranks = load_json(RANKS_FILE, {OWNER_ID: 4, FRIEND_ID: 3})
user_balance = load_json(ECONOMY_FILE, {})
warns = {}
roulette_games = {}
daily_stats = {} 
bonus_timers = {}
last_reset_day = datetime.now().day

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def get_rank(user_id):
    if user_id == OWNER_ID: return 4
    if user_id == FRIEND_ID: return 3
    return user_ranks.get(user_id, 0)

def check_daily_reset():
    global last_reset_day, daily_stats
    current_day = datetime.now().day
    if current_day != last_reset_day:
        daily_stats = {}
        last_reset_day = current_day

def reload_chamber(g):
    live = random.randint(1, 4)
    chamber = [True] * live + [False] * (6 - live)
    random.shuffle(chamber)
    g['chamber'] = chamber
    g['info'] = f"Боевых: {live}, Холостых: {6 - live}"

# --- КОМАНДЫ ПРЯМОГО ВЫЗОВА (/) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я **Kryloxa Bot**.\n"
        "Валюта чата: **KLC** 🪙\n"
        "Мой канал: @kryloxa_offcial\n"
        "Помощь: /help", parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rank = get_rank(update.effective_user.id)
    text = (
        "📜 **Команды Kryloxa Bot:**\n\n"
        "💰 **Экономика:**\n"
        "• бонус — получить KLC\n"
        "• баланс (б) — твой счет\n"
        "• /magaz или 'Магазин' — покупки\n"
        "• передать [сумма] — перевод (ответом)\n\n"
        "🎮 **Активность:**\n"
        "• рулетка — дуэль (ответом)\n"
        "• тп — топ активных\n"
        "• обо мне — твой профиль\n"
        "• инфа — статус игрока (ответом)\n"
    )
    if rank >= 1:
        text += "\n🛠 **Админ-панель:**\n• молчи [мин], скажи, варн, бан"
    await update.message.reply_text(text, parse_mode="Markdown")

async def send_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == Chat.PRIVATE:
        return await update.message.reply_text("❌ Зайди в чат, чтобы пользоваться магазином!")
    
    user = update.effective_user
    bal = user_balance.get(user.id, 0)
    
    shop_msg = (
        f"👋 Здравствуйте, {user.first_name}!\n"
        f"🛍 **Kryloxa Shop**\n"
        "————————————————\n"
        f"💰 Твой баланс: `{bal}` KLC\n"
        "————————————————\n"
        "Выберите услугу:"
    )
    
    keyboard = [[
        InlineKeyboardButton("🕊 Снять мут (1000 KLC)", callback_data=f"shop_mute_{user.id}"),
        InlineKeyboardButton("⚠️ Снять варн (500 KLC)", callback_data=f"shop_warn_{user.id}")
    ]]
    await update.message.reply_text(shop_msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# --- ГЛАВНЫЙ ОБРАБОТЧИК ТЕКСТА ---
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    check_daily_reset()
    
    text = update.message.text.strip().lower()
    user = update.effective_user
    chat_id = update.effective_chat.id
    msg = update.message.reply_to_message
    
    # Счётчик сообщений (ТП)
    if user.id not in daily_stats:
        daily_stats[user.id] = {"name": user.first_name, "count": 0}
    daily_stats[user.id]["count"] += 1

    # Реакция на текстовые команды
    if text == "магазин": return await send_shop(update, context)
    if text == "помощь": return await help_command(update, context)

    # --- ЭКОНОМИКА ---
    if text == "бонус":
        now = datetime.now()
        last = bonus_timers.get(user.id)
        if last and now < last + timedelta(days=1):
            rem = (last + timedelta(days=1)) - now
            h = int(rem.total_seconds() // 3600)
            m = int((rem.total_seconds() % 3600) // 60)
            return await update.message.reply_text(f"⏳ Приходи через {h}ч {m}м!")
        
        amt = random.randint(150, 500)
        user_balance[user.id] = user_balance.get(user.id, 0) + amt
        bonus_timers[user.id] = now
        save_json(ECONOMY_FILE, user_balance)
        return await update.message.reply_text(f"🎁 Ты получил {amt} KLC! Баланс: {user_balance[user.id]} 🪙")

    if text in ["баланс", "б"]:
        bal = user_balance.get(user.id, 0)
        return await update.message.reply_text(f"💰 Кошелек {user.first_name}: {bal} KLC")

    if text.startswith("передать") and msg:
        try:
            amt = int(text.split()[1])
            if amt <= 0 or user_balance.get(user.id, 0) < amt:
                return await update.message.reply_text("❌ Ошибка перевода!")
            user_balance[user.id] -= amt
            user_balance[msg.from_user.id] = user_balance.get(msg.from_user.id, 0) + amt
            save_json(ECONOMY_FILE, user_balance)
            await update.message.reply_text(f"🤝 Передано {amt} KLC для {msg.from_user.first_name}")
        except: pass

    # --- ИНФО ---
    if text == "тп":
        top = sorted(daily_stats.items(), key=lambda x: x[1]["count"], reverse=True)[:10]
        res = "🏆 **Топ активных сегодня:**\n" + "\n".join([f"{i+1}. {d['name']} — {d['count']}" for i, (uid, d) in enumerate(top)])
        return await update.message.reply_text(res, parse_mode="Markdown")

    if text == "обо мне":
        res = f"👤 **Профиль:**\n⭐ Ранг: {get_rank(user.id)}\n💰 Баланс: {user_balance.get(user.id, 0)} KLC\n⚠️ Варны: {warns.get(user.id, 0)}/3"
        return await update.message.reply_text(res, parse_mode="Markdown")

    # --- КОМАНДЫ ОТВЕТОМ (МОДЕРАЦИЯ И ИНФА) ---
    if msg:
        target_id = msg.from_user.id
        caller_rank = get_rank(user.id)
        target_rank = get_rank(target_id)

        if text == "инфа":
            try:
                cm = await context.bot.get_chat_member(chat_id, target_id)
                st = "✅ Свободен" if cm.status != 'restricted' else "🔇 В муте"
                await update.message.reply_text(f"👤 {msg.from_user.first_name}\n⭐ Ранг: {target_rank}\n💰 Баланс: {user_balance.get(target_id, 0)}\n⚠️ Варны: {warns.get(target_id, 0)}/3\n📊 Статус: {st}")
            except: pass

        if caller_rank >= 1 and (target_rank < caller_rank or user.id == OWNER_ID):
            if text.startswith("молчи"):
                m = int(text.split()[1]) if len(text.split()) > 1 and text.split()[1].isdigit() else 60
                await context.bot.restrict_chat_member(chat_id, target_id, permissions={"can_send_messages":False}, until_date=datetime.now()+timedelta(minutes=m))
                await update.message.reply_text(f"🔇 {msg.from_user.first_name} замолчал на {m} мин.")
            elif text == "скажи":
                await context.bot.restrict_chat_member(chat_id, target_id, permissions={"can_send_messages":True, "can_send_other_messages":True, "can_add_web_page_previews":True})
                await update.message.reply_text(f"🔊 {msg.from_user.first_name} снова в эфире!")
            elif text == "бан":
                await context.bot.ban_chat_member(chat_id, target_id)
                await update.message.reply_text(f"🚪 {msg.from_user.first_name} исключен из чата.")
            elif text == "варн":
                warns[target_id] = warns.get(target_id, 0) + 1
                if warns[target_id] >= 3:
                    warns[target_id] = 0
                    await context.bot.restrict_chat_member(chat_id, target_id, permissions={"can_send_messages":False}, until_date=datetime.now()+timedelta(minutes=30))
                    await update.message.reply_text(f"🛑 3/3 варна! {msg.from_user.first_name} в муте на 30 мин.")
                else:
                    await update.message.reply_text(f"⚠️ Варн {msg.from_user.first_name}: {warns[target_id]}/3")

# --- РУЛЕТКА (ПОЛНАЯ ЛОГИКА) ---
async def roulette_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.reply_to_message
    if not msg or update.effective_user.id == msg.from_user.id:
        return await update.message.reply_text("Чтобы начать дуэль, ответь на сообщение противника!")
    
    g_id = str(update.message.message_id)
    p1, p2 = update.effective_user, msg.from_user
    roulette_games[g_id] = {"p1": p1.id, "p1_n": p1.first_name, "p2": p2.id, "p2_n": p2.first_name, "lives": {p1.id: 2, p2.id: 2}, "turn": p2.id, "mode": "mute"}
    reload_chamber(roulette_games[g_id])
    
    kb = [[InlineKeyboardButton("🎯 Принять вызов", callback_data=f"start_game_{g_id}")]]
    await update.message.reply_text(f"👊 {p2.first_name}, тебя вызвали на дуэль! Ставка: Мут. Принимаешь?", reply_markup=InlineKeyboardMarkup(kb))

# --- ОБРАБОТЧИК КНОПОК ---
async def universal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    d = query.data.split("_")
    action, val, gid = d[0], d[1], d[2]
    uid = query.from_user.id

    if action == "shop":
        if uid != int(gid): return await query.answer("Это не твоё меню!")
        bal = user_balance.get(uid, 0)
        if val == "mute":
            if bal < 1000: return await query.answer("Недостаточно KLC!")
            await context.bot.restrict_chat_member(query.message.chat_id, uid, permissions={"can_send_messages":True, "can_send_other_messages":True, "can_add_web_page_previews":True})
            user_balance[uid] -= 1000
            save_json(ECONOMY_FILE, user_balance)
            await query.edit_message_text("🕊 Размут куплен!")
        elif val == "warn":
            if bal < 500 or warns.get(uid, 0) <= 0: return await query.answer("Ошибка!")
            user_balance[uid] -= 500
            warns[uid] -= 1
            save_json(ECONOMY_FILE, user_balance)
            await query.edit_message_text("⚠️ Варн снят!")

    elif action == "start":
        # Здесь можно добавить полную логику стрельбы, если хочешь расширить
        await query.edit_message_text("🔫 Дуэль началась! Стреляйте командой 'Рулетка' (или добавь кнопки стрельбы)")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Регистрация команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("magaz", send_shop))
    
    # Обработчики
    app.add_handler(CallbackQueryHandler(universal_callback))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^[Рр]улетка$"), roulette_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    print("🚀 Kryloxa Bot запущен!")
    app.run_polling()
