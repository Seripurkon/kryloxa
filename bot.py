import os
import json
import random
import logging
import re
from datetime import datetime, timedelta

from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup, 
    ChatPermissions,
    constants
)
from telegram.ext import (
    ApplicationBuilder, 
    ContextTypes, 
    MessageHandler, 
    filters, 
    CallbackQueryHandler, 
    CommandHandler,
    Defaults
)

# ==========================================
# [1] КОНФИГУРАЦИЯ (Из твоего файла)
# ==========================================
TOKEN = "8641381095:AAH44UdW5z66BkX0rO5qKHOcdESAoghso_g"
OWNER_ID = 5679520675
MY_CARD = "2202208415332171"

DB_DIR = "database"
if not os.path.exists(DB_DIR): os.makedirs(DB_DIR)

FILES = {
    "economy": f"{DB_DIR}/economy.json", 
    "donators": f"{DB_DIR}/donators.json", 
    "ranks": f"{DB_DIR}/ranks.json",
    "promos": f"{DB_DIR}/promos.json",
    "warns": f"{DB_DIR}/warns.json"
}

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)

# ==========================================
# [2] СУБД (ЗАГРУЗКА И СОХРАНЕНИЕ)
# ==========================================
def load_json(file_key, default_value):
    filepath = FILES[file_key]
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as file:
                data = json.load(file)
                return {int(k) if str(k).isdigit() else k: v for k, v in data.items()}
        except Exception as e:
            logging.error(f"Ошибка чтения {filepath}: {e}")
            return default_value
    return default_value

def save_json(file_key, data):
    filepath = FILES[file_key]
    try:
        with open(filepath, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Ошибка записи {filepath}: {e}")

# Инициализация баз данных
user_balance = load_json("economy", {})
donators_list = load_json("donators", [])
user_ranks = load_json("ranks", {OWNER_ID: 4})
promos_db = load_json("promos", {})
user_warns = load_json("warns", {})

# Временные кеши
roulette_games = {}
work_timers = {}
bonus_timers = {}

# ==========================================
# [3] ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================
def get_user_rank(user_id):
    if user_id == OWNER_ID: return 4
    return user_ranks.get(user_id, 0)

def parse_time(text):
    text = text.lower().strip()
    match = re.search(r"(\d+)\s*([мчдг])", text)
    if not match: return 3600, "1 час"
    amount, unit = int(match.group(1)), match.group(2)
    if unit == 'м': return amount * 60, f"{amount} мин."
    if unit == 'ч': return amount * 3600, f"{amount} ч."
    if unit == 'д': return amount * 86400, f"{amount} дн."
    if unit == 'г': return amount * 31536000, f"{amount} лет."
    return 3600, "1 час"

# ==========================================
# [4] ИГРОВАЯ ЛОГИКА (СЛОТЫ)
# ==========================================
async def play_slots(user_id, bet):
    if bet > 1000:
        return "❌ Максимальная ставка в слотах — **1000 KLC**.", False
    
    current_balance = user_balance.get(user_id, 0)
    if user_id != OWNER_ID:
        if current_balance < bet:
            return f"❌ Недостаточно средств! У вас {current_balance} KLC.", False
        user_balance[user_id] -= bet
    
    symbols = ["🍒", "🍋", "🔔", "💎", "7️⃣"]
    result = [random.choice(symbols) for _ in range(3)]
    
    win_amount = 0
    if result[0] == result[1] == result[2]:
        mult = 200 if result[0] == "7️⃣" else (50 if result[0] == "💎" else 15)
        win_amount = bet * mult
    elif result[0] == result[1] or result[1] == result[2]:
        win_amount = int(bet * 1.5)
        
    if win_amount > 0 and user_id != OWNER_ID:
        user_balance[user_id] += win_amount
    
    save_json("economy", user_balance)
    res_visual = f"🎰 `[ {result[0]} | {result[1]} | {result[2]} ]`"
    status = f"✅ **ПОБЕДА!** +**{win_amount} KLC**" if win_amount > 0 else "❌ **ПРОИГРЫШ!**"
    return f"{res_visual}\n\n{status}", True

# ==========================================
# [5] ОСНОВНОЙ ОБРАБОТЧИК СООБЩЕНИЙ
# ==========================================
async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    
    msg = update.message
    user = update.effective_user
    uid = user.id
    text = msg.text.lower().strip()
    args = msg.text.split()
    reply = msg.reply_to_message

    # --- ЭКОНОМИКА: БАЛАНС И ПРОФИЛЬ ---
    if text in ["баланс", "б"]:
        bal = "Бесконечно" if uid == OWNER_ID else user_balance.get(uid, 0)
        await msg.reply_text(f"👤 Профиль {user.first_name}:\n💰 Баланс: **{bal} KLC**")

    elif text in ["инфа", "профиль"]:
        target = reply.from_user if reply else user
        tid = target.id
        bal = "Бесконечно" if tid == OWNER_ID else user_balance.get(tid, 0)
        rank_name = "Владелец 👑" if tid == OWNER_ID else ("Донатер 💎" if tid in donators_list else "Игрок 🎮")
        w_count = user_warns.get(tid, 0)
        await msg.reply_text(f"👤 **Профиль {target.first_name}**\n⭐️ Статус: {rank_name}\n💰 Баланс: {bal} KLC\n⚠️ Варны: {w_count}/3")

    # --- ЭКОНОМИКА: РАБОТА И БОНУС ---
    elif text == "работа":
        now = datetime.now()
        if uid in work_timers and (now - work_timers[uid]).total_seconds() < 30:
            left = int(30 - (now - work_timers[uid]).total_seconds())
            return await msg.reply_text(f"⏳ Вы устали. Ждите {left} сек.")
        
        earn = random.randint(50, 150)
        user_balance[uid] = user_balance.get(uid, 0) + earn
        work_timers[uid] = now
        save_json("economy", user_balance)
        await msg.reply_text(f"⚒ Вы заработали **{earn} KLC**!")

    elif text == "бонус":
        now = datetime.now()
        if uid in bonus_timers and (now - bonus_timers[uid]).total_seconds() < 86400:
            left = int((86400 - (now - bonus_timers[uid]).total_seconds()) // 3600)
            return await msg.reply_text(f"❌ Бонус уже получен. Ждите {left} ч.")
        
        bonus = random.randint(500, 1500)
        user_balance[uid] = user_balance.get(uid, 0) + bonus
        bonus_timers[uid] = now
        save_json("economy", user_balance)
        await msg.reply_text(f"🎁 Ежедневный бонус: **{bonus} KLC**!")

    # --- ЭКОНОМИКА: ВЫВОД И ПЕРЕДАЧА ---
    elif args[0].lower() == "передать" and len(args) > 1 and reply:
        try:
            amt = int(args[1])
            if amt <= 0 or (uid != OWNER_ID and user_balance.get(uid, 0) < amt): return
            if uid != OWNER_ID: user_balance[uid] -= amt
            user_balance[reply.from_user.id] = user_balance.get(reply.from_user.id, 0) + amt
            save_json("economy", user_balance)
            await msg.reply_text(f"💸 Передано **{amt} KLC** для {reply.from_user.first_name}.")
        except: pass

    elif args[0].lower() == "вывод" and len(args) > 1:
        try:
            amt = int(args[1])
            if amt <= 0 or (uid != OWNER_ID and user_balance.get(uid, 0) < amt): return
            fee = 0 if (uid in donators_list or uid == OWNER_ID) else 65
            final = int(amt * (1 - fee / 100))
            if uid != OWNER_ID: user_balance[uid] -= amt
            save_json("economy", user_balance)
            await msg.reply_text(f"✅ Заявка создана!\nСписано: {amt} KLC\nКомиссия: {fee}%\nИтого: **{final} KLC**")
            await context.bot.send_message(OWNER_ID, f"💰 **ЗАПРОС НА ВЫВОД**\nОт: {user.full_name}\nСумма: {amt} (К выплате: {final})")
        except: pass

    # --- ИГРЫ: СЛОТЫ И РУЛЕТКА ---
    elif args[0].lower() == "слоты" and len(args) > 1:
        try:
            res_text, success = await play_slots(uid, int(args[1]))
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🎰 Снова", callback_data=f"sl_{args[1]}")]]) if success else None
            await msg.reply_text(res_text, reply_markup=kb)
        except: pass

    elif text == "рулетка" and reply:
        if reply.from_user.id == uid or reply.from_user.is_bot: return
        gid = f"duel_{uid}_{reply.from_user.id}_{random.randint(100, 999)}"
        roulette_games[gid] = {"p1": uid, "p1n": user.first_name, "p2": reply.from_user.id, "p2n": reply.from_user.first_name}
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("⚠️ Варн", callback_data=f"rt_{gid}_warn"),
            InlineKeyboardButton("🤫 Мут 1ч", callback_data=f"rt_{gid}_mute")
        ]])
        await msg.reply_text(f"🎲 {user.first_name} вызывает {reply.from_user.first_name} на дуэль!\nЖертва, выбирай наказание:", reply_markup=kb)

    # --- ПРОМОКОДЫ (ОДНОЙ СТРОКОЙ) ---
    elif args[0].lower() == "создатьпромо" and uid == OWNER_ID and len(args) > 3:
        p_code, p_time_raw, p_sum_raw = args[1], args[2], args[3]
        try:
            sec, t_str = parse_time(p_time_raw)
            until = (datetime.now() + timedelta(seconds=sec)).isoformat()
            promos_db[p_code] = {"sum": int(p_sum_raw), "until": until, "users": []}
            save_json("promos", promos_db)
            await msg.reply_text(f"✅ Промо `{p_code}` на {p_sum_raw} KLC создан (до {until[:16]})")
        except: pass

    elif args[0].lower() == "промо" and len(args) > 1:
        p_code = args[1]
        if p_code in promos_db:
            p = promos_db[p_code]
            if uid not in p["users"] and datetime.now() < datetime.fromisoformat(p["until"]):
                user_balance[uid] = user_balance.get(uid, 0) + p["sum"]
                p["users"].append(uid)
                save_json("economy", user_balance)
                save_json("promos", promos_db)
                await msg.reply_text(f"💎 Промо активирован! +{p['sum']} KLC")

    # --- МОДЕРАЦИЯ И АДМИНКА ---
    if uid == OWNER_ID or get_user_rank(uid) >= 1:
        if text.startswith("бан") and reply:
            await context.bot.ban_chat_member(msg.chat_id, reply.from_user.id)
            await msg.reply_text(f"🚫 {reply.from_user.first_name} забанен.")
        
        elif text.startswith("молчи") and reply:
            sec, t_str = parse_time(raw_text=msg.text)
            await context.bot.restrict_chat_member(msg.chat_id, reply.from_user.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(seconds=sec))
            await msg.reply_text(f"🤫 Мут для {reply.from_user.first_name} на {t_str}.")

        elif text.startswith("createpm") and reply and uid == OWNER_ID:
            try:
                amt = int(args[1])
                user_balance[reply.from_user.id] = user_balance.get(reply.from_user.id, 0) + amt
                save_json("economy", user_balance)
                await msg.reply_text(f"💎 Выдано {amt} KLC игроку {reply.from_user.first_name}")
            except: pass

# ==========================================
# [6] ОБРАБОТКА КНОПОК
# ==========================================
async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    data = q.data

    if data.startswith("sl_"):
        bet = int(data.split("_")[1])
        res, success = await play_slots(uid, bet)
        await q.message.edit_text(res, reply_markup=q.message.reply_markup if success else None)

    elif data.startswith("rt_"):
        _, gid, mode = data.split("_")
        if gid not in roulette_games or uid != roulette_games[gid]["p2"]:
            return await q.answer("Это не твой вызов!", show_alert=True)
        
        if random.choice([True, False, False, False, False, False]): # 1/6 шанс
            loser_id = roulette_games[gid]["p2"]
            res = f"💀 **БАБАХ!** {roulette_games[gid]['p2n']} проиграл!"
            if mode == "warn":
                user_warns[loser_id] = user_warns.get(loser_id, 0) + 1
                save_json("warns", user_warns)
            else:
                await context.bot.restrict_chat_member(q.message.chat_id, loser_id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(hours=1))
        else:
            res = f"💨 **ЩЕЛЧОК!** {roulette_games[gid]['p2n']} выжил!"
        
        await q.message.edit_text(res)
        del roulette_games[gid]

# ==========================================
# [7] ЗАПУСК
# ==========================================
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).defaults(Defaults(parse_mode=constants.ParseMode.MARKDOWN)).build()
    app.add_handler(CommandHandler("start", lambda u, c: u.message.reply_text("Бот запущен! Пиши 'инфа' или 'донат'")))
    app.add_handler(CallbackQueryHandler(handle_callbacks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))
    print("🚀 TITAN CORE SYSTEM STARTED")
    app.run_polling()
