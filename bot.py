"""
================================================================================
                    KRYLOXA BOT - TITAN EDITION (V4.2 - FIXED)
================================================================================
"""

import os
import json
import random
import logging
import sys
from datetime import datetime, timedelta

from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup, 
    ChatPermissions,
    constants,
    LinkPreviewOptions
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

# ==============================================================================
# [1] НАСТРОЙКИ
# ==============================================================================
TOKEN = "8641381095:AAH44UdW5z66BkX0rO5qKHOcdESAoghso_g"
OWNER_ID = 5679520675
SUPPORT_BOT = "@kryloxaHelper_bot"
MY_CARD = "2202208415332171"

WORK_LIMIT = 30  

DB_DIR = "database"
if not os.path.exists(DB_DIR): os.makedirs(DB_DIR)

PATHS = {
    "users": f"{DB_DIR}/users_main.json",
    "activity": f"{DB_DIR}/activity_daily.json"
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("TitanBot")

# ==============================================================================
# [2] БАЗА ДАННЫХ
# ==============================================================================
def load_json(path):
    if not os.path.exists(path): return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {int(k) if k.isdigit() else k: v for k, v in data.items()}
    except: return {}

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

u_db = load_json(PATHS["users"])
a_db = load_json(PATHS["activity"])
duel_data = {} 

def get_user_struct(uid, name="Игрок"):
    if uid not in u_db:
        u_db[uid] = {
            "name": name,
            "cash": 0,
            "bonus": 0,
            "warns": 0,
            "is_donator": False
        }
    return u_db[uid]

def sync_all():
    save_json(PATHS["users"], u_db)
    save_json(PATHS["activity"], a_db)

# ==============================================================================
# [3] ИГРЫ
# ==============================================================================
async def logic_slots(msg, uid, bet):
    u = get_user_struct(uid)
    total = u["cash"] + u["bonus"]
    
    if uid != OWNER_ID and total < bet:
        return await msg.reply_text("❌ Ошибка: недостаточно KLC!")
    
    if uid != OWNER_ID:
        if u["bonus"] >= bet: u["bonus"] -= bet
        else:
            diff = bet - u["bonus"]
            u["bonus"] = 0
            u["cash"] -= diff
            
    items = ["💎", "🍒", "7️⃣", "🍋", "🍏", "🎲"]
    reel = [random.choice(items) for _ in range(3)]
    
    win = 0
    if reel[0] == reel[1] == reel[2]:
        win = bet * (20 if reel[0] == "7️⃣" else 10)
    elif reel[0] == reel[1] or reel[1] == reel[2]:
        win = int(bet * 1.5)
        
    if win > 0 and uid != OWNER_ID: u["cash"] += win
    sync_all()
    
    status = f"🔥 **ПОБЕДА: +{win} KLC**" if win > 0 else "💀 **ПРОИГРЫШ**"
    text = f"🎰 **СЛОТЫ**\n━━━━━━━━━━━━━━\n| {reel[0]} | {reel[1]} | {reel[2]} |\n━━━━━━━━━━━━━━\n{status}\nСтавка: {bet} KLC"
    
    kb = [
        [InlineKeyboardButton("🔄 Крутить снова", callback_data=f"game_sl_{bet}")],
        [InlineKeyboardButton("💳 Изменить ставку", callback_data="game_sl_change"),
         InlineKeyboardButton("🛑 Выход", callback_data="game_sl_stop")]
    ]
    
    if hasattr(msg, 'edit_text'):
        await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    else:
        await msg.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

# ==============================================================================
# [4] ОБРАБОТЧИК ТЕКСТА (Здесь теперь работают все команды)
# ==============================================================================
async def main_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    
    text = update.message.text.lower().strip()
    uid = update.effective_user.id
    msg = update.message
    u = get_user_struct(uid, update.effective_user.first_name)

    # Активность для Топа
    today = datetime.now().strftime("%Y-%m-%d")
    if str(uid) not in a_db or a_db[str(uid)]["date"] != today:
        a_db[str(uid)] = {"msgs": 1, "date": today, "name": u["name"]}
    else:
        a_db[str(uid)]["msgs"] += 1
    save_json(PATHS["activity"], a_db)

    # --- ЭКОНОМИКА И ИНФО ---
    if text in ["баланс", "б"]:
        total = "Безлимит" if uid == OWNER_ID else (u["cash"] + u["bonus"])
        bal_msg = (
            f"🏦 **ПРОФИЛЬ: {u['name']}**\n"
            f"━━━━━━━━━━━━━━\n"
            f"💵 Чистые: `{u['cash']} KLC`\n"
            f"🎁 Бонусные: `{u['bonus']} KLC`\n"
            f"📊 Всего: `{total}`\n"
            f"⚠️ Варны: {u['warns']}/3"
        )
        await msg.reply_text(bal_msg, parse_mode="Markdown")

    elif text in ["донат", "donate", "/donate"]:
        await msg.reply_text(f"💎 **МАГАЗИН KRYLOXA**\n\nКарта: `{MY_CARD}`\n\n• **5.000 KLC** = 300₽\n• **Донатер (0% комиссия)** = 150₽\n\nСкрин чека кидать в {SUPPORT_BOT}", parse_mode="Markdown")

    elif text == "тп":
        daily_top = [v for k, v in a_db.items() if v["date"] == today]
        daily_top.sort(key=lambda x: x["msgs"], reverse=True)
        top_str = f"📊 **АКТИВНОСТЬ ЗА {today}**\n\n"
        for i, entry in enumerate(daily_top[:10], 1):
            top_str += f"{i}. {entry['name']} — `{entry['msgs']}` сообщ.\n"
        await msg.reply_text(top_str, parse_mode="Markdown")

    elif text == "работа":
        kb = [[InlineKeyboardButton("⚒ Выйти на смену", callback_data="work_start")]]
        await msg.reply_text("👷‍♂️ Готов поработать на благо проекта?", reply_markup=InlineKeyboardMarkup(kb))

    elif text.startswith("слоты"):
        try:
            bet = int(text.split()[1])
            await logic_slots(msg, uid, bet)
        except:
            await msg.reply_text("🎰 Введите ставку. Пример: `слоты 100`")

    elif text.startswith("передать") and msg.reply_to_message:
        try:
            target_user = msg.reply_to_message.from_user
            amount = int(text.split()[1])
            if amount <= 0: return
            
            target_u = get_user_struct(target_user.id, target_user.first_name)
            if u["cash"] < amount and uid != OWNER_ID:
                return await msg.reply_text("❌ Недостаточно чистых KLC!")
            
            if uid != OWNER_ID: u["cash"] -= amount
            target_u["cash"] += amount
            sync_all()
            await msg.reply_text(f"✅ Передано {amount} KLC игроку {target_user.first_name}.")
        except:
            await msg.reply_text("⚠️ Формат: `передать 100` (ответом)")

    elif text == "рулетка" and msg.reply_to_message:
        target = msg.reply_to_message.from_user
        if target.id == uid: return
        sid = f"rt_{uid}_{target.id}"
        duel_data[sid] = {"p2": target.id, "p2n": target.first_name}
        kb = [
            [InlineKeyboardButton("⚠️ Варн", callback_data=f"rt_{sid}_warn"), InlineKeyboardButton("🤫 Мут", callback_data=f"rt_{sid}_mute")],
            [InlineKeyboardButton("🚫 БАН (24ч)", callback_data=f"rt_{sid}_ban"), InlineKeyboardButton("💸 -100 KLC", callback_data=f"rt_{sid}_100")]
        ]
        await msg.reply_text(f"🎲 **ДУЭЛЬ!**\n{u['name']} вызывает {target.first_name}.\nВыбирай цену проигрыша:", reply_markup=InlineKeyboardMarkup(kb))

    # --- АДМИНКА ---
    if uid == OWNER_ID:
        if text.startswith("createpm") or text.startswith("/createpm"):
            if not msg.reply_to_message:
                return await msg.reply_text("❌ Ответь на сообщение игрока, которому хочешь выдать KLC!")
            try:
                amt = int(text.split()[1])
                target = msg.reply_to_message.from_user
                t_u = get_user_struct(target.id, target.first_name)
                t_u["bonus"] += amt
                sync_all()
                await msg.reply_text(f"💎 Начислено {amt} бонусов игроку {target.first_name}!")
            except:
                await msg.reply_text("Пиши: `createpm 100` (ответом на сообщение)")

        elif msg.reply_to_message:
            target_id = msg.reply_to_message.from_user.id
            target_n = msg.reply_to_message.from_user.first_name
            t_u = get_user_struct(target_id, target_n)

            if "бан" in text:
                await context.bot.ban_chat_member(update.effective_chat.id, target_id)
                await msg.reply_text(f"🚫 {target_n} забанен.")
            elif "молчи" in text:
                await context.bot.restrict_chat_member(update.effective_chat.id, target_id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(hours=2))
                await msg.reply_text(f"🤫 {target_n} замучен на 2 часа.")
            elif "варн" in text:
                t_u["warns"] += 1
                if t_u["warns"] >= 3:
                    await context.bot.ban_chat_member(update.effective_chat.id, target_id)
                    t_u["warns"] = 0
                    await msg.reply_text(f"⛔️ {target_n} получил 3-й варн и отлетел в бан.")
                else:
                    await msg.reply_text(f"⚠️ {target_n} получил варн ({t_u['warns']}/3).")
                sync_all()
            elif "скажи" in text:
                await context.bot.restrict_chat_member(update.effective_chat.id, target_id, permissions=ChatPermissions(can_send_messages=True))
                await msg.reply_text(f"🔊 С {target_n} сняты ограничения.")

# ==============================================================================
# [5] КНОПКИ
# ==============================================================================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    data = q.data
    u = get_user_struct(uid)

    if data.startswith("game_sl_"):
        if "stop" in data: await q.message.edit_text("🎮 Игра окончена.")
        elif "change" in data: await q.message.edit_text("💡 Введите текстом: `слоты [ставка]`")
        else:
            bet = int(data.split("_")[2])
            await logic_slots(q.message, uid, bet)

    elif data.startswith("rt_"):
        _, sid, mode = data.split("_")
        if sid not in duel_data or uid != duel_data[sid]["p2"]:
            return await q.answer("❌ Это не ваш вызов!", show_alert=True)
        
        death = random.choice([True, False, False, False, False, False])
        if death:
            res = f"💀 **БАХ!** {duel_data[sid]['p2n']} убит."
            if mode == "warn":
                u["warns"] += 1
                if u["warns"] >= 3: await context.bot.ban_chat_member(q.message.chat_id, uid); u["warns"] = 0
            elif mode == "mute":
                await context.bot.restrict_chat_member(q.message.chat_id, uid, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(hours=1))
            elif mode == "ban":
                await context.bot.ban_chat_member(q.message.chat_id, uid, until_date=datetime.now()+timedelta(days=1))
            elif mode == "100":
                u["cash"] = max(0, u["cash"] - 100)
            sync_all()
        else:
            res = f"💨 **ЩЕЛЧОК...** {duel_data[sid]['p2n']} выжил! Повезло."
        
        await q.message.edit_text(res)
        if sid in duel_data: del duel_data[sid]

    elif data == "work_start":
        now = datetime.now()
        last_work = context.user_data.get("last_work", datetime.min)
        if (now - last_work).total_seconds() < WORK_LIMIT:
            return await q.answer(f"⏳ Жди {int(WORK_LIMIT - (now - last_work).total_seconds())} сек.", show_alert=True)
        
        earn = random.randint(70, 150)
        u["cash"] += earn
        context.user_data["last_work"] = now
        sync_all()
        
        kb = [[InlineKeyboardButton("⚒ Работать еще", callback_data="work_start")]]
        await q.message.edit_text(f"👷‍♂️ Смена закончена!\nПолучено: `{earn} KLC`.", reply_markup=InlineKeyboardMarkup(kb))

# ==============================================================================
# ЗАПУСК
# ==============================================================================
if __name__ == "__main__":
    defaults = Defaults(
        parse_mode=constants.ParseMode.MARKDOWN, 
        link_preview_options=LinkPreviewOptions(is_disabled=True)
    )
    app = ApplicationBuilder().token(TOKEN).defaults(defaults).build()

    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT, main_handler))

    logger.info("Titan Bot Ready")
    app.run_polling()
