import os
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

# Временные словари для хранения состояния пользователей и рулетки (без БД)
admins = set()  # ID администраторов
warns = {}  # user_id : [timestamp1, timestamp2, timestamp3]
mutes = {}  # user_id : mute_end_time
bans = {}   # user_id : ban_end_time
roulette_games = {}  # chat_id : {initiator_id, opponent_id, stake, lives, bullets, turn}

TOKEN = os.getenv("BOT_TOKEN")

# --- Основные команды ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот для администрирования. Используй команды:\n"
        "- Мут\n"
        "- Варн\n"
        "- Бан\n"
        "- Снять мут\n"
        "- Снять варн\n"
        "- Разбан\n"
        "- Рулетка (ответ на сообщение игрока)"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Доступные команды:\n"
        "- Мут [ник] [минуты]\n"
        "- Варн [ник] [минуты]\n"
        "- Бан [ник] [минуты]\n"
        "- Снять мут [ник]\n"
        "- Снять варн [ник]\n"
        "- Разбан [ник]\n"
        "- Рулетка (ответ на сообщение игрока)"
    )

# --- Функции наказаний ---
def get_user_by_name(context, chat_id, username):
    for member in context.bot_data.get(chat_id, []):
        if member.username == username.replace("@", ""):
            return member
    return None

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Использование: Мут ник минуты")
        return
    username = args[0]
    minutes = int(args[1])
    user = get_user_by_name(context, update.effective_chat.id, username)
    if not user:
        await update.message.reply_text("Пользователь не найден.")
        return
    end_time = datetime.now() + timedelta(minutes=minutes)
    mutes[user.id] = end_time
    await update.message.reply_text(f"{username} замучен на {minutes} минут.")

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 1:
        await update.message.reply_text("Использование: Снять мут ник")
        return
    username = args[0]
    user = get_user_by_name(context, update.effective_chat.id, username)
    if not user:
        await update.message.reply_text("Пользователь не найден.")
        return
    mutes.pop(user.id, None)
    await update.message.reply_text(f"{username} размучен.")

async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Использование: Варн ник минуты")
        return
    username = args[0]
    minutes = int(args[1])
    user = get_user_by_name(context, update.effective_chat.id, username)
    if not user:
        await update.message.reply_text("Пользователь не найден.")
        return
    now = datetime.now()
    warns.setdefault(user.id, []).append(now)
    # Проверка на 3 варна
    warns[user.id] = [t for t in warns[user.id] if (now - t).total_seconds() <= 60*minutes]
    count = len(warns[user.id])
    if count >= 3:
        # Выдаём мут на 30 минут
        mutes[user.id] = now + timedelta(minutes=30)
        warns[user.id] = []
        await update.message.reply_text(f"{username} получил 3 варна. Выдан мут на 30 минут.")
    else:
        await update.message.reply_text(f"{username} получил предупреждение {count}/3.")

async def unwarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 1:
        await update.message.reply_text("Использование: Снять варн ник")
        return
    username = args[0]
    user = get_user_by_name(context, update.effective_chat.id, username)
    if not user:
        await update.message.reply_text("Пользователь не найден.")
        return
    warns.pop(user.id, None)
    await update.message.reply_text(f"{username} очищены варны.")

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Использование: Бан ник минуты")
        return
    username = args[0]
    minutes = int(args[1])
    user = get_user_by_name(context, update.effective_chat.id, username)
    if not user:
        await update.message.reply_text("Пользователь не найден.")
        return
    bans[user.id] = datetime.now() + timedelta(minutes=minutes)
    await update.message.reply_text(f"{username} заблокирован на {minutes} минут.")

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 1:
        await update.message.reply_text("Использование: Разбан ник")
        return
    username = args[0]
    user = get_user_by_name(context, update.effective_chat.id, username)
    if not user:
        await update.message.reply_text("Пользователь не найден.")
        return
    bans.pop(user.id, None)
    await update.message.reply_text(f"{username} разбанен.")

# --- Рулетка ---
async def roulette_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Чтобы начать рулетку, ответьте сообщением на игрока и напишите 'Рулетка'")
        return
    opponent = update.message.reply_to_message.from_user
    initiator = update.message.from_user
    chat_id = update.effective_chat.id
    roulette_games[chat_id] = {
        "initiator_id": initiator.id,
        "opponent_id": opponent.id,
        "stake": None,
        "lives": {initiator.id: 2, opponent.id: 2},
        "bullets": [1,1,0,0,0,0],  # 1 = патрон с порохом, 0 = холостой
        "turn": initiator.id
    }
    buttons = [
        [InlineKeyboardButton("Варн", callback_data="stake_warn"),
         InlineKeyboardButton("Мут", callback_data="stake_mute"),
         InlineKeyboardButton("Бан", callback_data="stake_ban")]
    ]
    await update.message.reply_text(
        f"{initiator.username} предложил рулетку {opponent.username}.\nВыберите, на что будете играть:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def roulette_stake_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    game = roulette_games.get(chat_id)
    if not game:
        await query.edit_message_text("Ошибка: игра не найдена")
        return
    user_id = query.from_user.id
    if user_id != game["initiator_id"]:
        await query.edit_message_text("Только инициатор может выбрать ставку.")
        return
    if query.data == "stake_warn":
        game["stake"] = "warn"
    elif query.data == "stake_mute":
        game["stake"] = "mute"
    elif query.data == "stake_ban":
        game["stake"] = "ban"
    await query.edit_message_text(f"Вы выбрали {game['stake'].capitalize()}. Ожидание подтверждения противника...")

# Здесь далее будут кнопки подтверждения противника и ходы рулетки с патронами, жизнями, выстрелами.
# В этой версии мы пока включаем основную логику ставок и интерфейс.

# --- Основное приложение ---
app = ApplicationBuilder().token(TOKEN).build()

# Команды
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("Мут", mute))
app.add_handler(CommandHandler("Снять мут", unmute))
app.add_handler(CommandHandler("Варн", warn))
app.add_handler(CommandHandler("Снять варн", unwarn))
app.add_handler(CommandHandler("Бан", ban))
app.add_handler(CommandHandler("Разбан", unban))

# Рулетка
app.add_handler(MessageHandler(filters.Regex("^Рулетка$") & filters.REPLY, roulette_start))
app.add_handler(CallbackQueryHandler(roulette_stake_callback, pattern="^stake_"))

# --- Запуск ---
if __name__ == "__main__":
    print("Бот запущен")
    app.run_polling()
