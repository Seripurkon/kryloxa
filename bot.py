from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
import random
import asyncio
from datetime import datetime, timedelta

# Твой ID для выдачи админки себе
OWNER_ID = 5679520675

# Словари для хранения данных в оперативной памяти
admins = {OWNER_ID: 4}  # Ранг админа: 1-4
warnings = {}  # user_id: количество варнов
mutes = {}     # user_id: время окончания мута
bans = {}      # user_id: время окончания бана
roulette_games = {}  # chat_id: данные игры

# --- Админ-команды ---
async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Только владелец может выдавать админку.")
        return
    if not context.args:
        await update.message.reply_text("Укажи никнейм для выдачи админки.")
        return
    username = context.args[0].replace("@", "")
    admins[username] = 1  # выдан первый ранг
    await update.message.reply_text(f"{username} теперь админ 1 ранга.")

async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Только владелец может снимать админку.")
        return
    if not context.args:
        await update.message.reply_text("Укажи никнейм для снятия админки.")
        return
    username = context.args[0].replace("@", "")
    if username in admins:
        del admins[username]
        await update.message.reply_text(f"{username} больше не админ.")
    else:
        await update.message.reply_text(f"{username} не найден в админах.")

# --- Система наказаний ---
async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Укажи никнейм для варна.")
        return
    username = context.args[0].replace("@", "")
    warnings[username] = warnings.get(username, 0) + 1
    if warnings[username] >= 3:
        warnings[username] = 0
        await mute_user_logic(username, 30)  # 30 минут
        await update.message.reply_text(f"{username} получил 3 варна и замучен на 30 минут!")
    else:
        await update.message.reply_text(f"{username} получает предупреждение {warnings[username]}/3")

async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Используй: -мут @никнейм время_в_минутах")
        return
    username = context.args[0].replace("@", "")
    try:
        minutes = int(context.args[1])
    except:
        await update.message.reply_text("Время должно быть числом в минутах")
        return
    await mute_user_logic(username, minutes)
    await update.message.reply_text(f"{username} замучен на {minutes} минут.")

async def mute_user_logic(username, minutes):
    mutes[username] = datetime.now() + timedelta(minutes=minutes)

async def unmute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Укажи никнейм для снятия мута")
        return
    username = context.args[0].replace("@", "")
    if username in mutes:
        del mutes[username]
        await update.message.reply_text(f"{username} больше не замучен.")
    else:
        await update.message.reply_text(f"{username} не был замучен.")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Используй: -бан @никнейм время_в_минутах")
        return
    username = context.args[0].replace("@", "")
    try:
        minutes = int(context.args[1])
    except:
        await update.message.reply_text("Время должно быть числом в минутах")
        return
    bans[username] = datetime.now() + timedelta(minutes=minutes)
    await update.message.reply_text(f"{username} забанен на {minutes} минут.")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Укажи никнейм для снятия бана")
        return
    username = context.args[0].replace("@", "")
    if username in bans:
        del bans[username]
        await update.message.reply_text(f"{username} больше не забанен.")
    else:
        await update.message.reply_text(f"{username} не был забанен.")

# --- Русская рулетка ---
async def roulette_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Ответ на сообщение
    if not update.message.reply_to_message:
        await update.message.reply_text("Ответь на сообщение игрока, с которым хочешь сыграть.")
        return
    opponent = update.message.reply_to_message.from_user
    chat_id = update.message.chat_id
    # Создаем игру
    roulette_games[chat_id] = {
        "player1": update.message.from_user,
        "player2": opponent,
        "life": {update.message.from_user.id: 2, opponent.id: 2},
        "turn": update.message.from_user.id,
        "state": "choose_bet"
    }
    keyboard = [
        [InlineKeyboardButton("Принять", callback_data="roulette_accept"),
         InlineKeyboardButton("Отклонить", callback_data="roulette_decline")]
    ]
    await update.message.reply_text(
        f"{opponent.first_name}, вас вызвали в русскую рулетку!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def roulette_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    game = roulette_games.get(chat_id)
    if not game:
        await query.edit_message_text("Игра не найдена.")
        return
    if query.data == "roulette_decline":
        await query.edit_message_text("Игрок отклонил вызов.")
        del roulette_games[chat_id]
        return
    if query.data == "roulette_accept":
        # Выбор ставки
        keyboard = [
            [InlineKeyboardButton("Варн", callback_data="bet_warn"),
             InlineKeyboardButton("Мут", callback_data="bet_mute"),
             InlineKeyboardButton("Бан", callback_data="bet_ban")]
        ]
        await query.edit_message_text("Выберите ставку на игру:", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    if query.data.startswith("bet_"):
        game["bet"] = query.data.split("_")[1]  # warn, mute, ban
        game["state"] = "playing"
        game["cylinder"] = [1 if i < 2 else 0 for i in range(6)]  # 2 патрона с порохом, 4 холостых
        random.shuffle(game["cylinder"])
        await query.edit_message_text(f"Игра начинается! {game['player1'].first_name} ходит первым.")
        await roulette_turn(context.bot, chat_id)

async def roulette_turn(bot, chat_id):
    game = roulette_games.get(chat_id)
    if not game:
        return
    player_id = game["turn"]
    player_name = game["player1"].first_name if player_id == game["player1"].id else game["player2"].first_name
    keyboard = [
        [InlineKeyboardButton("Стрельнуть в себя", callback_data="shoot_self"),
         InlineKeyboardButton("Стрельнуть в соперника", callback_data="shoot_other")]
    ]
    chat = await bot.get_chat(chat_id)
    await chat.send_message(f"Ход {player_name}!", reply_markup=InlineKeyboardMarkup(keyboard))

async def roulette_shoot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    game = roulette_games.get(chat_id)
    if not game or game["state"] != "playing":
        await query.edit_message_text("Игра не активна.")
        return
    player_id = game["turn"]
    player_name = game["player1"].first_name if player_id == game["player1"].id else game["player2"].first_name
    opponent_id = game["player2"].id if player_id == game["player1"].id else game["player1"].id
    opponent_name = game["player2"].first_name if player_id == game["player1"].id else game["player1"].first_name
    choice = query.data
    # Выбираем патрон
    bullet = game["cylinder"].pop(0)
    loser_id = None
    if bullet == 1:
        if choice == "shoot_self":
            game["life"][player_id] -= 1
            loser_id = player_id if game["life"][player_id] <= 0 else None
        else:
            game["life"][opponent_id] -= 1
            loser_id = opponent_id if game["life"][opponent_id] <= 0 else None
    else:
        await query.edit_message_text(f"{player_name} стреляет... Холостой патрон, никто не теряет жизнь.")
    # Проверка проигравшего
    if loser_id:
        loser_name = player_name if loser_id == player_id else opponent_name
        bet = game["bet"]
        if bet == "warn":
            warnings[loser_name] = 1
            await query.edit_message_text(f"{loser_name} проиграл! Получает варн на 1 день.")
        elif bet == "mute":
            mutes[loser_name] = datetime.now() + timedelta(days=1)
            await query.edit_message_text(f"{loser_name} проиграл! Замучен на 1 день.")
        elif bet == "ban":
            bans[loser_name] = datetime.now() + timedelta(days=1)
            await query.edit_message_text(f"{loser_name} проиграл! Забанен на 1 день.")
        del roulette_games[chat_id]
        return
    # Смена хода
    game["turn"] = opponent_id
    await roulette_turn(context.bot, chat_id)

# --- Старт и помощь ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    commands = """
Список команд:
- Мут @никнейм время_в_минутах
- Снять мут @никнейм
- Варн @никнейм
- Бан @никнейм время_в_минутах
- Снять бан @никнейм
- /roulette - сыграть в русскую рулетку (ответ на сообщение)
"""
    await update.message.reply_text(f"Здравствуйте, {update.effective_user.first_name}!\n{commands}")

# --- Основное ---
if __name__ == "__main__":
    app = ApplicationBuilder().token("ВАШ_ТОКЕН_ЗДЕСЬ").build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addadmin", add_admin))
    app.add_handler(CommandHandler("removeadmin", remove_admin))
    app.add_handler(CommandHandler("warn", warn_user))
    app.add_handler(CommandHandler("mute", mute_user))
    app.add_handler(CommandHandler("unmute", unmute_user))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))
    app.add_handler(CommandHandler("roulette", roulette_start))
    app.add_handler(CallbackQueryHandler(roulette_callback, pattern="^roulette_"))
    app.add_handler(CallbackQueryHandler(roulette_shoot, pattern="^shoot_"))
    app.run_polling()
