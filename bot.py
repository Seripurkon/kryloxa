import os
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler

# ====== Настройки ======
TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = 5679520675  # Твой Telegram ID

admins = {OWNER_ID: 4}  # id: уровень админки
warns = {}  # chat_id: {user: [время варна]}
mutes = {}  # chat_id: {user: end_time}
bans = {}   # chat_id: {user: end_time}
roulette_games = {}  # chat_id: игра

# ====== Вспомогательные функции ======
def parse_time_arg(arg: str):
    arg = arg.lower()
    if "день" in arg:
        return int(arg.split()[0]) * 24 * 60
    return int(arg)

# ====== Команды бота ======
async def start(update: Update, context: CallbackContext.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я бот для администрирования. Используй /help для списка команд.")

async def help_command(update: Update, context: CallbackContext.DEFAULT_TYPE):
    text = (
        "/start - старт бота\n"
        "/help - список команд\n"
        "-mute <ник> <время>\n"
        "-unmute <ник>\n"
        "-warn <ник> <время>\n"
        "-unwarn <ник>\n"
        "-ban <ник> <время>\n"
        "-unban <ник>\n"
        "Рулетка - ответом на сообщение игрока"
    )
    await update.message.reply_text(text)

# ====== Админ команды ======
async def mute(update: Update, context: CallbackContext.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Используй: -mute <ник> <время>")
        return
    nick = context.args[0]
    minutes = parse_time_arg(context.args[1])
    end_time = datetime.now() + timedelta(minutes=minutes)
    chat_id = update.message.chat_id
    mutes.setdefault(chat_id, {})[nick] = end_time
    await update.message.reply_text(f"{nick} замучен на {minutes} минут")

async def unmute(update: Update, context: CallbackContext.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text("Используй: -unmute <ник>")
        return
    nick = context.args[0]
    chat_id = update.message.chat_id
    if nick in mutes.get(chat_id, {}):
        del mutes[chat_id][nick]
        await update.message.reply_text(f"{nick} больше не замучен")
    else:
        await update.message.reply_text(f"{nick} не был в муте")

async def warn(update: Update, context: CallbackContext.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Используй: -warn <ник> <время>")
        return
    nick = context.args[0]
    minutes = parse_time_arg(context.args[1])
    end_time = datetime.now() + timedelta(minutes=minutes)
    chat_id = update.message.chat_id
    user_warns = warns.setdefault(chat_id, {}).setdefault(nick, [])
    user_warns.append(end_time)
    if len(user_warns) >= 3:
        mutes.setdefault(chat_id, {})[nick] = datetime.now() + timedelta(minutes=30)
        warns[chat_id][nick] = []
        await update.message.reply_text(f"{nick} получил 3 варна → мут на 30 минут")
    else:
        await update.message.reply_text(f"{nick} получает предупреждение {len(user_warns)}/3")

async def unwarn(update: Update, context: CallbackContext.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text("Используй: -unwarn <ник>")
        return
    nick = context.args[0]
    chat_id = update.message.chat_id
    if nick in warns.get(chat_id, {}):
        warns[chat_id][nick] = []
        await update.message.reply_text(f"{nick} предупреждения сняты")
    else:
        await update.message.reply_text(f"{nick} предупреждений не было")

async def ban(update: Update, context: CallbackContext.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Используй: -ban <ник> <время>")
        return
    nick = context.args[0]
    minutes = parse_time_arg(context.args[1])
    end_time = datetime.now() + timedelta(minutes=minutes)
    chat_id = update.message.chat_id
    bans.setdefault(chat_id, {})[nick] = end_time
    await update.message.reply_text(f"{nick} заблокирован на {minutes} минут")

async def unban(update: Update, context: CallbackContext.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text("Используй: -unban <ник>")
        return
    nick = context.args[0]
    chat_id = update.message.chat_id
    if nick in bans.get(chat_id, {}):
        del bans[chat_id][nick]
        await update.message.reply_text(f"{nick} разбанен")
    else:
        await update.message.reply_text(f"{nick} не был заблокирован")

# ====== Русская рулетка ======
async def roulette(update: Update, context: CallbackContext.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Ответьте на сообщение игрока для начала рулетки.")
        return
    opponent = update.message.reply_to_message.from_user.username
    player = update.message.from_user.username
    chat_id = update.message.chat_id
    roulette_games[chat_id] = {
        "player": player,
        "opponent": opponent,
        "status": "choose_penalty",
        "lives": {player: 2, opponent: 2},
        "penalty": None
    }
    keyboard = [
        [InlineKeyboardButton("Warn", callback_data="warn"),
         InlineKeyboardButton("Mute", callback_data="mute"),
         InlineKeyboardButton("Ban", callback_data="ban")]
    ]
    await update.message.reply_text(f"{opponent}, {player} предлагает сыграть! Выберите наказание:", 
                                    reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: CallbackContext.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    game = roulette_games.get(chat_id)
    if not game:
        await query.edit_message_text("Игра не найдена")
        return

    if game["status"] == "choose_penalty":
        game["penalty"] = query.data
        game["status"] = "playing"
        await query.edit_message_text(f"Выбрано наказание: {query.data}. Игра начинается! {game['player']} первый ход.")
        await play_turn(chat_id, context)

async def play_turn(chat_id, context: CallbackContext.DEFAULT_TYPE):
    game = roulette_games[chat_id]
    players = list(game["lives"].keys())
    for p in players:
        if game["lives"][p] <= 0:
            loser = p
            winner = [x for x in players if x != p][0]
            # Применяем наказание
            penalty = game["penalty"]
            minutes = 24*60  # 1 день
            if penalty == "mute":
                mutes.setdefault(chat_id, {})[loser] = datetime.now() + timedelta(minutes=minutes)
            elif penalty == "warn":
                warns.setdefault(chat_id, {}).setdefault(loser, []).append(datetime.now() + timedelta(minutes=minutes))
            elif penalty == "ban":
                bans.setdefault(chat_id, {})[loser] = datetime.now() + timedelta(minutes=minutes)
            await context.bot.send_message(chat_id, f"{loser} проиграл! Применено наказание: {penalty}")
            del roulette_games[chat_id]
            return
    # Рандом выстрел
    for p in players:
        shot = random.randint(1, 6)
        if shot == 1:
            game["lives"][p] -= 1
            await context.bot.send_message(chat_id, f"{p} получил урон! Осталось жизней: {game['lives'][p]}")
        else:
            await context.bot.send_message(chat_id, f"{p} выжил в этом раунде!")
    # Следующий раунд
    await play_turn(chat_id, context)

# ====== Приложение ======
app = ApplicationBuilder().token(TOKEN).build()

# Команды
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("mute", mute))
app.add_handler(CommandHandler("unmute", unmute))
app.add_handler(CommandHandler("warn", warn))
app.add_handler(CommandHandler("unwarn", unwarn))
app.add_handler(CommandHandler("ban", ban))
app.add_handler(CommandHandler("unban", unban))

# Рулетка
app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"(?i)Рулетка"), roulette))
app.add_handler(CallbackQueryHandler(button_handler))

app.run_polling()
