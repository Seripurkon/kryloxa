import asyncio
import random
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    CallbackQueryHandler,
)

TOKEN = "ВАШ_ТОКЕН_ТУТ"  # Вставьте свой токен
OWNER_ID = 5679520675

# Хранение админов, наказаний и игр
ADMINS = {OWNER_ID}
WARNINGS = {}  # {chat_id: {user_id: (count, expiration)}}
MUTES = {}     # {chat_id: {user_id: expiration}}
BANS = {}      # {chat_id: {user_id: expiration}}
ROULETTE_GAMES = {}  # {chat_id: game_data}

# --- Команды администрирования ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я бот для администрирования. Используй команды.")

async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Только владелец может выдавать админку.")
        return
    if not context.args:
        await update.message.reply_text("Укажите ID пользователя.")
        return
    try:
        user_id = int(context.args[0])
        ADMINS.add(user_id)
        await update.message.reply_text(f"Пользователь {user_id} теперь администратор.")
    except ValueError:
        await update.message.reply_text("Неправильный ID.")

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("У вас нет прав.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Используйте: -мут <ник/ID> <время в минутах/часах/днях>")
        return
    user_identifier = context.args[0]
    time_str = context.args[1]
    minutes = parse_time(time_str)
    expiration = datetime.now() + timedelta(minutes=minutes)
    chat_id = update.effective_chat.id
    user_id = await resolve_user_id(update, context, user_identifier)
    if chat_id not in MUTES:
        MUTES[chat_id] = {}
    MUTES[chat_id][user_id] = expiration
    await update.message.reply_text(f"{user_identifier} замучен на {time_str}.")

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("У вас нет прав.")
        return
    if not context.args:
        await update.message.reply_text("Укажите ник/ID.")
        return
    user_identifier = context.args[0]
    chat_id = update.effective_chat.id
    user_id = await resolve_user_id(update, context, user_identifier)
    if chat_id in MUTES and user_id in MUTES[chat_id]:
        del MUTES[chat_id][user_id]
        await update.message.reply_text(f"{user_identifier} больше не замучен.")
    else:
        await update.message.reply_text("Этот пользователь не в муте.")

# --- Вспомогательные функции ---

def parse_time(time_str: str) -> int:
    """Конвертирует строки вроде '60', '1h', '2d' в минуты"""
    if time_str.endswith("d"):
        return int(time_str[:-1]) * 1440
    elif time_str.endswith("h"):
        return int(time_str[:-1]) * 60
    else:
        return int(time_str)

async def resolve_user_id(update, context, identifier: str):
    """Определяет ID пользователя по никнейму или ID"""
    chat = update.effective_chat
    if identifier.startswith("@"):
        username = identifier[1:]
        for member in await chat.get_administrators():
            if member.user.username == username:
                return member.user.id
        # иначе ищем среди участников чата
        for member_id in range(0, 5):  # без базы сложно, упрощённо
            try:
                member = await chat.get_member(member_id)
                if member.user.username == username:
                    return member.user.id
            except:
                continue
        return None
    else:
        return int(identifier)

# --- Русская рулетка ---

async def roulette_call(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Ответьте на сообщение игрока, чтобы начать рулетку.")
        return
    opponent = update.message.reply_to_message.from_user
    caller = update.effective_user
    chat_id = update.effective_chat.id
    ROULETTE_GAMES[chat_id] = {
        "player1": caller.id,
        "player2": opponent.id,
        "state": "choose_penalty",
    }
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Варн", callback_data="penalty_warn")],
        [InlineKeyboardButton("Мут", callback_data="penalty_mute")],
        [InlineKeyboardButton("Бан", callback_data="penalty_ban")]
    ])
    await update.message.reply_text(f"{opponent.first_name}, выберите на что играть:", reply_markup=keyboard)

async def roulette_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    game = ROULETTE_GAMES.get(chat_id)
    if not game:
        await query.message.reply_text("Игра не найдена.")
        return

    # Только второй игрок подтверждает
    if query.data.startswith("penalty_") and query.from_user.id != game["player2"]:
        await query.message.reply_text("Только выбранный игрок может подтвердить.")
        return

    if game["state"] == "choose_penalty":
        game["penalty"] = query.data.split("_")[1]
        game["state"] = "confirm"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Подтвердить", callback_data="confirm")],
            [InlineKeyboardButton("Отклонить", callback_data="reject")]
        ])
        await query.message.reply_text("Вы выбрали. Игрок подтвердите:", reply_markup=keyboard)
        return

    if game["state"] == "confirm":
        if query.data == "confirm" and query.from_user.id == game["player2"]:
            await query.message.reply_text("Игра начинается! У каждого 2 жизни, 6 патронов (рандомно).")
            game["state"] = "playing"
            game["lives"] = {game["player1"]: 2, game["player2"]: 2}
            game["chambers"] = [0, 0, 0, 0, 1, 1]  # 1 = порох
            random.shuffle(game["chambers"])
            await next_turn(update, context)
        elif query.data == "reject" and query.from_user.id == game["player2"]:
            await query.message.reply_text("Игра отменена.")
            del ROULETTE_GAMES[chat_id]

async def next_turn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    game = ROULETTE_GAMES[chat_id]
    current_player = game["player1"] if len(game["chambers"]) % 2 == 0 else game["player2"]
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Выстрелить в себя", callback_data=f"shoot_self_{current_player}")],
        [InlineKeyboardButton("Выстрелить в соперника", callback_data=f"shoot_other_{current_player}")]
    ])
    await update.message.reply_text(f"Ход игрока {current_player}. Выберите действие:", reply_markup=keyboard)

async def shoot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    game = ROULETTE_GAMES.get(chat_id)
    if not game:
        await query.message.reply_text("Игра не найдена.")
        return

    action_parts = query.data.split("_")
    action_type = action_parts[1]
    player_turn = int(action_parts[2])
    if query.from_user.id != player_turn:
        await query.message.reply_text("Сейчас ход другого игрока.")
        return

    # Стрельба
    chamber = game["chambers"].pop(0)
    target = query.from_user.id if action_type == "self" else (game["player2"] if player_turn == game["player1"] else game["player1"])
    if chamber == 1:
        game["lives"][target] -= 1
        await query.message.reply_text(f"Выстрел с порохом! Игрок {target} теряет жизнь.")
    else:
        await query.message.reply_text(f"Выстрел холостой! Никто не теряет жизнь.")

    # Проверка жизни
    if game["lives"][target] <= 0:
        penalty = game["penalty"]
        if penalty == "warn":
            await query.message.reply_text(f"Игрок {target} получает варн на 1 день!")
        elif penalty == "mute":
            await query.message.reply_text(f"Игрок {target} замучен на 1 день!")
        elif penalty == "ban":
            await query.message.reply_text(f"Игрок {target} заблокирован на 1 день!")
        del ROULETTE_GAMES[chat_id]
        return

    if game["chambers"]:
        await next_turn(update, context)
    else:
        await query.message.reply_text("Все патроны использованы, игра завершена.")
        del ROULETTE_GAMES[chat_id]

# --- Основное ---

app = ApplicationBuilder().token(TOKEN).build()

# Команды
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("addadmin", add_admin))
app.add_handler(CommandHandler("mute", mute))
app.add_handler(CommandHandler("unmute", unmute))
app.add_handler(MessageHandler(filters.Regex(r"^Рулетка$") & filters.REPLY, roulette_call))
app.add_handler(CallbackQueryHandler(roulette_callback))
app.add_handler(CallbackQueryHandler(shoot_callback, pattern=r"shoot_.*"))

app.run_polling()
