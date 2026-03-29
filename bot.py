import os
import asyncio
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

# Получаем токен из переменной окружения BotHost
TOKEN = os.getenv("BOT_TOKEN")

# Хранилище (сбросится при перезагрузке)
admins = set()
punishments = {}
warns = {}
roulette_games = {}

# ===================== Админка =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Бот запущен! Команды: Мут, Варн, Бан, Разбан.\n"
        "Чтобы команды работали, добавь свой ID в код или стань админом чата."
    )

def is_admin(user_id):
    return user_id in admins

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    msg = update.message.reply_to_message
    if not msg: return
    user = msg.from_user
    duration = 60
    if context.args:
        try: duration = int(context.args[0])
        except: pass
    punishments[user.id] = ("mute", datetime.now() + timedelta(minutes=duration))
    await update.message.reply_text(f"🤐 {user.username} в муте на {duration} мин.")

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
        await update.message.reply_text(f"⚠️ Варн {user.username}: {warns[user.id]}/3")

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    msg = update.message.reply_to_message
    if not msg: return
    punishments[msg.from_user.id] = ("ban", datetime.now() + timedelta(days=1))
    await update.message.reply_text(f"🔨 {msg.from_user.username} забанен.")

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.reply_to_message
    if not msg: return
    if punishments.get(msg.from_user.id, (None,))[0] == "mute":
        del punishments[msg.from_user.id]
        await update.message.reply_text(f"🔊 {msg.from_user.username} размучен.")

# ===================== Рулетка =====================

async def roulette_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.reply_to_message
    if not msg:
        return await update.message.reply_text("Ответьте на сообщение игрока!")
    
    p1, p2 = update.effective_user, msg.from_user
    roulette_games[p1.id] = {"p2": p2.id, "step": "bet"}
    
    keyboard = [[
        InlineKeyboardButton("Варн", callback_data="r_warn"),
        InlineKeyboardButton("Мут", callback_data="r_mute")
    ]]
    await update.message.reply_text(f"🎯 {p2.username}, вызов от {p1.username}! Ставка:", 
                                   reply_markup=InlineKeyboardMarkup(keyboard))

async def roulette_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # Упрощенная логика для теста
    res = random.choice(["Выстрел! 💥", "Осечка... 💨"])
    await query.edit_message_text(f"Результат: {res}")

# ===================== Запуск =====================

if __name__ == "__main__":
    if not TOKEN:
        print("❌ ОШИБКА: BOT_TOKEN не задан в панели BotHost!")
    else:
        app = ApplicationBuilder().token(TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("mute", mute))
        app.add_handler(CommandHandler("warn", warn))
        app.add_handler(CommandHandler("ban", ban))
        app.add_handler(CommandHandler("unmute", unmute))
        app.add_handler(MessageHandler(filters.Regex(r"^[Рр]улетка$"), roulette_command))
        app.add_handler(CallbackQueryHandler(roulette_callback))
        
        print("🚀 Бот запущен!")
        app.run_polling()
