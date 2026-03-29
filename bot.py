import os
import json
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

# --- КОНФИГ ---
TOKEN = "8641381095:AAGLY3W93LQGfq_Ygm1OIfAMwlhb6SlQrXE"
OWNER_ID = 5679520675 
FRIEND_ID = 782585931
RANKS_FILE = "ranks.json"

# --- ДАННЫЕ И СТАТИСТИКА ---
user_ranks = {}
warns = {}
roulette_games = {}
daily_stats = {}  # {user_id: {"name": str, "count": int}}
last_reset_day = datetime.now().day

def load_ranks():
    global user_ranks
    if os.path.exists(RANKS_FILE):
        try:
            with open(RANKS_FILE, "r") as f:
                data = json.load(f)
                user_ranks = {int(k): v for k, v in data.items()}
        except: pass
    user_ranks[OWNER_ID] = 4
    user_ranks[FRIEND_ID] = 3

def save_ranks():
    with open(RANKS_FILE, "w") as f:
        json.dump(user_ranks, f)

load_ranks()

def get_rank(user_id):
    if user_id == OWNER_ID: return 4
    if user_id == FRIEND_ID: return 3
    return user_ranks.get(user_id, 0)

# --- ВСПОМОГАТЕЛЬНЫЕ ---
def check_daily_reset():
    global last_reset_day, daily_stats
    current_day = datetime.now().day
    if current_day != last_reset_day:
        daily_stats = {}
        last_reset_day = current_day

def reload_chamber(g):
    live = random.randint(1, 4)
    g['chamber'] = [True] * live + [False] * (6 - live)
    random.shuffle(g['chamber'])
    g['info'] = f"Боевых: {live}, Холостых: {6 - live}"

# --- ОБРАБОТЧИК ТЕКСТА (ВКЛЮЧАЯ ТОП И ИНФУ) ---
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    
    check_daily_reset()
    text = update.message.text.strip().lower()
    user = update.effective_user
    
    # Считаем сообщение для топа
    if user.id not in daily_stats:
        daily_stats[user.id] = {"name": user.first_name, "count": 0}
    daily_stats[user.id]["count"] += 1

    # Команда ТП (Топ дня)
    if text == "тп":
        if not daily_stats:
            return await update.message.reply_text("Сегодня еще никто не писал!")
        
        # Сортируем по количеству сообщений
        top_list = sorted(daily_stats.items(), key=lambda x: x[1]["count"], reverse=True)[:10]
        
        message = "🏆 **Топ общительных за сегодня (ТП):**\n\n"
        for i, (uid, data) in enumerate(top_list, 1):
            medals = {1: "🥇", 2: "🥈", 3: "🥉"}
            prefix = medals.get(i, f"{i}.")
            message += f"{prefix} {data['name']} — {data['count']} сообщ.\n"
        
        await update.message.reply_text(message, parse_mode="Markdown")
        return

    # Команда ОБО МНЕ
    if text == "обо мне":
        rank = get_rank(user.id)
        w = warns.get(user.id, 0)
        msgs = daily_stats.get(user.id, {}).get("count", 0)
        await update.message.reply_text(f"👤 **О вас:**\nИмя: {user.first_name}\nID: `{user.id}`\n⭐ Ранг: {rank}\n⚠️ Варны: {w}/3\n✉️ Сообщений сегодня: {msgs}", parse_mode="Markdown")
        return

    # --- Команды ОТВЕТОМ ---
    msg = update.message.reply_to_message
    if not msg: return
    
    target_id = msg.from_user.id
    target_rank = get_rank(target_id)
    caller_rank = get_rank(user.id)
    cmd_parts = text.split()

    if text == "инфа":
        await update.message.reply_text(f"👤 Пользователь: {msg.from_user.first_name}\n⭐ Ранг: {target_rank}\n⚠️ Варны: {warns.get(target_id, 0)}/3")
        return

    # Модерация (Бан, Мут, Варн и т.д. — логика та же)
    if caller_rank < 1 or (target_rank >= caller_rank and user.id != OWNER_ID): return

    try:
        if cmd_parts[0] == "молчи":
            m = int(cmd_parts[1]) if len(cmd_parts) > 1 and cmd_parts[1].isdigit() else 60
            await context.bot.restrict_chat_member(update.effective_chat.id, target_id, permissions={"can_send_messages":False}, until_date=datetime.now()+timedelta(minutes=m))
            await update.message.reply_text(f"🔇 {msg.from_user.first_name} в муте на {m} мин.")
        elif cmd_parts[0] == "скажи":
            await context.bot.restrict_chat_member(update.effective_chat.id, target_id, permissions={"can_send_messages":True, "can_send_other_messages":True, "can_add_web_page_previews":True})
            await update.message.reply_text(f"🔊 {msg.from_user.first_name} размучен.")
        elif cmd_parts[0] == "бан":
            await context.bot.ban_chat_member(update.effective_chat.id, target_id)
            await update.message.reply_text(f"🚫 {msg.from_user.first_name} забанен.")
    except: pass

# --- РУЛЕТКА (БЕЗ ИЗМЕНЕНИЙ) ---
async def roulette_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.reply_to_message
    if not msg or update.effective_user.id == msg.from_user.id: return
    g_id = str(update.message.message_id)
    roulette_games[g_id] = {"p1": update.effective_user.id, "p1_n": update.effective_user.first_name, "p2": msg.from_user.id, "p2_n": msg.from_user.first_name, "lives": {update.effective_user.id: 2, msg.from_user.id: 2}, "turn": msg.from_user.id, "mode": None}
    reload_chamber(roulette_games[g_id])
    kb = [[InlineKeyboardButton("Варн", callback_data=f"set_warn_{g_id}"), InlineKeyboardButton("Мут (10м)", callback_data=f"set_mute_{g_id}"), InlineKeyboardButton("Бан (1д)", callback_data=f"set_ban_{g_id}")]]
    await update.message.reply_text(f"🎯 Дуэль! Выбирай ставку:", reply_markup=InlineKeyboardMarkup(kb))

async def roulette_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.split("_")
    if len(data) < 3: return
    action, val, g_id = data[0], data[1], data[2]
    if g_id not in roulette_games: return
    g = roulette_games[g_id]
    if query.from_user.id not in [g['p1'], g['p2']]: return await query.answer("Не твоя дуэль!", show_alert=True)
    
    if action == "set":
        g['mode'] = val
        await update_roulette_msg(query, g, g_id)
    elif action == "shoot":
        if query.from_user.id != g['turn']: return
        if not g['chamber']: reload_chamber(g)
        bullet = g['chamber'].pop(0)
        if bullet:
            g['lives'][query.from_user.id] -= 1
            res = "💥 БАХ!"
        else: res = "💨 Холостой!"
        
        if any(l <= 0 for l in g['lives'].values()):
            await query.edit_message_text(f"💀 Игра окончена! Проиграл тот, у кого 0 хп.")
            del roulette_games[g_id]
        else:
            g['turn'] = g['p2'] if g['turn'] == g['p1'] else g['p1']
            await update_roulette_msg(query, g, g_id, res)

async def update_roulette_msg(query, g, g_id, last=""):
    t_name = g['p1_n'] if g['turn'] == g['p1'] else g['p2_n']
    kb = [[InlineKeyboardButton("🎯 В противника", callback_data=f"shoot_opp_{g_id}"), InlineKeyboardButton("🔫 В себя", callback_data=f"shoot_self_{g_id}")]]
    await query.edit_message_text(f"{last}\n\n👤 {g['p1_n']}: {'❤️'*g['lives'][g['p1']]}\n👤 {g['p2_n']}: {'❤️'*g['lives'][g['p2']]}\n👉 Ходит: {t_name}", reply_markup=InlineKeyboardMarkup(kb))

# --- ЗАПУСК ---
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", lambda u, c: u.message.reply_text("Команды: Инфа, Обо мне, Рулетка, ТП")))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^[Рр]улетка$"), roulette_command))
    app.add_handler(CallbackQueryHandler(roulette_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.run_polling()
