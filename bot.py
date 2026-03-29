import os
import random
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

# Владелец бота
OWNER_ID = 5679520675

# Временные структуры
admins = {OWNER_ID: 4}  # id: уровень (1-4)
warns = {}  # user_id: количество варнов
mutes = {}  # user_id: время окончания (пока в памяти)
bans = {}   # user_id: время окончания (пока в памяти)

# Русская рулетка
duels = {}  # chat_id: {player1_id, player2_id, punishment, lives, chamber}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я бот для администрирования. Используй команды.")

# ---------------- Команды админки ----------------

async def mute_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Использование: -мут @username время_в_минутах")
        return
    username = context.args[0].replace("@", "")
    time_min = int(context.args[1])
    user = await context.bot.get_chat_member(update.effective_chat.id, username)
    mutes[user.user.id] = time_min
    await update.message.reply_text(f"{username} замучен на {time_min} минут.")

async def warn_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text("Использование: -варн @username")
        return
    username = context.args[0].replace("@", "")
    user = await context.bot.get_chat_member(update.effective_chat.id, username)
    warns[user.user.id] = warns.get(user.user.id, 0) + 1
    if warns[user.user.id] >= 3:
        mutes[user.user.id] = 30
        warns[user.user.id] = 0
        await update.message.reply_text(f"{username} получил 3 варна и замучен на 30 минут.")
    else:
        await update.message.reply_text(f"{username} получает предупреждение {warns[user.user.id]}/3.")

async def ban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text("Использование: -бан @username")
        return
    username = context.args[0].replace("@", "")
    user = await context.bot.get_chat_member(update.effective_chat.id, username)
    bans[user.user.id] = 1440
    await update.message.reply_text(f"{username} заблокирован в этом чате на 1 день.")

# ---------------- Снятие наказаний ----------------

async def unmute_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text("Использование: снять мут @username")
        return
    username = context.args[0].replace("@", "")
    user = await context.bot.get_chat_member(update.effective_chat.id, username)
    if user.user.id in mutes:
        del mutes[user.user.id]
    await update.message.reply_text(f"{username} больше не замучен.")

async def unwarn_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text("Использование: снять варн @username")
        return
    username = context.args[0].replace("@", "")
    user = await context.bot.get_chat_member(update.effective_chat.id, username)
    warns[user.user.id] = 0
    await update.message.reply_text(f"{username} варны сброшены.")

async def unban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text("Использование: разбан @username")
        return
    username = context.args[0].replace("@", "")
    user = await context.bot.get_chat_member(update.effective_chat.id, username)
    if user.user.id in bans:
        del bans[user.user.id]
    await update.message.reply_text(f"{username} больше не заблокирован.")

# ---------------- Русская рулетка ----------------

async def roulette_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Ответьте на сообщение человека, с которым хотите сыграть.")
        return
    player1 = update.message.from_user
    player2 = update.message.reply_to_message.from_user

    keyboard = [
        [InlineKeyboardButton("Варн", callback_data=f"punish_warn"),
         InlineKeyboardButton("Мут", callback_data=f"punish_mute"),
         InlineKeyboardButton("Бан", callback_data=f"punish_ban")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    duels[update.effective_chat.id] = {
        "player1": player1.id,
        "player2": player2.id,
        "lives": {player1.id: 2, player2.id: 2},
        "chamber": [0,0,0,0,0,1]  # один патрон с порохом
    }
    await update.message.reply_text(
        f"{player2.first_name}, {player1.first_name} предлагает сыграть в русскую рулетку. Выберите наказание:",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    duel = duels.get(chat_id)
    if not duel:
        await query.edit_message_text("Игра уже завершена или не найдена.")
        return
    punishment = query.data.split("_")[1]
    duel["punishment"] = punishment
    await query.edit_message_text(f"Выбрано наказание: {punishment}. Игра начинается!")
    # Процесс игры в рулетку упрощён: случайная смерть
    loser_id = random.choice([duel["player1"], duel["player2"]])
    if punishment == "warn":
        warns[loser_id] = 1
    elif punishment == "mute":
        mutes[loser_id] = 1440
    elif punishment == "ban":
        bans[loser_id] = 1440
    await context.bot.send_message(chat_id, f"Проиграл <a href='tg://user?id={loser_id}'>игрок</a>, наказание: {punishment}", parse_mode="HTML")
    del duels[chat_id]

# ---------------- Основное ----------------

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))

app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^-мут"), mute_cmd))
app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^-варн"), warn_cmd))
app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^-бан"), ban_cmd))

app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^снять мут"), unmute_cmd))
app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^снять варн"), unwarn_cmd))
app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^разбан"), unban_cmd))

app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^Рулетка"), roulette_cmd))
app.add_handler(CallbackQueryHandler(button_handler))

print("Бот запущен!")
app.run_polling()
