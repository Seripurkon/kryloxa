import os
import json
import random
import re
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

# ===================== КОНФИГ И ДАННЫЕ =====================

TOKEN = "8641381095:AAGLY3W93LQGfq_Ygm1OIfAMwlhb6SlQrXE"
OWNER_ID = 5679520675 
FRIEND_ID = 782585931
RANKS_FILE = "ranks.json"

# Словари для хранения данных в памяти
warns = {}
roulette_games = {}
daily_stats = {} 
last_reset_day = datetime.now().day

# Загрузка системы рангов
def load_ranks():
    if os.path.exists(RANKS_FILE):
        try:
            with open(RANKS_FILE, "r") as f:
                data = json.load(f)
                return {int(k): v for k, v in data.items()}
        except: 
            pass
    return {OWNER_ID: 4, FRIEND_ID: 3}

# Сохранение рангов
def save_ranks():
    with open(RANKS_FILE, "w") as f:
        json.dump(user_ranks, f)

user_ranks = load_ranks()

# Получение ранга пользователя
def get_rank(user_id):
    if user_id == OWNER_ID: 
        return 4
    if user_id == FRIEND_ID: 
        return 3
    return user_ranks.get(user_id, 0)

# Парсинг времени (1 час, 2 дня и т.д.)
def parse_time(text):
    # Ищем число и слово после него
    match = re.search(r"(\d+)\s*(мин|час|дн|ден|сут)", text.lower())
    if not match:
        # Если слов нет, ищем просто первое число
        simple_match = re.search(r"(\d+)", text)
        return int(simple_match.group(1)) if simple_match else 60
    
    value = int(match.group(1))
    unit = match.group(2)
    
    if "час" in unit:
        return value * 60
    elif "дн" in unit or "ден" in unit or "сут" in unit:
        return value * 1440
    return value # По умолчанию минуты

# Перезарядка рулетки
def reload_chamber(g):
    live = random.randint(1, 4)
    chamber = [True] * live + [False] * (6 - live)
    random.shuffle(chamber)
    g['chamber'] = chamber
    g['info'] = f"Боевых: {live}, Холостых: {6 - live}"

# Сброс ежедневной статистики сообщений
def check_daily_reset():
    global last_reset_day, daily_stats
    current_day = datetime.now().day
    if current_day != last_reset_day:
        daily_stats = {}
        last_reset_day = current_day

# ===================== КОМАНДЫ ПАНЕЛИ =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rank = get_rank(update.effective_user.id)
    text = (
        "Подпишитесь на новостной канал бота и следите за его разработкой @kryloxa_offcial 😊\n\n"
        f"👤 Твой ранг: {rank}\n\n"
        "Список команд - /help"
    )
    await update.message.reply_text(text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rank = get_rank(update.effective_user.id)
    text = (
        "📜 **Список доступных команд:**\n\n"
        "ℹ️ **Общие:**\n"
        "Инфа — статус игрока (ответом)\n"
        "Обо мне — инфо о себе\n"
        "ТП — топ общительных за день\n"
        "Рулетка — дуэль (ответом)\n\n"
    )
    if rank >= 1:
        text += (
            "🛠 **Модерация (ответом):**\n"
            "Молчи [время] — мут (напр. 1 час)\n"
            "Скажи — размут\n"
            "Бан [время] — бан (напр. 2 дня)\n"
            "Разбан — разбан\n"
            "Варн — предупреждение\n"
            "Снять варн — убрать предупреждение\n\n"
        )
    if rank >= 3:
        text += "⭐ **Админка:**\nДать админку [1-3] / Снять админку\n"
    await update.message.reply_text(text, parse_mode="Markdown")

# ===================== ОСНОВНОЙ ОБРАБОТЧИК =====================

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: 
        return
        
    check_daily_reset()
    text = update.message.text.strip().lower()
    user = update.effective_user
    
    # Счётчик сообщений для ТОПа
    if user.id not in daily_stats: 
        daily_stats[user.id] = {"name": user.first_name, "count": 0}
    daily_stats[user.id]["count"] += 1

    # Команда ТОП ДНЯ (ТП)
    if text == "тп":
        if not daily_stats: 
            return await update.message.reply_text("Сегодня еще никто не писал!")
        top_list = sorted(daily_stats.items(), key=lambda x: x[1]["count"], reverse=True)[:10]
        msg_top = "🏆 **Топ общительных за сегодня (ТП):**\n\n"
        for i, (uid, data) in enumerate(top_list, 1): 
            msg_top += f"{i}. {data['name']} — {data['count']} сообщ.\n"
        return await update.message.reply_text(msg_top, parse_mode="Markdown")

    # Команда ОБО МНЕ
    if text == "обо мне":
        rank = get_rank(user.id)
        w = warns.get(user.id, 0)
        msgs = daily_stats.get(user.id, {}).get("count", 0)
        return await update.message.reply_text(
            f"👤 **О вас:**\nИмя: {user.first_name}\nID: `{user.id}`\n⭐ Ранг: {rank}\n⚠️ Варны: {w}/3\n✉️ Сообщений сегодня: {msgs}", 
            parse_mode="Markdown"
        )

    # Работа с ответами на сообщения
    msg = update.message.reply_to_message
    if not msg: 
        return
    
    target_id = msg.from_user.id
    target_rank = get_rank(target_id)
    caller_rank = get_rank(user.id)

    # Команда ИНФА
    if text == "инфа":
        try:
            chat_member = await context.bot.get_chat_member(update.effective_chat.id, target_id)
            w_c = warns.get(target_id, 0)
            status_msg = "✅ Ограничений нет"
            if chat_member.status in ['restricted'] and not chat_member.can_send_messages:
                until = chat_member.until_date
                if until:
                    now = datetime.now(until.tzinfo)
                    diff = until - now
                    ts = diff.total_seconds()
                    if ts > 0:
                        h, m = int(ts // 3600), int((ts % 3600) // 60)
                        if h == 0 and m == 0: m = 1
                        status_msg = f"🔇 В муте (осталось {h}ч {m}м)"
                    else: 
                        status_msg = "✅ Ограничений нет"
                else: 
                    status_msg = "🔇 В муте навсегда"
            await update.message.reply_text(
                f"👤 Пользователь: {msg.from_user.first_name}\n⭐ Ранг: {target_rank}\n⚠️ Варны: {w_c}/3\nСтатус наказания: {status_msg}"
            )
        except: 
            await update.message.reply_text("❌ Ошибка получения данных.")
        return

    # УПРАВЛЕНИЕ РАНГАМИ (Админ 3+)
    if text.startswith("дать админку") and caller_rank >= 3:
        nums = re.findall(r"\d+", text)
        val = int(nums[0]) if nums else 1
        if val >= caller_rank and user.id != OWNER_ID: 
            return await update.message.reply_text("Ранг выше вашего!")
        user_ranks[target_id] = min(3, val)
        save_ranks()
        return await update.message.reply_text(f"⭐ {msg.from_user.first_name} теперь ранг {user_ranks[target_id]}")

    if text == "снять админку" and caller_rank >= 3:
        if target_id in [OWNER_ID, FRIEND_ID]:
            return await update.message.reply_text("Этого админа нельзя снять.")
        if target_id in user_ranks: 
            del user_ranks[target_id]
        save_ranks()
        return await update.message.reply_text(f"❌ {msg.from_user.first_name} разжалован.")

    # МОДЕРАЦИЯ (Ранг 1+)
    if caller_rank < 1: 
        return
    if target_rank >= caller_rank and user.id != OWNER_ID: 
        return

    try:
        if text.startswith("молчи"):
            mins = parse_time(text)
            await context.bot.restrict_chat_member(
                update.effective_chat.id, target_id, 
                permissions={"can_send_messages":False}, 
                until_date=datetime.now()+timedelta(minutes=mins)
            )
            await update.message.reply_text(f"🔇 {msg.from_user.first_name} замолчал на {mins} мин.")

        elif text.startswith("скажи"):
            await context.bot.restrict_chat_member(
                update.effective_chat.id, target_id, 
                permissions={"can_send_messages":True, "can_send_other_messages":True, "can_add_web_page_previews":True}
            )
            await update.message.reply_text(f"🔊 {msg.from_user.first_name} снова говорит.")

        elif text.startswith("бан"):
            mins = parse_time(text)
            await context.bot.ban_chat_member(
                update.effective_chat.id, target_id, 
                until_date=datetime.now()+timedelta(minutes=mins)
            )
            await update.message.reply_text(f"🚫 {msg.from_user.first_name} забанен на {mins} мин.")

        elif text == "разбан":
            await context.bot.unban_chat_member(update.effective_chat.id, target_id, only_if_banned=True)
            await update.message.reply_text(f"✅ {msg.from_user.first_name} разбанен.")

        elif text.startswith("варн"):
            warns[target_id] = warns.get(target_id, 0) + 1
            if warns[target_id] >= 3:
                warns[target_id] = 0
                await context.bot.restrict_chat_member(
                    update.effective_chat.id, target_id, 
                    permissions={"can_send_messages":False}, 
                    until_date=datetime.now()+timedelta(days=1)
                )
                await update.message.reply_text(f"🛑 3/3 варна! {msg.from_user.first_name} мут на 1 день.")
            else: 
                await update.message.reply_text(f"⚠️ Варн {msg.from_user.first_name}: {warns[target_id]}/3")

        elif text == "снять варн":
            warns[target_id] = max(0, warns.get(target_id, 0) - 1)
            await update.message.reply_text(f"✅ Варн снят. Теперь {warns[target_id]}/3")
    except: 
        pass

# ===================== РУЛЕТКА =====================

async def roulette_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.reply_to_message
    if not msg or update.effective_user.id == msg.from_user.id: 
        return
    g_id = str(update.message.message_id)
    roulette_games[g_id] = {
        "p1": update.effective_user.id, "p1_n": update.effective_user.first_name, 
        "p2": msg.from_user.id, "p2_n": msg.from_user.first_name, 
        "lives": {update.effective_user.id: 2, msg.from_user.id: 2}, 
        "turn": msg.from_user.id, "mode": None
    }
    reload_chamber(roulette_games[g_id])
    kb = [[
        InlineKeyboardButton("Варн", callback_data=f"set_warn_{g_id}"), 
        InlineKeyboardButton("Мут (10м)", callback_data=f"set_mute_{g_id}"), 
        InlineKeyboardButton("Бан (1д)", callback_data=f"set_ban_{g_id}")
    ]]
    await update.message.reply_text(f"🎯 Дуэль! {msg.from_user.first_name}, выбирай ставку:", reply_markup=InlineKeyboardMarkup(kb))

async def roulette_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.split("_")
    if len(data) < 3: 
        return
    action, val, g_id = data[0], data[1], data[2]
    if g_id not in roulette_games: 
        return await query.answer("Игра окончена.")
    g = roulette_games[g_id]
    u_id = query.from_user.id
    if u_id not in [g['p1'], g['p2']]: 
        return await query.answer("Это не ваша дуэль!", show_alert=True)

    if action == "set":
        if u_id != g['p2']: 
            return await query.answer("Выбирает тот, кого вызвали!")
        g['mode'] = val
        await update_roulette_msg(query, g, g_id)
    elif action == "mercy":
        await query.edit_message_text(f"🤝 Игра окончена по пощаде!")
        del roulette_games[g_id]
    elif action == "shoot":
        if u_id != g['turn']: 
            return await query.answer("Не твой ход!")
        if not g['chamber']: 
            reload_chamber(g)
        bullet = g['chamber'].pop(0)
        target, res = val, ""
        if target == 'self':
            if bullet:
                g['lives'][u_id] -= 1
                res = "💥 БАХ! Попал в себя!"
                g['turn'] = g['p2'] if u_id == g['p1'] else g['p1']
            else: 
                res = "💨 Холостой! Доп. ход!"
        else:
            opp_id = g['p2'] if u_id == g['p1'] else g['p1']
            if bullet: 
                g['lives'][opp_id] -= 1
                res = f"💥 БАХ! Попадание!"
            else: 
                res = "💨 Холостой... Промах."
            g['turn'] = opp_id

        if any(l <= 0 for l in g['lives'].values()):
            dead_id = next(uid for uid, l in g['lives'].items() if l <= 0)
            await finish_roulette(query, g, dead_id, context)
            if g_id in roulette_games: 
                del roulette_games[g_id]
        else:
            if not g['chamber']: 
                reload_chamber(g)
                res += "\n🔄 Перезарядка!"
            await update_roulette_msg(query, g, g_id, res)

async def update_roulette_msg(query, g, g_id, last=""):
    t_name = g['p1_n'] if g['turn'] == g['p1'] else g['p2_n']
    text = (
        f"{last}\n\n👤 {g['p1_n']}: {'❤️' * g['lives'][g['p1']]}\n👤 {g['p2_n']}: {'❤️' * g['lives'][g['p2']]}\n"
        f"🔋 Ствол: {len(g['chamber'])} ({g['info']})\n\n👉 Ходит: **{t_name}**"
    )
    kb = [[
        InlineKeyboardButton("🎯 В противника", callback_data=f"shoot_opp_{g_id}"), 
        InlineKeyboardButton("🔫 В себя", callback_data=f"shoot_self_{g_id}")
    ]]
    if any(l == 1 for l in g['lives'].values()): 
        kb.append([InlineKeyboardButton("🤝 Пощадить", callback_data=f"mercy_0_{g_id}")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def finish_roulette(query, g, l_id, context):
    l_name = g['p1_n'] if l_id == g['p1'] else g['p2_n']
    mode, txt = g['mode'], f"💀 **{l_name} ПРОИГРАЛ!**\nНаказание: {g['mode'].capitalize()}"
    try:
        chat_id = query.message.chat_id
        if mode == "mute": 
            await context.bot.restrict_chat_member(chat_id, l_id, permissions={"can_send_messages":False}, until_date=datetime.now()+timedelta(minutes=10))
        elif mode == "ban": 
            await context.bot.ban_chat_member(chat_id, l_id, until_date=datetime.now()+timedelta(days=1))
        elif mode == "warn":
            warns[l_id] = warns.get(l_id, 0) + 1
            if warns[l_id] >= 3:
                warns[l_id] = 0
                await context.bot.restrict_chat_member(chat_id, l_id, permissions={"can_send_messages":False}, until_date=datetime.now()+timedelta(days=1))
                txt += "\n🛑 3/3 варна! Мут на 1 день!"
    except: 
        txt += "\n(Нет прав)"
    await query.edit_message_text(txt, parse_mode="Markdown")

# ===================== ЗАПУСК =====================

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^[Рр]улетка$"), roulette_command))
    app.add_handler(CallbackQueryHandler(roulette_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    print("🚀 Бот запущен!")
    app.run_polling()
