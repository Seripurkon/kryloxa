"""
================================================================================
                    KRYLOXA BOT - TITAN EDITION (V4.0)
================================================================================
Разработчик: Gemini / Владелец: @kryloxa
Статус: Stable / Оптимизировано для больших чатов
================================================================================
"""

import os
import json
import random
import logging
import asyncio
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
# [1] ГЛОБАЛЬНЫЕ НАСТРОЙКИ (CONFIG)
# ==============================================================================
TOKEN = "8641381095:AAH44UdW5z66BkX0rO5qKHOcdESAoghso_g"
OWNER_ID = 5679520675
SUPPORT_BOT = "@kryloxaHelper_bot"
MY_CARD = "2202208415332171"

# Экономические константы
WORK_LIMIT = 30           # Кулдаун работы (сек)
MIN_WITHDRAWAL = 100      # Мин. вывод KLC
BASE_TAX = 0.65           # Комиссия 65% для обычных
XP_PER_MSG = 2            # Опыт за сообщение

# Пути к базам
DB_DIR = "database"
if not os.path.exists(DB_DIR): os.makedirs(DB_DIR)

PATHS = {
    "users": f"{DB_DIR}/users_main.json",
    "punish": f"{DB_DIR}/punishments.json",
    "activity": f"{DB_DIR}/activity_daily.json",
    "logs": f"{DB_DIR}/event_logs.txt"
}

# Настройка логов
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(name)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(PATHS["logs"])]
)
logger = logging.getLogger("TitanBot")

# ==============================================================================
# [2] СИСТЕМА УПРАВЛЕНИЯ ДАННЫМИ (DATA ENGINE)
# ==============================================================================
def load_json(path):
    if not os.path.exists(path): return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {int(k) if k.isdigit() else k: v for k, v in data.items()}
    except Exception as e:
        logger.error(f"Ошибка загрузки {path}: {e}")
        return {}

def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Ошибка сохранения {path}: {e}")

# Загрузка баз в ОЗУ
u_db = load_json(PATHS["users"])
p_db = load_json(PATHS["punish"])
a_db = load_json(PATHS["activity"])
duel_data = {} # Добавлено: хранилище для активных рулеток

def get_user_struct(uid, name="Игрок"):
    if uid not in u_db:
        u_db[uid] = {
            "name": name,
            "cash": 0,
            "bonus": 0,
            "xp": 0,
            "lvl": 1,
            "warns": 0,
            "is_donator": False,
            "reg_date": datetime.now().strftime("%d.%m.%Y")
        }
    return u_db[uid]

# ==============================================================================
# [3] ЛОГИКА УРОВНЕЙ И ТРАНЗАКЦИЙ
# ==============================================================================
def add_xp(uid, amount):
    u = get_user_struct(uid)
    u["xp"] += amount
    next_lvl_xp = u["lvl"] * 100
    if u["xp"] >= next_lvl_xp:
        u["lvl"] += 1
        u["xp"] = 0
        return True
    return False

def sync_all():
    save_json(PATHS["users"], u_db)
    save_json(PATHS["punish"], p_db)
    save_json(PATHS["activity"], a_db)

# ==============================================================================
# [4] ОБРАБОТЧИКИ КОМАНД (COMMANDS)
# ==============================================================================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_user_struct(user.id, user.first_name)
    welcome = (
        f"🛡 **TITAN SYSTEM ONLINE**\n\n"
        f"Привет, {user.first_name}! Я официальный бот проекта KRYLOXA.\n"
        f"Твой ID: `{user.id}`\n\n"
        f"Используй `баланс` для проверки счёта или /help для списка команд."
    )
    await update.message.reply_text(welcome, parse_mode="Markdown")

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 **МЕНЮ ИНСТРУКЦИЙ**\n\n"
        "💰 **ЭКОНОМИКА:**\n"
        "└ `баланс` — твой кошелек и уровень\n"
        "└ `работа` — заработок чистых KLC\n"
        "└ `передать [сумма]` — перевод (ответ на сообщение)\n"
        "└ `вывод [сумма] [карта]` — запрос на выплату\n\n"
        "🎰 **РАЗВЛЕЧЕНИЯ:**\n"
        "└ `слоты [ставка]` — классический автомат\n"
        "└ `рулетка` — дуэль на выживание (ответ)\n\n"
        "📊 **СТАТИСТИКА:**\n"
        "└ `тп` — топ самых активных за сутки\n\n"
        "👑 **АДМИН-КОМАНДЫ:**\n"
        "└ `бан`, `молчи`, `варн`, `скажи` (через ответ)\n"
        "└ `/createpm [сумма]` — выдать бонусы\n"
        "└ `/donate` — магазин привилегий"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

# Добавлена недостающая функция admin_createpm
async def admin_createpm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    try:
        amt = int(context.args[0])
        target = update.message.reply_to_message.from_user if update.message.reply_to_message else update.effective_user
        t_u = get_user_struct(target.id, target.first_name)
        t_u["bonus"] += amt
        sync_all()
        await update.message.reply_text(f"💎 Начислено {amt} бонусов игроку {target.first_name}!")
    except:
        await update.message.reply_text("Используй: `/createpm 100` (ответом на сообщение)")

# ==============================================================================
# [5] ИГРОВОЙ МОДУЛЬ (GAMES ENGINE)
# ==============================================================================
async def logic_slots(msg, uid, bet):
    u = get_user_struct(uid)
    total = u["cash"] + u["bonus"]
    
    if uid != OWNER_ID and total < bet:
        return await msg.reply_text("❌ Ошибка: недостаточно средств на балансе!")
    
    # Списание средств (приоритет на бонусы)
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
        mult = 20 if reel[0] == "7️⃣" else 10
        win = bet * mult
    elif reel[0] == reel[1] or reel[1] == reel[2]:
        win = int(bet * 1.5)
        
    if win > 0 and uid != OWNER_ID: u["cash"] += win
    sync_all()
    
    status = f"🔥 **ПОБЕДА: +{win} KLC**" if win > 0 else "💀 **ПРОИГРЫШ**"
    text = (
        f"🎰 **ИГРОВОЙ АППАРАТ**\n"
        f"━━━━━━━━━━━━━━\n"
        f"| {reel[0]} | {reel[1]} | {reel[2]} |\n"
        f"━━━━━━━━━━━━━━\n"
        f"{status}\n"
        f"Ваша ставка: {bet} KLC"
    )
    
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
# [6] ЦЕНТРАЛЬНЫЙ ОБРАБОТЧИК (CORE)
# ==============================================================================
async def main_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    
    text = update.message.text.lower().strip()
    uid = update.effective_user.id
    msg = update.message
    u = get_user_struct(uid, update.effective_user.first_name)

    # 1. Опыт и активность
    if add_xp(uid, XP_PER_MSG):
        await msg.reply_text(f"🆙 **НОВЫЙ УРОВЕНЬ!**\nПоздравляем, {u['name']}, теперь твой уровень: {u['lvl']}!")
    
    today = datetime.now().strftime("%Y-%m-%d")
    if str(uid) not in a_db or a_db[str(uid)]["date"] != today:
        a_db[str(uid)] = {"msgs": 1, "date": today, "name": u["name"]}
    else:
        a_db[str(uid)]["msgs"] += 1
    save_json(PATHS["activity"], a_db)

    # 2. Экономические команды
    if text in ["баланс", "б"]:
        status = "👑 Владелец" if uid == OWNER_ID else ("💎 Донатер" if u["is_donator"] else "👤 Игрок")
        total = "Безлимит" if uid == OWNER_ID else (u["cash"] + u["bonus"])
        bal_msg = (
            f"🏦 **ПРОФИЛЬ: {u['name']}**\n"
            f"━━━━━━━━━━━━━━\n"
            f"💵 Чистые: `{u['cash']} KLC`\n"
            f"🎁 Бонусные: `{u['bonus']} KLC`\n"
            f"📊 Всего: `{total}`\n"
            f"━━━━━━━━━━━━━━\n"
            f"🌟 Уровень: `{u['lvl']}` (XP: {u['xp']}/{u['lvl']*100})\n"
            f"🛡 Статус: {status}\n"
            f"⚠️ Варны: {u['warns']}/3"
        )
        await msg.reply_text(bal_msg, parse_mode="Markdown")

    elif text == "тп":
        # Формируем топ за сегодня
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
            if bet < 1 or bet > 1000: raise ValueError
            await logic_slots(msg, uid, bet)
        except:
            await msg.reply_text("🎰 Введите ставку от 1 до 1000. Пример: `слоты 100`")

    elif text.startswith("передать") and msg.reply_to_message:
        try:
            target_user = msg.reply_to_message.from_user
            amount = int(text.split()[1])
            if amount <= 0: return
            
            target_u = get_user_struct(target_user.id, target_user.first_name)
            if u["cash"] < amount and uid != OWNER_ID:
                return await msg.reply_text("❌ У вас недостаточно чистых KLC!")
            
            if uid != OWNER_ID: u["cash"] -= amount
            target_u["cash"] += amount
            sync_all()
            await msg.reply_text(f"✅ Успешно! Передано {amount} KLC игроку {target_user.first_name}.")
        except:
            await msg.reply_text("⚠️ Формат: `передать [сумма]` (ответом на сообщение)")

    elif text == "рулетка" and msg.reply_to_message:
        target = msg.reply_to_message.from_user
        if target.id == uid: return
        
        sid = f"rt_{uid}_{target.id}"
        duel_data[sid] = {"p2": target.id, "p2n": target.first_name}
        
        kb = [
            [InlineKeyboardButton("⚠️ Варн", callback_data=f"rt_{sid}_warn"),
             InlineKeyboardButton("🤫 Мут", callback_data=f"rt_{sid}_mute")],
            [InlineKeyboardButton("🚫 БАН (24ч)", callback_data=f"rt_{sid}_ban"),
             InlineKeyboardButton("💸 -100 KLC", callback_data=f"rt_{sid}_100")]
        ]
        await msg.reply_text(f"🎲 **ДУЭЛЬ!**\n{u['name']} вызывает {target.first_name}.\nЖертва, выбирай цену проигрыша:", reply_markup=InlineKeyboardMarkup(kb))

    # 3. Модерация (Только для OWNER_ID)
    if uid == OWNER_ID and msg.reply_to_message:
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
                await msg.reply_text(f"⛔️ {target_n} получил 3-й варн и был забанен.")
            else:
                await msg.reply_text(f"⚠️ {target_n} получил варн ({t_u['warns']}/3).")
            sync_all()
        elif "скажи" in text:
            await context.bot.restrict_chat_member(update.effective_chat.id, target_id, permissions=ChatPermissions(can_send_messages=True))
            await msg.reply_text(f"🔊 С {target_n} сняты ограничения.")

# ==============================================================================
# [7] CALLBACK ENGINE (КНОПКИ)
# ==============================================================================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    data = q.data
    u = get_user_struct(uid)

    if data.startswith("game_sl_"):
        if "stop" in data: await q.message.edit_text("🎮 Игра окончена.")
        elif "change" in data: await q.message.edit_text("💡 Введите: `слоты [сумма]`")
        else:
            bet = int(data.split("_")[2])
            await logic_slots(q.message, uid, bet)

    elif data.startswith("rt_"):
        _, sid, mode = data.split("_")
        if sid not in duel_data or uid != duel_data[sid]["p2"]:
            return await q.answer("❌ Это не ваш вызов!", show_alert=True)
        
        death = random.choice([True, False, False, False, False, False]) # 1 из 6
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
            return await q.answer(f"⏳ Рано! Жди {int(WORK_LIMIT - (now - last_work).total_seconds())} сек.", show_alert=True)
        
        earn = random.randint(70, 150)
        u["cash"] += earn
        context.user_data["last_work"] = now
        sync_all()
        
        kb = [[InlineKeyboardButton("⚒ Работать еще", callback_data="work_start")]]
        await q.message.edit_text(f"👷‍♂️ Смена закончена!\nВы получили: `{earn} KLC` (чистыми).", reply_markup=InlineKeyboardMarkup(kb))

# ==============================================================================
# [8] ЗАПУСК ПРИЛОЖЕНИЯ
# ==============================================================================
async def cmd_donate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"💎 **МАГАЗИН KRYLOXA**\n\nКарта: `{MY_CARD}`\n\n• **5.000 KLC** = 300₽\n• **Донатер (0% комиссия)** = 150₽\n\nСкрин чека в {SUPPORT_BOT}", parse_mode="Markdown")

async def cmd_magaz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("🤫 Размут (2000 KLC)", callback_data="buy_unmute")],
        [InlineKeyboardButton("⚠️ Снять варн (4000 KLC)", callback_data="buy_unwarn")]
    ]
    await update.message.reply_text("🛒 **ВНУТРИИГРОВЫЕ УСЛУГИ**", reply_markup=InlineKeyboardMarkup(kb))

if __name__ == "__main__":
    # Исправлена ошибка Defaults (LinkPreviewOptions вместо disable_web_page_preview)
    defaults = Defaults(
        parse_mode=constants.ParseMode.MARKDOWN, 
        link_preview_options=LinkPreviewOptions(is_disabled=True)
    )
    
    app = ApplicationBuilder().token(TOKEN).defaults(defaults).build()

    # Регистрация команд
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("donate", cmd_donate))
    app.add_handler(CommandHandler("magaz", cmd_magaz))
    app.add_handler(CommandHandler("createpm", admin_createpm))

    # Обработчики кнопок и текста
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, main_handler))

    logger.info("Titan Bot Started Successfully")
    app.run_polling()
