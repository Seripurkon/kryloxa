import os
import json
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

# --- ДАННЫЕ (ОСТАВЛЯЕМ ТВОИ) ---
TOKEN = "8641381095:AAGLY3W93LQGfq_Ygm1OIfAMwlhb6SlQrXE"
OWNER_ID = 5679520675 
FRIEND_ID = 782585931
RANKS_FILE = "ranks.json"

# Загрузка рангов
def load_ranks():
    if os.path.exists(RANKS_FILE):
        try:
            with open(RANKS_FILE, "r") as f:
                data = json.load(f)
                return {int(k): v for k, v in data.items()}
        except: pass
    return {OWNER_ID: 4, FRIEND_ID: 3}

def save_ranks():
    with open(RANKS_FILE, "w") as f:
        json.dump(user_ranks, f)

user_ranks = load_ranks()
warns = {}
roulette_games = {}

def get_rank(user_id):
    if user_id == OWNER_ID: return 4
    if user_id == FRIEND_ID: return 3
    return user_ranks.get(user_id, 0)

# --- ФУНКЦИЯ ПЕРЕЗАРЯДКИ ---
def reload_chamber(g):
    live = random.randint(1, 4)
    chamber = [True] * live + [False] * (6 - live)
    random.shuffle(chamber)
    g['chamber'] = chamber
    g['info'] = f"Боевых: {live}, Холостых: {6 - live}"

# --- КОМАНДЫ START / HELP / TEXT ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rank = get_rank(update.effective_user.id)
    await update.message.reply_text(f"Подпишитесь на @kryloxa_offcial 😊\n\n👤 Твой ранг: {rank}\nСписок команд - /help")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rank = get_rank(update.effective_user.id)
    text = "📜 **Команды:**\nИнфа, Обо мне, Рулетка\n"
    if rank >= 1: text += "Молчи, Скажи, Бан, Разбан, Варн\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    if text == "обо мне":
        r = get_rank(update.effective_user.id)
        w = warns.get(update.effective_user.id, 0)
        await update.message.reply_text(f"👤 Имя: {update.effective_user.first_name}\n⭐ Ранг: {r}\n⚠️ Варны: {w}/3")

# --- РУЛЕТКА ---
async def roulette_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.reply_to_message
    if not msg or update.effective_user.id == msg.from_user.id:
        return await update.message.reply_text("Ответь на сообщение противника!")
    
    g_id = str(update.message.message_id)
    p1, p2 = update.effective_user, msg.from_user
    
    roulette_games[g_id] = {
        "p1": p1.id, "p1_n": p1.first_name,
        "p2": p2.id, "p2_n": p2.first_name,
        "lives": {p1.id: 2, p2.id: 2},
        "turn": p2.id,
        "mode": None
    }
    reload_chamber(roulette_games[g_id])
    
    text = (
        f"⚠️ **ДУЭЛЬ** ⚠️\nВ дробовике 6 патронов ({roulette_games[g_id]['info']}).\n"
        f"У каждого по **2 ❤️**.\n"
        f"Выстрел в себя (холостой) = доп. ход.\n"
        f"👊 {p2.first_name}, выбирай ставку:"
    )
    kb = [[InlineKeyboardButton("Варн", callback_data=f"set_warn_{g_id}"),
           InlineKeyboardButton("Мут (10м)", callback_data=f"set_mute_{g_id}"),
           InlineKeyboardButton("Бан (1д)", callback_data=f"set_ban_{g_id}")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def roulette_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.split("_")
    action, val, g_id = data[0], data[1], data[2]
    
    if g_id not in roulette_games: return await query.answer("Игра окончена.")
    g = roulette_games[g_id]
    u_id = query.from_user.id

    if u_id not in [g['p1'], g['p2']]: return await query.answer("Не твоя дуэль!", show_alert=True)

    if action == "set":
        if u_id != g['p2']: return await query.answer("Выбирает тот, кого вызвали!")
        g['mode'] = val
        await update_msg(query, g, g_id)
    
    elif action == "mercy":
        await query.edit_message_text(f"🤝 {query.from_user.first_name} пощадил соперника. Игра окончена без крови!")
        del roulette_games[g_id]

    elif action == "shoot":
        if u_id != g['turn']: return await query.answer("Не твой ход!")
        
        bullet = g['chamber'].pop(0)
        target = val # 'self' или 'opp'
        res = ""

        if target == 'self':
            if bullet: # Боевой в себя
                g['lives'][u_id] -= 1
                res = "💥 БАХ! Ты попал в себя!"
                g['turn'] = g['p2'] if u_id == g['p1'] else g['p1']
            else: # Холостой в себя
                res = "💨 Холостой! У тебя дополнительный ход!"
        else: # В противника
            opp_id = g['p2'] if u_id == g['p1'] else g['p1']
            if bullet:
                g['lives'][opp_id] -= 1
                res = f"💥 БАХ! Попадание в противника!"
            else:
                res = "💨 Холостой... Обидный промах."
            g['turn'] = opp_id

        # Проверка смерти
        dead_id = next((uid for uid, l in g['lives'].items() if l <= 0), None)
        if dead_id:
            await finish_game(query, g, dead_id, context)
            del roulette_games[g_id]
        else:
            if not g['chamber']: 
                reload_chamber(g)
                res += "\n🔄 Патроны кончились. Перезарядка!"
            await update_msg(query, g, g_id, res)

async def update_msg(query, g, g_id, last=""):
    t_name = g['p1_n'] if g['turn'] == g['p1'] else g['p2_n']
    text = (f"{last}\n\n👤 {g['p1_n']}: {'❤️' * g['lives'][g['p1']]}\n👤 {g['p2_n']}: {'❤️' * g['lives'][g['p2']]}\n"
            f"🔋 В стволе: {len(g['chamber'])} ({g['info']})\n\n👉 Ходит: **{t_name}**")
    
    kb = [[InlineKeyboardButton("🎯 В противника", callback_data=f"shoot_opp_{g_id}"),
           InlineKeyboardButton("🔫 В себя", callback_data=f"shoot_self_{g_id}")]]
    
    # Кнопка пощады при 1/2 жизни
    if any(l == 1 for l in g['lives'].values()):
        kb.append([InlineKeyboardButton("🤝 Пощадить", callback_data=f"mercy_0_{g_id}")])
        
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def finish_game(query, g, l_id, context):
    l_name = g['p1_n'] if l_id == g['p1'] else g['p2_n']
    mode, txt = g['mode'], f"💀 **{l_name} ПОГИБ!**\nНаказание: {g['mode']}"
    try:
        if mode == "mute": await context.bot.restrict_chat_member(query.message.chat_id, l_id, permissions={"can_send_messages":False}, until_date=datetime.now()+timedelta(minutes=10))
        elif mode == "ban": await context.bot.ban_chat_member(query.message.chat_id, l_id, until_date=datetime.now()+timedelta(days=1))
        elif mode == "warn":
            warns[l_id] = warns.get(l_id, 0) + 1
            if warns[l_id] >= 3:
                warns[l_id] = 0
                await context.bot.restrict_chat_member(query.message.chat_id, l_id, permissions={"can_send_messages":False}, until_date=datetime.now()+timedelta(days=1))
                txt += "\n🛑 3/3 варна! Мут на 1 день!"
    except: txt += "\n(Нет прав)"
    await query.edit_message_text(txt, parse_mode="Markdown")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start)); app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^[Рр]улетка$"), roulette_command))
    app.add_handler(CallbackQueryHandler(roulette_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.run_polling()
