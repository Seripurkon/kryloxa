"""
================================================================================
                    KRYLOXA ULTIMATE BOT (VERSION 2.5)
================================================================================
Владелец: @kryloxa (ID: 5679520675)
Функционал: 
- Система двойного баланса (Чистые / Бонусные KLC)
- Два магазина: /donate (Real Money) и /magaz (Game KLC)
- Работа через Inline-кнопки с таймером
- Админ-панель выплат с кнопками
- Развернутая модерация и Игры (Слоты, Рулетка)
================================================================================
"""

import os
import json
import random
import logging
import asyncio
import re
import sys
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

# ==============================================================================
# [1] КОНФИГУРАЦИЯ И НАСТРОЙКИ (CONFIG)
# ==============================================================================
TOKEN = "8641381095:AAH44UdW5z66BkX0rO5qKHOcdESAoghso_g"
OWNER_ID = 5679520675
SUPPORT_BOT = "@kryloxaHelper_bot"
MY_CARD = "2202208415332171"

# Экономические настройки
WORK_COOLDOWN = 30  # Секунд между сменами
MIN_WITHDRAW = 100  # Минимальный вывод KLC
DEFAULT_FEE = 65    # Комиссия для обычных игроков (%)

# Цены игрового магазина (/magaz) в KLC
PRICES = {
    "unmute": 1500,
    "unwarn": 3000
}

# База данных файлов
DB_FILES = {
    "users": "economy_db.json",
    "donators": "donators_db.json",
    "warns": "warns_db.json"
}

# Логирование в консоль
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("KryloxaBot")

# ==============================================================================
# [2] СЕРВИСЫ ДАННЫХ (DATABASE)
# ==============================================================================
def load_db(key, default):
    """Безопасная загрузка JSON данных"""
    path = DB_FILES.get(key)
    if not path or not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Телеграм ID всегда должны быть целыми числами
            if isinstance(data, dict):
                return {int(k) if k.isdigit() else k: v for k, v in data.items()}
            return data
    except Exception as e:
        logger.error(f"Ошибка при чтении базы {key}: {e}")
        return default

def save_db(key, data):
    """Сохранение данных с защитой от повреждения"""
    path = DB_FILES.get(key)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Ошибка при записи базы {key}: {e}")

# Инициализация данных в памяти
user_stats = load_db("users", {})      # {id: {"cash": 0, "bonus": 0}}
donators = load_db("donators", [])     # [id1, id2...]
warns_db = load_db("warns", {})        # {id: count}

# Кэш для сессий (не сохраняется в файлы)
work_sessions = {}
duel_sessions = {}

# ==============================================================================
# [3] ВСПОМОГАТЕЛЬНЫЕ ИНСТРУМЕНТЫ (UTILS)
# ==============================================================================
def get_u(user_id: int):
    """Инициализация игрока в базе"""
    if user_id not in user_stats:
        user_stats[user_id] = {"cash": 0, "bonus": 0, "exp": 0}
        save_db("users", user_stats)
    return user_stats[user_id]

def is_owner(uid: int) -> bool:
    """Проверка прав создателя"""
    return uid == OWNER_ID

async def notify_admin(context, text: str, markup=None):
    """Быстрая отправка уведомления админу"""
    try:
        await context.bot.send_message(
            chat_id=OWNER_ID, 
            text=text, 
            reply_markup=markup, 
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.warning(f"Не удалось уведомить админа: {e}")

# ==============================================================================
# [4] ГЛАВНЫЕ КОМАНДЫ (BASE COMMANDS)
# ==============================================================================
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Та самая команда /help, которую я забыл в прошлый раз"""
    help_text = (
        "📜 **СПРАВОЧНИК КОМАНД KRYLOXA**\n\n"
        "💰 **Экономика и Баланс:**\n"
        "• `баланс` (или `б`) — проверить свой счёт\n"
        "• `работа` — выход на смену (кнопочный фарм)\n"
        "• `тп [сумма]` — перевод чистых KLC (ответом)\n\n"
        "🎰 **Азартные Игры:**\n"
        "• `слоты [ставка]` — попытать удачу (макс. 1000)\n"
        "• `рулетка` — дуэль на мут или варн (ответом)\n\n"
        "🛒 **Магазины:**\n"
        "• `/magaz` — внутриигровые услуги (за KLC)\n"
        "• `/donate` — покупка валюты и VIP (за рубли)\n\n"
        "💳 **Выплаты:**\n"
        "• `вывод [сумма] [карта]` — вывод чистых KLC\n\n"
        "⚙️ **Для Администрации:**\n"
        "• `/createpm [сумма]` — выдать бонусы\n"
        "• Команды: `бан`, `молчи`, `варн`, `скажи`"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def cmd_donate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Магазин за реальные деньги"""
    donate_msg = (
        "💎 **МАГАЗИН ДОНАТА (RUB)**\n\n"
        "Здесь ты покупаешь чистые KLC и особые статусы.\n\n"
        "📌 **Наши предложения:**\n"
        "• **Статус Донатера** — 100 ₽\n"
        "  └ *Убирает комиссию 65% на любой вывод!*\n"
        "• **5.000 KLC** — 300 ₽\n"
        "• **10.000 KLC** — 550 ₽\n\n"
        f"💳 **Карта для оплаты:**\n`{MY_CARD}`\n\n"
        f"✅ **Что делать:** Оплати нужную сумму и пришли скрин чека в {SUPPORT_BOT}. "
        "Админ начислит всё вручную в течение часа!"
    )
    await update.message.reply_text(donate_msg, parse_mode="Markdown")

async def cmd_magaz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Магазин за игровую валюту KLC"""
    uid = update.effective_user.id
    u = get_u(uid)
    
    shop_msg = (
        "🛒 **ИГРОВОЙ МАГАЗИН (KLC)**\n"
        "Трать заработанные монеты на полезные услуги!\n\n"
        f"💰 Твой баланс: **{u['cash'] + u['bonus']} KLC**\n\n"
        f"🔹 **Снять мут** — {PRICES['unmute']} KLC\n"
        f"🔹 **Убрать 1 варн** — {PRICES['unwarn']} KLC\n\n"
        "Выберите товар для покупки кнопкой ниже:"
    )
    
    kb = [
        [InlineKeyboardButton("🤫 Снять мут", callback_data="buy_mute")],
        [InlineKeyboardButton("⚠️ Убрать варн", callback_data="buy_warn")]
    ]
    await update.message.reply_text(
        shop_msg, 
        reply_markup=InlineKeyboardMarkup(kb), 
        parse_mode="Markdown"
    )

# ==============================================================================
# [5] ЭКОНОМИЧЕСКАЯ ЛОГИКА (ECONOMY)
# ==============================================================================
async def process_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вывод информации о балансе"""
    user = update.effective_user
    u = get_u(user.id)
    
    # Визуальное оформление для владельца
    if is_owner(user.id):
        cash_val, bonus_val, total_val = "∞", "∞", "∞"
    else:
        cash_val, bonus_val = u["cash"], u["bonus"]
        total_val = cash_val + bonus_val
        
    bal_text = (
        f"🏦 **БАНКОВСКИЙ СЧЁТ: {user.first_name}**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💵 **Чистые KLC:** `{cash_val}`\n"
        f"🎁 **Бонусные KLC:** `{bonus_val}`\n"
        f"📊 **Всего в наличии:** `{total_val}`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ **Предупреждения:** {warns_db.get(user.id, 0)}/3\n"
        f"💎 **Статус:** {'Донатер' if user.id in donators or is_owner(user.id) else 'Игрок'}"
    )
    await update.message.reply_text(bal_text, parse_mode="Markdown")

async def cmd_work_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вызов кнопки работы"""
    kb = [[InlineKeyboardButton("⚒ Начать смену", callback_data="work_exec")]]
    await update.message.reply_text(
        "👋 Хочешь заработать немного **чистых KLC**?\n"
        "Нажимай кнопку и приступай к работе!",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def cmd_withdraw_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка запроса на вывод денег"""
    uid = update.effective_user.id
    u = get_u(uid)
    
    try:
        # Проверка аргументов
        if len(context.args) < 2:
            return await update.message.reply_text("⚠️ Формат: `вывод [сумма] [карта]`")
            
        amount = int(context.args[0])
        card_data = " ".join(context.args[1:])
        
        if amount < MIN_WITHDRAW:
            return await update.message.reply_text(f"❌ Минимальная сумма для вывода — {MIN_WITHDRAW} KLC.")
            
        if not is_owner(uid) and u["cash"] < amount:
            return await update.message.reply_text(f"❌ Недостаточно чистых KLC! Твой баланс: {u['cash']}")
            
        # Расчет комиссии
        fee = 0 if (uid in donators or is_owner(uid)) else DEFAULT_FEE
        payout_rub = int(amount * (1 - fee/100))
        
        # Списание и уведомления
        if not is_owner(uid):
            u["cash"] -= amount
            save_db("users", user_stats)
            
        await update.message.reply_text(
            f"✅ **Заявка создана!**\n\n"
            f"Списано: {amount} KLC\n"
            f"Комиссия: {fee}%\n"
            f"К получению: **{payout_rub} ₽**\n"
            "Ожидайте проверки владельцем."
        )
        
        # Кнопки для владельца
        adm_kb = [[
            InlineKeyboardButton("✅ Оплачено", callback_data=f"p_ok_{uid}_{payout_rub}"),
            InlineKeyboardButton("❌ Отказ", callback_data=f"p_no_{uid}_{amount}")
        ]]
        
        await notify_admin(context, 
            f"💰 **НОВЫЙ ВЫВОД**\n"
            f"Юзер: {update.effective_user.full_name} (`{uid}`)\n"
            f"Сумма: {amount} KLC -> **{payout_rub} ₽**\n"
            f"Карта: `{card_data}`", 
            InlineKeyboardMarkup(adm_kb)
        )
        
    except ValueError:
        await update.message.reply_text("❌ Введите корректную сумму числом!")

# ==============================================================================
# [6] АДМИНИСТРИРОВАНИЕ (ADMIN TOOLS)
# ==============================================================================
async def admin_createpm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выдача бонусных KLC админом"""
    if not is_owner(update.effective_user.id): return

    try:
        val = int(context.args[0])
        target = update.message.reply_to_message.from_user if update.message.reply_to_message else update.effective_user
        
        t_u = get_u(target.id)
        t_u["bonus"] += val
        save_db("users", user_stats)
        
        await update.message.reply_text(f"👑 **KRYLOXA** начислил {val} бонусных KLC юзеру {target.first_name}!")
    except:
        await update.message.reply_text("⚠️ `/createpm [сумма]` (можно реплаем)")

async def admin_add_donator(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выдача статуса донатера"""
    if not is_owner(update.effective_user.id): return
    if not update.message.reply_to_message: return
    
    tid = update.message.reply_to_message.from_user.id
    if tid not in donators:
        donators.append(tid)
        save_db("donators", donators)
        await update.message.reply_text(f"💎 Юзер {tid} теперь официальный Донатер!")

# ==============================================================================
# [7] ИГРОВЫЕ МОДУЛИ (GAMES)
# ==============================================================================
async def game_slots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Слоты с лимитом 1000"""
    uid = update.effective_user.id
    u = get_u(uid)
    
    try:
        bet = int(context.args[0])
        if bet <= 0: return
        if bet > 1000:
            return await update.message.reply_text("❌ Максимальная ставка в слотах — 1000 KLC!")
            
        total = u["cash"] + u["bonus"]
        if not is_owner(uid) and total < bet:
            return await update.message.reply_text("❌ Недостаточно средств!")
            
        # Списание (бонусы приоритетнее)
        if not is_owner(uid):
            if u["bonus"] >= bet: u["bonus"] -= bet
            else:
                rem = bet - u["bonus"]
                u["bonus"] = 0
                u["cash"] -= rem
        
        # Механика
        items = ["🍒", "🍋", "🔔", "💎", "7️⃣"]
        r = [random.choice(items) for _ in range(3)]
        
        win = 0
        if r[0] == r[1] == r[2]:
            mult = 50 if r[0] == "7️⃣" else (20 if r[0] == "💎" else 10)
            win = bet * mult
        elif r[0] == r[1] or r[1] == r[2]:
            win = int(bet * 1.5)
            
        if win > 0:
            if not is_owner(uid): u["cash"] += win
            msg = f"🎰 `[ {r[0]} | {r[1]} | {r[2]} ]` \n\n🥳 **ПОБЕДА!**\nТы забираешь **{win} чистых KLC**!"
        else:
            msg = f"🎰 `[ {r[0]} | {r[1]} | {r[2]} ]` \n\n💀 **ПРОИГРЫШ!**"
            
        save_db("users", user_stats)
        await update.message.reply_text(msg, parse_mode="Markdown")
        
    except:
        await update.message.reply_text("⚠️ Формат: `слоты [ставка]`")

async def game_roulette_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вызов на дуэль"""
    if not update.message.reply_to_message:
        return await update.message.reply_text("❌ Ответь на сообщение противника!")
        
    p1, p2 = update.effective_user, update.message.reply_to_message.from_user
    if p1.id == p2.id: return
    
    sid = f"r_{p1.id}_{p2.id}_{random.randint(10, 99)}"
    duel_sessions[sid] = {"p1": p1.id, "p1n": p1.first_name, "p2": p2.id, "p2n": p2.first_name}
    
    kb = [[
        InlineKeyboardButton("⚠️ Варн", callback_data=f"rl_{sid}_warn"),
        InlineKeyboardButton("🤫 Мут (1ч)", callback_data=f"rl_{sid}_mute")
    ]]
    await update.message.reply_text(
        f"🎲 **ДУЭЛЬ!** {p1.first_name} vs {p2.first_name}\n"
        f"🎯 {p2.first_name}, выбирай ставку смерти:",
        reply_markup=InlineKeyboardMarkup(kb)
    )

# ==============================================================================
# [8] ОБРАБОТЧИК CALLBACK (BUTTONS LOGIC)
# ==============================================================================
async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    data = q.data
    u = get_u(uid)

    # --- РАБОТА ---
    if data == "work_exec":
        now = datetime.now()
        if uid in work_sessions:
            diff = (now - work_sessions[uid]).total_seconds()
            if diff < WORK_COOLDOWN:
                return await q.answer(f"⏳ Слишком рано! Жди {int(WORK_COOLDOWN - diff)} сек.", show_alert=True)
        
        earned = random.randint(50, 110)
        u["cash"] += earned
        work_sessions[uid] = now
        save_db("users", user_stats)
        
        await q.message.edit_text(
            f"👷‍♂️ **Смена отработана!**\nТы получил `{earned} чистых KLC`.\n"
            f"Следующая смена через {WORK_COOLDOWN} сек.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚒ Еще разок", callback_data="work_exec")]]),
            parse_mode="Markdown"
        )

    # --- МАГАЗИН ---
    elif data.startswith("buy_"):
        item = data.split("_")[1]
        cost = PRICES[item]
        total = u["cash"] + u["bonus"]
        
        if total < cost:
            return await q.answer("❌ Недостаточно KLC!", show_alert=True)
            
        # Снятие (бонусы вперед)
        if u["bonus"] >= cost: u["bonus"] -= cost
        else:
            rem = cost - u["bonus"]
            u["bonus"] = 0
            u["cash"] -= rem
            
        if item == "mute":
            try:
                await context.bot.restrict_chat_member(q.message.chat_id, uid, permissions=ChatPermissions(can_send_messages=True))
                await q.answer("✅ Мут снят!", show_alert=True)
            except: pass
        elif item == "warn":
            if warns_db.get(uid, 0) > 0:
                warns_db[uid] -= 1
                save_db("warns", warns_db)
                await q.answer("✅ Варн удален!", show_alert=True)
            else:
                return await q.answer("🧐 У тебя нет варнов!", show_alert=True)
        
        save_db("users", user_stats)
        await q.message.edit_text(f"🛍 **Покупка завершена!**\nТвой баланс обновлен.")

    # --- РУЛЕТКА ---
    elif data.startswith("rl_"):
        _, sid, penalty = data.split("_")
        if sid not in duel_sessions: return
        game = duel_sessions[sid]
        
        if uid != game["p2"]:
            return await q.answer("❌ Ставку выбирает жертва!", show_alert=True)
            
        is_bad = random.choice([True] + [False]*5) # 1 к 6
        if is_bad:
            res = f"💀 **БА-БАХ!** {game['p2n']} убит!"
            if penalty == "mute":
                await context.bot.restrict_chat_member(q.message.chat_id, game["p2"], permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(hours=1))
            else:
                warns_db[game["p2"]] = warns_db.get(game["p2"], 0) + 1
                save_db("warns", warns_db)
        else:
            res = f"💨 **ЩЕЛЧОК!** {game['p2n']} выжил. Повезло!"
            
        await q.message.edit_text(res)
        del duel_sessions[sid]

    # --- АДМИН-ВЫПЛАТЫ ---
    elif data.startswith("p_"):
        if not is_owner(uid): return
        _, act, target, amt = data.split("_")
        target, amt = int(target), int(amt)
        
        if act == "ok":
            await context.bot.send_message(target, f"💰 **ВЫПЛАТА ПОДТВЕРЖДЕНА!**\n{amt} ₽ зачислены на твой счёт.")
            await q.message.edit_text(q.message.text + "\n\n✅ **ОПЛАЧЕНО**")
        else:
            t_u = get_u(target)
            t_u["cash"] += amt
            save_db("users", user_stats)
            await context.bot.send_message(target, "❌ **ВЫПЛАТА ОТКЛОНЕНА.**\nKLC возвращены на баланс.")
            await q.message.edit_text(q.message.text + "\n\n❌ **ОТКАЗАНО**")

# ==============================================================================
# [9] МОДЕРАЦИЯ И ТЕКСТОВЫЕ ТРИГГЕРЫ
# ==============================================================================
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    
    text = update.message.text.lower().strip()
    uid = update.effective_user.id
    msg = update.message
    
    # Экономика (текстовые команды)
    if text in ["баланс", "б"]:
        await process_balance(update, context)
    elif text == "работа":
        await cmd_work_trigger(update, context)
    elif text.startswith("слоты"):
        context.args = text.split()[1:]
        await game_slots(update, context)
    elif text.startswith("вывод"):
        context.args = text.split()[1:]
        await cmd_withdraw_req(update, context)
    elif text == "рулетка":
        await game_roulette_start(update, context)
    elif text.startswith("тп"):
        # Перевод чистых монет
        if not msg.reply_to_message: return
        try:
            amt = int(text.split()[1])
            if amt <= 0: return
            u_from = get_u(uid)
            u_to = get_u(msg.reply_to_message.from_user.id)
            if not is_owner(uid) and u_from["cash"] < amt: return
            if not is_owner(uid): u_from["cash"] -= amt
            u_to["cash"] += amt
            save_db("users", user_stats)
            await msg.reply_text(f"💸 Передано {amt} чистых KLC!")
        except: pass

    # Модерация
    if is_owner(uid) and msg.reply_to_message:
        target_id = msg.reply_to_message.from_user.id
        target_name = msg.reply_to_message.from_user.first_name
        chat_id = update.effective_chat.id
        
        if "бан" in text:
            await context.bot.ban_chat_member(chat_id, target_id)
            await msg.reply_text(f"🚫 {target_name} забанен навсегда.")
        elif "молчи" in text:
            await context.bot.restrict_chat_member(chat_id, target_id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(hours=2))
            await msg.reply_text(f"🤫 {target_name} замолк на 2 часа.")
        elif "варн" in text:
            count = warns_db.get(target_id, 0) + 1
            warns_db[target_id] = count
            save_db("warns", warns_db)
            if count >= 3:
                await context.bot.ban_chat_member(chat_id, target_id)
                await msg.reply_text(f"⛔️ {target_name} набрал 3 варна и улетел в бан.")
            else:
                await msg.reply_text(f"⚠️ {target_name} получил варн ({count}/3).")
        elif "скажи" in text:
            await context.bot.restrict_chat_member(chat_id, target_id, permissions=ChatPermissions(can_send_messages=True))
            await msg.reply_text(f"🔊 {target_name} снова может говорить.")

# ==============================================================================
# [10] ЗАПУСК (RUNNER)
# ==============================================================================
if __name__ == "__main__":
    defaults = Defaults(parse_mode=constants.ParseMode.MARKDOWN)
    app = ApplicationBuilder().token(TOKEN).defaults(defaults).build()

    # Регистрация команд /
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("start", lambda u, c: u.message.reply_text("👋 Бот активен! Пиши /help")))
    app.add_handler(CommandHandler("donate", cmd_donate))
    app.add_handler(CommandHandler("magaz", cmd_magaz))
    app.add_handler(CommandHandler("createpm", admin_createpm))
    app.add_handler(CommandHandler("add_don", admin_add_donator))

    # Кнопки
    app.add_handler(CallbackQueryHandler(handle_callbacks))

    # Текстовое ядро
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    print("""
    [OK] KRYLOXA BOT В СЕТИ
    [LOG] Базы данных загружены
    [LOG] Слушаю команды...
    """)
    
    app.run_polling()
