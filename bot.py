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

# --- СИСТЕМА РАНГОВ ---
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

def reload_chamber(g):
    live = random.randint(1, 4)
    chamber = [True] * live + [False] * (6 - live)
    random.shuffle(chamber)
    g['chamber'] = chamber
    g['info'] = f"Боевых: {live}, Холостых: {6 - live}"

# --- КОМАНДЫ /START И /HELP ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rank = get_rank(update.effective_user.id)
    text = (
        "Подпишитесь на новостной канал бота и следите за его разработкой @kryloxa_offcial 😊\n\n"
        f"👤 Твой ранг: {rank}\n\n"
        "Список команд - /help"
    )
    await update.message.reply_text(text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rank = get_rank(update.effective_user.id)
    text = (
        "📜 **Список команд:**\n\n"
        "ℹ️ **Общие:**\n"
        "Инфа — статус игрока (ответом)\n"
        "Обо мне — инфо о себе\n"
        "Рулетка — дуэль (ответом)\n\n"
    )
    if rank >= 1:
        text += "🛠 **Модерация (ответом):**\nМолчи [мин] / Скажи\nБан [дн] / Разбан\nВарн / Снять варн\n\n"
    if rank >= 3:
        text += "⭐ **Админка:**\nДать админку [1-3] / Снять админку\n"
    await update.message.reply_text(text, parse_mode="Markdown")

# --- ГЛАВНЫЙ ОБРАБОТЧИК ТЕКСТА ---
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    text = update.message.text.strip().lower()
    caller_id = update.effective_user.id
    caller_rank = get_rank(caller_id)

    # Команда ОБО МНЕ
    if text == "обо мне":
        w_count = warns.get(caller_id, 0)
        await update.message.reply_text(f"👤 О вас:\nИмя: {update.effective_user.first_name}\nID: `{caller_id}`\n⭐ Ранг: {caller_rank}\n⚠️ Варны: {w_count}/3", parse_mode="Markdown")
        return

    msg = update.message.reply_to_message
    if not msg: return 
    
    target_id = msg.from_user.id
    target_rank = get_rank(target_id)
    cmd_parts = text.split()

    # Команда ИНФА
    if text == "инфа":
        await update.message.reply_text(f"👤 Пользователь: {msg.from_user.first_name}\n⭐ Ранг: {target_rank}\n⚠️ Варны: {warns.get(target_id, 0)}/3")
        return

    # УПРАВЛЕНИЕ АДМИНКАМИ (Ранг 3+)
    if text.startswith("дать админку") and caller_rank >= 3:
        try:
            val = int(cmd_parts[2]) if len(cmd_parts) > 2 else 1
            if val >= caller_rank and caller_id != OWNER_ID: return await update.message.reply_text("Ранг выше вашего!")
            user_ranks[target_id] = min(3, val); save_ranks()
            await update.message.reply_text(f"⭐ {msg.from_user.first_name} теперь ранг {user_ranks[target_id]}")
        except: pass
        return
    elif text == "снять админку" and caller_rank >= 3:
        if target_id in [OWNER_ID, FRIEND_ID]: return
        if target_id in user_ranks: del user_ranks[target_id]
        save_ranks()
        await update.message.reply_text(f"❌ {msg.from_user.first_name} снят.")
        return

    # НАКАЗАНИЯ (Ранг 1+)
    if caller_rank < 1 or (target_rank >= caller_rank and caller_id != OWNER_ID): return

    try:
        if cmd_parts[0] == "молчи":
            m = int(cmd_parts[1]) if len(cmd_parts) > 1 and cmd_parts[1].isdigit() else 60
            await context.bot.restrict_chat_member(update.effective_chat.id, target_id, permissions={"can_send_messages":False}, until_date=datetime.now()+timedelta(minutes=m))
            await update.message.reply_text(f"🔇 {msg.from_user.first_name} в муте на {m} мин.")
        elif cmd_parts[0] == "скажи":
            await context.bot.restrict_chat_member(update.effective_chat.id, target_id, permissions={"can_send_messages":True, "can_send_other_messages":True, "can_add_web_page_previews":True})
            await update.message.reply_text(f"🔊 {msg.from_user.first_name} размучен.")
        elif cmd_parts[0] == "бан":
            d = int(cmd_parts[1]) if len(cmd_parts) > 1 and cmd_parts[1].isdigit() else 1
            await context.bot.ban_chat_member(update.effective_chat.id, target_id, until_date=datetime.now()+timedelta(days=d))
            await update.message.reply_text(f"🚫 {msg.from_user.first_name} забанен на {d} дн.")
        elif cmd_parts[0] == "разбан":
            await context.bot.unban_chat_member(update.effective_chat.id, target_id, only_if_banned=True)
            await update.message.reply_text(f"✅ {msg.from_user.first_name} разбанен.")
        elif cmd_parts[0] == "варн":
            warns[target_id] = warns.get(target_id, 0) + 1
            if warns[target_id] >= 3:
                warns[target_id] = 0
                await context.bot.restrict_chat_member(update.effective_chat.id, target_id, permissions={"can_send_messages":False}, until_date=datetime.now()+timedelta(minutes=30))
                await update.message.reply_text(f"🛑 3/3 варна! {msg.from_user.first_name} в муте на 30м.")
            else:
                await update.message.reply_text(f"⚠️ Варн {msg.from_user.first_name}: {warns[target_id]}/3")
        elif text == "снять варн":
            warns[target_id] = max(0, warns.get(target_id, 0) - 1)
            await update.message.reply_text(f"✅ Варн снят. Теперь {warns[target_id]}/3")
    except: pass

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
        f"⚠️ **ДУЭЛЬ** ⚠️\nВ барабане 6 патронов ({roulette_games[g_id]['info']}).\n"
        f"У каждого по **2 ❤️**.\n"
        f"Выстрел в себя (холостой) = доп. ход.\n\n"
        f"👊 {p2.first_name}, выбирай ставку:"
    )
    kb = [[InlineKeyboardButton("Варн", callback_data=f"set_warn_{g_id}"),
           InlineKeyboardButton("Мут (10м)", callback_data=f"set_mute_{g_id}"),
           InlineKeyboardButton("Бан (1д)", callback_data=f"set_ban_{g_id}")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def roulette_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.split("_")
    if len(data) < 3: return
    action, val, g_id = data[0], data[1], data[2]
    
    if g_id not in roulette_games: return await query.answer("Игра окончена.")
    g = roulette_games[g_id]
    u_id = query.from_user.id
    if u_id not in [g['p1'], g['p2']]: return await query.answer("Это не ваша дуэль!", show_alert=True)

    if action == "set":
        if u_id != g['p2']: return await query.answer("Выбирает тот, кого вызвали!")
        g['mode'] = val
        await update_roulette_msg(query, g, g_id)
    
    elif action == "mercy":
        await query.edit_message_text(f"🤝 {query.from_user.first_name} пощадил соперника. Игра завершена!")
        del roulette_games[g_id]

    elif action == "shoot":
        if u_id != g['turn']: return await query.answer("Не твой ход!")
        if not g['chamber']: reload_chamber(g)

        bullet = g['chamber'].pop(0)
        target = val # 'self' или 'opp'
        res = ""

        if target == 'self':
            if bullet:
                g['lives'][u_id] -= 1
                res = "💥 БАХ! Попал в себя!"
                g['turn'] = g['p2'] if u_id == g['p1'] else g['p1']
            else:
                res = "💨 Холостой! Доп. ход!"
        else:
            opp_id = g['p2'] if u_id == g['p1'] else g['p1']
            if bullet:
                g['lives'][opp_id] -= 1
                res = f"💥 БАХ! Попадание в противника!"
            else:
                res = "💨 Холостой... Промах."
            g['turn'] = opp_id

        if any(l <= 0 for l in g['lives'].values()):
            dead_id = next(uid for uid, l in g['lives'].items() if l <= 0)
            await finish_roulette(query, g, dead_id, context)
            if g_id in roulette_games: del roulette_games[g_id]
        else:
            if not g['chamber']: 
                reload_chamber(g)
                res += "\n🔄 Перезарядка!"
            await update_roulette_msg(query, g, g_id, res)

async def update_roulette_msg(query, g, g_id, last=""):
    t_name = g['p1_n'] if g['turn'] == g['p1'] else g['p2_n']
    text = (f"{last}\n\n👤 {g['p1_n']}: {'❤️' * g['lives'][g['p1']]}\n👤 {g['p2_n']}: {'❤️' * g['lives'][g['p2']]}\n"
            f"🔋 Ствол: {len(g['chamber'])} ({g['info']})\n\n👉 Ходит: **{t_name}**")
    
    kb = [[InlineKeyboardButton("🎯 В противника", callback_data=f"shoot_opp_{g_id}"),
           InlineKeyboardButton("🔫 В себя", callback_data=f"shoot_self_{g_id}")]]
    if any(l == 1 for l in g['lives'].values()):
        kb.append([InlineKeyboardButton("🤝 Пощадить", callback_data=f"mercy_0_{g_id}")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def finish_roulette(query, g, l_id, context):
    l_name = g['p1_n'] if l_id == g['p1'] else g['p2_n']
    mode, txt = g['mode'], f"💀 **{l_name} ПОГИБ!**\nНаказание: {g['mode'].capitalize()}"
    try:
        chat_id = query.message.chat_id
        if mode == "mute": await context.bot.restrict_chat_member(chat_id, l_id, permissions={"can_send_messages":False}, until_date=datetime.now()+timedelta(minutes=10))
        elif mode == "ban": await context.bot.ban_chat_member(chat_id, l_id, until_date=datetime.now()+timedelta(days=1))
        elif mode == "warn":
            warns[l_id] = warns.get(l_id, 0) + 1
            if warns[l_id] >= 3:
                warns[l_id] = 0
                await context.bot.restrict_chat_member(chat_id, l_id, permissions={"can_send_messages":False}, until_date=datetime.now()+timedelta(days=1))
                txt += "\n🛑 3/3 варна! Мут на 1 день!"
    except: txt += "\n(Нет прав на наказание)"
    await query.edit_message_text(txt, parse_mode="Markdown")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^[Рр]улетка$"), roulette_command))
    app.add_handler(CallbackQueryHandler(roulette_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    print("🚀 Бот запущен!")
    app.run_polling()
