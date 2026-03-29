import os
import json
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

# --- ДАННЫЕ ---
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

# --- ОБРАБОТЧИК ТЕКСТА ---
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    text = update.message.text.strip().lower()
    caller_id = update.effective_user.id
    caller_rank = get_rank(caller_id)

    if text == "обо мне":
        w_count = warns.get(caller_id, 0)
        await update.message.reply_text(f"👤 О вас:\nИмя: {update.effective_user.first_name}\nID: `{caller_id}`\n⭐ Ранг: {caller_rank}\n⚠️ Варны: {w_count}/3", parse_mode="Markdown")
        return

    msg = update.message.reply_to_message
    if not msg: return 
    target_id = msg.from_user.id
    target_rank = get_rank(target_id)
    cmd_parts = text.split()

    if text == "инфа":
        await update.message.reply_text(f"👤 Пользователь: {msg.from_user.first_name}\n⭐ Ранг: {target_rank}\n⚠️ Варны: {warns.get(target_id, 0)}/3")
        return

    # Логика выдачи админок и наказаний (сокращена для краткости)
    if text.startswith("дать админку") and caller_rank >= 3:
        try:
            val = int(cmd_parts[2]) if len(cmd_parts) > 2 else 1
            user_ranks[target_id] = min(3, val); save_ranks()
            await update.message.reply_text(f"⭐ {msg.from_user.first_name} ранг {val}")
        except: pass

# --- РУЛЕТКА ---
async def roulette_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.reply_to_message
    if not msg or update.effective_user.id == msg.from_user.id:
        return await update.message.reply_text("Ответь на сообщение противника!")
    
    p1, p2 = update.effective_user, msg.from_user
    # Используем уникальный ID игры
    g_id = str(update.message.message_id)
    
    live = random.randint(1, 4)
    chamber = [True] * live + [False] * (6 - live)
    random.shuffle(chamber)
    
    roulette_games[g_id] = {
        "p1": p1.id, "p1_n": p1.first_name,
        "p2": p2.id, "p2_n": p2.first_name,
        "lives": {p1.id: 2, p2.id: 2},
        "chamber": chamber,
        "turn": p2.id,
        "mode": None,
        "info": f"Боевых: {live}, Холостых: {6 - live}"
    }
    
    text = (
        f"⚠️ **ПРАВИЛА ДУЭЛИ** ⚠️\n"
        f"В дробовике 6 патронов ({roulette_games[g_id]['info']}).\n"
        f"У каждого игрока по **2 жизни ❤️**.\n"
        f"Стреляете по очереди. Выстрел боевым отнимает жизнь.\n"
        f"Проигрывает тот, кто первым потеряет обе жизни!\n\n"
        f"👊 {p2.first_name}, выбирай ставку:"
    )
    kb = [[
        InlineKeyboardButton("Варн", callback_data=f"set_warn_{g_id}"),
        InlineKeyboardButton("Мут (10м)", callback_data=f"set_mute_{g_id}"),
        InlineKeyboardButton("Бан (1д)", callback_data=f"set_ban_{g_id}")
    ]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def roulette_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.split("_")
    
    if len(data) < 3: return
    action, mode, g_id = data[0], data[1], data[2]
    
    if g_id not in roulette_games:
        return await query.answer("Игра не найдена или уже окончена.", show_alert=True)
    
    g = roulette_games[g_id]
    user_id = query.from_user.id

    # Только участники могут жать на кнопки
    if user_id not in [g['p1'], g['p2']]:
        return await query.answer("Это не ваша дуэль! 🚫", show_alert=True)

    if action == "set":
        if user_id != g['p2']:
            return await query.answer("Ставку выбирает тот, кого вызвали!", show_alert=True)
        g['mode'] = mode
        await update_roulette_msg(query, g, g_id)
    
    elif action == "shoot":
        if user_id != g['turn']:
            return await query.answer("Сейчас не твой ход!", show_alert=True)
        
        bullet = g['chamber'].pop(0)
        res = "💨 Холостой! Повезло..."
        if bullet:
            g['lives'][user_id] -= 1
            res = "💥 БАХ! Попадание!"
        
        if g['lives'][user_id] <= 0:
            await finish_roulette(query, g, user_id, context)
            if g_id in roulette_games: del roulette_games[g_id]
        else:
            g['turn'] = g['p2'] if g['turn'] == g['p1'] else g['p1']
            await update_roulette_msg(query, g, g_id, res)

async def update_roulette_msg(query, g, g_id, last=""):
    t_name = g['p1_n'] if g['turn'] == g['p1'] else g['p2_n']
    text = (
        f"{last}\n\n"
        f"👤 {g['p1_n']}: {'❤️' * g['lives'][g['p1']]}\n"
        f"👤 {g['p2_n']}: {'❤️' * g['lives'][g['p2']]}\n"
        f"🔋 Патронов в стволе: {len(g['chamber'])}\n\n"
        f"👉 Следующий выстрел: **{t_name}**"
    )
    kb = [[InlineKeyboardButton("🔥 ВЫСТРЕЛ", callback_data=f"shoot_0_{g_id}")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def finish_roulette(query, g, l_id, context):
    l_name = g['p1_n'] if l_id == g['p1'] else g['p2_n']
    mode = g['mode']
    txt = f"💀 **{l_name} ПОТЕРЯЛ ВСЕ ЖИЗНИ!**\nНаказание: {mode.capitalize()}"
    try:
        chat_id = query.message.chat_id
        if mode == "mute":
            await context.bot.restrict_chat_member(chat_id, l_id, permissions={"can_send_messages": False}, until_date=datetime.now() + timedelta(minutes=10))
        elif mode == "ban":
            await context.bot.ban_chat_member(chat_id, l_id, until_date=datetime.now() + timedelta(days=1))
        elif mode == "warn":
            warns[l_id] = warns.get(l_id, 0) + 1
            if warns[l_id] >= 3:
                warns[l_id] = 0
                await context.bot.restrict_chat_member(chat_id, l_id, permissions={"can_send_messages": False}, until_date=datetime.now() + timedelta(days=1))
                txt += "\n🛑 3/3 варна! Мут на 1 день!"
            else:
                txt += f"\n⚠️ Текущие варны: {warns[l_id]}/3"
    except:
        txt += "\n(Недостаточно прав для наказания)"
    await query.edit_message_text(txt, parse_mode="Markdown")

# --- ЗАПУСК ---
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^[Рр]улетка$"), roulette_command))
    app.add_handler(CallbackQueryHandler(roulette_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.run_polling()
