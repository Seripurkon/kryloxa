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
TOKEN = os.getenv("TOKEN")  # В .env: TOKEN=твой_токен

OWNER_ID = 5679520675
admins = {OWNER_ID}
warns = {}
punishments = {}
roulette_games = {}  # chat_id -> game info

# -------------------- Команды админа --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот для администрирования.\nИспользуй команды:\n- Мут\n- Варн\n- Бан\n- Снять мут\n- Снять варн\n- Разбан\n- Рулетка (ответом на сообщение)"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Команды:\n- Мут [ник/ответ] [минуты]\n- Варн [ник/ответ] [минуты]\n- Бан [ник/ответ] [минуты]\n"
        "- Снять мут [ник/ответ]\n- Снять варн [ник/ответ]\n- Разбан [ник/ответ]\n- Рулетка (ответом на сообщение)"
    )

def parse_time(arg: str) -> int:
    units = {"минут": 1, "час": 60, "день": 1440, "месяц": 43200, "год": 525600}
    try:
        parts = arg.lower().split()
        if len(parts) == 2:
            num = int(parts[0])
            unit = parts[1]
            return num * units.get(unit, 1)
        return int(arg)
    except:
        return 60

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    args = context.args
    if len(args) < 1 and not msg.reply_to_message:
        await msg.reply_text("Укажи ник или ответь на сообщение.")
        return
    target = msg.reply_to_message.from_user if msg.reply_to_message else None
    duration = parse_time(args[1]) if len(args) > 1 else 60
    if target:
        punishments[target.id] = ("mute", datetime.now() + timedelta(minutes=duration))
        await msg.reply_text(f"{target.full_name} замучен на {duration} минут.")

async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    args = context.args
    target = msg.reply_to_message.from_user if msg.reply_to_message else None
    if not target:
        return
    warns[target.id] = warns.get(target.id, 0) + 1
    if warns[target.id] >= 3:
        punishments[target.id] = ("mute", datetime.now() + timedelta(minutes=30))
        warns[target.id] = 0
        await msg.reply_text(f"{target.full_name} получил 3/3 варнов и замучен на 30 минут.")
    else:
        await msg.reply_text(f"{target.full_name} получает предупреждение {warns[target.id]}/3.")

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    target = msg.reply_to_message.from_user if msg.reply_to_message else None
    if not target:
        return
    duration = parse_time(context.args[1]) if len(context.args) > 1 else 1440
    punishments[target.id] = ("ban", datetime.now() + timedelta(minutes=duration))
    await msg.reply_text(f"{target.full_name} заблокирован на {duration} минут.")

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    target = msg.reply_to_message.from_user if msg.reply_to_message else None
    if target and punishments.get(target.id, (None,))[0] == "mute":
        punishments.pop(target.id)
        await msg.reply_text(f"{target.full_name} больше не замучен.")

async def unwarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    target = msg.reply_to_message.from_user if msg.reply_to_message else None
    if target and target.id in warns:
        warns[target.id] = 0
        await msg.reply_text(f"{target.full_name} варны сброшены.")

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    target = msg.reply_to_message.from_user if msg.reply_to_message else None
    if target and punishments.get(target.id, (None,))[0] == "ban":
        punishments.pop(target.id)
        await msg.reply_text(f"{target.full_name} разбанен.")

# -------------------- РУССКАЯ РУЛЕТКА --------------------
async def roulette(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg.reply_to_message:
        await msg.reply_text("Ответь на сообщение того, с кем хочешь сыграть в рулетку.")
        return
    opponent = msg.reply_to_message.from_user
    player = msg.from_user
    roulette_games[msg.chat.id] = {
        "player1": player,
        "player2": opponent,
        "lives": {player.id: 2, opponent.id: 2},
        "turn": player.id,
        "bullet_chamber": random.sample([True, False, False, False, False, False], 6),
        "punishment_type": None,
        "confirmed": False
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
        choice = data.split("_")[-1]
        game["punishment_type"] = choice
        # Подтверждение второго игрока
        opp_id = game["player2"].id
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Принять", callback_data="roulette_accept"),
             InlineKeyboardButton("Отклонить", callback_data="roulette_decline")]
        ])
        await query.message.edit_text(f"{game['player1'].full_name} выбрал: {choice.upper()}. {game['player2'].full_name}, подтвердите участие.", reply_markup=keyboard)
    elif data == "roulette_accept":
        game["confirmed"] = True
        await query.message.edit_text("Игра подтверждена! Начинаем первый ход.")
        await play_turn(chat_id, context)
    elif data == "roulette_decline":
        roulette_games.pop(chat_id)
        await query.message.edit_text("Игра отменена.")

async def play_turn(chat_id, context: ContextTypes.DEFAULT_TYPE):
    game = roulette_games.get(chat_id)
    if not game:
        return
    current_id = game["turn"]
    current_name = context.bot.get_chat(chat_id).get_member(current_id).user.full_name
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Выстрелить в себя", callback_data="shoot_self"),
         InlineKeyboardButton("Выстрелить в соперника", callback_data="shoot_opp")]
    ])
    await context.bot.send_message(chat_id, f"Ход {current_name}: выберите действие.", reply_markup=keyboard)

async def roulette_shoot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    game = roulette_games.get(chat_id)
    if not game or not game.get("confirmed"):
        await query.message.edit_text("Игра не активна.")
        return
    shooter_id = game["turn"]
    opponent_id = game["player2"].id if shooter_id == game["player1"].id else game["player1"].id
    shoot_self = query.data == "shoot_self"
    # Рандомный патрон
    bullet = game["bullet_chamber"].pop(0)
    if bullet:
        if shoot_self:
            game["lives"][shooter_id] -= 1
            await query.message.reply_text(f"{context.bot.get_chat(chat_id).get_member(shooter_id).user.full_name} выстрелил в себя и потерял жизнь!")
        else:
            game["lives"][opponent_id] -= 1
            await query.message.reply_text(f"{context.bot.get_chat(chat_id).get_member(shooter_id).user.full_name} выстрелил в соперника! Соперник теряет жизнь.")
    else:
        await query.message.reply_text("Холостой патрон, никто не пострадал.")

    # Проверка проигравшего
    for uid, lives in game["lives"].items():
        if lives <= 0:
            loser = uid
            loser_name = context.bot.get_chat(chat_id).get_member(uid).user.full_name
            punishment = game["punishment_type"]
            if punishment == "mute":
                punishments[loser] = ("mute", datetime.now() + timedelta(minutes=1440))
            elif punishment == "warn":
                warns[loser] = warns.get(loser, 0) + 1
            elif punishment == "ban":
                punishments[loser] = ("ban", datetime.now() + timedelta(minutes=1440))
            await query.message.reply_text(f"{loser_name} проиграл. Применено наказание: {punishment.upper()}")
            roulette_games.pop(chat_id)
            return

    # Следующий ход
    game["turn"] = opponent_id if shooter_id == game["player1"].id else game["player1"].id
    if game["bullet_chamber"]:
        await play_turn(chat_id, context)
    else:
        await query.message.reply_text("Все патроны использованы, игра окончена.")
        roulette_games.pop(chat_id)

# -------------------- Основной запуск --------------------
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
app.add_handler(CallbackQueryHandler(roulette_button, pattern="^roulette_"))
app.add_handler(CallbackQueryHandler(roulette_shoot, pattern="^shoot_"))

print("Бот запущен!")
app.run_polling()
