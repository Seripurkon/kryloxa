import os
import json
import random
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CallbackQueryHandler, CommandHandler
from telegram.request import HTTPXRequest

# --- НАСТРОЙКИ ---
TOKEN = "8641381095:AAGLY3W93LQGfq_Ygm1OIfAMwlhb6SlQrXE"
OWNER_ID = 5679520675 
ECONOMY_FILE = "economy.json"
RANKS_FILE = "ranks.json"

# --- ЛОГИРОВАНИЕ ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- РАБОТА С ФАЙЛАМИ ---
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

user_ranks = load_json(RANKS_FILE, {OWNER_ID: 4})
user_balance = load_json(ECONOMY_FILE, {})
warns, roulette_games, daily_stats, bonus_timers = {}, {}, {}, {}
last_reset_day = datetime.now().day

# --- ФУНКЦИИ ---
def get_rank(user_id):
    return user_ranks.get(user_id, 0) if user_id != OWNER_ID else 4

def reload_chamber(g):
    # 6 патронов всего: 3 боевых (True), 3 холостых (False)
    chamber = [True, True, True, False, False, False]
    random.shuffle(chamber)
    g['chamber'] = chamber

# --- БАЗОВЫЕ КОМАНДЫ (/start, /help, /magaz) ---
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Привет! Я бот. Напиши /help, чтобы узнать, что я умею.")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📜 **Доступные команды:**\n"
        "/start - Запуск бота\n"
        "/help - Помощь\n"
        "/magaz - Магазин\n\n"
        "💰 **Экономика:**\n"
        "баланс (или б) - Узнать баланс\n"
        "бонус - Ежедневный бонус\n"
        "тп - Топ общительных\n\n"
        "🛡 **Модерация (ответом на сообщение):**\n"
        "инфа - Информация о пользователе\n"
        "молчи / скажи - Выдать/снять мут\n"
        "варн - Выдать предупреждение\n\n"
        "🎲 **Игры (ответом на сообщение):**\n"
        "Рулетка - Вызвать на дуэль"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def magaz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🛒 **Магазин:**\n(Здесь скоро появятся товары)")

# --- ОБРАБОТЧИК ТЕКСТА (ЭКОНОМИКА И МОДЕРАЦИЯ) ---
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    text = update.message.text.strip().lower()
    user, chat_id, msg = update.effective_user, update.effective_chat.id, update.message.reply_to_message

    # Статистика
    if user.id not in daily_stats: daily_stats[user.id] = {"name": user.first_name, "count": 0}
    daily_stats[user.id]["count"] += 1

    # Баланс / Бонус
    if text in ["баланс", "б"]:
        await update.message.reply_text(f"💰 Баланс {user.first_name}: {user_balance.get(user.id, 0)} KLC")
    elif text == "бонус":
        now = datetime.now()
        if user.id in bonus_timers and now < bonus_timers[user.id] + timedelta(days=1):
            return await update.message.reply_text("❌ Бонус раз в 24 часа!")
        amt = random.randint(150, 600)
        user_balance[user.id] = user_balance.get(user.id, 0) + amt
        bonus_timers[user.id] = now
        save_json(ECONOMY_FILE, user_balance)
        await update.message.reply_text(f"🎁 +{amt} KLC!")

    # Админка / Модерация
    if msg:
        t_id = msg.from_user.id
        c_rank, t_rank = get_rank(user.id), get_rank(t_id)
        
        if text == "инфа":
            await update.message.reply_text(f"👤 {msg.from_user.first_name}\n⭐ Ранг: {t_rank}\n💰 Баланс: {user_balance.get(t_id, 0)}\n⚠️ Варны: {warns.get(t_id, 0)}/3")
        
        if c_rank >= 1 and (t_rank < c_rank or user.id == OWNER_ID):
            try:
                if text == "молчи":
                    await context.bot.restrict_chat_member(chat_id, t_id, permissions={"can_send_messages":False}, until_date=datetime.now()+timedelta(hours=1))
                    await update.message.reply_text("🤫 Замолчал.")
                elif text == "скажи":
                    await context.bot.restrict_chat_member(chat_id, t_id, permissions={"can_send_messages":True, "can_send_other_messages":True, "can_send_polls":True, "can_send_media_messages":True})
                    await update.message.reply_text("🔊 Говори.")
                elif text == "варн":
                    warns[t_id] = warns.get(t_id, 0) + 1
                    await update.message.reply_text(f"⚠️ Варн ({warns[t_id]}/3)")
            except: pass

# --- РУЛЕТКА ---
async def roulette_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.reply_to_message
    if not msg or update.effective_user.id == msg.from_user.id: return
    p1, p2 = update.effective_user, msg.from_user
    g_id = f"{p1.id}_{p2.id}_{random.randint(100,999)}"
    
    roulette_games[g_id] = {
        "p1": p1.id, "p1_n": p1.first_name, 
        "p2": p2.id, "p2_n": p2.first_name, 
        "lives": {p1.id: 2, p2.id: 2}, 
        "turn": p2.id, "bet_type": None
    }
    
    text = (f"🎲 **Вызов на дуэль!**\n\n"
            f"👤 {p1.first_name} вызывает {p2.first_name}\n"
            f"В дробовике: 6 патронов (3 боевых, 3 холостых)\n"
            f"У каждого по 2 ❤️\n\n"
            f"👉 {p2.first_name}, выбирай ставку:")
            
    kb = [[InlineKeyboardButton("Варн", callback_data=f"rbet_warn_{g_id}"), InlineKeyboardButton("Мут", callback_data=f"rbet_mute_{g_id}")],
          [InlineKeyboardButton("100 KLC", callback_data=f"rbet_klc_{g_id}")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def rt_bet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    _, b, g_id = q.data.split("_", 2)
    if g_id not in roulette_games or q.from_user.id != roulette_games[g_id]['p2']: return
    roulette_games[g_id]['bet_type'] = b
    reload_chamber(roulette_games[g_id])
    await update_ui(q, g_id, "🔥 Ставка принята! Игра началась.")

async def update_ui(q, g_id, status):
    g = roulette_games[g_id]
    t_n = g['p1_n'] if g['turn'] == g['p1'] else g['p2_n']
    
    live_bullets = g['chamber'].count(True)
    blank_bullets = g['chamber'].count(False)
    total_bullets = len(g['chamber'])
    
    txt = (f"🎰 Ставка: {g['bet_type'].upper()}\n"
           f"🔫 В дробовике: {total_bullets} шт. ({live_bullets} боевых, {blank_bullets} холостых)\n\n"
           f"📢 {status}\n\n"
           f"👤 {g['p1_n']}: {'❤️'*g['lives'][g['p1']]}\n"
           f"👤 {g['p2_n']}: {'❤️'*g['lives'][g['p2']]}\n"
           f"👉 Ход: {t_n}")
           
    kb = [[InlineKeyboardButton("🎯 В оппонента", callback_data=f"rt_opp_{g_id}"), InlineKeyboardButton("🔫 В себя", callback_data=f"rt_self_{g_id}")]]
    await q.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(kb))

async def rt_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    _, act, g_id = q.data.split("_", 2)
    if g_id not in roulette_games or q.from_user.id != roulette_games[g_id]['turn']: return
    g = roulette_games[g_id]
    
    hit = g['chamber'].pop(0)
    curr, opp = g['turn'], (g['p2'] if g['turn'] == g['p1'] else g['p1'])
    
    if act == "opp":
        if hit: 
            g['lives'][opp] -= 1
            msg = "💥 БАХ! ПОПАЛ В ОППОНЕНТА!"
        else: 
            msg = "💨 Щелчок... Холостой! Ход переходит."
            g['turn'] = opp
    else:
        if hit: 
            g['lives'][curr] -= 1
            msg = "💥 БАХ! САМОСТРЕЛ!"
            g['turn'] = opp
        else: 
            msg = "💨 Щелчок... Холостой! Дополнительный ход!"

    if any(l <= 0 for l in g['lives'].values()):
        winner = g['p1_n'] if g['lives'][g['p2']] <= 0 else g['p2_n']
        await q.edit_message_text(f"{msg}\n\n🏆 Игра окончена! Победил {winner}.")
        del roulette_games[g_id]
    else:
        if not g['chamber']: 
            reload_chamber(g)
            msg += "\n🔄 Барабан перезаряжен!"
        await update_ui(q, g_id, msg)

# --- ПУСК ---
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).request(HTTPXRequest(connect_timeout=20)).build()
    
    # Команды
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("magaz", magaz_cmd))
    
    # Рулетка
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^[Рр]улетка$"), roulette_start))
    app.add_handler(CallbackQueryHandler(rt_bet_callback, pattern="^rbet_"))
    app.add_handler(CallbackQueryHandler(rt_action_callback, pattern="^rt_"))
    
    # Обычный текст
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    print("🚀 Бот запущен!")
    app.run_polling(drop_pending_updates=True)
