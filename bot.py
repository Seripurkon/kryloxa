import os
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TOKEN")  # В .env должно быть: TOKEN=твой_токен

# Админ ID для выдачи прав
OWNER_ID = 5679520675
admins = {OWNER_ID}  # set с ID админов

# Словарь варнов: user_id -> кол-во варнов
warns = {}

# Хранение активных мутов/банов: user_id -> (тип, время окончания)
punishments = {}

# Хранение рулетки: chat_id -> dict с info о текущей игре
roulette_games = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот для администрирования.\nИспользуй команды:\n- Мут\n- Варн\n- Бан\n- Снять мут\n- Снять варн\n- Разбан\n- Рулетка (ответом на сообщение)"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Команды:\n"
        "- Мут [ник] [минуты]\n"
        "- Варн [ник] [минуты]\n"
        "- Бан [ник] [минуты]\n"
        "- Снять мут [ник]\n"
        "- Снять варн [ник]\n"
        "- Разбан [ник]\n"
        "- Рулетка (ответом на сообщение)"
    )

def parse_time(arg: str) -> int:
    # Конвертируем минуты/дни/часы в минуты
    units = {"минут": 1, "час": 60, "день": 1440, "месяц": 43200, "год": 525600}
    try:
        parts = arg.lower().split()
        if len(parts) == 2:
            num = int(parts[0])
            unit = parts[1]
            return num * units.get(unit, 1)
        return int(arg)
    except:
        return 60  # по умолчанию 60 минут

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        msg = update.message
        args = context.args
        if len(args) < 1 and not msg.reply_to_message:
            await msg.reply_text("Укажи ник или ответь на сообщение пользователя.")
            return

        # Получаем пользователя
        target_user = None
        if msg.reply_to_message:
            target_user = msg.reply_to_message.from_user
        else:
            username = args[0].replace("@", "")
            for member in msg.chat.get_members():
                if member.user.username == username:
                    target_user = member.user
                    break
        if not target_user:
            await msg.reply_text("Пользователь не найден.")
            return

        duration = parse_time(args[1]) if len(args) > 1 else 60
        punishments[target_user.id] = ("mute", datetime.now() + timedelta(minutes=duration))
        await msg.reply_text(f"{target_user.full_name} замучен на {duration} минут.")
    except Exception as e:
        await msg.reply_text(str(e))

async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    args = context.args
    if len(args) < 1 and not msg.reply_to_message:
        await msg.reply_text("Укажи ник или ответь на сообщение пользователя.")
        return

    target_user = None
    if msg.reply_to_message:
        target_user = msg.reply_to_message.from_user
    else:
        username = args[0].replace("@", "")
        for member in msg.chat.get_members():
            if member.user.username == username:
                target_user = member.user
                break
    if not target_user:
        await msg.reply_text("Пользователь не найден.")
        return

    warns[target_user.id] = warns.get(target_user.id, 0) + 1
    if warns[target_user.id] >= 3:
        punishments[target_user.id] = ("mute", datetime.now() + timedelta(minutes=30))
        warns[target_user.id] = 0
        await msg.reply_text(f"{target_user.full_name} получил 3/3 варнов и замучен на 30 минут.")
    else:
        await msg.reply_text(f"{target_user.full_name} получает предупреждение {warns[target_user.id]}/3.")

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    args = context.args
    if len(args) < 1 and not msg.reply_to_message:
        await msg.reply_text("Укажи ник или ответь на сообщение пользователя.")
        return

    target_user = None
    if msg.reply_to_message:
        target_user = msg.reply_to_message.from_user
    else:
        username = args[0].replace("@", "")
        for member in msg.chat.get_members():
            if member.user.username == username:
                target_user = member.user
                break
    if not target_user:
        await msg.reply_text("Пользователь не найден.")
        return

    duration = parse_time(args[1]) if len(args) > 1 else 1440
    punishments[target_user.id] = ("ban", datetime.now() + timedelta(minutes=duration))
    await msg.reply_text(f"{target_user.full_name} заблокирован на {duration} минут.")

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    target_user = msg.reply_to_message.from_user if msg.reply_to_message else None
    if target_user and target_user.id in punishments and punishments[target_user.id][0] == "mute":
        punishments.pop(target_user.id)
        await msg.reply_text(f"{target_user.full_name} больше не замучен.")

async def unwarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    target_user = msg.reply_to_message.from_user if msg.reply_to_message else None
    if target_user and target_user.id in warns:
        warns[target_user.id] = 0
        await msg.reply_text(f"{target_user.full_name} варны сброшены.")

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    target_user = msg.reply_to_message.from_user if msg.reply_to_message else None
    if target_user and target_user.id in punishments and punishments[target_user.id][0] == "ban":
        punishments.pop(target_user.id)
        await msg.reply_text(f"{target_user.full_name} разбанен.")

# ---------- РУССКАЯ РУЛЕТКА ----------

async def roulette(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg.reply_to_message:
        await msg.reply_text("Ответьте на сообщение того, с кем хотите сыграть в рулетку.")
        return

    opponent = msg.reply_to_message.from_user
    player = msg.from_user

    # Инициализация игры
    roulette_games[msg.chat.id] = {
        "player1": player,
        "player2": opponent,
        "lives": {player.id: 2, opponent.id: 2},
        "turn": player.id,
        "bullet_chamber": random.sample([True, False, False, False, False, False], 6),
        "punishment_type": None,
    }
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Варн", callback_data="roulette_choice_warn"),
         InlineKeyboardButton("Мут", callback_data="roulette_choice_mute"),
         InlineKeyboardButton("Бан", callback_data="roulette_choice_ban")]
    ])
    await msg.reply_text(f"{player.full_name} предложил рулетку {opponent.full_name}. Выберите на что играть:", reply_markup=keyboard)

async def roulette_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat.id
    game = roulette_games.get(chat_id)
    if not game:
        await query.message.edit_text("Игра не найдена.")
        return

    if data.startswith("roulette_choice_"):
        game["punishment_type"] = data.split("_")[-1]
        await query.message.edit_text(f"Вы выбрали: {game['punishment_type'].upper()}. Начинаем игру!")

        await play_turn(chat_id, context)

async def play_turn(chat_id, context: ContextTypes.DEFAULT_TYPE):
    game = roulette_games.get(chat_id)
    if not game:
        return

    current_player_id = game["turn"]
    player_name = context.bot.get_chat(chat_id).get_member(current_player_id).user.full_name
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Выстрелить в себя", callback_data="shoot_self"),
         InlineKeyboardButton("Выстрелить в соперника", callback_data="shoot_opp")]
    ])
    await context.bot.send_message(chat_id, f"Ход {player_name}: выберите действие.", reply_markup=keyboard)

# ----------------- Основной запуск -----------------

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("mute", mute))
app.add_handler(CommandHandler("warn", warn))
app.add_handler(CommandHandler("ban", ban))
app.add_handler(CommandHandler("unmute", unmute))
app.add_handler(CommandHandler("unwarn", unwarn))
app.add_handler(CommandHandler("unban", unban))
app.add_handler(MessageHandler(filters.Regex(r"Рулетка"), roulette))
app.add_handler(CallbackQueryHandler(roulette_button))

print("Бот запущен!")
app.run_polling()
