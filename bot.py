import os
import asyncio
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

# Загружаем переменные из .env файла
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

# Список ID админов (добавь сюда свой ID цифрами, чтобы команды работали)
admins = {5679520675} 

punishments = {}
warns = {}
roulette_games = {}

def is_admin(user_id):
    return user_id in admins

# ===================== Команды Админки =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот для администрирования.\n"
        "Команды (ответом на сообщение):\n"
        "/mute [минуты]\n"
        "/warn\n"
        "/ban\n"
        "/unmute, /unwarn, /unban\n"
        "Напиши 'Рулетка' ответом на сообщение для игры."
    )

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    msg = update.message.reply_to_message
    if not msg: return await update.message.reply_text("Ответьте на сообщение.")
    
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
    if not msg:
        return await update.message.reply_text("Ответьте на сообщение оппонента словом 'Рулетка'")
    
    p1, p2 = update.effective_user, msg.from_user
    if p1.id == p2.id:
        return await update.message.reply_text("Нельзя играть с самим собой!")

    roulette_games[p2.id] = {
        "p1": p1.id, "p1_name": p1.first_name,
        "p2": p2.id, "p2_name": p2.first_name,
        "bullets": sorted([random.randint(0, 5) for _ in range(2)]), # 2 случайных патрона
        "current_step": 0
    }
    
    keyboard = [[
        InlineKeyboardButton("Варн", callback_data="r_warn"),
        InlineKeyboardButton("Мут (10м)", callback_data="r_mute")
    ]]
    await update.message.reply_text(
        f"🎮 {p2.first_name}, вызываю тебя на дуэль!\nВыбери наказание для проигравшего:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def roulette_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id

    if user_id not in roulette_games:
        return await query.answer("Эта игра не для тебя или уже закончена.", show_alert=True)

    game = roulette_games[user_id]
    punishment = "варн" if data == "r_warn" else "мут"
    
    # Имитация выстрелов
    fate = random.choice([True, False]) # Упрощенный шанс 50/50 для быстроты
    winner = game['p1_name'] if fate else game['p2_name']
    loser_id = game['p2'] if fate else game['p1']
    loser_name = game['p2_name'] if fate else game['p1_name']

    await query.edit_message_text(f"💥 БАХ! {loser_name} проиграл. Наказание: {punishment}")
    
    try:
        if data == "r_mute":
            until = datetime.now() + timedelta(minutes=10)
            await context.bot.restrict_chat_member(update.effective_chat.id, loser_id, permissions={"can_send_messages": False}, until_date=until)
        else:
            warns[loser_id] = warns.get(loser_id, 0) + 1
    except:
        await query.message.reply_text("Не удалось применить наказание (бот не админ или цель — админ)")

    del roulette_games[user_id]

# ===================== Запуск =====================

if __name__ == "__main__":
    if not TOKEN:
        print("ОШИБКА: Токен не найден! Проверь переменную bot_token")
        exit(1)

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("warn", warn))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(MessageHandler(filters.REPLY & filters.Regex(r"^(?i)Рулетка$"), roulette_command))
    app.add_handler(CallbackQueryHandler(roulette_callback, pattern="^r_"))

    print("🚀 Бот запущен...")
    app.run_polling()
