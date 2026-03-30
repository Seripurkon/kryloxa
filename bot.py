import os
import json
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

TOKEN = "ТВОЙ_ТОКЕН"

OWNER_ID = 5679520675

ECONOMY_FILE = "economy.json"
STATS_FILE = "stats.json"

def load_json(filename, default):
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return default

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

economy = load_json(ECONOMY_FILE, {})
stats = load_json(STATS_FILE, {"daily": {}, "last_chat": {}})

daily_stats = stats["daily"]
last_chat = stats["last_chat"]

roulette_games = {}

def get_balance(uid):
    if str(uid) not in economy:
        economy[str(uid)] = {"balance": 0, "last_bonus": "2000-01-01 00:00:00"}
    return economy[str(uid)]["balance"]

def add_balance(uid, amt):
    get_balance(uid)
    economy[str(uid)]["balance"] += amt
    save_json(ECONOMY_FILE, economy)

# ================= СТАРТ =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Kryvox Bot\n\n"
        "Рулетка (ответом)\n"
        "Баланс\n"
        "Бонус\n"
        "ТП\n"
        "Магазин"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Напиши 'Рулетка' ответом на сообщение")

# ================= МАГАЗИН =================

async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    bal = get_balance(uid)

    kb = [
        [InlineKeyboardButton("Снять мут (1000)", callback_data="unmute")]
    ]

    await update.message.reply_text(
        f"💰 Баланс: {bal} KLC",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def shop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id

    if query.data == "unmute":
        chat_id = last_chat.get(str(uid))

        if not chat_id:
            return await query.answer("Нет данных о группе", show_alert=True)

        await context.bot.restrict_chat_member(
            chat_id,
            uid,
            permissions=ChatPermissions(can_send_messages=True)
        )

        add_balance(uid, -1000)

        await query.edit_message_text("✅ Размут выдан")

# ================= ТЕКСТ =================

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    uid = update.effective_user.id
    chat_id = update.effective_chat.id

    if update.effective_chat.type != "private":
        last_chat[str(uid)] = chat_id
        stats["last_chat"] = last_chat

    if str(uid) not in daily_stats:
        daily_stats[str(uid)] = {"name": update.effective_user.first_name, "count": 0}

    daily_stats[str(uid)]["count"] += 1
    stats["daily"] = daily_stats
    save_json(STATS_FILE, stats)

    if text == "баланс":
        await update.message.reply_text(f"💰 {get_balance(uid)} KLC")

    if text == "бонус":
        add_balance(uid, random.randint(100, 300))
        await update.message.reply_text("🎁 Бонус получен")

    if text == "тп":
        top = sorted(daily_stats.items(), key=lambda x: x[1]["count"], reverse=True)[:10]
        msg = "🏆 Топ:\n"
        for i, (u, d) in enumerate(top, 1):
            msg += f"{i}. {d['name']} — {d['count']}\n"
        await update.message.reply_text(msg)

    if text == "магазин":
        await shop(update, context)

# ================= РУЛЕТКА =================

def reload_chamber(g):
    bullets = random.randint(1, 4)
    g["chamber"] = [True]*bullets + [False]*(6-bullets)
    random.shuffle(g["chamber"])

async def roulette(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.reply_to_message
    if not msg:
        return

    p1 = update.effective_user
    p2 = msg.from_user

    gid = str(update.message.message_id)

    roulette_games[gid] = {
        "p1": p1.id,
        "p2": p2.id,
        "lives": {p1.id: 2, p2.id: 2},
        "turn": p1.id
    }

    reload_chamber(roulette_games[gid])

    kb = [[
        InlineKeyboardButton("Принять", callback_data=f"accept_{gid}"),
        InlineKeyboardButton("Отклонить", callback_data=f"decline_{gid}")
    ]]

    await update.message.reply_text(
        f"{p2.first_name}, тебе вызов!",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def roulette_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.split("_")

    action = data[0]
    gid = data[1]

    if gid not in roulette_games:
        return

    game = roulette_games[gid]
    uid = query.from_user.id

    if action == "accept":
        if uid != game["p2"]:
            return await query.answer("Не твоя кнопка")

        kb = [[
            InlineKeyboardButton("В себя", callback_data=f"shoot_self_{gid}"),
            InlineKeyboardButton("В него", callback_data=f"shoot_opp_{gid}")
        ]]

        await query.edit_message_text("Игра началась!", reply_markup=InlineKeyboardMarkup(kb))

    elif action == "shoot":
        target = data[1]
        gid = data[2]

        game = roulette_games[gid]

        if uid != game["turn"]:
            return

        bullet = game["chamber"].pop(0)

        if target == "self":
            victim = uid
        else:
            victim = game["p2"] if uid == game["p1"] else game["p1"]

        if bullet:
            game["lives"][victim] -= 1
            text = "💥 Попал!"
        else:
            text = "💨 Холостой"

        if game["lives"][victim] <= 0:
            await query.edit_message_text("💀 Игра окончена")
            del roulette_games[gid]
            return

        game["turn"] = game["p2"] if uid == game["p1"] else game["p1"]

        kb = [[
            InlineKeyboardButton("В себя", callback_data=f"shoot_self_{gid}"),
            InlineKeyboardButton("В него", callback_data=f"shoot_opp_{gid}")
        ]]

        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

# ================= ЗАПУСК =================

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))

app.add_handler(MessageHandler(filters.Regex("^[Рр]улетка$"), roulette))
app.add_handler(CallbackQueryHandler(roulette_callback))
app.add_handler(CallbackQueryHandler(shop_callback, pattern="unmute"))

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

print("🚀 Бот запущен")
app.run_polling()
