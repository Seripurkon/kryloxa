import os
import json
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

# Данные
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
                ranks = {int(k): v for k, v in data.items()}
                ranks[OWNER_ID] = 4
                ranks[FRIEND_ID] = 3
                return ranks
        except: pass
    return {OWNER_ID: 4, FRIEND_ID: 3}

def save_ranks():
    with open(RANKS_FILE, "w") as f:
        json.dump(user_ranks, f)

user_ranks = load_ranks()
warns = {}
roulette_games = {}

def get_rank(user_id):
    return user_ranks.get(user_id, 0)

# ===================== Команды /start и /help =====================

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
        "📜 **Список доступных команд:**\n\n"
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

# ===================== Обработчик текста =====================

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

    if text.startswith("дать админку") and caller_rank >= 3:
        try:
            val = int(cmd_parts[2]) if len(cmd_parts)>2 else 1
            if val >= caller_rank and caller_id != OWNER_ID: return await update.message.reply_text("Ранг выше вашего!")
            user_ranks[target_id] = min(3, val); save_ranks()
            await update.message.reply_text(f"⭐ {msg.from_user.first_name} теперь ранг {user_ranks[target_id]}")
        except: pass
    elif text == "снять админку" and caller_rank >= 3:
        if target_id not in [OWNER_ID, FRIEND_ID]:
            user_ranks[target_id] = 0; save_ranks()
            await update.message.reply_text(f"❌ {msg.from_user.first_name} снят.")

    if caller_rank < 1 or (target_rank >= caller_rank and caller_id != OWNER_ID): return

    if cmd_parts[0] == "молчи":
        m = int(cmd_parts[1]) if len(cmd_parts)>1 and cmd_parts[1].isdigit() else 60
        await context.bot.restrict_chat_member(update.effective_chat.id, target_id, permissions={"can_send_messages":False}, until_date=datetime.now()+timedelta(minutes=m))
        await update.message.reply_text(f"🔇 {msg.from_user.first_name} в муте на {m} мин.")
    elif cmd_parts[0] == "скажи":
        await context.bot.restrict_chat_member(update.effective_chat.id, target_id, permissions={"can_send_messages":True, "can_send_other_messages":True, "can_add_web_page_previews":True})
        await update.message.reply_text(f"🔊 {msg.from_user.first_name} размучен.")
    elif cmd_parts[0] == "бан":
        d = int(cmd_parts[1]) if len(cmd_parts)>1 and cmd_parts[1].isdigit() else 1
        await context.bot.ban_chat_member(update.effective_chat.id, target_id, until_date=datetime.now()+timedelta(days=d))
        await update.message.reply_text(f"🚫 {msg.from_user.first_name} забанен на {d} дн.")

# ===================== РУЛЕТКА (ЗАЩИЩЕННАЯ) =====================

async def roulette_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.reply_to_message
    if not msg or update.effective_user.id == msg.from_user.id: return
    
    # Привязываем игру к ID сообщения, чтобы избежать путаницы
    game_id = f"{update.effective_chat.id}_{update.message.message_id}"
    roulette_games[game_id] = {
        "p1": update.effective_user.id, "p1_n": update.effective_user.first_name,
        "p2": msg.from_user.id, "p2_n": msg.from_user.first_name
    }
    
    keyboard = [[
        InlineKeyboardButton("Варн", callback_data=f"r_warn_{game_id}"),
        InlineKeyboardButton("Мут (10м)", callback_data=f"r_mute_{game_id}"),
        InlineKeyboardButton("Бан (1д)", callback_data=f"r_ban_{game_id}")
    ]]
    await update.message.reply_text(f"🎯 {msg.from_user.first_name}, дуэль от {update.effective_user.first_name}!\nВыберите наказание:", reply_markup=InlineKeyboardMarkup(keyboard))

async def roulette_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.split("_") # r, mode, chatid, msgid
    mode = data[1]
    game_id = f"{data[2]}_{data[3]}"
    
    if game_id not in roulette_games:
        return await query.answer("Игра устарела или не найдена.", show_alert=True)
    
    g = roulette_games[game_id]
    
    # ПРОВЕРКА: может нажать только участник
    if query.from_user.id not in [g['p1'], g['p2']]:
        return await query.answer("Это не ваша дуэль! 🚫", show_alert=True)
    
    await query.answer()
    chat_id = update.effective_chat.id
    fate = random.choice([True, False])
    loser_id = g['p2'] if fate else g['p1']
    loser_name = g['p2_n'] if fate else g['p1_n']
    
    result_text = f"💥 БАХ! {loser_name} проиграл! Наказание: {mode}\n"

    try:
        if mode == "mute":
            await context.bot.restrict_chat_member(chat_id, loser_id, permissions={"can_send_messages": False}, until_date=datetime.now() + timedelta(minutes=10))
        elif mode == "ban":
            await context.bot.ban_chat_member(chat_id, loser_id, until_date=datetime.now() + timedelta(days=1))
        elif mode == "warn":
            warns[loser_id] = warns.get(loser_id, 0) + 1
            if warns[loser_id] >= 3:
                warns[loser_id] = 0
                await context.bot.restrict_chat_member(chat_id, loser_id, permissions={"can_send_messages": False}, until_date=datetime.now() + timedelta(days=1))
                result_text += "🛑 3/3 варна! Мут на 1 день!"
            else:
                result_text += f"⚠️ Текущие варны: {warns[loser_id]}/3"
                
        await query.edit_message_text(result_text)
    except:
        await query.edit_message_text(f"💥 {loser_name} проиграл, но у бота нет прав.")
    
    if game_id in roulette_games: del roulette_games[game_id]

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^[Рр]улетка$"), roulette_command))
    app.add_handler(CallbackQueryHandler(roulette_callback, pattern="^r_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.run_polling()
