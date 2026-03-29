import os
import asyncio
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

# === ВСТАВЬ СВОЙ ТОКЕН НИЖЕ В КАВЫЧКАХ ===
TOKEN = "8641381095:AAGLY3W93LQGfq_Ygm1OIfAMwlhb6SlQrXE"

# Список ID админов (ЗАМЕНИ 123456789 НА СВОЙ ID)
admins = {5679520675} 

warns = {}
roulette_games = {}

def is_admin(user_id):
    return user_id in admins

# ===================== Команды Админки =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Бот готов к работе!\n"
        "Команды (ответом на сообщение):\n"
        "/mute [мин], /warn, /ban\n"
        "Для игры ответь пользователю словом 'Рулетка'."
    )

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    msg = update.message.reply_to_message
    if not msg: return await update.message.reply_text("Ответь на сообщение пользователя.")
    
    duration = int(context.args[0]) if context.args and context.args[0].isdigit() else 60
    until = datetime.now() + timedelta(minutes=duration)
    
    try:
        await context.bot.restrict_chat_member(update.effective_chat.id, msg.from_user.id, permissions={"can_send_messages": False}, until_date=until)
        await update.message.reply_text(f"🔇 {msg.from_user.first_name} замучен на {duration} мин.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    msg = update.message.reply_to_message
    if not msg: return
    
    user_id = msg.from_user.id
    warns[user_id] = warns.get(user_id, 0) + 1
    
    if warns[user_id] >= 3:
        warns[user_id] = 0
        until = datetime.now() + timedelta(minutes=30)
        await context.bot.restrict_chat_member(update.effective_chat.id, user_id, permissions={"can_send_messages": False}, until_date=until)
        await update.message.reply_text(f"⚠️ {msg.from_user.first_name} получил 3-й варн и мут на 30 мин.")
    else:
        await update.message.reply_text(f"⚠️ Предупреждение {msg.from_user.first_name}: {warns[user_id]}/3")

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    msg = update.message.reply_to_message
    if not msg: return
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, msg.from_user.id)
        await update.message.reply_text(f"🚫 {msg.from_user.first_name} забанен.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

# ===================== Русская Рулетка =====================

async def roulette_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.reply_to_message
    if not msg: return
    
    p1, p2 = update.effective_user, msg.from_user
    if p1.id == p2.id: return await update.message.reply_text("Нельзя играть с самим собой.")

    roulette_games[p2.id] = {
        "p1": p1.id, "p1_name": p1.first_name,
        "p2": p2.id, "p2_name": p2.first_name,
    }
    
    keyboard = [[
        InlineKeyboardButton("Варн", callback_data="r_warn"),
        InlineKeyboardButton("Мут (10м)", callback_data="r_mute")
    ]]
    await update.message.reply_text(
        f"🎮 {p2.first_name}, дуэль от {p1.first_name}!\nВыбери наказание для проигравшего:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def roulette_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in roulette_games:
        return await query.answer("Это не твой вызов!", show_alert=True)

    game = roulette_games[user_id]
    punishment = "варн" if query.data == "r_warn" else "мут"
    
    fate = random.choice([True, False]) 
    loser_id = game['p2'] if fate else game['p1']
    loser_name = game['p2_name'] if fate else game['p1_name']

    await query.edit_message_text(f"💥 БАХ! {loser_name} проиграл и получает {punishment}!")
    
    try:
        if query.data == "r_mute":
            until = datetime.now() + timedelta(minutes=10)
            await context.bot.restrict_chat_member(update.effective_chat.id, loser_id, permissions={"can_send_messages": False}, until_date=until)
        else:
            warns[loser_id] = warns.get(loser_id, 0) + 1
    except:
        await query.message.reply_text("⚠️ Не удалось применить наказание (бот не админ или цель — админ)")

    del roulette_games[user_id]

# ===================== Запуск =====================

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("warn", warn))
    app.add_handler(CommandHandler("ban", ban))
    # ИСПРАВЛЕННЫЙ ФЛАГ ТУТ:
    app.add_handler(MessageHandler(filters.REPLY & filters.Regex(r"(?i)^Рулетка$"), roulette_command))
    app.add_handler(CallbackQueryHandler(roulette_callback, pattern="^r_"))

    print("🚀 Бот запущен!")
    app.run_polling()
