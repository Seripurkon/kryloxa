import os
import json
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Chat
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

# --- КОНФИГ ---
TOKEN = "8641381095:AAGLY3W93LQGfq_Ygm1OIfAMwlhb6SlQrXE"
OWNER_ID = 5679520675 
RANKS_FILE = "ranks.json"
ECONOMY_FILE = "economy.json"

# --- ХРАНИЛИЩЕ ---
def load_json(filename, default):
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {int(k): v for k, v in data.items()}
        except: return default
    return default

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

user_ranks = load_json(RANKS_FILE, {OWNER_ID: 4})
user_balance = load_json(ECONOMY_FILE, {})
warns = {}
roulette_games = {}
daily_stats = {} 
bonus_timers = {}
last_reset_day = datetime.now().day

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def get_rank(user_id):
    return user_ranks.get(user_id, 0)

def check_daily_reset():
    global last_reset_day, daily_stats
    if datetime.now().day != last_reset_day:
        daily_stats = {}
        last_reset_day = datetime.now().day

def reload_chamber(g):
    live = random.randint(1, 3)
    chamber = [True] * live + [False] * (6 - live)
    random.shuffle(chamber)
    g['chamber'] = chamber
    g['live_count'] = live
    g['blank_count'] = 6 - live

# --- КОМАНДЫ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 **Kryloxa Bot** запущен! Напиши /help для списка команд.", parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rank = get_rank(update.effective_user.id)
    text = (
        "📜 **Список доступных команд:**\n\n"
        "ℹ️ **Общие:**\n"
        "Инфа — статус игрока (ответом)\n"
        "Обо мне — инфо о себе\n"
        "ТП — топ общительных за день\n"
        "Рулетка — дуэль (ответом)\n"
        "Магазин (или /magaz) — лавка KLC\n\n"
        "🛠 **Модерация (ответом):**\n"
        "Молчи [время] — мут (напр. 1 час)\n"
        "Скажи — размут\n"
        "Бан [время] — бан (напр. 2 дня)\n"
        "Разбан — разбан\n"
        "Варн — предупреждение\n"
        "Снять варн — убрать предупреждение\n"
    )
    if rank >= 4:
        text += "\n⭐ **Админка:**\nДать админку [1-3] (ответом)\nСнять админку (ответом)"
    await update.message.reply_text(text, parse_mode="Markdown")

# --- ГЛАВНЫЙ ОБРАБОТЧИК ТЕКСТА ---
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    check_daily_reset()
    text = update.message.text.strip().lower()
    user = update.effective_user
    chat_id = update.effective_chat.id
    msg = update.message.reply_to_message

    # ТП (счётчик)
    if user.id not in daily_stats: daily_stats[user.id] = {"name": user.first_name, "count": 0}
    daily_stats[user.id]["count"] += 1

    # Простые команды
    if text in ["магазин", "/magaz"]:
        bal = user_balance.get(user.id, 0)
        kb = [[InlineKeyboardButton("🕊 Снять мут (1000 KLC)", callback_data=f"shop_mute_{user.id}"),
               InlineKeyboardButton("⚠️ Снять варн (500 KLC)", callback_data=f"shop_warn_{user.id}")]]
        return await update.message.reply_text(f"🛍 **Kryloxa Shop**\n💰 Баланс: `{bal}` KLC", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    if text == "бонус":
        now = datetime.now()
        if bonus_timers.get(user.id) and now < bonus_timers[user.id] + timedelta(days=1):
            return await update.message.reply_text("⏳ Бонус можно брать раз в сутки!")
        amt = random.randint(150, 500)
        user_balance[user.id] = user_balance.get(user.id, 0) + amt
        bonus_timers[user.id] = now
        save_json(ECONOMY_FILE, user_balance)
        return await update.message.reply_text(f"💰 +{amt} KLC! Баланс: {user_balance[user.id]}")

    if text in ["баланс", "б"]:
        return await update.message.reply_text(f"💰 Баланс: {user_balance.get(user.id, 0)} KLC")

    if text == "тп":
        top = sorted(daily_stats.items(), key=lambda x: x[1]["count"], reverse=True)[:10]
        res = "🏆 **Топ общительных за день:**\n" + "\n".join([f"{i+1}. {d['name']} — {d['count']}" for i, (uid, d) in enumerate(top)])
        return await update.message.reply_text(res, parse_mode="Markdown")

    if text == "обо мне":
        r = get_rank(user.id)
        return await update.message.reply_text(f"👤 {user.first_name}\n⭐ Ранг: {r}\n💰 Баланс: {user_balance.get(user.id, 0)}")

    # Команды ответом
    if msg:
        t_id = msg.from_user.id
        c_rank = get_rank(user.id)
        t_rank = get_rank(t_id)

        if text == "инфа":
            cm = await context.bot.get_chat_member(chat_id, t_id)
            st = "✅ Чист"
            if cm.status == 'restricted':
                st = f"🔇 В муте ({cm.until_date.strftime('%H:%M') if cm.until_date else 'навсегда'})"
            res = f"👤 {msg.from_user.first_name}\n⭐ Ранг: {t_rank}\n💰 Баланс: {user_balance.get(t_id, 0)}\n⚠️ Варны: {warns.get(t_id, 0)}/3\n📊 Статус: {st}"
            return await update.message.reply_text(res)

        if c_rank >= 1 and (t_rank < c_rank or user.id == OWNER_ID):
            if text.startswith("молчи"):
                await context.bot.restrict_chat_member(chat_id, t_id, permissions={"can_send_messages":False}, until_date=datetime.now()+timedelta(hours=1))
                await update.message.reply_text(f"🔇 {msg.from_user.first_name} замолчал.")
            elif text == "скажи":
                await context.bot.restrict_chat_member(chat_id, t_id, permissions={"can_send_messages":True, "can_send_other_messages":True, "can_add_web_page_previews":True})
                await update.message.reply_text(f"🔊 {msg.from_user.first_name} снова говорит.")
            elif text == "варн":
                warns[t_id] = warns.get(t_id, 0) + 1
                await update.message.reply_text(f"⚠️ Варн {msg.from_user.first_name}: {warns[t_id]}/3")
            elif text == "снять варн":
                warns[t_id] = max(0, warns.get(t_id, 0) - 1)
                await update.message.reply_text(f"✅ Варн снят. У {msg.from_user.first_name} теперь {warns[t_id]}/3")

        if user.id == OWNER_ID:
            if text.startswith("дать админку"):
                lvl = int(text.split()[-1]) if text.split()[-1].isdigit() else 1
                user_ranks[t_id] = lvl
                save_json(RANKS_FILE, user_ranks)
                await update.message.reply_text(f"⭐ {msg.from_user.first_name} теперь админ {lvl} ур.")
            elif text == "снять админку":
                if t_id in user_ranks: del user_ranks[t_id]
                save_json(RANKS_FILE, user_ranks)
                await update.message.reply_text(f"❌ Админка снята с {msg.from_user.first_name}")

# --- РУЛЕТКА ---
async def roulette_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.reply_to_message
    if not msg or update.effective_user.id == msg.from_user.id: return
    g_id = str(update.message.message_id)
    p1, p2 = update.effective_user, msg.from_user
    roulette_games[g_id] = {"p1": p1.id, "p1_n": p1.first_name, "p2": p2.id, "p2_n": p2.first_name, "lives": {p1.id: 2, p2.id: 2}, "turn": p2.id}
    reload_chamber(roulette_games[g_id])
    
    text = (f"👤 {p1.first_name}: ❤️❤️\n👤 {p2.first_name}: ❤️❤️\n🔋 Ствол: 6 (Боевых: {roulette_games[g_id]['live_count']})\n\n👉 Ходит: {p2.first_name}")
    kb = [[InlineKeyboardButton("🎯 В противника", callback_data=f"rt_opp_{g_id}"), InlineKeyboardButton("🔫 В себя", callback_data=f"rt_self_{g_id}")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))

async def rt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, action, g_id = query.data.split("_")
    if g_id not in roulette_games: return await query.answer("Игра окончена")
    g = roulette_games[g_id]
    if query.from_user.id != g['turn']: return await query.answer("Не твой ход!", show_alert=True)

    bullet = g['chamber'].pop(0)
    if bullet: g['live_count'] -= 1
    else: g['blank_count'] -= 1
    
    res_text = ""
    if action == "opp":
        opp = g['p2'] if g['turn'] == g['p1'] else g['p1']
        if bullet: g['lives'][opp] -= 1; res_text = "💥 БАХ! Попадание!"
        else: res_text = "💨 Холостой..."
        g['turn'] = opp
    elif action == "self":
        if bullet: g['lives'][g['turn']] -= 1; res_text = "💥 БАХ! Самострел..."; g['turn'] = g['p2'] if g['turn'] == g['p1'] else g['p1']
        else: res_text = "💨 Холостой! Доп. ход!"
    elif action == "mercy":
        await query.edit_message_text(f"🤝 {query.from_user.first_name} пощадил соперника."); del roulette_games[g_id]; return

    if any(l <= 0 for l in g['lives'].values()):
        winner = g['p1_n'] if g['lives'][g['p2']] <= 0 else g['p2_n']
        await query.edit_message_text(f"{res_text}\n\n🏆 Победил {winner}!"); del roulette_games[g_id]
    else:
        if not g['chamber']: reload_chamber(g)
        turn_name = g['p1_n'] if g['turn'] == g['p1'] else g['p2_n']
        text = (f"{res_text}\n\n👤 {g['p1_n']}: {'❤️' * g['lives'][g['p1']]}\n👤 {g['p2_n']}: {'❤️' * g['lives'][g['p2']]}\n"
                f"🔋 Ствол: {len(g['chamber'])} (Боевых: {g['live_count']}, Холостых: {g['blank_count']})\n\n👉 Ходит: {turn_name}")
        kb = [[InlineKeyboardButton("🎯 В противника", callback_data=f"rt_opp_{g_id}"), InlineKeyboardButton("🔫 В себя", callback_data=f"rt_self_{g_id}")]]
        if 1 in g['lives'].values(): kb.append([InlineKeyboardButton("🤝 Пощадить", callback_data=f"rt_mercy_{g_id}")])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

# --- ЗАПУСК ---
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(rt_callback, pattern="^rt_"))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^[Рр]улетка$"), roulette_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    print("🚀 Бот запущен!")
    app.run_polling()
