import random
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters

# Ваш токен
TOKEN = "ВАШ_ТОКЕН_ЗДЕСЬ"

# Администраторы и привилегии
admins = {5679520675: 4}  # Ваш ID с максимальной привилегией
warnings = {}  # словарь: chat_id -> {user_id: [timestamp1, timestamp2,...]}

# Русская рулетка
roulette_games = {}  # chat_id -> {"player1": user, "player2": user, "punishment_type": str, "bullet_chamber": [], "confirmed": False, "lives": {}}

# ------------------ Команды ------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот для администрирования.\n"
        "Используй команды: мут, варн, бан, снять мут, снять варн, разбан.\n"
        "В группе доступна команда /start."
    )

# ---- Административные команды ----
async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Команда должна быть ответом на сообщение пользователя.")
        return
    user = update.message.reply_to_message.from_user
    chat_id = update.message.chat.id
    await update.message.reply_text(f"{user.full_name} замучен на 1 день.")
    
async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Команда должна быть ответом на сообщение пользователя.")
        return
    user = update.message.reply_to_message.from_user
    await update.message.reply_text(f"{user.full_name} снят мут.")

async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Команда должна быть ответом на сообщение пользователя.")
        return
    user = update.message.reply_to_message.from_user
    chat_id = update.message.chat.id
    warnings.setdefault(chat_id, {}).setdefault(user.id, [])
    warnings[chat_id][user.id].append(1)
    count = len(warnings[chat_id][user.id])
    if count >= 3:
        await update.message.reply_text(f"{user.full_name} получил 3/3 варна и замучен на 30 минут.")
        warnings[chat_id][user.id] = []
    else:
        await update.message.reply_text(f"{user.full_name} получает предупреждение {count}/3.")

async def unwarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Команда должна быть ответом на сообщение пользователя.")
        return
    user = update.message.reply_to_message.from_user
    chat_id = update.message.chat.id
    if chat_id in warnings and user.id in warnings[chat_id]:
        warnings[chat_id][user.id] = []
    await update.message.reply_text(f"{user.full_name} снят варн.")

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Команда должна быть ответом на сообщение пользователя.")
        return
    user = update.message.reply_to_message.from_user
    await update.message.reply_text(f"{user.full_name} заблокирован в этом чате на 1 день.")

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Команда должна быть ответом на сообщение пользователя.")
        return
    user = update.message.reply_to_message.from_user
    await update.message.reply_text(f"{user.full_name} разбанен.")

# ------------------ Русская рулетка ------------------
async def roulette(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Вы должны ответить на сообщение того, с кем хотите сыграть в рулетку и написать 'Рулетка'.")
        return
    if update.message.text.lower() != "рулетка":
        return

    player1 = update.message.from_user
    player2 = update.message.reply_to_message.from_user
    chat_id = update.message.chat.id
    bullets = [True, True, False, False, False, False]  # 2 с порохом, 4 холостые
    random.shuffle(bullets)

    roulette_games[chat_id] = {
        "player1": player1,
        "player2": player2,
        "punishment_type": None,
        "bullet_chamber": bullets,
        "confirmed": False,
        "lives": {player1.id: 2, player2.id: 2}
    }

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Варн", callback_data="roulette_choice_warn"),
         InlineKeyboardButton("Мут", callback_data="roulette_choice_mute"),
         InlineKeyboardButton("Бан", callback_data="roulette_choice_ban")]
    ])
    await update.message.reply_text(f"{player1.full_name} предложил игру {player2.full_name}.\nВыберите, на что играть:", reply_markup=keyboard)

async def roulette_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat.id
    game = roulette_games.get(chat_id)
    if not game:
        await query.message.edit_text("Игра не найдена.")
        return

    # Выбор ставки первым игроком
    if data.startswith("roulette_choice_"):
        choice = data.split("_")[-1]
        if query.from_user.id != game["player1"].id:
            await query.message.answer("Только тот, кто предложил игру, может выбирать ставку.")
            return
        game["punishment_type"] = choice
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Принять", callback_data="roulette_accept"),
             InlineKeyboardButton("Отклонить", callback_data="roulette_decline")]
        ])
        await query.message.edit_text(f"{game['player1'].full_name} выбрал: {choice.upper()}. "
                                      f"{game['player2'].full_name}, подтвердите участие.", reply_markup=keyboard)

    # Подтверждение второго игрока
    elif data == "roulette_accept":
        if query.from_user.id != game["player2"].id:
            await query.message.answer("Только приглашенный игрок может подтвердить участие.")
            return
        game["confirmed"] = True

        # Ознакомительное сообщение
        bullets = game["bullet_chamber"]
        total = len(bullets)
        live_bullets = sum(1 for b in bullets if b)
        empty_bullets = total - live_bullets
        await query.message.edit_text(
            f"Игра подтверждена! Начинаем.\n"
            f"Всего патронов: {total}\n"
            f"Холостые: {empty_bullets}, с порохом: {live_bullets}\n"
            f"У каждого игрока 2 жизни.\n"
            f"Используйте кнопки 'Выстрелить в себя' или 'Выстрелить в соперника'.\n"
            f"Если вы потеряете все жизни, применится выбранное наказание: {game['punishment_type'].upper()}."
        )

    elif data == "roulette_decline":
        if query.from_user.id != game["player2"].id:
            await query.message.answer("Только приглашенный игрок может отклонить игру.")
            return
        roulette_games.pop(chat_id)
        await query.message.edit_text("Игра отклонена.")

# ------------------ Основное ------------------
app = ApplicationBuilder().token(TOKEN).build()

# Команды
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.Regex(r"^(мут|варн|бан|снять мут|снять варн|разбан)$"), lambda u, c: None))  # тут нужно привязать функции по тексту
app.add_handler(MessageHandler(filters.Regex(r"Рулетка"), roulette))
app.add_handler(CallbackQueryHandler(roulette_button))

app.run_polling()
