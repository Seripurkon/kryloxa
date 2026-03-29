import os
import asyncio
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

# Получаем токен из переменных окружения BotHost
TOKEN = os.getenv("BOT_TOKEN")

# Проверка наличия токена
if not TOKEN:
    print("❌ ОШИБКА: Переменная BOT_TOKEN не найдена в настройках BotHost!")

# Хранилища данных
admins = set()
punishments = {}
warns = {}
roulette_games = {}

# ===================== Команды Админки =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Бот запущен и готов к работе!\n"
        "Доступные команды: /mute, /warn, /ban, /unmute, /unwarn, /unban\n"
        "Для игры напишите слово: Рулетка"
    )

def is_admin(user_id):
    return user_id in admins

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    msg = update.message.reply_to_message
    if not msg: return
    user = msg.from_user
    duration = int(context.args[0]) if context.args and context.args[0].isdigit() else 60
    punishments[user.id] = ("mute", datetime.now() + timedelta(minutes=duration))
    await update.message.reply_text(f"🔇 {user.username} замучен на {duration} мин.")

async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    msg = update.message.reply_to_message
    if not msg: return
    user = msg.from_user
    warns[user.id] = warns.get(user.id, 0) + 1
    if warns[user.id] >= 3:
        punishments[user.id] = ("mute", datetime.now() + timedelta(minutes=30))
        warns[user.id] = 0
        await update.message.reply_text(f"🛑 {user.username} получил 3 варна -> Мут 30 мин.")
    else:
        await update.message.reply_text(f"⚠️ Предупреждение {user.username}: {warns[user.id]}/3")

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    msg = update.message.reply_to_message
    if not msg: return
    punishments[msg.from_user.id] = ("ban", datetime.now() + timedelta(days=1))
    await update.message.reply_text(f"🔨 {msg.from_user.username} забанен.")

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    msg = update.message.reply_to_message
    if not msg: return
    if punishments.get(msg.from_user.id, (None,))[0] == "mute":
        del punishments[msg.from_user.id]
        await update.message.reply_text(f"🔊 {msg.from_user.username} размучен.")

# ===================== Русская Рулетка =====================

async def roulette_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.reply_to_message
    if not msg:
        return await update.message.reply_text("Ответьте на сообщение игрока, чтобы начать!")
    
    p1, p2 = update.effective_user, msg.from_user
    roulette_games[p1.id] = {"p2": p2.id, "state": "bet"}
    
    keyboard = [[
        InlineKeyboardButton("Варн", callback_data="r_warn"),
        InlineKeyboardButton("Мут", callback_data="r_mute"),
        InlineKeyboardButton("Бан", callback_data="r_ban")
    ]]
    await update.message.reply_text(
        f"🎯 {p2.username}, вас вызвал на дуэль {p1.username}!\nВыберите наказание для проигравшего:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def roulette_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # Простая имитация выстрела для теста
    result = random.choice(["Выстрел! 💥", "Осечка... 💨"])
    await query.edit_message_text(f"Результат дуэли: {result}")

# ===================== Основной цикл =====================

if __name__ == "__main__":
    if TOKEN:
        app = ApplicationBuilder().token(TOKEN).build()
        
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("mute", mute))
        app.add_handler(CommandHandler("warn", warn))
        app.add_handler(CommandHandler("ban", ban))
        app.add_handler(CommandHandler("unmute", unmute))
        
        app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^[Рр]улетка$"), roulette_command))
        app.add_handler(CallbackQueryHandler(roulette_callback))
        
        print("🚀 Бот успешно запущен!")
        app.run_polling()
    else:
        print("🛑 Бот не запущен: отсутствует токен.")
