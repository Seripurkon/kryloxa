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
    CommandHandler
)
from telegram.request import HTTPXRequest

# ==============================================================================
# 1. ГЛОБАЛЬНАЯ КОНФИГУРАЦИЯ
# ==============================================================================
TOKEN = "8641381095:AAH44UdW5z66BkX0rO5qKHOcdESAoghso_g"
OWNER_ID = 5679520675

# Финансовые настройки
CARD_NUMBER = "2202 2084 1533 2171"
SUPPORT_BOT_NAME = "kryloxaHelper_bot"
MIN_WITHDRAW_KLC = 4000 

# Экономические константы
BASE_RATE = 0.06          # Курс: 1 KLC = 0.06 рубля
MORTAL_COMMISSION = 0.65  # Комиссия 65% для обычных игроков (0.65)
DONATOR_COMMISSION = 0.0  # Комиссия 0% для донатеров

# Пути к файлам базы данных
ECONOMY_FILE = "economy.json"
DONATORS_FILE = "donators.json"
RANKS_FILE = "ranks.json"

# Настройки казино (Слоты)
SLOTS_SYMBOLS = ["🍋", "🍒", "🔔", "💎", "7️⃣"]
# Веса для шансов: Лимоны (часто), Семерки (0.1% шанс)
SLOTS_WEIGHTS = [50, 30, 15, 4.9, 0.1] 
MIN_BET_SLOTS = 500

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)

# ==============================================================================
# 2. СИСТЕМА ЗАГРУЗКИ И СОХРАНЕНИЯ ДАННЫХ
# ==============================================================================
def load_json_data(filename, default_value):
    """Универсальная функция загрузки JSON файлов"""
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Конвертируем ключи в числа, если это ID пользователей
                return {int(k) if isinstance(k, str) and k.isdigit() else k: v for k, v in data.items()}
        except Exception as e:
            logging.error(f"Ошибка при чтении файла {filename}: {e}")
            return default_value
    return default_value

def save_json_data(filename, data):
    """Универсальная функция сохранения данных"""
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Ошибка при сохранении файла {filename}: {e}")

# Инициализация баз данных в оперативной памяти
user_balance = load_json_data(ECONOMY_FILE, {})
donators_list = load_json_data(DONATORS_FILE, []) # Список ID донатеров
user_ranks = load_json_data(RANKS_FILE, {OWNER_ID: 4})

# Временные словари (очищаются при перезапуске)
withdraw_requests = {} # Активные заявки на вывод
work_timers = {}       # Кулдаун на команду 'работа'
bonus_timers = {}      # Кулдаун на команду 'бонус'

# ==============================================================================
# 3. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ЭКОНОМИКИ
# ==============================================================================
def get_user_stats(user_id):
    """Получение баланса пользователя с созданием записи, если его нет"""
    if user_id not in user_balance:
        user_balance[user_id] = {"main": 500, "bonus": 0}
    
    # Исправление старого формата данных (если там было просто число)
    if isinstance(user_balance[user_id], int):
        old_val = user_balance[user_id]
        user_balance[user_id] = {"main": old_val, "bonus": 0}
        
    return user_balance[user_id]

def is_user_donator(user_id):
    """Проверка наличия статуса донатера"""
    if user_id == OWNER_ID:
        return True
    return user_id in donators_list

def update_user_balance(user_id, amount, balance_type="main"):
    """Изменение баланса (main - чистые, bonus - бонусы)"""
    # Владелец не может уйти в минус
    if user_id == OWNER_ID and amount < 0:
        return
        
    stats = get_user_stats(user_id)
    stats[balance_type] += amount
    
    # Защита от отрицательного баланса
    if stats[balance_type] < 0:
        stats[balance_type] = 0
        
    save_json_data(ECONOMY_FILE, user_balance)

# ==============================================================================
# 4. ЯДРО КАЗИНО (МЕХАНИКА СЛОТОВ)
# ==============================================================================
async def execute_slots_spin(user_id, bet_amount):
    """Логика вращения игрового автомата"""
    stats = get_user_stats(user_id)
    total_balance = stats["main"] + stats["bonus"]
    
    if total_balance < bet_amount:
        return "❌ У вас недостаточно средств для этой ставки!", False
    
    # Списание ставки: сначала списываем с бонусного счета
    if stats["bonus"] >= bet_amount:
        update_user_balance(user_id, -bet_amount, "bonus")
    else:
        # Если бонусов не хватает, списываем остаток с основного счета
        rem_bet = bet_amount - stats["bonus"]
        update_user_balance(user_id, -stats["bonus"], "bonus")
        update_user_balance(user_id, -rem_bet, "main")

    # Генерация результата (3 барабана)
    result = [random.choices(SLOTS_SYMBOLS, weights=SLOTS_WEIGHTS)[0] for _ in range(3)]
    payout = 0

    # Проверка комбинаций
    if result[0] == result[1] == result[2]:
        # Три в ряд
        if result[0] == "7️⃣":
            payout = bet_amount * 200 # Джекпот!
        elif result[0] == "💎":
            payout = bet_amount * 25
        else:
            payout = bet_amount * 10
    elif (result[0] == result[1] or result[1] == result[2] or result[0] == result[2]):
        # Пара одинаковых символов (шанс 40% на выигрыш x1.5)
        if random.random() < 0.4:
            payout = int(bet_amount * 1.5)
    
    # Обработка выигрыша
    if payout > 0:
        update_user_balance(user_id, payout, "main") # Выигрыш всегда в чистые KLC
        msg = (
            f"🎰 Результат: `[ {result[0]} | {result[1]} | {result[2]} ]` \n\n"
            f"🎉 **ПОБЕДА!**\n"
            f"Вы выиграли: +{payout} KLC (Чистые)"
        )
        return msg, True
    
    # Проигрыш
    msg = (
        f"🎰 Результат: `[ {result[0]} | {result[1]} | {result[2]} ]` \n\n"
        f"💀 **ПРОИГРЫШ**\n"
        f"Ставка уходит в банк казино. Попробуйте еще раз!"
    )
    return msg, True

# ==============================================================================
# 5. ОБРАБОТЧИКИ КОМАНД ПОЛЬЗОВАТЕЛЕЙ
# ==============================================================================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие бота"""
    await update.message.reply_text(
        "👋 Добро пожаловать в Kryloxa System v2.0!\n"
        "Я ваш персональный бот-казино с системой вывода средств.\n\n"
        "Напишите /help, чтобы увидеть список всех команд."
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список доступных команд"""
    help_text = (
        "📜 **СПРАВОЧНИК КОМАНД**\n\n"
        "💰 **Экономика и Баланс:**\n"
        "• `баланс` (или `б`) — проверить состояние счета\n"
        "• `бонус` — забрать ежедневный подарок\n"
        "• `тп [сумма]` — перевести монеты (ответом на сообщение)\n\n"
        "🎰 **Азартные Игры:**\n"
        "• `слоты [ставка]` — запустить игровой аппарат\n"
        "• `работа` — быстрый заработок бонусов\n\n"
        "📤 **Вывод Средств:**\n"
        "• `вывод [сумма] [карта]` — создать заявку на выплату\n\n"
        "💎 **Для Донатеров:**\n"
        "• `/donators` — список почетных участников\n"
        "• `/donate` — как купить KLC и статус"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def cmd_donators(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вывод списка донатеров"""
    if not donators_list:
        return await update.message.reply_text("📜 Список донатеров пока пуст. Стань первым! /donate")
    
    text = "💎 **НАШИ VIP-КЛИЕНТЫ (0% КОМИССИИ):**\n\n"
    for index, d_id in enumerate(donators_list, 1):
        text += f"{index}. ID: `{d_id}`\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_set_donator(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админ-команда: назначить донатера (через реплай)"""
    if update.effective_user.id != OWNER_ID:
        return # Только владелец может назначать

    if not update.message.reply_to_message:
        return await update.message.reply_text("❌ Ошибка! Команду нужно писать в ответ на сообщение игрока.")
    
    target_user_id = update.message.reply_to_message.from_user.id
    
    if target_user_id not in donators_list:
        donators_list.append(target_user_id)
        save_json_data(DONATORS_FILE, donators_list)
        await update.message.reply_text(f"✅ УСПЕХ! Пользователь `{target_user_id}` теперь ДОНАТЕР.")
    else:
        await update.message.reply_text("❕ Этот пользователь уже имеет статус донатера.")

# ==============================================================================
# 6. ОСНОВНОЙ ТЕКСТОВЫЙ ОБРАБОТЧИК
# ==============================================================================
async def text_message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Маршрутизация текстовых команд (баланс, слоты, вывод и т.д.)"""
    if not update.message or not update.message.text:
        return
    
    raw_message = update.message.text
    clean_text = raw_message.lower().strip()
    user_info = update.effective_user
    u_id = user_info.id
    stats = get_user_stats(u_id)

    # --- КОМАНДА: БАЛАНС ---
    if clean_text in ["баланс", "б"]:
        status = "💎 ДОНАТЕР (0%)" if is_user_donator(u_id) else "👤 ОБЫЧНЫЙ (65%)"
        balance_msg = (
            f"👤 **Профиль:** {user_info.first_name}\n"
            f"💳 **Чистые KLC:** {stats['main']}\n"
            f"🎁 **Бонусы:** {stats['bonus']}\n"
            f"🎭 **Статус:** {status}"
        )
        await update.message.reply_text(balance_msg, parse_mode="Markdown")

    # --- КОМАНДА: БОНУС ---
    elif clean_text == "бонус":
        now = datetime.now()
        if u_id in bonus_timers and now < bonus_timers[u_id] + timedelta(days=1):
            return await update.message.reply_text("❌ Вы уже забирали бонус сегодня. Приходите завтра!")
        
        bonus_value = random.randint(200, 600)
        update_user_balance(u_id, bonus_value, "bonus")
        bonus_timers[u_id] = now
        await update.message.reply_text(f"🎁 Ежедневный бонус зачислен: +{bonus_value} KLC")

    # --- КОМАНДА: СЛОТЫ ---
    elif clean_text.startswith("слоты "):
        try:
            bet_parts = clean_text.split()
            if len(bet_parts) < 2: return
            
            bet_value = int(bet_parts[1])
            if bet_value < MIN_BET_SLOTS:
                return await update.message.reply_text(f"❌ Минимальная ставка в казино: {MIN_BET_SLOTS} KLC")
            
            # Запуск логики
            response_text, is_playable = await execute_slots_spin(u_id, bet_value)
            
            # Создание клавиатуры для повтора
            keyboard = None
            if is_playable:
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🎰 Крутить еще", callback_data=f"spin_again_{bet_value}"),
                    InlineKeyboardButton("🛑 Стоп", callback_data="spin_stop")
                ]])
            
            await update.message.reply_text(response_text, reply_markup=keyboard, parse_mode="Markdown")
        except ValueError:
            await update.message.reply_text("❌ Пожалуйста, укажите ставку числом. Пример: `слоты 1000`")

    # --- КОМАНДА: ВЫВОД СРЕДСТВ (HARDCORE LOGIC) ---
    elif clean_text.startswith("вывод "):
        try:
            args = raw_message.split()
            if len(args) < 3:
                return await update.message.reply_text("❌ Формат: `вывод [сумма] [номер карты]`")
            
            withdraw_amount = int(args[1])
            card_details = " ".join(args[2:])
            
            if withdraw_amount < MIN_WITHDRAW_KLC:
                return await update.message.reply_text(f"❌ Минимальная сумма вывода: {MIN_WITHDRAW_KLC} KLC")
            
            if (stats["main"] + stats["bonus"]) < withdraw_amount:
                return await update.message.reply_text("❌ У вас недостаточно монет для вывода такой суммы!")

            # ЗАМОРОЗКА СРЕДСТВ: Списываем монеты мгновенно
            if stats["main"] >= withdraw_amount:
                update_user_balance(u_id, -withdraw_amount, "main")
            else:
                remaining_debt = withdraw_amount - stats["main"]
                update_user_balance(u_id, -stats["main"], "main")
                update_user_balance(u_id, -remaining_debt, "bonus")

            # РАСЧЕТ ИТОГОВОЙ СУММЫ К ВЫПЛАТЕ (Комиссии)
            if is_user_donator(u_id):
                # Донатеры получают всё (0% комиссия)
                rub_payout = int(withdraw_amount * BASE_RATE)
                commission_label = "0% (VIP)"
            else:
                # Обычные игроки теряют 65% (100% - 65% = 35% чистого дохода)
                rub_payout = int(withdraw_amount * BASE_RATE * (1 - MORTAL_COMMISSION))
                commission_label = "65% (Стандартная)"

            request_id = random.randint(1000, 9999)
            # Сохраняем заявку во временную память
            withdraw_requests[request_id] = {
                "u_id": u_id, 
                "amount_klc": withdraw_amount, 
                "amount_rub": rub_payout
            }

            await update.message.reply_text(f"✅ Заявка #{request_id} создана. Ожидайте подтверждения от администратора.")

            # Уведомление Владельцу (OWNER_ID)
            admin_notification = (
                f"💰 **НОВАЯ ЗАЯВКА НА ВЫПЛАТУ #{request_id}**\n\n"
                f"👤 Игрок: {user_info.first_name} (ID: `{u_id}`)\n"
                f"💎 Сумма вывода: {withdraw_amount} KLC\n"
                f"🎭 Комиссия системы: {commission_label}\n\n"
                f"💵 **НУЖНО СКИНУТЬ НА КАРТУ: {rub_payout} РУБ**\n"
                f"💳 Реквизиты: `{card_details}`"
            )
            
            admin_keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Оплачено", callback_data=f"adm_confirm_{request_id}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"adm_cancel_{request_id}")
            ]])
            
            await context.bot.send_message(
                OWNER_ID, 
                admin_notification, 
                reply_markup=admin_keyboard, 
                parse_mode="Markdown"
            )

        except ValueError:
            await update.message.reply_text("❌ Ошибка в сумме. Используйте цифры.")

# ==============================================================================
# 7. ОБРАБОТЧИК ИНЛАЙН-КНОПОК (CALLBACKS)
# ==============================================================================
async def global_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка всех нажатий на кнопки в боте"""
    query = update.callback_query
    u_id = query.from_user.id
    callback_data = query.data

    # --- КНОПКИ КАЗИНО ---
    if callback_data.startswith("spin_again_"):
        bet_to_repeat = int(callback_data.split("_")[2])
        new_msg, is_ok = await execute_slots_spin(u_id, bet_to_repeat)
        
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🎰 Крутить еще", callback_data=f"spin_again_{bet_to_repeat}"),
            InlineKeyboardButton("🛑 Стоп", callback_data="spin_stop")
        ]]) if is_ok else None
        
        await query.edit_message_text(new_msg, reply_markup=kb, parse_mode="Markdown")

    elif callback_data == "spin_stop":
        await query.edit_message_text("🛑 Вы вышли из игры. Ваш текущий баланс сохранен.")

    # --- КНОПКИ РАБОТЫ ---
    elif callback_data == "do_work_task":
        now = datetime.now()
        if u_id in work_timers and now < work_timers[u_id] + timedelta(seconds=45):
            return await query.answer("⏳ Вы слишком устали. Подождите 45 секунд!", show_alert=True)
        
        earned = random.randint(50, 120)
        update_user_balance(u_id, earned, "bonus")
        work_timers[u_id] = now
        await query.answer(f"⚒ Работа завершена! Получено {earned} бонусов.")
        await query.edit_message_text(
            f"⚒ Смена окончена! Вы заработали {earned} бонусных KLC.\nСледующая смена через 45 секунд.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚒ Работать снова", callback_data="do_work_task")]])
        )

    # --- АДМИН-КНОПКИ ВЫВОДА ---
    elif callback_data.startswith("adm_"):
        _, action, rid = callback_data.split("_")
        rid = int(rid)
        request_data = withdraw_requests.get(rid)
        
        if not request_data:
            return await query.answer("❌ Заявка не найдена или уже была обработана.")
        
        target_player_id = request_data["u_id"]
        
        if action == "confirm":
            # Уведомляем игрока об успехе
            await context.bot.send_message(
                target_player_id, 
                f"✅ Ваша заявка #{rid} исполнена! Деньги отправлены на ваши реквизиты. Спасибо за игру!"
            )
            await query.edit_message_text(query.message.text + "\n\n✅ **ИТОГ: ВЫПЛАЧЕНО**")
        
        elif action == "cancel":
            # Возвращаем монеты игроку (в Чистые KLC)
            update_user_balance(target_player_id, request_data["amount_klc"], "main")
            await context.bot.send_message(
                target_player_id, 
                f"❌ Ваша заявка #{rid} была отклонена администратором. Все KLC возвращены на ваш баланс."
            )
            await query.edit_message_text(query.message.text + "\n\n❌ **ИТОГ: ОТКАЗАНО (СРЕДСТВА ВОЗВРАЩЕНЫ)**")
        
        # Удаляем заявку из списка активных
        del withdraw_requests[rid]

# ==============================================================================
# 8. ЗАПУСК БОТА
# ==============================================================================
if __name__ == "__main__":
    # Инициализация приложения
    bot_app = ApplicationBuilder().token(TOKEN).request(HTTPXRequest(connect_timeout=30)).build()

    # Регистрация команд через /
    bot_app.add_handler(CommandHandler("start", cmd_start))
    bot_app.add_handler(CommandHandler("help", cmd_help))
    bot_app.add_handler(CommandHandler("donators", cmd_donators))
    bot_app.add_handler(CommandHandler("setdonator", cmd_set_donator))
    
    # Регистрация текстовой "Работы"
    bot_app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^[Рр]абота$"), 
        lambda u, c: u.message.reply_text("⚒ Нажмите на кнопку, чтобы начать смену и получить бонусы:", 
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚒ Начать работу", callback_data="do_work_task")]]))))

    # Регистрация обработчика нажатий
    bot_app.add_handler(CallbackQueryHandler(global_callback_handler))
    
    # Регистрация основного текстового движка (должен быть последним)
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_router))
    
    print("--- KRYLOXA SYSTEM v2.0 СТАТУС: ЗАПУЩЕНО ---")
    bot_app.run_polling()
