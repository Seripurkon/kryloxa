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
ECONOMY_FILE = "economy.json"
STATS_FILE = "stats.json"

# --- ЗАГРУЗКА / СОХРАНЕНИЕ ---
def load_json(filename, default):
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return default

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# Инициализация
user_ranks = {int(k): v for k, v in load_json(RANKS_FILE, {}).items()}
user_ranks[OWNER_ID] = 4
user_ranks[FRIEND_ID] = 3

economy = {int(k): v for k, v in load_json(ECONOMY_FILE, {}).items()}
# Добавили last_chat для привязки к группе
stats_data = load_json(STATS_FILE, {"daily": {}, "warns": {}, "last_chat": {}, "last_reset": datetime.now().strftime("%Y-%m-%d")})
daily_stats = {int(k): v for k, v in stats_data.get("daily", {}).items()}
warns = {int(k): v for k, v in stats_data.get("warns", {}).items()}
last_chat = {int(k): v for k, v in stats_data.get("last_chat", {}).items()}

roulette_games = {}

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def get_rank(user_id):
    if user_id == OWNER_ID: return 4
    if user_id == FRIEND_ID: return 3
    return user_ranks.get(user_id, 0)

def get_balance(user_id):
    if user_id not in economy:
        economy[user_id] = {"balance": 0, "last_bonus": "2000-01-01 00:00:00"}
    return economy[user_id]["balance"]

def add_balance(user_id, amount):
    get_balance(user_id)
    economy[user_id]["balance"] += amount
    save_json(ECONOMY_FILE, economy)

async def check_daily_reset(context: ContextTypes.DEFAULT_TYPE, chat_id):
    global daily_stats, stats_data
    today = datetime.now().strftime("%Y-%m-%d")
    if today != stats_data["last_reset"]:
        if daily_stats:
            top = sorted(daily_stats.items(), key=lambda x: x["count"], reverse=True)[:3]
            rewards = {0: 100, 1: 50, 2: 25}
            medals = ["🥇", "🥈", "🥉"]
            msg = "🔔 **Итоги вчерашнего дня!**\nНаграды KLC начислены:\n"
            for i, (uid, data) in enumerate(top):
                amt = rewards.get(i, 0)
                add_balance(uid, amt)
                msg += f"{medals[i]} {data['name']} — **+{amt} KLC**\n"
            try: await context.bot.send_message(chat_id, msg, parse_mode="Markdown")
            except: pass
        daily_stats = {}
        stats_data["daily"] = {}
        stats_data["last_reset"] = today
        save_json(STATS_FILE, stats_data)

def reload_chamber(g):
    live = random.randint(1, 4)
    g['chamber'] = [True] * live + [False] * (6 - live); random.shuffle(g['chamber'])
    g['info'] = f"Боевых: {live}, Холостых: {6 - live}"

# ===================== МАГАЗИН С ПРИВЯЗКОЙ К ГРУППЕ =====================

async def shop_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u_id = update.effective_user.id
    bal = get_balance(u_id)
    text = (f"🏪 **Магазин Kryloxa Coin**\n\n"
            f"💰 Ваш баланс: **{bal} KLC**\n"
            f"Выберите товар:")
    
    kb = [
        [InlineKeyboardButton("🧹 Снять 1 варн (500 KLC)", callback_data="shop_ask_warn")],
        [InlineKeyboardButton("🔊 Снять мут (1000 KLC)", callback_data="shop_ask_mute")],
        [InlineKeyboardButton("❌ Закрыть", callback_data="shop_close")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def shop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    u_id = query.from_user.id
    data = query.data
    bal = get_balance(u_id)

    if data == "shop_close": return await query.message.delete()
    if data == "shop_back":
        kb = [[InlineKeyboardButton("🧹 Снять 1 варн (500 KLC)", callback_data="shop_ask_warn")],
              [InlineKeyboardButton("🔊 Снять мут (1000 KLC)", callback_data="shop_ask_mute")],
              [InlineKeyboardButton("❌ Закрыть", callback_data="shop_close")]]
        return await query.edit_message_text(f"🏪 **Магазин Kryloxa Coin**\n💰 Баланс: **{bal} KLC**", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    # ПОДТВЕРЖДЕНИЯ
    if data == "shop_ask_warn":
        kb = [[InlineKeyboardButton("✅ Подтвердить", callback_data="shop_buy_warn"), InlineKeyboardButton("🔙 Назад", callback_data="shop_back")]]
        await query.edit_message_text(f"❓ Снять 1 варн за **500 KLC**?\nБаланс: {bal} KLC", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    
    if data == "shop_ask_mute":
        kb = [[InlineKeyboardButton("✅ Подтвердить", callback_data="shop_buy_mute"), InlineKeyboardButton("🔙 Назад", callback_data="shop_back")]]
        await query.edit_message_text(f"❓ Снять мут за **1000 KLC**?\nБаланс: {bal} KLC", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    # ПОКУПКА ВАРНА
    if data == "shop_buy_warn":
        if bal < 500: return await query.answer("Недостаточно KLC!", show_alert=True)
        if warns.get(u_id, 0) <= 0: return await query.answer("У вас нет варнов!", show_alert=True)
        add_balance(u_id, -500); warns[u_id] -= 1
        stats_data["warns"] = warns; save_json(STATS_FILE, stats_data)
        await query.edit_message_text(f"✅ Готово! 1 варн снят.\nОсталось: {warns[u_id]}/3")

    # ПОКУПКА РАЗМУТА (УМНАЯ)
    if data == "shop_buy_mute":
        if bal < 1000: return await query.answer("Недостаточно KLC!", show_alert=True)
        
        target_chat = last_chat.get(u_id) # Ищем группу, где юзер был последний раз
        if not target_chat:
            return await query.answer("Бот не знает, в какой группе вас размутить. Напишите что-нибудь в группе сначала!", show_alert=True)
        
        try:
            await context.bot.restrict_chat_member(target_chat, u_id, 
                permissions={"can_send_messages":True, "can_send_other_messages":True, "can_add_web_page_previews":True})
            add_balance(u_id, -1000)
            await query.edit_message_text(f"🔊 Размут выполнен в вашей группе! Баланс: {get_balance(u_id)} KLC")
        except:
            await query.edit_message_text(f"❌ Ошибка! Бот не смог размутить вас. Убедитесь, что бот админ в группе.")

# ===================== ОБРАБОТЧИК ТЕКСТА =====================

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    chat_id = update.effective_chat.id
    user = update.effective_user
    u_id = user.id

    # ПРИВЯЗКА К ГРУППЕ: Запоминаем, где юзер пишет
    if update.effective_chat.type != 'private':
        last_chat[u_id] = chat_id
        stats_data["last_chat"] = last_chat
        await check_daily_reset(context, chat_id)
    
    text = update.message.text.strip().lower()

    # Статистика ТП
    if u_id not in daily_stats: daily_stats[u_id] = {"name": user.first_name, "count": 0}
    daily_stats[u_id]["count"] += 1
    stats_data["daily"] = daily_stats; save_json(STATS_FILE, stats_data)

    if text in ["баланс", "бал"]:
        await update.message.reply_text(f"💰 Баланс: **{get_balance(u_id)} KLC**", parse_mode="Markdown")
        return

    if text == "бонус":
        last_b_str = economy.get(u_id, {}).get("last_bonus", "2000-01-01 00:00:00")
        last_b = datetime.strptime(last_b_str, "%Y-%m-%d %H:%M:%S")
        if datetime.now() - last_b > timedelta(hours=24):
            amt = random.randint(100, 500); add_balance(u_id, amt)
            economy[u_id]["last_bonus"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_json(ECONOMY_FILE, economy); await update.message.reply_text(f"🎁 +{amt} KLC!")
        else:
            rem = (last_b + timedelta(hours=24)) - datetime.now()
            await update.message.reply_text(f"⏳ Жди {rem.seconds // 3600}ч.")
        return

    if text == "тп":
        top = sorted(daily_stats.items(), key=lambda x: x["count"], reverse=True)[:10]
        m_t = "🏆 **Топ дня:**\n"
        for i, (uid, d) in enumerate(top, 1): m_t += f"{i}. {d['name']} — {d['count']}\n"
        return await update.message.reply_text(m_t, parse_mode="Markdown")

    if text == "магазин":
        await shop_menu(update, context); return

    # --- ОТВЕТОМ ---
    msg = update.message.reply_to_message
    if not msg: return
    t_id, t_name = msg.from_user.id, msg.from_user.first_name

    if text == "инфа":
        try:
            chat_m = await context.bot.get_chat_member(chat_id, t_id)
            st = "✅ Ок"
            if chat_m.status == 'restricted' and not chat_m.can_send_messages:
                diff = chat_m.until_date - datetime.now(chat_m.until_date.tzinfo)
                if diff.total_seconds() > 0: st = f"🔇 Мут ({int(diff.total_seconds()//3600)}ч)"
            await update.message.reply_text(f"👤 {t_name}\n⭐ Ранг: {get_rank(t_id)}\n💰 Баланс: {get_balance(t_id)} KLC\n⚠️ Варны: {warns.get(t_id, 0)}/3\nСтатус: {st}")
        except: pass

# --- РУЛЕТКА И ЗАПУСК ---
async def roulette_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.reply_to_message
    if not msg or update.effective_user.id == msg.from_user.id: return
    g_id = str(update.message.message_id)
    roulette_games[g_id] = {"p1": update.effective_user.id, "p1_n": update.effective_user.first_name, "p2": msg.from_user.id, "p2_n": msg.from_user.first_name, "lives": {update.effective_user.id: 2, msg.from_user.id: 2}, "turn": msg.from_user.id, "mode": None}
    reload_chamber(roulette_games[g_id])
    kb = [[InlineKeyboardButton("Варн", callback_data=f"set_warn_{g_id}"), InlineKeyboardButton("Мут (10м)", callback_data=f"set_mute_{g_id}"), InlineKeyboardButton("Бан (1д)", callback_data=f"set_ban_{g_id}")]]
    await update.message.reply_text(f"🎯 Дуэль! {msg.from_user.first_name}, выбирай ставку:", reply_markup=InlineKeyboardMarkup(kb))

async def roulette_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; data = query.data.split("_")
    if len(data) < 3: return
    action, val, g_id = data, data, data
    if g_id not in roulette_games: return
    g = roulette_games[g_id]; u_id = query.from_user.id
    if action == "set":
        g['mode'] = val; await update_roulette_msg(query, g, g_id)
    elif action == "shoot":
        if u_id != g['turn']: return
        bullet = g['chamber'].pop(0); res = ""
        if val == 'self':
            if bullet: g['lives'][u_id] -= 1; res = "💥 БАХ! В себя!"; g['turn'] = g['p2'] if u_id == g['p1'] else g['p1']
            else: res = "💨 Холостой! Доп. ход!"
        else:
            opp_id = g['p2'] if u_id == g['p1'] else g['p1']
            if bullet: g['lives'][opp_id] -= 1; res = f"💥 БАХ! В цель!"
            else: res = "💨 Холостой... Промах."
            g['turn'] = opp_id
        if any(l <= 0 for l in g['lives'].values()):
            dead_id = next(uid for uid, l in g['lives'].items() if l <= 0)
            l_n = g['p1_n'] if dead_id == g['p1'] else g['p2_n']
            await query.edit_message_text(f"💀 {l_n} ПРОИГРАЛ! Наказание: {g['mode']}"); del roulette_games[g_id]
        else:
            if not g['chamber']: reload_chamber(g)
            await update_roulette_msg(query, g, g_id, res)

async def update_roulette_msg(query, g, g_id, last=""):
    t_name = g['p1_n'] if g['turn'] == g['p1'] else g['p2_n']
    kb = [[InlineKeyboardButton("🎯 В противника", callback_data=f"shoot_opp_{g_id}"), InlineKeyboardButton("🔫 В себя", callback_data=f"shoot_self_{g_id}")]]
    await query.edit_message_text(f"{last}\n\n👤 {g['p1_n']}: {'❤️'*g['lives'][g['p1']]}\n👤 {g['p2_n']}: {'❤️'*g['lives'][g['p2']]}\n👉 Ходит: {t_name}", reply_markup=InlineKeyboardMarkup(kb))

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start)); app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^[Рр]улетка$"), roulette_command))
    app.add_handler(CallbackQueryHandler(shop_callback, pattern="^shop_"))
    app.add_handler(CallbackQueryHandler(roulette_callback)); app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    print("🚀 Бот запущен!"); app.run_polling()
