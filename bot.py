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
    ChatPermissions
)
from telegram.ext import (
    ApplicationBuilder, 
    ContextTypes, 
    MessageHandler, 
    filters, 
    CallbackQueryHandler, 
    CommandHandler,
    ConversationHandler
)

# ==========================================
# КОНФИГУРАЦИЯ
# ==========================================
TOKEN = "8641381095:AAFKIiqcwLoupJIQ034SvmcpRQSrG4fOWns"
OWNER_ID = 5679520675
VERSION = "1.0"

FILES = {"economy": "economy.json", "promos": "promos.json", "ranks": "ranks.json"}
PROMO_NAME, PROMO_DUR, PROMO_AMT = range(3)

logging.basicConfig(level=logging.INFO)

# ==========================================
# СИСТЕМА ДАННЫХ
# ==========================================
def load_json(file_key, default):
    path = FILES[file_key]
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
                return {int(k) if str(k).isdigit() else k: v for k, v in d.items()}
        except: return default
    return default

def save_json(file_key, data):
    with open(FILES[file_key], "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

user_balance = load_json("economy", {})
user_ranks = load_json("ranks", {OWNER_ID: 4})
promos_data = load_json("promos", {})
warns = {}
work_timers = {}
duel_sessions = {}

def get_rank_str(uid):
    if uid == OWNER_ID: return "4 (Owner)"
    r = user_ranks.get(uid, 0)
    return "-1 Tester" if r == -1 else str(r)

def parse_admin_request(text):
    parts = text.split('\n')
    cmd = parts[0].lower().strip()
    reason = parts[1] if len(parts) > 1 else "Не указана"
    
    if "навсегда" in cmd: 
        return 31536000 * 99, "навсегда", reason
    
    match = re.search(r"(\d+)\s*([мчд])", cmd)
    if not match: 
        return None, None, reason
    
    val, unit = int(match.group(1)), match.group(2)
    mult = {"м": 60, "ч": 3600, "д": 86400}.get(unit, 3600)
    label = {"м": "мин.", "ч": "час(ов)", "д": "дн."}.get(unit, "")
    return val * mult, f"{val} {label}", reason

# ==========================================
# ЛОГИКА ДУЭЛИ (🔥 БОЕВЫЕ / ❄️ ХОЛОСТЫЕ)
# ==========================================
async def handle_duel(query, context, gid, striker_id):
    game = duel_sessions.get(gid)
    if not game or striker_id != game["turn"]: return
    
    # 1. ЗАЩИТА ОТ ПУСТОГО БАРАБАНА (исправляет ValueError)
    if not game.get("chamber"):
        if gid in duel_sessions: del duel_sessions[gid]
        await query.message.edit_text("🫙 В барабане кончились патроны. Ничья!")
        return

    # Рандомный выстрел
    bullet = game["chamber"].pop(random.randint(0, len(game["chamber"]) - 1))
    
    if bullet == "🔥":
        game[f"hp{1 if striker_id == game['p1'] else 2}"] -= 1
        effect = "💥 **БАБАХ!**"
    else:
        effect = "💨 **ОСЕЧКА!**"

    # 2. ПРОВЕРКА ЗАВЕРШЕНИЯ ИГРЫ
    if game["hp1"] <= 0 or game["hp2"] <= 0 or not game["chamber"]:
        winner_n = game["p2_n"] if game["hp1"] <= 0 else game["p1_n"]
        loser_n = game["p1_n"] if game["hp1"] <= 0 else game["p2_n"]
        loser_id = game["p1"] if game["hp1"] <= 0 else game["p2"]
        chat_id = query.message.chat_id
        
        res = f"📢 {effect}\n\n🏆 Победил {winner_n}!\n"
        
        # 3. ЗАЩИТА ОТ БАНА ВЛАДЕЛЬЦА (исправляет BadRequest)
        try:
            if game["bet"] == "warn":
                warns[loser_id] = warns.get(loser_id, 0) + 1
                res += f"⚠️ {loser_n} получает ВАРН!"
            elif game["bet"] == "ban":
                await context.bot.ban_chat_member(chat_id, loser_id, until_date=datetime.now() + timedelta(days=1))
                res += f"🚫 {loser_n} улетает в бан на 1 день!"
            elif game["bet"] == "mute":
                await context.bot.restrict_chat_member(chat_id, loser_id, ChatPermissions(can_send_messages=False), until_date=datetime.now() + timedelta(days=1))
                res += f"😶 {loser_n} в муте на 1 день!"
            else:
                user_balance[loser_id] = max(0, user_balance.get(loser_id, 0) - 100)
                winner_id = game["p2"] if game["hp1"] <= 0 else game["p1"]
                user_balance[winner_id] = user_balance.get(winner_id, 0) + 100
                save_json("economy", user_balance)
                res += f"💰 {loser_n} теряет 100 KLC!"
        except Exception:
            # Если бот не может наказать (админ/владелец), просто пишем результат
            res += f"\n🛡 {loser_n} защищен высшими силами (админ/владелец)!"
            
        await query.message.edit_text(res)
        if gid in duel_sessions: del duel_sessions[gid]
    else:
        # Переход хода
        game["turn"] = game["p2"] if striker_id == game["p1"] else game["p1"]
        turn_n = game["p1_n"] if game["turn"] == game["p1"] else game["p2_n"]
        
        fires = game["chamber"].count("🔥")
        ices = game["chamber"].count("❄️")
        
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔫 СТРЕЛЯТЬ", callback_data=f"shot_{gid}_{game['turn']}")]])
        status = (
            f"🎰 Ставка: {game['bet'].upper()}\n"
            f"🔫 Патроны: {len(game['chamber'])} (🔥 {fires} | ❄️ {ices})\n\n"
            f"👤 {game['p1_n']}: {'❤️' * game['hp1']}\n"
            f"👤 {game['p2_n']}: {'❤️' * game['hp2']}\n"
            f"👉 Ход: {turn_n}"
        )
        await query.message.edit_text(f"📢 {effect}\n{status}", reply_markup=kb)

    # Проверка на победу или пустой барабан
    if game["hp1"] <= 0 or game["hp2"] <= 0 or not game["chamber"]:
        winner_n = game["p2_n"] if game["hp1"] <= 0 else game["p1_n"]
        loser_n = game["p1_n"] if game["hp1"] <= 0 else game["p2_n"]
        loser_id = game["p1"] if game["hp1"] <= 0 else game["p2"]
        chat_id = query.message.chat_id
        
        res = f"📢 {effect}\n\n🏆 Победил {winner_n}!\n"
        
        if game["bet"] == "warn":
            warns[loser_id] = warns.get(loser_id, 0) + 1
            res += f"⚠️ {loser_n} получает ВАРН!"
        elif game["bet"] == "ban":
            await context.bot.ban_chat_member(chat_id, loser_id, until_date=datetime.now() + timedelta(days=1))
            res += f"🚫 {loser_n} улетает в бан на 1 день!"
        elif game["bet"] == "mute":
            await context.bot.restrict_chat_member(chat_id, loser_id, ChatPermissions(can_send_messages=False), until_date=datetime.now() + timedelta(days=1))
            res += f"😶 {loser_n} в муте на 1 день!"
        else:
            user_balance[loser_id] = max(0, user_balance.get(loser_id, 0) - 100)
            winner_id = game["p2"] if game["hp1"] <= 0 else game["p1"]
            user_balance[winner_id] = user_balance.get(winner_id, 0) + 100
            save_json("economy", user_balance)
            res += f"💰 {loser_n} теряет 100 KLC!"
            
        await query.message.edit_text(res)
        del duel_sessions[gid]
    else:
        # Переход хода
        game["turn"] = game["p2"] if striker_id == game["p1"] else game["p1"]
        turn_n = game["p1_n"] if game["turn"] == game["p1"] else game["p2_n"]
        
        fires = game["chamber"].count("🔥")
        ices = game["chamber"].count("❄️")
        
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔫 СТРЕЛЯТЬ", callback_data=f"shot_{gid}_{game['turn']}")]])
        status = (
            f"🎰 Ставка: {game['bet'].upper()}\n"
            f"🔫 Патроны: {len(game['chamber'])} (🔥 {fires} | ❄️ {ices})\n\n"
            f"👤 {game['p1_n']}: {'❤️' * game['hp1']}\n"
            f"👤 {game['p2_n']}: {'❤️' * game['hp2']}\n"
            f"👉 Ход: {turn_n}"
        )
        await query.message.edit_text(f"📢 {effect}\n{status}", reply_markup=kb)

# ==========================================
# ОБРАБОТКА СООБЩЕНИЙ
# ==========================================
async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    raw = update.message.text
    text = raw.lower().strip()
    user = update.effective_user
    reply = update.message.reply_to_message
    cid = update.effective_chat.id

    if text in ["баланс", "б"]:
        b = "∞ (Owner)" if user.id == OWNER_ID else f"{user_balance.get(user.id, 0)} KLC"
        await update.message.reply_text(f"💰 Ваш баланс: {b}")
        return

    if text == "обо мне" or (text == "инфа" and reply):
        t = reply.from_user if (text == "инфа" and reply) else user
        b = "∞ (Owner)" if t.id == OWNER_ID else f"{user_balance.get(t.id, 0)} KLC"
        await update.message.reply_text(
            f"👤 Профиль пользователя {t.first_name}:\n🆔 ID: `{t.id}`\n⭐️ Ранг: {get_rank_str(t.id)}\n"
            f"💰 Баланс: {b}\n⚠️ Варны: {warns.get(t.id, 0)}/3\n────────────────\n🤖 Версия: {VERSION}", parse_mode="Markdown"
        )
        return

    if text.startswith("промо "):
        code = text.split(" ", 1)[1].strip()
        if code in promos_data:
            promo = promos_data[code]
            if user.id in promo.get("used", []):
                await update.message.reply_text("❌ Вы уже активировали этот промокод.")
                return
            user_balance[user.id] = user_balance.get(user.id, 0) + promo["amt"]
            promo.setdefault("used", []).append(user.id)
            save_json("economy", user_balance); save_json("promos", promos_data)
            await update.message.reply_text(f"✅ Промокод `{code}` активирован! +{promo['amt']} KLC.")
        return

    if text == "работа":
        if update.effective_chat.type != "private":
            await update.message.reply_text("⚒ Работа доступна только в ЛС бота!")
            return
        now = datetime.now()
        if user.id in work_timers and (now - work_timers[user.id]).seconds < 30:
            await update.message.reply_text(f"⏳ Жди {30 - (now - work_timers[user.id]).seconds} сек.")
            return
        gain = random.randint(50, 150)
        user_balance[user.id] = user_balance.get(user.id, 0) + gain
        work_timers[user.id] = now
        save_json("economy", user_balance)
        await update.message.reply_text(f"⛏ Заработано {gain} KLC!")
        return

    if text == "рулетка" and reply:
        if reply.from_user.id == user.id: return
        gid = f"{user.id}_{reply.from_user.id}"
        # Инициализация барабана: 2 боевых, 4 холостых
        chamber = ["🔥", "🔥", "❄️", "❄️", "❄️", "❄️"]
        duel_sessions[gid] = {
            "p1": user.id, "p1_n": user.first_name, 
            "p2": reply.from_user.id, "p2_n": reply.from_user.first_name, 
            "hp1": 2, "hp2": 2, "turn": None, "chamber": chamber
        }
        kb = [
            [InlineKeyboardButton("💰 100 KLC", callback_data=f"set_klc_{gid}"), InlineKeyboardButton("⚠️ ВАРН", callback_data=f"set_warn_{gid}")],
            [InlineKeyboardButton("🚫 БАН 1д", callback_data=f"set_ban_{gid}"), InlineKeyboardButton("😶 МУТ 1д", callback_data=f"set_mute_{gid}")]
        ]
        await update.message.reply_text(
            f"🎲 **ДУЭЛЬ!**\n\n👤 {user.first_name} VS {reply.from_user.first_name}\n🔫 Барабан: 6 патронов\n\n👉 {reply.from_user.first_name}, выбирай ставку:", 
            reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
        )
        return

    if reply and user_ranks.get(user.id, 0) >= 1:
        t_id, t_n = reply.from_user.id, reply.from_user.first_name
        if text.startswith("бан"):
            s, l, r = parse_admin_request(raw)
            await context.bot.ban_chat_member(cid, t_id, until_date=datetime.now()+timedelta(seconds=s) if s else None)
            await update.message.reply_text(f"🚫 {t_n} забанен ({l if l else 'навсегда'}).\n📝 Причина: {r}")
        elif text.startswith("молчи"):
            s, l, r = parse_admin_request(raw)
            await context.bot.restrict_chat_member(cid, t_id, ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(seconds=s if s else 3600))
            await update.message.reply_text(f"🤫 {t_n} в муте ({l if l else '1 час'}).\n📝 Причина: {r}")
        elif text == "скажи":
            await context.bot.restrict_chat_member(cid, t_id, ChatPermissions(can_send_messages=True, can_send_photos=True, can_send_videos=True, can_send_other_messages=True))
            await update.message.reply_text(f"🔊 {t_n} размучен.")
        elif text.startswith("варн"):
            _, _, r = parse_admin_request(raw)
            warns[t_id] = warns.get(t_id, 0) + 1
            if warns[t_id] >= 3:
                await context.bot.ban_chat_member(cid, t_id)
                await update.message.reply_text(f"⛔️ {t_n} забанен (3/3 варнов).\nПричина: {r}")
                warns[t_id] = 0
            else:
                await update.message.reply_text(f"⚠️ Варн {t_n} ({warns[t_id]}/3). Причина: {r}")

# ==========================================
# CALLBACKS (ОБРАБОТКА КНОПОК)
# ==========================================
async def on_call(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    d = q.data
    
    if d.startswith("set_"):
        parts = d.split("_")
        bet, gid = parts[1], f"{parts[2]}_{parts[3]}"
        game = duel_sessions.get(gid)
        if game and q.from_user.id == game["p2"]:
            game["bet"], game["turn"] = bet, game["p1"]
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔫 СТРЕЛЯТЬ", callback_data=f"shot_{gid}_{game['turn']}")]])
            status = (
                f"🎰 Ставка: {bet.upper()}\n"
                f"🔫 Патроны: 6 (🔥 2 | ❄️ 4)\n\n"
                f"👤 {game['p1_n']}: ❤️❤️\n"
                f"👤 {game['p2_n']}: ❤️❤️\n"
                f"👉 Ход: {game['p1_n']}"
            )
            await q.message.edit_text(status, reply_markup=kb)
            
    elif d.startswith("shot_"):
        parts = d.split("_")
        gid, striker = f"{parts[1]}_{parts[2]}", int(parts[3])
        await handle_duel(q, context, gid, striker)
        
    elif d.startswith("shop_"):
        uid = q.from_user.id
        if d == "shop_unmute" and user_balance.get(uid, 0) >= 1000:
            user_balance[uid] -= 1000; save_json("economy", user_balance)
            await context.bot.restrict_chat_member(q.message.chat_id, uid, ChatPermissions(can_send_messages=True, can_send_photos=True, can_send_videos=True, can_send_other_messages=True))
            await q.answer("✅ Мут снят!")
        elif d == "shop_unwarn" and user_balance.get(uid, 0) >= 500:
            user_balance[uid] -= 500; warns[uid] = max(0, warns.get(uid, 0) - 1); save_json("economy", user_balance)
            await q.answer("✅ Варн снят!")
        else: await q.answer("❌ Недостаточно KLC", show_alert=True)

# ==========================================
# ЗАПУСК
# ==========================================
async def start(u, c):
    await u.message.reply_text(f"🤖 **Kryloxa Bot v{VERSION}** запущен!")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        f"📜 **СПИСОК КОМАНД ({VERSION})**\n\n"
        "🕹 **Меню:** /start, /help, /magaz\n"
        "💰 **Экономика:** баланс, б, обо мне, передать [сумма]\n"
        "⚒ **Фарм:** работа (только в ЛС бота)\n"
        "🎫 **Промо:** промо [код]\n"
        "🛡 **Модер:** инфа, молчи, скажи, бан, разбан, варн\n"
        "🎲 **Игра:** рулетка (ответом)"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def magaz(u, c):
    kb = [[InlineKeyboardButton("🧼 Снять мут (1000 KLC)", callback_data="shop_unmute")],
          [InlineKeyboardButton("💊 Снять варн (500 KLC)", callback_data="shop_unwarn")]]
    await u.message.reply_text("🛒 **Kryloxa Shop**", reply_markup=InlineKeyboardMarkup(kb))

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Регистрация команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd)) # Вот эта строчка была пропущена!
    app.add_handler(CommandHandler("magaz", magaz))
    
    # Обработка кнопок и текста
    app.add_handler(CallbackQueryHandler(on_call))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    
    app.run_polling()
