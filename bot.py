import os
import json
import random
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CallbackQueryHandler, CommandHandler
from telegram.request import HTTPXRequest

# --- НАСТРОЙКИ ---
TOKEN = "8641381095:AAH44UdW5z66BkX0rO5qKHOcdESAoghso_g"
OWNER_ID = 5679520675
TESTER_ID = 782585931 #for testing purpose
ECONOMY_FILE = "economy.json"
RANKS_FILE = "ranks.json"
BOT_VERSION = "0.9.6"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- РАБОТА С ДАННЫМИ ---
def load_json(filename, default):
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {int(k): v for k, v in data.items()}
        except: return default
    return default

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

user_ranks = load_json(RANKS_FILE, {OWNER_ID: 4, TESTER_ID: 4})
user_balance = load_json(ECONOMY_FILE, {})
warns = {}
roulette_games = {}
daily_stats = {}
bonus_timers = {}

def get_rank(user_id):
    if user_id == OWNER_ID: return 4
    return user_ranks.get(user_id, 0)

def reload_chamber(g):
    chamber = [True, True, True, False, False, False]
    random.shuffle(chamber)
    g['chamber'] = chamber

# --- ФУНКЦИЯ ПРОФИЛЯ ---
async def show_profile(update: Update, user):
    u_id = user.id
    if u_id == OWNER_ID:
        bal_text = "∞ (Owner)"
    else:
        bal_text = f"{user_balance.get(u_id, 0)} KLC"
    
    text = (
        f"👤 Профиль пользователя {user.first_name}:**\n"
        f"🆔 ID: `{u_id}`\n"
        f"⭐️ Ранг: {get_rank(u_id)}\n"
        f"💰 Баланс: {bal_text}\n"
        f"⚠️ Варны: {warns.get(u_id, 0)}/3\n"
        f"────────────────\n"
        f"🤖 Версия: `{BOT_VERSION}`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# --- КОМАНДЫ ---
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Бот запущен в режиме Beta! Напиши /help.")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        f"📜 **СПИСОК КОМАНД ({BOT_VERSION})**\n\n"
        "🕹 **Меню: /start, /help, /magaz\n"
        "💰 Экономика: баланс (б), бонус, тп, обо мне\n"
        "💸 Передача: передать [сумма] (ответом)\n"
        "🛡 Модер: инфа, молчи, скажи, бан, варн (ответом)\n"
        "🎲 Игра: Рулетка (ответом)"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def magaz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    bal = user_balance.get(user.id, 0) if user.id != OWNER_ID else "∞"
    text = (
        f"🛒 **Kryloxa Shop {BOT_VERSION}**\n"
        f"👋 Привет, {user.first_name}!\n\n"
        f"💰 Твой баланс: {bal} KLC\n"
        f"Выберите услугу:"
    )
    kb = [[InlineKeyboardButton("🚫 Снять мут (1000 KLC)", callback_data="buy_unmute")],
          [InlineKeyboardButton("⚠️ Снять варн (500 KLC)", callback_data="buy_unwarn")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def shop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    u_id = q.from_user.id
    bal = user_balance.get(u_id, 0)
    
    if q.data == "buy_unmute":
        if u_id == OWNER_ID or bal >= 1000:
            if u_id != OWNER_ID: user_balance[u_id] -= 1000
            save_json(ECONOMY_FILE, user_balance)
            try:
                await context.bot.unban_chat_member(q.message.chat_id, u_id, only_if_banned=False)
                await q.answer("✅ Ограничения сняты!", show_alert=True)
            except: await q.answer("❌ Ошибка прав.")
        else: await q.answer("❌ Недостаточно KLC!", show_alert=True)
    
    elif q.data == "buy_unwarn":
        if u_id == OWNER_ID or bal >= 500:
            if warns.get(u_id, 0) > 0:
                if u_id != OWNER_ID: user_balance[u_id] -= 500
                warns[u_id] -= 1
                save_json(ECONOMY_FILE, user_balance)
                await q.answer("✅ Варн снят!", show_alert=True)
            else: await q.answer("❌ У вас нет варнов.")
        else: await q.answer("❌ Недостаточно KLC!", show_alert=True)

# --- ГЛАВНЫЙ ОБРАБОТЧИК ---
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    
    # Система причин (через новую строку)
    lines = update.message.text.split('\n', 1)
    first_line = lines[0].strip().lower()
    reason = lines[1].strip() if len(lines) > 1 else "Не указана"
    cmd_parts = first_line.split()
    main_cmd = cmd_parts[0] if cmd_parts else ""
    
    user, chat_id, msg = update.effective_user, update.effective_chat.id, update.message.reply_to_message

    if user.id not in daily_stats: daily_stats[user.id] = {"name": user.first_name, "count": 0}
    daily_stats[user.id]["count"] += 1

    if first_line == "тп":
        top_list = sorted(daily_stats.items(), key=lambda x: x[1]['count'], reverse=True)[:10]
        res = "📊 **ТОП ОБЩИТЕЛЬНЫХ:**\n\n"
        for i, (uid, data) in enumerate(top_list, 1):
            res += f"{i}. {data['name']} — {data['count']} сообщ.\n"
        return await update.message.reply_text(res, parse_mode="Markdown")

    if first_line == "обо мне":
        return await show_profile(update, user)

    if first_line in ["баланс", "б"]:
        bal = "∞" if user.id == OWNER_ID else user_balance.get(user.id, 0)
        await update.message.reply_text(f"💰 Баланс {user.first_name}: {bal} KLC")

    elif first_line == "бонус":
        now = datetime.now()
        if user.id in bonus_timers and now < bonus_timers[user.id] + timedelta(days=1):
            return await update.message.reply_text("❌ Бонус доступен раз в 24 часа!")
        amt = random.randint(150, 600)
        if user.id != OWNER_ID:
            user_balance[user.id] = user_balance.get(user.id, 0) + amt
        bonus_timers[user.id] = now
        save_json(ECONOMY_FILE, user_balance)
        await update.message.reply_text(f"🎁 +{amt} KLC!")

    if msg:
        t_id = msg.from_user.id
        c_rank, t_rank = get_rank(user.id), get_rank(t_id)

        if main_cmd == "передать":
            try:
                amount = int(cmd_parts[1])
                if user.id != OWNER_ID and user_balance.get(user.id, 0) < amount:
                    return await update.message.reply_text("❌ Недостаточно KLC")
                if user.id != OWNER_ID: user_balance[user.id] -= amount
                user_balance[t_id] = user_balance.get(t_id, 0) + amount
                save_json(ECONOMY_FILE, user_balance)
                await update.message.reply_text(f"✅ Передано {amount} KLC пользователю {msg.from_user.first_name}")
            except: await update.message.reply_text("❌ Формат: передать 100")
            return

        if main_cmd == "инфа":
            return await show_profile(update, msg.from_user)

        if c_rank >= 1 and (t_rank < c_rank or user.id == OWNER_ID):
            try:
                if main_cmd == "молчи":
                    await context.bot.restrict_chat_member(chat_id, t_id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(hours=1))
                    await update.message.reply_text(f"🤫 Тишина на час.\n📝 Причина: {reason}")
                elif main_cmd == "скажи":
                    # Твой друг доделает, я оставил базовый unban
                    await context.bot.restrict_chat_member(chat_id,t_id,permissions=ChatPermissions(
                            can_send_messages=True,
                            can_send_media_messages=True,
                            can_send_other_messages=True,
                            can_add_web_page_previews=True
                        )
                    )
                    await update.message.reply_text("🔊 Пользователь снова может писать")
                elif main_cmd == "бан":
                    await context.bot.ban_chat_member(chat_id, t_id, until_date=datetime.now()+timedelta(days=1))
                    await update.message.reply_text(f"🚫 Бан на день.\n📝 Причина: {reason}")
                elif main_cmd == "варн":
                    warns[t_id] = warns.get(t_id, 0) + 1
                    await update.message.reply_text(f"⚠️ Варн выдан ({warns[t_id]}/3)\n📝 Причина: {reason}")
            except: pass

# --- РУЛЕТКА ---
async def roulette_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.reply_to_message
    if not msg or update.effective_user.id == msg.from_user.id: return
    p1, p2 = update.effective_user, msg.from_user
    g_id = f"{p1.id}_{p2.id}_{random.randint(100,999)}"
    roulette_games[g_id] = {"p1": p1.id, "p1_n": p1.first_name, "p2": p2.id, "p2_n": p2.first_name, "lives": {p1.id: 2, p2.id: 2}, "turn": p2.id, "bet_type": None}
    text = (f"🎲 **ДУЭЛЬ!**\n\n👤 {p1.first_name} VS {p2.first_name}\n🔫 Барабан: 6 патронов\n\n👉 {p2.first_name}, выбирай ставку:")
    kb = [[InlineKeyboardButton("Варн", callback_data=f"rbet_warn_{g_id}"), InlineKeyboardButton("Мут", callback_data=f"rbet_mute_{g_id}")],
          [InlineKeyboardButton("Бан (1д)", callback_data=f"rbet_ban_{g_id}"), InlineKeyboardButton("100 KLC", callback_data=f"rbet_klc_{g_id}")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def rt_bet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    _, b, g_id = q.data.split("_", 2)
    if g_id not in roulette_games or q.from_user.id != roulette_games[g_id]['p2']: return
    roulette_games[g_id]['bet_type'] = b
    reload_chamber(roulette_games[g_id])
    await update_ui(q, g_id, "🔥 БОЙ НАЧАЛСЯ!")

async def update_ui(q, g_id, status):
    g = roulette_games[g_id]
    t_n = g['p1_n'] if g['turn'] == g['p1'] else g['p2_n']
    l, bl = g['chamber'].count(True), g['chamber'].count(False)
    txt = (f"🎰 Ставка: {g['bet_type'].upper()}\n🔫 Патроны: {len(g['chamber'])} (🔥 {l} | ❄️ {bl})\n\n📢 {status}\n👤 {g['p1_n']}: {'❤️'*g['lives'][g['p1']]}\n👤 {g['p2_n']}: {'❤️'*g['lives'][g['p2']]}\n👉 Ход: {t_n}")
    kb = [[InlineKeyboardButton("🎯 Оппонент", callback_data=f"rt_opp_{g_id}"), InlineKeyboardButton("🔫 Себя", callback_data=f"rt_self_{g_id}")]]
    await q.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(kb))

async def rt_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    _, act, g_id = q.data.split("_", 2)
    if g_id not in roulette_games or q.from_user.id != roulette_games[g_id]['turn']: return
    g = roulette_games[g_id]
    hit = g['chamber'].pop(0)
    curr, opp = g['turn'], (g['p2'] if g['turn'] == g['p1'] else g['p1'])
    
    if act == "opp":
        if hit: g['lives'][opp] -= 1; msg = "💥 БАХ!"
        else: msg = "💨 Холостой!"; g['turn'] = opp
    else:
        if hit: g['lives'][curr] -= 1; msg = "💥 БАХ! Самострел!"; g['turn'] = opp
        else: msg = "💨 Холостой! Доп. ход."

    if any(l <= 0 for l in g['lives'].values()):
        winner_id = g['p1'] if g['lives'][g['p2']] <= 0 else g['p2']
        loser_id = g['p2'] if winner_id == g['p1'] else g['p1']
        w_name, l_name = (g['p1_n'], g['p2_n']) if winner_id == g['p1'] else (g['p2_n'], g['p1_n'])
        bet, pun = g['bet_type'], ""
        try:
            if bet == "warn":
                warns[loser_id] = warns.get(loser_id, 0) + 1
                pun = f"⚠️ {l_name} получает ВАРН!"
            elif bet == "mute":
                await context.bot.restrict_chat_member(q.message.chat_id, loser_id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(hours=1))
                pun = f"🤫 {l_name} в МУТЕ на час!"
            elif bet == "ban":
                await context.bot.ban_chat_member(q.message.chat_id, loser_id, until_date=datetime.now()+timedelta(days=1))
                pun = f"🚫 {l_name} ЗАБАНЕН на день!"
            elif bet == "klc":
                if loser_id != OWNER_ID: user_balance[loser_id] = user_balance.get(loser_id, 0) - 100
                user_balance[winner_id] = user_balance.get(winner_id, 0) + 100
                save_json(ECONOMY_FILE, user_balance)
                pun = f"💰 {l_name} теряет 100 KLC, а {w_name} их забирает!"
        except: pun = "⚠️ Ошибка прав."
        await q.edit_message_text(f"{msg}\n\n🏆 **Победил {w_name}!**\n{pun}", parse_mode="Markdown")
        del roulette_games[g_id]
    else:
        if not g['chamber']: reload_chamber(g)
        await update_ui(q, g_id, msg)

# --- ЗАПУСК ---
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).request(HTTPXRequest(connect_timeout=20)).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("magaz", magaz_cmd))
    app.add_handler(CallbackQueryHandler(shop_callback, pattern="^buy_"))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^[Рр]улетка$"), roulette_start))
    app.add_handler(CallbackQueryHandler(rt_bet_callback, pattern="^rbet_"))
    app.add_handler(CallbackQueryHandler(rt_action_callback, pattern="^rt_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.run_polling(drop_pending_updates=True)
