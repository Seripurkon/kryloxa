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

# ===================== Команда /start =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rank = get_rank(update.effective_user.id)
    text = (
        "Подпишитесь на новостной канал бота и следите за его разработкой @kryloxa_offcial 😊\n\n"
        f"👤 Твой ранг: {rank}\n\n"
        "Список команд - /help"
    )
    await update.message.reply_text(text)

# ===================== Команда /help =====================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rank = get_rank(update.effective_user.id)
    text = (
        "📜 **Список доступных команд:**\n\n"
        "ℹ️ **Общие:**\n"
        "Инфа — узнать статус игрока (ответом)\n"
        "Обо мне — информация о себе\n"
        "Рулетка — начать дуэль (ответом)\n\n"
    )
    
    if rank >= 1:
        text += (
            "🛠 **Модерация (ответом):**\n"
            "Молчи [мин] — мут\n"
            "Скажи — размут\n"
            "Бан [дн] — забанить\n"
            "Разбан — разбанить\n"
            "Варн — выдать пред\n"
            "Снять варн — убрать пред\n\n"
        )
        
    if rank >= 3:
        text += (
            "⭐ **Администрирование:**\n"
            "Дать админку [1-3] — выдать ранг\n"
            "Снять админку — убрать ранг\n"
        )
    
    await update.message.reply_text(text, parse_mode="Markdown")

# ===================== Обработчик текста =====================

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    
    text = update.message.text.strip().lower()
    caller_id = update.effective_user.id
    caller_rank = get_rank(caller_id)

    # --- Команда ОБО МНЕ ---
    if text == "обо мне":
        w_count = warns.get(caller_id, 0)
        status_text = (
            f"👤 О вас:\n"
            f"Имя: {update.effective_user.first_name}\n"
            f"ID: `{caller_id}`\n"
            f"⭐ Ваш ранг: {caller_rank}\n"
            f"⚠️ Варны: {w_count}/3"
        )
        await update.message.reply_text(status_text, parse_mode="Markdown")
        return

    msg = update.message.reply_to_message
    if not msg: return 
    
    target_id = msg.from_user.id
    target_rank = get_rank(target_id)
    cmd_parts = text.split()

    # --- ИНФА ---
    if text == "инфа":
        status_text = (
            f"👤 Пользователь: {msg.from_user.first_name}\n"
            f"⭐ Ранг: {target_rank}\n"
            f"⚠️ Варны: {warns.get(target_id, 0)}/3"
        )
        await update.message.reply_text(status_text)
        return

    # --- УПРАВЛЕНИЕ АДМИНКАМИ ---
    if text.startswith("дать админку") and caller_rank >= 3:
        try:
            new_rank = int(cmd_parts[2]) if len(cmd_parts) > 2 and cmd_parts[2].isdigit() else 1
            if new_rank >= caller_rank and caller_id != OWNER_ID:
                return await update.message.reply_text("Нельзя дать ранг выше своего!")
            user_ranks[target_id] = min(3, new_rank)
            save_ranks()
            await update.message.reply_text(f"⭐ {msg.from_user.first_name} теперь ранг {user_ranks[target_id]}")
        except: pass
        return

    elif text == "снять админку" and caller_rank >= 3:
        if target_id in [OWNER_ID, FRIEND_ID]: return
        if target_id in user_ranks: del user_ranks[target_id]
        save_ranks()
        await update.message.reply_text(f"❌ {msg.from_user.first_name} больше не админ.")
        return

    # --- НАКАЗАНИЯ ---
    if caller_rank < 1 or (target_rank >= caller_rank and caller_id != OWNER_ID): return

    if cmd_parts[0] == "молчи":
        mins = int(cmd_parts[1]) if len(cmd_parts) > 1 and cmd_parts[1].isdigit() else 60
        until = datetime.now() + timedelta(minutes=mins)
        await context.bot.restrict_chat_member(update.effective_chat.id, target_id, permissions={"can_send_messages": False}, until_date=until)
        await update.message.reply_text(f"🔇 {msg.from_user.first_name} в муте на {mins} мин.")

    elif cmd_parts[0] == "скажи":
        await context.bot.restrict_chat_member(update.effective_chat.id, target_id, permissions={"can_send_messages": True, "can_send_other_messages": True, "can_add_web_page_previews": True})
        await update.message.reply_text(f"🔊 {msg.from_user.first_name} размучен.")

# ===================== РУЛЕТКА И ЗАПУСК =====================

async def roulette_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.reply_to_message
    if not msg or update.effective_user.id == msg.from_user.id: return
    roulette_games[msg.from_user.id] = {"p1": update.effective_user.id, "p1_n": update.effective_user.first_name, "p2": msg.from_user.id, "p2_n": msg.from_user.first_name}
    keyboard = [[InlineKeyboardButton("Варн", callback_data="r_warn"), InlineKeyboardButton("Мут", callback_data="r_mute")]]
    await update.message.reply_text(f"🎯 {msg.from_user.first_name}, дуэль от {update.effective_user.first_name}!", reply_markup=InlineKeyboardMarkup(keyboard))

async def roulette_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id not in roulette_games: return
    g = roulette_games[query.from_user.id]
    fate = random.choice([True, False])
    loser_n = g['p2_n'] if fate else g['p1_n']
    await query.edit_message_text(f"💥 БАХ! {loser_n} проиграл!")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^[Рр]улетка$"), roulette_command))
    app.add_handler(CallbackQueryHandler(roulette_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    print("🚀 Бот запущен!")
    app.run_polling()
