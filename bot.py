import os
import asyncio
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

# Исправлено: теперь бот ищет переменную BOT_TOKEN (заглавными буквами)
TOKEN = os.getenv("BOT_TOKEN")

# Хранилище наказаний и админов
admins = set()
punishments = {}
warns = {}
roulette_games = {}

# ===================== Команды Админки =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот для администрирования.\n"
        "Используй команды:\n"
        "- Мут\n"
        "- Варн\n"
        "- Бан\n"
        "- Снять мут\n"
        "- Снять варн\n"
        "- Разбан"
    )

def is_admin(user_id):
    return user_id in admins

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    msg = update.message.reply_to_message
    if msg is None:
        await update.message.reply_text("Ответьте на сообщение пользователя.")
        return
    user = msg.from_user
    duration = 60  # по умолчанию 60 минут
    args = context.args
    if args:
        try:
            duration = int(args[0])
        except:
            pass
    punishments[user.id] = ("mute", datetime.now() + timedelta(minutes=duration))
    await update.message.reply_text(f"{user.username} замучен на {duration} минут")

async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    msg = update.message.reply_to_message
    if msg is None:
        await update.message.reply_text("Ответьте на сообщение пользователя.")
        return
    user = msg.from_user
    warns[user.id] = warns.get(user.id, 0) + 1
    if warns[user.id] >= 3:
        punishments[user.id] = ("mute", datetime.now() + timedelta(minutes=30))
        warns[user.id] = 0
        await update.message.reply_text(f"{user.username} получил 3 варна и замучен на 30 минут")
    else:
        await update.message.reply_text(f"{user.username} получает предупреждение {warns[user.id]}/3")

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    msg = update.message.reply_to_message
    if msg is None:
        await update.message.reply_text("Ответьте на сообщение пользователя.")
        return
    user = msg.from_user
    punishments[user.id] = ("ban", datetime.now() + timedelta(days=1))
    await update.message.reply_text(f"{user.username} заблокирован на один день")

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.reply_to_message
    if msg is None:
        await update.message.reply_text("Ответьте на сообщение пользователя.")
        return
    user = msg.from_user
    if punishments.get(user.id, (None,))[0] == "mute":
        del punishments[user.id]
        await update.message.reply_text(f"{user.username} размучен")

async def unwarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.reply_to_message
    if msg is None:
        await update.message.reply_text("Ответьте на сообщение пользователя.")
        return
    user = msg.from_user
    warns[user.id] = max(0, warns.get(user.id, 0) - 1)
    await update.message.reply_text(f"{user.username} варн снят. Текущий варн {warns[user.id]}/3")

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.reply_to_message
    if msg is None:
        await update.message.reply_text("Ответьте на сообщение пользователя.")
        return
    user = msg.from_user
    if punishments.get(user.id, (None,))[0] == "ban":
        del punishments[user.id]
        await update.message.reply_text(f"{user.username} разбанен")

# ===================== Русская Рулетка =====================

async def roulette_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.reply_to_message
    if msg is None:
        await update.message.reply_text("Ответьте на сообщение игрока, чтобы начать рулетку")
        return
    opponent = msg.from_user
    player1 = update.effective_user
    roulette_games[player1.id] = {
        "player2": opponent.id,
        "state": "choose_punishment",
        "punishment": None,
        "lives": {player1.id: 2, opponent.id: 2},
    }
    keyboard = [
        [InlineKeyboardButton("Варн", callback_data="roulette_warn"),
         InlineKeyboardButton("Мут", callback_data="roulette_mute"),
         InlineKeyboardButton("Бан", callback_data="roulette_ban")]
    ]
    await update.message.reply_text(
        f"{opponent.username}, вы выбраны для игры в русскую рулетку от {player1.username}\nВыберите наказание:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def roulette_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    for p1, game in roulette_games.items():
        if game["player2"] == user_id or p1 == user_id:
            if game["state"] == "choose_punishment" and p1 == user_id:
                # только второй игрок подтверждает
                await query.edit_message_text("Только выбранный игрок может подтвердить выбор.")
                return
            elif game["state"] == "choose_punishment" and game["player2"] == user_id:
                game["punishment"] = query.data.replace("roulette_", "")
                game["state"] = "playing"
                await query.edit_message_text(f"Наказание выбрано: {game['punishment'].capitalize()}\nИгра начинается!\n6 патронов, 2 жизни на каждого")
                await start_roulette_game(query, game)
                return

async def start_roulette_game(query, game):
    bullets = [0]*6
    for i in range(2):  # 2 патрона с порохом
        bullets[i] = 1
    random.shuffle(bullets)
    player_order = [list(game["lives"].keys())[0], list(game["lives"].keys())[1]]
    for i, bullet in enumerate(bullets):
        current_player = player_order[i % 2]
        other_player = player_order[(i + 1) % 2]
        # Простейшая имитация выстрела
        if bullet == 1:
            game["lives"][current_player] -= 1
        # После каждого выстрела проверка жизни
        if game["lives"][current_player] <= 0:
            await query.message.reply_text(
                f"Игрок {current_player} проиграл. Применяется наказание: {game['punishment'].capitalize()}"
            )
            break
    del roulette_games[player_order[0]]  # удаляем игру

# ===================== Основная =====================

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Команда не распознана.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("warn", warn))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("unmute", unmute))
    app.add_handler(CommandHandler("unwarn", unwarn))
    app.add_handler(CommandHandler("unban", unban))

    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^Рулетка$"), roulette_command))
    app.add_handler(CallbackQueryHandler(roulette_button))

    app.add_handler(MessageHandler(filters.COMMAND, unknown))

    print("Бот запущен")
    app.run_polling()
