"""
================================================================================
                    KRYLOXA ULTIMATE BOT (VERSION 2.0)
================================================================================
Владелец: @kryloxa (ID: 5679520675)
Функционал: Экономика (2 типа валют), Азартные игры, Модерация, Магазины.
================================================================================
"""

import os
import json
import random
import logging
import asyncio
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

# ==============================================================================
# [1] ГЛОБАЛЬНЫЕ НАСТРОЙКИ И КОНСТАНТЫ
# ==============================================================================
TOKEN = "8641381095:AAH44UdW5z66BkX0rO5qKHOcdESAoghso_g"
OWNER_ID = 5679520675
SUPPORT_BOT = "@kryloxaHelper_bot"
MY_CARD = "2202208415332171"

# Цены в игровом магазине (/magaz)
SHOP_PRICES = {
    "unmute": 1500,  # Снять мут
    "unwarn": 3000   # Снять 1 предупреждение
}

# Пути к файлам базы данных
DB_FILES = {
    "users": "database_users.json",
    "donators": "database_donators.json",
    "warns": "database_warns.json",
    "settings": "database_settings.json"
}

# Настройка логирования для отладки
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==============================================================================
# [2] СИСТЕМА УПРАВЛЕНИЯ ДАННЫМИ (JSON)
# ==============================================================================
def load_db(key, default_type):
    """Загрузка данных из файла с проверкой на существование"""
    file_path = DB_FILES[key]
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                data = json.load(file)
                # Конвертируем ключи в int (Telegram ID всегда числа)
                if isinstance(data, dict):
                    return {int(k) if k.isdigit() else k: v for k, v in data.items()}
                return data
        except Exception as e:
            logger.error(f"Критическая ошибка при чтении {file_path}: {e}")
            return default_type
    return default_type

def save_db(key, data):
    """Сохранение данных в файл"""
    file_path = DB_FILES[key]
    try:
        with open(file_path, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Ошибка при записи в {file_path}: {e}")

# Инициализация оперативной памяти бота
# user_data: { user_id: {"cash": 0, "bonus": 0, "total_earned": 0} }
user_data = load_db("users", {})
donators_list = load_db("donators", [])
user_warns = load_db("warns", {})

# Временные словари (не сохраняются после перезагрузки)
work_cooldowns = {}
active_duels = {}

# ==============================================================================
# [3] ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (HELPERS)
# ==============================================================================
def initialize_user(user_id: int):
    """Создание записи о пользователе, если её нет"""
    if user_id not in user_data:
        user_data[user_id] = {
            "cash": 0,      # Чистые KLC (для вывода)
            "bonus": 0,     # Бонусные KLC (нельзя выводить)
            "earned": 0     # Статистика всего
        }
        save_db("users", user_data)

def is_admin(user_id: int) -> bool:
    """Проверка на права владельца"""
    return user_id == OWNER_ID

def get_balance_text(user_id: int, name: str) -> str:
    """Формирование красивого сообщения о балансе"""
    u = user_data.get(user_id, {"cash": 0, "bonus": 0})
    cash = u["cash"]
    bonus = u["bonus"]
    total = "Бесконечно 👑" if user_id == OWNER_ID else (cash + bonus)
    
    msg = (
        f"👤 **Профиль: {name}**\n"
        f"━━━━━━━━━━━━━━\n"
        f"💵 **Чистые KLC:** `{cash}`\n"
        f"🎁 **Бонусные KLC:** `{bonus}`\n"
        f"📊 **Общий счёт:** `{total}`\n"
        f"━━━━━━━━━━━━━━\n"
        f"⚠️ **Варны:** {user_warns.get(user_id, 0)}/3"
    )
    return msg

# ==============================================================================
# [4] МАГАЗИНЫ И ЭКОНОМИКА (ОСНОВНОЕ)
# ==============================================================================
async def cmd_donate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Магазин за реальные деньги (Донат)"""
    text = (
        "💎 **ОФИЦИАЛЬНЫЙ ДОНАТ KRYLOXA**\n\n"
        "Здесь вы можете приобрести валюту или статус донатера за реальные деньги.\n\n"
        "📜 **ПРАЙС-ЛИСТ:**\n"
        "• **Статус Донатера** — 100 ₽\n"
        "  *(Дает 0% комиссии на вывод средств)*\n"
        "• **5.000 KLC** — 300 ₽\n"
        "• **10.000 KLC** — 550 ₽\n\n"
        f"💳 **РЕКВИЗИТЫ (Карта):**\n`{MY_CARD}`\n\n"
        f"⚠️ **ВАЖНО:** После перевода обязательно отправьте скриншот чека в нашего бота поддержки: {SUPPORT_BOT}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_magaz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Магазин за игровые KLC (Внутриигровой)"""
    uid = update.effective_user.id
    initialize_user(uid)
    
    text = (
        "🛒 **ВНУТРИИГРОВОЙ МАГАЗИН**\n"
        "Здесь тратятся ваши KLC (сначала бонусные, потом чистые).\n\n"
        f"1️⃣ **Снять мут** — {SHOP_PRICES['unmute']} KLC\n"
        f"2️⃣ **Снять 1 варн** — {SHOP_PRICES['unwarn']} KLC\n\n"
        "Выберите товар для покупки:"
    )
    
    keyboard = [
        [InlineKeyboardButton("🤫 Снять мут", callback_data="shop_unmute")],
        [InlineKeyboardButton("⚠️ Снять варн", callback_data="shop_unwarn")]
    ]
    await update.message.reply_text(
        text, 
        reply_markup=InlineKeyboardMarkup(keyboard), 
        parse_mode="Markdown"
    )

async def cmd_work(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда работы (через кнопку)"""
    uid = update.effective_user.id
    initialize_user(uid)
    
    keyboard = [[InlineKeyboardButton("⚒ Начать смену", callback_data="work_logic")]]
    await update.message.reply_text(
        "👷‍♂️ Вы можете подработать на стройке и получить чистые KLC.\n"
        "Нажмите кнопку ниже, чтобы начать работу.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def cmd_createpm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выдача БОНУСНЫХ KLC владельцем"""
    if not is_admin(update.effective_user.id):
        return

    try:
        amount = int(context.args[0])
        # Проверяем, ответил ли админ на сообщение пользователя
        if update.message.reply_to_message:
            target_id = update.message.reply_to_message.from_user.id
            target_name = update.message.reply_to_message.from_user.first_name
        else:
            target_id = update.effective_user.id
            target_name = "себе"

        initialize_user(target_id)
        user_data[target_id]["bonus"] += amount
        save_db("users", user_data)
        
        await update.message.reply_text(
            f"👑 **АДМИН-ДЕЙСТВИЕ**\n"
            f"Выдано **{amount} бонусных KLC** пользователю {target_name}!",
            parse_mode="Markdown"
        )
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Ошибка! Используйте: `/createpm [сумма]`")

# ==============================================================================
# [5] СИСТЕМА ВЫВОДА СРЕДСТВ
# ==============================================================================
async def cmd_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Заявка на вывод чистых KLC"""
    uid = update.effective_user.id
    initialize_user(uid)
    
    if len(context.args) < 2:
        return await update.message.reply_text(
            "⚠️ **Ошибка формата!**\nИспользуйте: `вывод [сумма] [номер карты]`",
            parse_mode="Markdown"
        )
        
    try:
        amount = int(context.args[0])
        card_details = " ".join(context.args[1:])
        
        if amount < 100:
            return await update.message.reply_text("❌ Минимальная сумма вывода: 100 KLC.")
            
        u = user_data[uid]
        if uid != OWNER_ID and u["cash"] < amount:
            return await update.message.reply_text(
                f"❌ У вас недостаточно чистых KLC!\nДоступно: {u['cash']} KLC."
            )
            
        # Расчет комиссии (65% для обычных, 0% для донатеров/владельца)
        is_don = (uid in donators_list) or (uid == OWNER_ID)
        fee_percent = 0 if is_don else 65
        final_rub = int(amount * (1 - fee_percent / 100))
        
        # Списание средств
        if uid != OWNER_ID:
            u["cash"] -= amount
            save_db("users", user_data)
            
        await update.message.reply_text(
            f"✅ **Заявка принята!**\n\n"
            f"Списано: {amount} KLC\n"
            f"Комиссия: {fee_percent}%\n"
            f"Будет зачислено: **{final_rub} ₽**\n\n"
            f"Ожидайте подтверждения от администратора."
        )
        
        # Уведомление владельцу
        admin_kb = [
            [
                InlineKeyboardButton("✅ Оплачено", callback_data=f"adm_pay_{uid}_{final_rub}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"adm_ref_{uid}_{amount}")
            ]
        ]
        await context.bot.send_message(
            OWNER_ID,
            f"💰 **НОВАЯ ЗАЯВКА НА ВЫВОД**\n\n"
            f"👤 От: {update.effective_user.first_name} (ID: `{uid}`)\n"
            f"🔹 Сумма KLC: {amount}\n"
            f"🔹 К выплате: **{final_rub} ₽**\n"
            f"💳 Карта: `{card_details}`",
            reply_markup=InlineKeyboardMarkup(admin_kb),
            parse_mode="Markdown"
        )
        
    except ValueError:
        await update.message.reply_text("❌ Сумма должна быть числом!")

# ==============================================================================
# [6] ИГРЫ: СЛОТЫ И РУЛЕТКА
# ==============================================================================
async def cmd_slots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Азартная игра Слоты"""
    uid = update.effective_user.id
    initialize_user(uid)
    
    try:
        bet = int(context.args[0])
        if bet <= 0: return
        if bet > 1000:
            return await update.message.reply_text("❌ Максимальная ставка: 1000 KLC.")
            
        u = user_data[uid]
        total_bal = u["cash"] + u["bonus"]
        
        if uid != OWNER_ID and total_bal < bet:
            return await update.message.reply_text("❌ Недостаточно средств для ставки!")
            
        # Списание (сначала бонусы, потом чистые)
        if uid != OWNER_ID:
            if u["bonus"] >= bet:
                u["bonus"] -= bet
            else:
                remaining = bet - u["bonus"]
                u["bonus"] = 0
                u["cash"] -= remaining
        
        # Генерация результата
        symbols = ["🍒", "🍋", "🔔", "💎", "7️⃣"]
        res = [random.choice(symbols) for _ in range(3)]
        
        win_amount = 0
        if res[0] == res[1] == res[2]:
            if res[0] == "7️⃣": win_amount = bet * 50
            elif res[0] == "💎": win_amount = bet * 20
            else: win_amount = bet * 10
        elif res[0] == res[1] or res[1] == res[2]:
            win_amount = int(bet * 1.5)
            
        if win_amount > 0:
            if uid != OWNER_ID: u["cash"] += win_amount # Выигрыш всегда чистыми!
            result_text = f"🎰 `[ {res[0]} | {res[1]} | {res[2]} ]` \n\n🔥 **ПОБЕДА!**\nВы выиграли **{win_amount} чистых KLC**!"
        else:
            result_text = f"🎰 `[ {res[0]} | {res[1]} | {res[2]} ]` \n\n❌ **ПРОИГРЫШ!**"
            
        save_db("users", user_data)
        await update.message.reply_text(result_text, parse_mode="Markdown")
        
    except (IndexError, ValueError):
        await update.message.reply_text("⚠️ Используйте: `слоты [ставка]`")

async def cmd_roulette(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вызов на дуэль (Рулетка)"""
    if not update.message.reply_to_message:
        return await update.message.reply_text("❌ Команда должна быть ответом на сообщение оппонента!")
        
    p1 = update.effective_user
    p2 = update.message.reply_to_message.from_user
    
    if p1.id == p2.id:
        return await update.message.reply_text("❌ Нельзя играть с самим собой!")
        
    duel_id = f"duel_{p1.id}_{p2.id}_{random.randint(100, 999)}"
    active_duels[duel_id] = {"p1": p1.id, "p1_name": p1.first_name, "p2": p2.id, "p2_name": p2.first_name}
    
    kb = [[
        InlineKeyboardButton("⚠️ Варн", callback_data=f"rl_{duel_id}_warn"),
        InlineKeyboardButton("🤫 Мут (1ч)", callback_data=f"rl_{duel_id}_mute")
    ]]
    await update.message.reply_text(
        f"🎲 **ДУЭЛЬ ВЫЗВАНА!**\n\n{p1.first_name} вызывает {p2.first_name} на русскую рулетку!\n"
        f"👉 {p2.first_name}, выбирай наказание для проигравшего:",
        reply_markup=InlineKeyboardMarkup(kb)
    )

# ==============================================================================
# [7] МОДЕРАЦИЯ (БАЗА)
# ==============================================================================
async def handle_moderation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых команд модерации (бан, мут и т.д.)"""
    if not update.message.reply_to_message: return
    
    text = update.message.text.lower()
    admin_id = update.effective_user.id
    target_id = update.message.reply_to_message.from_user.id
    target_name = update.message.reply_to_message.from_user.first_name
    chat_id = update.effective_chat.id
    
    # Только владелец или админы (если добавишь систему рангов)
    if not is_admin(admin_id): return

    try:
        if "бан" in text:
            await context.bot.ban_chat_member(chat_id, target_id)
            await update.message.reply_text(f"🚫 Пользователь {target_name} забанен!")
            
        elif "молчи" in text:
            # Парсинг времени (по умолчанию 1 час)
            until = datetime.now() + timedelta(hours=1)
            await context.bot.restrict_chat_member(
                chat_id, target_id, 
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until
            )
            await update.message.reply_text(f"🤫 {target_name} отправлен в мут на 1 час.")
            
        elif "варн" in text:
            count = user_warns.get(target_id, 0) + 1
            user_warns[target_id] = count
            save_db("warns", user_warns)
            
            if count >= 3:
                await context.bot.ban_chat_member(chat_id, target_id)
                await update.message.reply_text(f"⛔️ {target_name} получил 3/3 варна и был забанен!")
                user_warns[target_id] = 0
            else:
                await update.message.reply_text(f"⚠️ {target_name} получил предупреждение ({count}/3).")
                
        elif "скажи" in text:
            perms = ChatPermissions(
                can_send_messages=True, can_send_audios=True, can_send_documents=True,
                can_send_photos=True, can_send_videos=True, can_send_other_messages=True
            )
            await context.bot.restrict_chat_member(chat_id, target_id, permissions=perms)
            await update.message.reply_text(f"🔊 С пользователя {target_name} сняты все ограничения!")
            
    except Exception as e:
        logger.error(f"Ошибка модерации: {e}")

# ==============================================================================
# [8] CALLBACK QUERY HANDLER (ОБРАБОТКА КНОПОК)
# ==============================================================================
async def on_callback_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    data = query.data
    
    # --- ЛОГИКА РАБОТЫ ---
    if data == "work_logic":
        now = datetime.now()
        if uid in work_cooldowns:
            passed = (now - work_cooldowns[uid]).total_seconds()
            if passed < 30:
                rem = int(30 - passed)
                return await query.answer(f"⏳ Вы слишком устали! Отдохните еще {rem} сек.", show_alert=True)
        
        # Начисление чистых денег
        reward = random.randint(45, 95)
        initialize_user(uid)
        user_data[uid]["cash"] += reward
        work_cooldowns[uid] = now
        save_db("users", user_data)
        
        await query.message.edit_text(
            f"✅ **Смена завершена!**\nВы заработали: `{reward} чистых KLC`.\n"
            f"Приходите снова через 30 секунд.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚒ Работать снова", callback_data="work_logic")]]),
            parse_mode="Markdown"
        )

    # --- МАГАЗИН (/magaz) ---
    elif data.startswith("shop_"):
        initialize_user(uid)
        u = user_data[uid]
        total = u["cash"] + u["bonus"]
        
        item = data.split("_")[1]
        price = SHOP_PRICES[item]
        
        if total < price:
            return await query.answer("❌ Недостаточно KLC для покупки!", show_alert=True)
            
        # Списание (сначала бонусы)
        if u["bonus"] >= price: u["bonus"] -= price
        else:
            rem = price - u["bonus"]
            u["bonus"] = 0
            u["cash"] -= rem
            
        if item == "unmute":
            try:
                perms = ChatPermissions(can_send_messages=True, can_send_other_messages=True)
                await context.bot.restrict_chat_member(query.message.chat_id, uid, permissions=perms)
                await query.answer("✅ Мут успешно снят!", show_alert=True)
            except:
                await query.answer("❌ Ошибка при снятии мута (я не админ?)", show_alert=True)
        
        elif item == "unwarn":
            if user_warns.get(uid, 0) > 0:
                user_warns[uid] -= 1
                save_db("warns", user_warns)
                await query.answer("✅ Один варн аннулирован!", show_alert=True)
            else:
                return await query.answer("🧐 У вас и так нет варнов!", show_alert=True)
        
        save_db("users", user_data)
        await query.message.edit_text(f"🎁 **Покупка совершена!**\nВы приобрели услугу через /magaz.")

    # --- РУЛЕТКА (Дуэль) ---
    elif data.startswith("rl_"):
        _, duel_id, penalty = data.split("_")
        if duel_id not in active_duels: return
        
        duel = active_duels[duel_id]
        if uid != duel["p2"]:
            return await query.answer("❌ Нажать может только тот, кого вызвали!", show_alert=True)
            
        # Логика выстрела (1 к 6)
        is_dead = random.choice([True, False, False, False, False, False])
        
        if is_dead:
            loser_id, loser_name = duel["p2"], duel["p2_name"]
            res_msg = f"💀 **БА-БАХ!** {loser_name} проигрывает дуэль!"
            if penalty == "mute":
                until = datetime.now() + timedelta(hours=1)
                await context.bot.restrict_chat_member(query.message.chat_id, loser_id, permissions=ChatPermissions(can_send_messages=False), until_date=until)
            else:
                user_warns[loser_id] = user_warns.get(loser_id, 0) + 1
                save_db("warns", user_warns)
        else:
            res_msg = f"💨 **ЩЕЛЧОК!** {duel['p2_name']} выжил. Настала очередь оппонента... (но мы закончим на этом 😉)"
            
        await query.message.edit_text(res_msg)
        del active_duels[duel_id]

    # --- АДМИН-ДЕЙСТВИЯ (Выплаты) ---
    elif data.startswith("adm_"):
        if uid != OWNER_ID: return
        _, action, target_id, val = data.split("_")
        target_id, val = int(target_id), int(val)
        
        if action == "pay":
            await context.bot.send_message(target_id, f"✅ **Выплата произведена!**\nСумма {val} ₽ отправлена на ваши реквизиты.")
            await query.message.edit_text(query.message.text + "\n\n✅ **СТАТУС: ОПЛАЧЕНО**")
        else:
            # Возврат KLC пользователю
            initialize_user(target_id)
            user_data[target_id]["cash"] += val
            save_db("users", user_data)
            await context.bot.send_message(target_id, "❌ **Ваша заявка на вывод отклонена.**\nKLC возвращены на баланс.")
            await query.message.edit_text(query.message.text + "\n\n❌ **СТАТУС: ОТКЛОНЕНО**")

# ==============================================================================
# [9] ГЛАВНЫЙ ОБРАБОТЧИК СООБЩЕНИЙ
# ==============================================================================
async def main_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ловит команды, написанные обычным текстом"""
    if not update.message or not update.message.text: return
    
    text = update.message.text.lower().strip()
    uid = update.effective_user.id
    
    # Баланс
    if text in ["баланс", "б"]:
        initialize_user(uid)
        await update.message.reply_text(get_balance_text(uid, update.effective_user.first_name), parse_mode="Markdown")
        
    # Работа
    elif text == "работа":
        await cmd_work(update, context)
        
    # Игры
    elif text.startswith("слоты"):
        context.args = text.split()[1:]
        await cmd_slots(update, context)
        
    elif text == "рулетка":
        await cmd_roulette(update, context)
        
    # Вывод
    elif text.startswith("вывод"):
        context.args = text.split()[1:]
        await cmd_withdraw(update, context)

    # Передача (ТП)
    elif text.startswith("тп"):
        context.args = text.split()[1:]
        await cmd_transfer_logic(update, context)
        
    # Модерация (бан, мут, варн)
    elif any(x in text for x in ["бан", "молчи", "варн", "скажи"]):
        await handle_moderation(update, context)

async def cmd_transfer_logic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Логика передачи монет"""
    if not update.message.reply_to_message:
        return await update.message.reply_text("❌ Ответь на сообщение получателя!")
    try:
        amount = int(context.args[0])
        sender_id = update.effective_user.id
        target_id = update.message.reply_to_message.from_user.id
        if amount <= 0: return
        
        initialize_user(sender_id)
        initialize_user(target_id)
        
        if sender_id != OWNER_ID and user_data[sender_id]["cash"] < amount:
            return await update.message.reply_text("❌ У вас мало чистых KLC!")
            
        if sender_id != OWNER_ID: user_data[sender_id]["cash"] -= amount
        user_data[target_id]["cash"] += amount
        save_db("users", user_data)
        
        await update.message.reply_text(f"💸 Вы передали **{amount} чистых KLC** юзеру {update.message.reply_to_message.from_user.first_name}!")
    except: pass

# ==============================================================================
# [10] ТОЧКА ВХОДА (START)
# ==============================================================================
if __name__ == "__main__":
    # Настройки по умолчанию
    defaults = Defaults(parse_mode=constants.ParseMode.MARKDOWN)
    
    # Сборка приложения
    app = ApplicationBuilder().token(TOKEN).defaults(defaults).build()

    # Регистрация команд / (слэш)
    app.add_handler(CommandHandler("start", lambda u, c: u.message.reply_text("🚀 Kryloxa Bot запущен! Пиши /help")))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("donate", cmd_donate))
    app.add_handler(CommandHandler("magaz", cmd_magaz))
    app.add_handler(CommandHandler("createpm", cmd_createpm))
    
    # Обработчик кнопок
    app.add_handler(CallbackQueryHandler(on_callback_click))
    
    # Главный текстовый фильтр
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, main_text_handler))

    print("""
    *****************************************
    * Бот KRYLOXA успешно запущен      *
    * Система готова к работе!         *
    *****************************************
    """)
    
    app.run_polling()
