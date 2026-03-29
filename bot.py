import asyncio
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    MessageHandler, filters, CallbackQueryHandler
)
import os
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")  # Убедись, что токен в .env

# ====== Память без БД ======
admins = set()  # ID админов
owner_id = 5679520675  # твой ID
punishments = {}  # {'chat_id': {'user_id': {'warn': count, 'mute': until, 'ban': until}}}
roulette_games = {}  # {'chat_id': {'player1': id, 'player2': id, 'stake': 'warn/mute/ban', ...}}

# ====== Вспомогательные функции ======
def get_time_delta(value: str) -> timedelta:
    """Парсим время из формата '10 минут', '1 день'"""
    parts = value.lower().split()
    number = int(parts[0])
    if 'минут' in parts[1]:
        return timedelta(minutes=number)
    elif 'час' in parts[1]:
        return timedelta(hours=number)
    elif 'день' in parts[1]:
        return timedelta(days=number)
    elif 'год' in parts[1]:
        return timedelta(days=number*365)
    return timedelta(minutes=number)

def add_punishment(chat_id, user_id, kind, duration: timedelta):
    if chat_id not in punishments:
        punishments[chat_id] = {}
    if user_id not in punishments[chat_id]:
        punishments[chat_id][user_id] = {'warn': 0, 'mute': None, 'ban': None}
    if kind == 'warn':
        punishments[chat_id][user_id]['warn'] += 1
        if punishments[chat_id][user_id]['warn'] >= 3:
            punishments[chat_id][user_id]['warn'] = 0
            punishments[chat_id][user_id]['mute'] = datetime.utcnow() + timedelta(minutes=30)
            return 'mute', 30
    else:
        punishments[chat_id][user_id][kind] = datetime.utcnow() + duration
    return kind, duration

# ====== Команды админки ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Бот запущен. Используйте /help для списка команд.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    commands = [
        "-mute <user> <время>",
        "-warn <user> <время>",
        "-ban <user> <время>",
        "-unmute <user>",
        "-removewarn <user>",
        "-unban <user>",
        "-roulette (ответом на сообщение)"
    ]
    await update.message.reply_text("Список команд:\n" + "\n".join(commands))

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not update.message.reply_to_message:
        await update.message.reply_text("Ответьте на сообщение пользователя.")
        return
    target_id = update.message.reply_to_message.from_user.id
    duration = timedelta(hours=1)  # по умолчанию 1 час
    add_punishment(chat_id, target_id, 'mute', duration)
    await update.message.reply_text(f"{update.message.reply_to_message.from_user.first_name} замучен на {duration}.")

async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not update.message.reply_to_message:
        await update.message.reply_text("Ответьте на сообщение пользователя.")
        return
    target_id = update.message.reply_to_message.from_user.id
    kind, val = add_punishment(chat_id, target_id, 'warn', timedelta(minutes=0))
    if kind == 'warn':
        await update.message.reply_text(f"{update.message.reply_to_message.from_user.first_name} получает предупреждение 1/3.")
    else:
        await update.message.reply_text(f"{update.message.reply_to_message.from_user.first_name} автоматически замучен на {val} минут (3 варна).")

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not update.message.reply_to_message:
        await update.message.reply_text("Ответьте на сообщение пользователя.")
        return
    target_id = update.message.reply_to_message.from_user.id
    add_punishment(chat_id, target_id, 'ban', timedelta(days=1))
    await update.message.reply_text(f"{update.message.reply_to_message.from_user.first_name} заблокирован в этом чате на 1 день.")

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not update.message.reply_to_message:
        await update.message.reply_text("Ответьте на сообщение пользователя.")
        return
    target_id = update.message.reply_to_message.from_user.id
    if chat_id in punishments and target_id in punishments[chat_id]:
        punishments[chat_id][target_id]['mute'] = None
    await update.message.reply_text(f"{update.message.reply_to_message.from_user.first_name} больше не замучен.")

async def removewarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not update.message.reply_to_message:
        await update.message.reply_text("Ответьте на сообщение пользователя.")
        return
    target_id = update.message.reply_to_message.from_user.id
    if chat_id in punishments and target_id in punishments[chat_id]:
        punishments[chat_id][target_id]['warn'] = 0
    await update.message.reply_text(f"Предупреждения для {update.message.reply_to_message.from_user.first_name} сброшены.")

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not update.message.reply_to_message:
        await update.message.reply_text("Ответьте на сообщение пользователя.")
        return
    target_id = update.message.reply_to_message.from_user.id
    if chat_id in punishments and target_id in punishments[chat_id]:
        punishments[chat_id][target_id]['ban'] = None
    await update.message.reply_text(f"{update.message.reply_to_message.from_user.first_name} больше не забанен.")

# ====== Русская рулетка ======
async def roulette(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Ответьте на сообщение игрока, чтобы предложить дуэль.")
        return
    chat_id = update.effective_chat.id
    p1_id = update.message.from_user.id
    p2_id = update.message.reply_to_message.from_user.id
    # Инициализация игры
    roulette_games[chat_id] = {
        'player1': p1_id,
        'player2': p2_id,
        'lives': {p1_id: 2, p2_id: 2},
        'stake': 'mute',  # Можно потом добавить выбор
        'current': p1_id,
        'turns': 6,
        'barrels': random.sample([0,0,0,0,0,1], 6)  # один боевой патрон
    }
    await update.message.reply_text(f"{update.message.from_user.first_name} вызывает {update.message.reply_to_message.from_user.first_name} на рулетку!")

async def roulette_fire(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.message.from_user.id
    if chat_id not in roulette_games:
        return
    game = roulette_games[chat_id]
    if user_id != game['current']:
        await update.message.reply_text("Сейчас ход другого игрока.")
        return
    # Стрельба
    barrel = game['barrels'].pop(0)
    target = user_id
    if barrel:
        game['lives'][target] -= 1
        await update.message.reply_text(f"Бах! {update.message.from_user.first_name} теряет жизнь.")
    else:
        await update.message.reply_text(f"{update.message.from_user.first_name} промахнулся.")
    if game['lives'][target] <= 0:
        await update.message.reply_text(f"{update.message.from_user.first_name} проиграл рулетку! Выполняем наказание: {game['stake']}")
        add_punishment(chat_id, target, game['stake'], timedelta(days=1))
        del roulette_games[chat_id]
        return
    # Меняем ход
    game['current'] = game['player1'] if user_id == game['player2'] else game['player2']

# ====== Настройка приложения ======
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("mute", mute))
app.add_handler(CommandHandler("warn", warn))
app.add_handler(CommandHandler("ban", ban))
app.add_handler(CommandHandler("unmute", unmute))
app.add_handler(CommandHandler("removewarn", removewarn))
app.add_handler(CommandHandler("unban", unban))
app.add_handler(MessageHandler(filters.Regex("Рулетка"), roulette))
app.add_handler(MessageHandler(filters.Regex("стрельнуть"), roulette_fire))

print("Бот запущен!")
app.run_polling()
