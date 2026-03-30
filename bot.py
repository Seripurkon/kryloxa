import os
import json
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Chat
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

# --- КОНФИГ ---
TOKEN = "8641381095:AAGLY3W93LQGfq_Ygm1OIfAMwlhb6SlQrXE"
OWNER_ID = 5679520675 
FRIEND_ID = 782585931
RANKS_FILE = "ranks.json"
ECONOMY_FILE = "economy.json"

# --- СИСТЕМА ХРАНЕНИЯ ---
def load_json(filename, default):
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {int(k): v for k, v in data.items()}
        except: pass
    return default

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

user_ranks = load_json(RANKS_FILE, {OWNER_ID: 4, FRIEND_ID: 3})
user_balance = load_json(ECONOMY_FILE, {})
warns = {}
roulette_games = {}
daily_stats = {} 
bonus_timers = {}
last_reset_day = datetime.now().day

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def get_rank(user_id):
    if user_id == OWNER_ID: return 4
    if user_id == FRIEND_ID: return 3
    return user_ranks.get(user_id, 0)

def check_daily_reset():
    global last_reset_day, daily_stats
    current_day = datetime.now().day
    if current_day != last_reset_day:
        daily_stats = {}
        last_reset_day = current_day

def reload_chamber(g):
    live = random.randint(1, 4)
    chamber = [True] * live + [False] * (6 - live)
    random.shuffle(chamber)
    g['chamber'] = chamber
    g['info'] = f"Боевых: {live}, Холостых: {6 - live}"

# --- МАГАЗИН (КОМАНДА /MAGAZ) ---
async def send_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == Chat.PRIVATE:
        return await update.message.reply_text("❌ Магазин доступен только в группах!")

    user = update.effective_user
    bal = user_balance.get(user.id, 0)
    
    shop_msg = (
        f"👋 **Здравствуйте, {user.first_name}!**\n\n"
        "🛍 **Добро пожаловать в Kryloxa Shop!**\n"
        "————————————————\n"
        "Ниже вы можете выбрать доступные функции магазина.\n"
        "Используйте свои **KLC** с умом, чтобы снять ограничения или варны. 😎\n\n"
        f"💰 Твой баланс: `{bal}` KLC\n"
        "————————————————\n"
        "Выберите услугу:"
    )
    
    keyboard = [[
        InlineKeyboardButton("🕊 Снять мут (1000 KLC)", callback_data=f"shop_mute_{user.id}"),
        InlineKeyboardButton("⚠️ Снять варн (500 KLC)", callback_data=f"shop_warn_{user.id}")
    ]]
    await update.message.reply_text(shop_msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# --- ГЛАВНЫЙ ОБРАБОТЧИК ТЕКСТА ---
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    check_daily_reset()
    
    text = update.message.text.strip().lower()
    user = update.effective_user
    chat_id = update.effective_chat.id
    msg = update.message.reply_to_message
    cmd_parts = text.split()

    # Счётчик ТП
    if user.id not in daily_stats:
        daily_stats[user.id] = {"name": user.first_name, "count": 0}
    daily_stats[user.id]["count"] += 1

    if text == "магазин":
        await send_shop(update, context)
        return

    # Экономика
    if text == "бонус":
        now = datetime.now()
        last = bonus_timers.get(user.id)
        if last and now < last + timedelta(days=1):
            rem = (last + timedelta(days=1)) - now
            return await update.message.reply_text(f"⏳ Бонус через {int(rem.total_seconds()//3600)}ч {int((rem.total_seconds()%3600)//60)}м")
        
        amt = random.randint(150, 500)
        user_balance[user.id] = user_balance.get(user.id, 0) + amt
        bonus_timers[user.id] = now
        save_json(ECONOMY_FILE, user_balance)
        return await update.message.reply_text(f"🎁 +{amt} KLC! Баланс: {user_balance[user.id]} KLC 🪙")

    if text in ["баланс", "б"]:
        return await update.message.reply_text(f"💰 Баланс {user.first_name}: {user_balance.get(user.id, 0)} KLC")

    if text == "тп":
        top = sorted(daily_stats.items(), key=lambda x: x[1]["count"], reverse=True)[:10]
        res = "🏆 **Топ дня:**\n" + "\n".join([f"{i+1}. {d['name']} — {d['count']}" for i, (uid, d) in enumerate(top)])
        return await update.message.reply_text(res, parse_mode="Markdown")

    if text == "обо мне":
        bal = user_balance.get(user.id, 0)
        res = f"👤 **Профиль:**\n⭐ Ранг: {get_rank(user.id)}\n💰 Баланс: {bal} KLC\n⚠️ Варны: {warns.get(user.id, 0)}/3"
        return await update.message.reply_text(res, parse_mode="Markdown")

    # Команды ответом
    if not msg: return
    target_id = msg.from_user.id
    target_rank = get_rank(target_id)
    caller_rank = get_rank(user.id)

    if text == "инфа":
        try:
            chat_member = await context.bot.get_chat_member(chat_id, target_id)
            status_msg = "✅ Чист"
            if chat_member.status == 'restricted' and not chat_member.can_send_messages:
                until = chat_member.until_date
                if until:
                    now = datetime.now(until.tzinfo)
                    diff = until - now
                    if diff.total_seconds() > 0:
                        h, m = int(diff.total_seconds()//3600), int((diff.total_seconds()%3600)//60)
                        status_msg = f"🔇 Мут (осталось {h}ч {m}м)"
                else: status_msg = "🔇 Мут навсегда"
            res = (f"👤 {msg.from_user.first_name}\n⭐ Ранг: {target_rank}\n"
                   f"💰 Баланс: {user_balance.get(target_id, 0)} KLC\n⚠️ Варны: {warns.get(target_id, 0)}/3\n📊 Статус: {status_msg}")
            await update.message.reply_text(res)
        except: pass

    # Модерация (rank 1+)
    if caller_rank >= 1 and (target_rank < caller_rank or user.id == OWNER_ID):
        try:
            if text.startswith("молчи"):
                m = int(cmd_parts[1]) if len(cmd_parts) > 1 and cmd_parts[1].isdigit() else 60
                await context.bot.restrict_chat_member(chat_id, target_id, permissions={"can_send_messages":False}, until_date=datetime.now()+timedelta(minutes=m))
                await update.message.reply_text(f"🔇 {msg.from_user.first_name} в муте на {m} мин.")
            elif text == "скажи":
                await context.bot.restrict_chat_member(chat_id, target_id, permissions={"can_send_messages":True, "can_send_other_messages":True, "can_add_web_page_previews":True})
                await update.message.reply_text(f"🔊 {msg.from_user.first_name} размучен.")
            elif text == "варн":
                warns[target_id] = warns.get(target_id, 0) + 1
                if warns[target_id] >= 3:
                    warns[target_id] = 0
                    await context.bot.restrict_chat_member(chat_id, target_id, permissions={"can_send_messages":False}, until_date=datetime.now()+timedelta(minutes=30))
                    await update.message.reply_text(f"🛑 3/3 варна! Мут на 30м.")
                else: await update.message.reply_text(f"⚠️ Варн {msg.from_user.first_name}: {warns[target_id]}/3")
        except: pass

# --- ЛОГИКА РУЛЕТКИ ---
async def roulette_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.reply_to_message
    if not msg or update.effective_user.id == msg.from_user.id:
        return await update.message.reply_text("Ответь на сообщение противника!")
    
    g_id = str(update.message.message_id)
    p1, p2 = update.effective_user, msg.from_user
    roulette_games[g_id] = {"p1": p1.id, "p1_n": p1.first_name, "p2": p2.id, "p2_n": p2.first_name, "lives": {p1.id: 2, p2.id: 2}, "turn": p2.id, "mode": None}
    reload_chamber(roulette_games[g_id])
    
    kb = [[InlineKeyboardButton("Варн", callback_data=f"set_warn_{g_id}"),
           InlineKeyboardButton("Мут (10м)", callback_data=f"set_mute_{g_id}"),
           InlineKeyboardButton("Бан (1д)", callback_data=f"set_ban_{g_id}")]]
    await update.message.reply_text(f"👊 {p2.first_name}, выбирай ставку дуэли:", reply_markup=InlineKeyboardMarkup(kb))

async def update_roulette_msg(query, g, g_id, last=""):
    t_name = g['p1_n'] if g['turn'] == g['p1'] else g['p2_n']
    text = (f"{last}\n\n👤 {g['p1_n']}: {'❤️' * g['lives'][g['p1']]}\n👤 {g['p2_n']}: {'❤️' * g['lives'][g['p2']]}\n"
            f"🔋 Ствол: {len(g['chamber'])} ({g['info']})\n\n👉 Ходит: **{t_name}**")
    kb = [[InlineKeyboardButton("🎯 В противника", callback_data=f"shoot_opp_{g_id}"),
           InlineKeyboardButton("🔫 В себя", callback_data=f"shoot_self_{g_id}")]]
    if any(l == 1 for l in g['lives'].values()):
        kb.append([InlineKeyboardButton("🤝 Пощадить", callback_data=f"mercy_0_{g_id}")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

# --- ОБЩИЙ ОБРАБОТЧИК КНОПОК ---
async def universal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.split("_")
    action, val, g_id = data[0], data[1], data[2]
    u_id = query.from_user.id

    if action == "shop":
        if u_id != int(g_id): return await query.answer("Это не ваш магазин!", show_alert=True)
        user_bal = user_balance.get(u_id, 0)
        if val == "mute":
            price = 1000
            if user_bal < price: return await query.answer(f"❌ Нужно {price} KLC!", show_alert=True)
            try:
                await context.bot.restrict_chat_member(query.message.chat_id, u_id, permissions={"can_send_messages": True, "can_send_other_messages": True, "can_add_web_page_previews": True})
                user_balance[u_id] -= price; save_json(ECONOMY_FILE, user_balance); await query.edit_message_text("🕊 Свобода куплена!")
            except: await query.answer("Ошибка!", show_alert=True)
        elif val == "warn":
            price = 500
            if warns.get(u_id, 0) <= 0: return await query.answer("0 варнов!", show_alert=True)
            if user_bal < price: return await query.answer(f"❌ Нужно {price} KLC!", show_alert=True)
            user_balance[u_id] -= price; warns[u_id] -= 1; save_json(ECONOMY_FILE, user_balance); await query.edit_message_text("⚠️ Варн снят!")

    elif g_id in roulette_games:
        g = roulette_games[g_id]
        if action == "set":
            if u_id != g['p2']: return await query.answer("Выбирает тот, кого вызвали!")
            g['mode'] = val
            await update_roulette_msg(query, g, g_id)
        elif action == "mercy":
            await query.edit_message_text(f"🤝 {query.from_user.first_name} пощадил соперника!")
            del roulette_games[g_id]
        elif action == "shoot":
            if u_id != g['turn']: return await query.answer("Не твой ход!")
            bullet = g['chamber'].pop(0)
            if val == 'self':
                if bullet:
                    g['lives'][u_id] -= 1; res = "💥 БАХ! В себя!"
                    g['turn'] = g['p2'] if u_id == g['p1'] else g['p1']
                else: res = "💨 Холостой! Доп. ход!"
            else:
                opp = g['p2'] if u_id == g['p1'] else g['p1']
                if bullet: g['lives'][opp] -= 1; res = "💥 ПОПАЛ!"
                else: res = "💨 Мимо..."
                g['turn'] = opp
            
            if any(l <= 0 for l in g['lives'].values()):
                l_id = next(uid for uid, l in g['lives'].items() if l <= 0)
                txt = f"💀 Погиб: {g['p1_n'] if l_id == g['p1'] else g['p2_n']}!"
                try:
                    if g['mode'] == "mute": await context.bot.restrict_chat_member(query.message.chat_id, l_id, permissions={"can_send_messages":False}, until_date=datetime.now()+timedelta(minutes=10))
                except: pass
                await query.edit_message_text(txt); del roulette_games[g_id]
            else:
                if not g['chamber']: reload_chamber(g)
                await update_roulette_msg(query, g, g_id, res)

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("magaz", send_shop))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^[Рр]улетка$"), roulette_command))
    app.add_handler(CallbackQueryHandler(universal_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    print("🚀 Kryloxa Bot готов!")
    app.run_polling()
