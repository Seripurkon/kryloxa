import os
import asyncio
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

# Берем токен СТРОГО из переменной BOT_TOKEN
TOKEN = os.getenv("BOT_TOKEN")

# Если токена нет, бот сразу упадет с понятной ошибкой в консоли
if not TOKEN:
    raise ValueError("❌ ОШИБКА: Переменная BOT_TOKEN не найдена в настройках BotHost!")

# Хранилище наказаний и админов
admins = set()
punishments = {}
warns = {}
roulette_games = {}

# ===================== Команды Админки =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот для администрирования.\n"
        "Используй команды:\n- Мут\n- Варн\n- Бан\n- Снять мут\n- Снять варн\n- Разбан"
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
    await update.message.reply_text(f"{user.username} замучен на {duration} минут")

async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    msg = update.message.reply_to_message
    if not msg: return
    user = msg.from_user
    warns[user.id] = warns.get(user.id, 0) + 1
    if warns[user.id] >= 3:
        punishments[user.id] = ("mute", datetime.now() + timedelta(minutes=30))
        warns[user.id] = 0
        await update.message.reply_text(f"{user.username} получил 3 варна и замучен на 30 минут")
    else:
        await update.message.reply_text(f"{user.username} получает предупреждение {warns[user.id]}/3")

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    msg = update.message.reply_to_message
    if not msg: return
    user = msg.from_user
    punishments[user.id] = ("ban", datetime.now() + timedelta(days=1))
    await update.message.reply_text(f"{user.username} заблокирован на один день")

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.reply_to_message
    if not msg: return
    user = msg.from_user
    if punishments.get(user.id, (None,))[0] == "mute":
        del punishments[user.id]
        await update.message.reply_text(f"{user.username} размучен")

async def unwarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.reply_to_message
    if not msg: return
    user = msg.from_user
    warns[user.id] = max(0, warns.get(user.id, 0) - 1)
    await update.message.reply_text(f"{user.username} варн снят. Текущий варн {warns[user.id]}/3")

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.reply_to_message
    if not msg: return
    user = msg.from_user
    if punishments.get(user.id, (None,))[0] == "ban":
        del punishments[user.id]
        await update.message.reply_text(f"{user.username} разбанен")

# ===================== Русская Рулетка =====================

async def roulette_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.reply_to_message
    if not msg: return
    opponent = msg.from_user
    player1 = update.effective_user
    roulette_games[player1.id] = {
        "player2": opponent.id,
        "state": "choose_punishment",
        "punishment": None,
        "lives": {player1.id: 2, opponent.id: 2},
    }
    keyboard = [[
        InlineKeyboardButton("Варн", callback_data="roulette_warn"),
        InlineKeyboardButton("Мут", callback_data="roulette_mute"),
        InlineKeyboardButton("Бан", callback_data="roulette_ban")
    ]]
    await update.message.reply_text(
        f"{opponent.username}, вы выбраны для игры от {player1.username}\nВыберите наказание:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def roulette_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    for p1, game in list(roulette_games.items()):
        if game["player2"] == user_id or p1 == user_id:
            if game["state"] == "choose_punishment" and game["player2"] == user_id:
                game["punishment"] = query.data.replace("roulette_", "")
                game["state"] = "playing"
                await query.edit_message_text(f"Игра началась! Наказание: {game['punishment']}")
                # Упрощенный запуск
                bullets = [0,0,0,0,1,1]
                random.shuffle(bullets)
                loser = random.choice([p1, game["player2"]])
                await query.message.reply_text(f"Бах! Игрок с ID {loser} проиграл.")
                del roulette_games[p1]
                return

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("warn", warn))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("unmute", unmute))
    app.add_handler(CommandHandler("unwarn", unwarn))
    app.add_handler(CommandHandler("unban", unban))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^[Рр]улетка$"), roulette_command))
    app.add_handler(CallbackQueryHandler(roulette_button))
    
    print("🚀 Бот запущен!")
    app.run_polling()
