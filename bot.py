import os
import json
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

# Данные
TOKEN = "8641381095:AAGLY3W93LQGfq_Ygm1OIfAMwlhb6SlQrXE"
OWNER_ID = 5679520675 
RANKS_FILE = "ranks.json"

# Загрузка рангов из файла
def load_ranks():
    if os.path.exists(RANKS_FILE):
        with open(RANKS_FILE, "r") as f:
            data = json.load(f)
            return {int(k): v for k, v in data.items()}
    return {OWNER_ID: 4}

# Сохранение рангов в файл
def save_ranks():
    with open(RANKS_FILE, "w") as f:
        json.dump(user_ranks, f)

user_ranks = load_ranks()
warns = {}
roulette_games = {}

def get_rank(user_id):
    return user_ranks.get(user_id, 0)

# ===================== Обработчик текстовых команд =====================

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    
    text = update.message.text.strip().lower()
    msg = update.message.reply_to_message
    caller_id = update.effective_user.id
    caller_rank = get_rank(caller_id)
    
    if not msg: return 
    
    target_id = msg.from_user.id
    target_rank = get_rank(target_id)
    cmd_parts = text.split()
    
    # --- УПРАВЛЕНИЕ АДМИНКАМИ ---
    if text.startswith("дать админку") and caller_rank >= 3:
        try:
            new_rank = int(cmd_parts[2]) if len(cmd_parts) > 2 and cmd_parts[2].isdigit() else 1
            if new_rank >= caller_rank and caller_id != OWNER_ID:
                return await update.message.reply_text("Нельзя дать ранг выше своего!")
            user_ranks[target_id] = min(3, new_rank)
            save_ranks() # Сохраняем в файл
            await update.message.reply_text(f"⭐ {msg.from_user.first_name} теперь ранг {user_ranks[target_id]}")
        except: pass
        return

    elif text == "снять админку" and caller_rank >= 3:
        if target_rank >= caller_rank and caller_id != OWNER_ID:
            return await update.message.reply_text("Недостаточно прав.")
        if target_id in user_ranks: 
            del user_ranks[target_id]
            save_ranks() # Сохраняем в файл
        await update.message.reply_text(f"❌ {msg.from_user.first_name} больше не админ.")
        return

    # --- НАКАЗАНИЯ ---
    if caller_rank < 1: return 
    if target_rank >= caller_rank and caller_id != OWNER_ID:
        return await update.message.reply_text("🛡️ Этот пользователь защищен рангом.")

    if cmd_parts[0] == "молчи":
        mins = int(cmd_parts[1]) if len(cmd_parts) > 1 and cmd_parts[1].isdigit() else 60
        until = datetime.now() + timedelta(minutes=max(1, min(525600, mins)))
        await context.bot.restrict_chat_member(update.effective_chat.id, target_id, permissions={"can_send_messages": False}, until_date=until)
        await update.message.reply_text(f"🔇 {msg.from_user.first_name} замолчал на {mins} мин.")

    elif cmd_parts[0] == "скажи":
        await context.bot.restrict_chat_member(update.effective_chat.id, target_id, permissions={"can_send_messages": True, "can_send_polls": True, "can_send_other_messages": True, "can_add_web_page_previews": True})
        await update.message.reply_text(f"🔊 {msg.from_user.first_name} размучен.")

    elif cmd_parts[0] == "бан":
        days = int(cmd_parts[1]) if len(cmd_parts) > 1 and cmd_parts[1].isdigit() else 1
        until = datetime.now() + timedelta(days=max(1, min(365, days)))
        await context.bot.ban_chat_member(update.effective_chat.id, target_id, until_date=until)
        await update.message.reply_text(f"🚫 {msg.from_user.first_name} забанен на {days} дн.")

    elif cmd_parts[0] == "разбан":
        await context.bot.unban_chat_member(update.effective_chat.id, target_id, only_if_banned=True)
        await update.message.reply_text(f"✅ {msg.from_user.first_name} разбанен.")

    elif cmd_parts[0] == "варн":
        warns[target_id] = warns.get(target_id, 0) + 1
        if warns[target_id] >= 3:
            warns[target_id] = 0
            await context.bot.restrict_chat_member(update.effective_chat.id, target_id, permissions={"can_send_messages": False}, until_date=datetime.now() + timedelta(minutes=30))
            await update.message.reply_text(f"⚠️ 3/3 варна! {msg.from_user.first_name} в муте на 30м.")
        else:
            await update.message.reply_text(f"⚠️ Варн {msg.from_user.first_name}: {warns[target_id]}/3")

    elif text.startswith("снять варн"):
        warns[target_id] = max(0, warns.get(target_id, 0) - 1)
        await update.message.reply_text(f"✅ Варн снят. У {msg.from_user.first_name} теперь {warns[target_id]}/3")

# ===================== Команды помощи =====================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rank = get_rank(update.effective_user.id)
    text = (
        "Подпишитесь на новостной канал бота и следите за его разработкой😊\n\n"
        f"👤 Твой ранг: {rank}\n\n"
        "Список команд (ответом на сообщение):\n"
        "• Молчи [мин] / Скажи\n"
        "• Бан [дн] / Разбан\n"
        "• Варн / Снять варн\n"
    )
    if rank >= 3:
        text += "⭐ Дать админку [1-3] / Снять админку\n"
    
    text += "\n🎮 Напиши Рулетка для дуэли"
    await update.message.reply_text(text)

async def roulette_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.reply_to_message
    if not msg or update.effective_user.id == msg.from_user.id: return
    roulette_games[msg.from_user.id] = {"p1": update.effective_user.id, "p1_n": update.effective_user.first_name, "p2": msg.from_user.id, "p2_n": msg.from_user.first_name}
    keyboard = [[InlineKeyboardButton("Варн", callback_data="r_warn"), InlineKeyboardButton("Мут", callback_data="r_mute"), InlineKeyboardButton("Бан (1д)", callback_data="r_ban")]]
    await update.message.reply_text(f"🎮 {msg.from_user.first_name}, дуэль от {update.effective_user.first_name}!", reply_markup=InlineKeyboardMarkup(keyboard))

async def roulette_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id not in roulette_games: return await query.answer("Не твоя игра!", show_alert=True)
    g = roulette_games[query.from_user.id]
    mode = query.data.replace("r_", "")
    fate = random.choice([True, False])
    l_id = g['p2'] if fate else g['p1']
    l_n = g['p2_n'] if fate else g['p1_n']
    await query.edit_message_text(f"💥 БАХ! {l_n} проиграл и получает {mode}!")
    try:
        if mode == "mute": await context.bot.restrict_chat_member(update.effective_chat.id, l_id, permissions={"can_send_messages": False}, until_date=datetime.now() + timedelta(minutes=10))
        elif mode == "ban": await context.bot.ban_chat_member(update.effective_chat.id, l_id, until_date=datetime.now() + timedelta(days=1))
        else: warns[l_id] = warns.get(l_id, 0) + 1
    except: pass
    del roulette_games[query.from_user.id]

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", help_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.REPLY & filters.Regex(r"(?i)^Рулетка$"), roulette_command))
    app.add_handler(CallbackQueryHandler(roulette_callback, pattern="^r_"))
    app.add_handler(MessageHandler(filters.REPLY & filters.TEXT & ~filters.COMMAND, text_handler))
    app.run_polling()
