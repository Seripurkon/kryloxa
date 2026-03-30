import os
import json
import random
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
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
        except Exception:
            return default
    return default

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# Загрузка баз данных
user_ranks = load_json(RANKS_FILE, {OWNER_ID: 4})
user_balance = load_json(ECONOMY_FILE, {})
warns = {}
roulette_games = {}
daily_stats = {} 
bonus_timers = {}
last_reset_day = datetime.now().day

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def get_rank(user_id):
    if user_id == OWNER_ID: return 4
    return user_ranks.get(user_id, 0)

def check_daily_reset():
    global last_reset_day, daily_stats
    if datetime.now().day != last_reset_day:
        daily_stats = {}
        last_reset_day = datetime.now().day

def reload_chamber(g):
    # 3 боевых (True), 3 холостых (False) — строго по правилам
    chamber = [True, True, True, False, False, False]
    random.shuffle(chamber)
    g['chamber'] = chamber

# --- ГЛАВНЫЙ ОБРАБОТЧИК (ЭКОНОМИКА, МОДЕРАЦИЯ, АДМИНКА) ---
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    check_daily_reset()
    
    text = update.message.text.strip().lower()
    user = update.effective_user
    chat_id = update.effective_chat.id
    msg = update.message.reply_to_message

    # Статистика сообщений (ТП)
    if user.id not in daily_stats:
        daily_stats[user.id] = {"name": user.first_name, "count": 0}
    daily_stats[user.id]["count"] += 1

    # --- ЭКОНОМИКА ---
    if text == "бонус":
        now = datetime.now()
        if user.id in bonus_timers and now < bonus_timers[user.id] + timedelta(days=1):
            rem = (bonus_timers[user.id] + timedelta(days=1)) - now
            return await update.message.reply_text(f"❌ Бонус доступен через {rem.seconds // 3600}ч { (rem.seconds // 60) % 60}м")
        
        amt = random.randint(150, 600)
        user_balance[user.id] = user_balance.get(user.id, 0) + amt
        bonus_timers[user.id] = now
        save_json(ECONOMY_FILE, user_balance)
        await update.message.reply_text(f"🎁 {user.first_name}, ты забрал бонус: {amt} KLC!")

    elif text in ["баланс", "б"]:
        bal = user_balance.get(user.id, 0)
        await update.message.reply_text(f"💰 Баланс {user.first_name}: {bal} KLC")

    elif text == "тп":
        top = sorted(daily_stats.items(), key=lambda x: x[1]["count"], reverse=True)[:10]
        res = "🏆 **Топ общительных за день:**\n"
        for i, (uid, d) in enumerate(top):
            res += f"{i+1}. {d['name']} — {d['count']} сообщений\n"
        await update.message.reply_text(res, parse_mode="Markdown")

    elif text == "обо мне":
        r = get_rank(user.id)
        bal = user_balance.get(user.id, 0)
        w = warns.get(user.id, 0)
        await update.message.reply_text(f"👤 Имя: {user.first_name}\n⭐ Ранг: {r}\n💰 Баланс: {bal} KLC\n⚠️ Варны: {w}/3")

    # --- КОМАНДЫ МОДЕРАЦИИ (ПО ОТВЕТУ) ---
    if msg:
        t_id = msg.from_user.id
        c_rank = get_rank(user.id)
        t_rank = get_rank(t_id)

        if text == "инфа":
            cm = await context.bot.get_chat_member(chat_id, t_id)
            st = "🔇 В муте" if cm.status == 'restricted' else "✅ Активен"
            await update.message.reply_text(
                f"👤 Цель: {msg.from_user.first_name}\n"
                f"⭐ Ранг: {t_rank}\n"
                f"💰 Баланс: {user_balance.get(t_id, 0)} KLC\n"
                f"⚠️ Варны: {warns.get(t_id, 0)}/3\n"
                f"📊 Статус: {st}"
            )

        # Проверка прав (Ранг 1+ и выше цели)
        if c_rank >= 1 and (t_rank < c_rank or user.id == OWNER_ID):
            try:
                if text.startswith("молчи"):
                    await context.bot.restrict_chat_member(chat_id, t_id, permissions={"can_send_messages":False}, until_date=datetime.now()+timedelta(hours=1))
                    await update.message.reply_text(f"🤫 {msg.from_user.first_name} замолчал на час.")
                
                elif text == "скажи":
                    await context.bot.restrict_chat_member(chat_id, t_id, permissions={"can_send_messages":True, "can_send_other_messages":True, "can_add_web_page_previews":True, "can_send_polls":True})
                    await update.message.reply_text(f"🔊 {msg.from_user.first_name} снова может говорить.")
                
                elif text == "варн":
                    warns[t_id] = warns.get(t_id, 0) + 1
                    if warns[t_id] >= 3:
                        await context.bot.restrict_chat_member(chat_id, t_id, permissions={"can_send_messages":False}, until_date=datetime.now()+timedelta(days=1))
                        await update.message.reply_text(f"⛔ {msg.from_user.first_name} набрал 3/3 варна и ушел в мут на сутки.")
                        warns[t_id] = 0
                    else:
                        await update.message.reply_text(f"⚠️ {msg.from_user.first_name} получил предупреждение ({warns[t_id]}/3)")
                
                elif text == "снять варн":
                    warns[t_id] = max(0, warns.get(t_id, 0) - 1)
                    await update.message.reply_text(f"✅ У {msg.from_user.first_name} снят один варн.")
                
                elif text.startswith("бан"):
                    await context.bot.ban_chat_member(chat_id, t_id)
                    await update.message.reply_text(f"🚪 {msg.from_user.first_name} забанен и исключен.")
                
                elif text == "разбан":
                    await context.bot.unban_chat_member(chat_id, t_id)
                    await update.message.reply_text(f"🔓 {msg.from_user.first_name} разбанен.")
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка: проверьте права бота.")

        # Команды владельца (Ранг 4)
        if user.id == OWNER_ID:
            if text.startswith("дать админку"):
                lvl = int(text.split()[-1]) if text.split()[-1].isdigit() else 1
                user_ranks[t_id] = lvl
                save_json(RANKS_FILE, user_ranks)
                await update.message.reply_text(f"⭐ {msg.from_user.first_name} назначен админом {lvl} уровня.")
            
            elif text == "снять админку":
                if t_id in user_ranks: del user_ranks[t_id]
                save_json(RANKS_FILE, user_ranks)
                await update.message.reply_text(f"❌ {msg.from_user.first_name} больше не админ.")

# --- РУЛЕТКА (ГЕЙМПЛЕЙ) ---
async def roulette_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.reply_to_message
    if not msg or update.effective_user.id == msg.from_user.id:
        return await update.message.reply_text("Чтобы начать дуэль, ответь на сообщение противника словом 'Рулетка'!")
    
    p1, p2 = update.effective_user, msg.from_user
    g_id = f"{p1.id}_{p2.id}_{random.randint(100,999)}"
    
    roulette_games[g_id] = {
        "p1": p1.id, "p1_n": p1.first_name, 
        "p2": p2.id, "p2_n": p2.first_name,
        "lives": {p1.id: 2, p2.id: 2}, 
        "turn": p2.id, 
        "bet_type": None
    }

    text = (f"⚠️ **ДУЭЛЬ ВЫЗВАНА** ⚠️\n\n"
            f"👤 {p1.first_name} vs 👤 {p2.first_name}\n"
            f"Барабан: 6 патронов (3 боевых)\n"
            f"Здоровье: по 2 ❤️\n\n"
            f"🤝 {p2.first_name}, выбирай ставку:")
    
    kb = [
        [InlineKeyboardButton("Варн", callback_data=f"rbet_warn_{g_id}"),
         InlineKeyboardButton("Мут (10м)", callback_data=f"rbet_mute_{g_id}")],
        [InlineKeyboardButton("Бан (1д)", callback_data=f"rbet_ban_{g_id}"),
         InlineKeyboardButton("100 KLC", callback_data=f"rbet_klc_{g_id}")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def rt_bet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.split("_")
    bet_type, g_id = data[1], "_".join(data[2:])
    
    if g_id not in roulette_games: return
    g = roulette_games[g_id]
    
    if query.from_user.id != g['p2']:
        return await query.answer("Ставку должен выбрать тот, кого вызвали!", show_alert=True)
    
    g['bet_type'] = bet_type
    reload_chamber(g)
    await update_roulette_ui(query, g_id, "🔥 Ставка принята! Игра начинается.")

async def update_roulette_ui(query, g_id, status_text):
    g = roulette_games[g_id]
    turn_id = g['turn']
    turn_name = g['p1_n'] if turn_id == g['p1'] else g['p2_n']
    bet_display = {"warn":"ВАРН", "mute":"МУТ (10м)", "ban":"БАН (1д)", "klc":"100 KLC"}[g['bet_type']]
    
    text = (f"🎰 **РУССКАЯ РУЛЕТКА**\n"
            f"💰 Ставка: **{bet_display}**\n\n"
            f"👤 {g['p1_n']}: {'❤️' * g['lives'][g['p1']]}\n"
            f"👤 {g['p2_n']}: {'❤️' * g['lives'][g['p2']]}\n\n"
            f"📢 {status_text}\n"
            f"👉 Сейчас ход: **{turn_name}**")
    
    kb = [[InlineKeyboardButton("🎯 В противника", callback_data=f"rt_opp_{g_id}"),
           InlineKeyboardButton("🔫 В себя", callback_data=f"rt_self_{g_id}")]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def rt_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.split("_")
    action, g_id = data[1], "_".join(data[2:])
    
    if g_id not in roulette_games: return
    g = roulette_games[g_id]
    
    if query.from_user.id != g['turn']:
        return await query.answer("Сейчас не твой ход!", show_alert=True)

    bullet = g['chamber'].pop(0)
    current_id = g['turn']
    opponent_id = g['p2'] if current_id == g['p1'] else g['p1']
    res_msg = ""

    if action == "opp":
        if bullet:
            g['lives'][opponent_id] -= 1
            res_msg = f"💥 БАХ! {g['p1_n'] if current_id == g['p1'] else g['p2_n']} попал в оппонента!"
        else:
            res_msg = "💨 Щелчок... Холостой. Ход переходит."
        g['turn'] = opponent_id
    else: # в себя
        if bullet:
            g['lives'][current_id] -= 1
            res_msg = f"💥 БАХ! Самострел! {g['p1_n'] if current_id == g['p1'] else g['p2_n']} ранен."
            g['turn'] = opponent_id
        else:
            res_msg = "💨 Смело! Холостой. У тебя дополнительный ход!"

    # Проверка на конец игры
    if g['lives'][g['p1']] <= 0 or g['lives'][g['p2']] <= 0:
        winner_id = g['p1'] if g['lives'][g['p2']] <= 0 else g['p2']
        loser_id = g['p2'] if winner_id == g['p1'] else g['p1']
        winner_name = g['p1_n'] if winner_id == g['p1'] else g['p2_n']
        
        punishment = ""
        try:
            cid = update.effective_chat.id
            if g['bet_type'] == "warn":
                warns[loser_id] = warns.get(loser_id, 0) + 1
                punishment = f"⚠️ Проигравший получил варн ({warns[loser_id]}/3)."
            elif g['bet_type'] == "mute":
                await context.bot.restrict_chat_member(cid, loser_id, permissions={"can_send_messages":False}, until_date=datetime.now()+timedelta(minutes=10))
                punishment = "🔇 Проигравший отправлен в мут на 10 минут."
            elif g['bet_type'] == "ban":
                await context.bot.ban_chat_member(cid, loser_id, until_date=datetime.now()+timedelta(days=1))
                punishment = "🚪 Проигравший забанен на 1 день."
            elif g['bet_type'] == "klc":
                user_balance[winner_id] = user_balance.get(winner_id, 0) + 100
                user_balance[loser_id] = user_balance.get(loser_id, 0) - 100
                save_json(ECONOMY_FILE, user_balance)
                punishment = "💰 100 KLC переведены победителю!"
        except:
            punishment = "❌ Не удалось применить наказание (проверьте права бота)."

        final_text = f"💀 **ИГРА ОКОНЧЕНА** 💀\n\n{res_msg}\n\n🏆 Победитель: **{winner_name}**\n{punishment}"
        await query.edit_message_text(final_text, parse_mode="Markdown")
        del roulette_games[g_id]
    else:
        if not g['chamber']: reload_chamber(g)
        await update_roulette_ui(query, g_id, res_msg)

# --- ЗАПУСК ---
if __name__ == "__main__":
    request = HTTPXRequest(connect_timeout=30, read_timeout=30)
    app = ApplicationBuilder().token(TOKEN).request(request).build()
    
    # Обработчики рулетки
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^[Рр]улетка$"), roulette_start))
    app.add_handler(CallbackQueryHandler(rt_bet_callback, pattern="^rbet_"))
    app.add_handler(CallbackQueryHandler(rt_action_callback, pattern="^rt_"))
    
    # Главный обработчик текста (все остальное)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    print("🚀 БОТ ЗАПУЩЕН. Ошибок Conflict быть не должно.")
    app.run_polling(drop_pending_updates=True)
