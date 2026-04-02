import logging
import json
import os
import random
import httpx
import re
import asyncio
from datetime import datetime, timedelta

from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup, 
    Permissions
)
from telegram.ext import (
    ApplicationBuilder, 
    ContextTypes, 
    MessageHandler, 
    filters, 
    CommandHandler, 
    CallbackQueryHandler
)
from telegram.request import HTTPXRequest

# ================================================================
# --- ГЛОБАЛЬНАЯ КОНФИГУРАЦИЯ СИСТЕМЫ KRYLOXA v0.9.6-FINAL ---
# ================================================================

# Твой новый токен, который ты скинул последним
TOKEN = "8548759774:AAGdsv1JThkVBonbFgYURkKFHvJP6juc8CE"

# Твой ID владельца
OWNER_ID = 5679520675

# Названия файлов для базы данных
ECONOMY_FILE = "economy.json"
WARNS_FILE = "warns.json"

# Настройка подробного логирования для отладки на хостинге
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================================================================
# --- МЕХАНИКА РАБОТЫ С ДАННЫМИ (JSON СИСТЕМА) ---
# ================================================================

def load_json(filename, default):
    """Загружает данные из файлов JSON с проверкой на повреждения"""
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding='utf-8') as file:
                return json.load(file)
        except Exception as error:
            logger.error(f"Критическая ошибка при чтении {filename}: {error}")
            return default
    return default

def save_json(filename, data):
    """Сохраняет данные в файлы JSON с красивыми отступами"""
    try:
        with open(filename, "w", encoding='utf-8') as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
    except Exception as error:
        logger.error(f"Ошибка при сохранении {filename}: {error}")

# Инициализация оперативной памяти бота
user_balance = load_json(ECONOMY_FILE, {})
warns = load_json(WARNS_FILE, {})
roulette_games = {}

# ================================================================
# --- ИНСТРУМЕНТЫ ПАРСИНГА И ЛОГИКИ ---
# ================================================================

def parse_punishment(text):
    """
    Тот самый парсер для системы причин.
    Разделяет текст по первому переносу строки.
    Пример:
    Мут 10 минут
    Причина: Оскорбление
    """
    parts = text.split('\n', 1)
    
    # Первая строка разбивается на слова для команд
    first_line_words = parts[0].split()
    
    # Вторая часть - это причина, если она есть
    reason_text = parts[1].strip() if len(parts) > 1 else None
    
    return first_line_words, reason_text

# ================================================================
# --- ОСНОВНЫЕ КОМАНДЫ БОТА ---
# ================================================================

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    welcome_text = (
        "🦾 **Kryloxa Bot v0.9.6-beta в строю!**\n\n"
        "Система активирована. Все конфликты 409 устранены.\n"
        "Для просмотра команд напиши: `Помощь`"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда Помощь"""
    help_text = (
        "📜 **ИНСТРУКЦИЯ ПО ЭКСПЛУАТАЦИИ:**\n\n"
        "🎮 **ГЕЙМПЛЕЙ:**\n"
        "• `Рулетка` — Смертельная дуэль (нужно 2 игрока).\n\n"
        "💰 **ЭКОНОМИКА:**\n"
        "• `Баланс` — Твои накопленные KLC.\n"
        "• `/magaz` — Магазин для покупки бонусов.\n\n"
        "🛠 **АДМИН-ПАНЕЛЬ (реплаем):**\n"
        "• `Мут [время]` + [абзац] + [причина]\n"
        "• `Варн` + [абзац] + [причина]\n"
        "• `Бан` + [абзац] + [причина]\n\n"
        "🔍 **ДЕТЕКТОР GARTIC:**\n"
        "• Просто скинь ссылку в чат, и я проверю комнату."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

# ================================================================
# --- СИСТЕМА МАГАЗИНА ---
# ================================================================

async def magaz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вызов меню магазина"""
    keyboard = [
        [InlineKeyboardButton("💎 VIP Статус (500 KLC)", callback_data="buy_vip")],
        [InlineKeyboardButton("🃏 Снять 1 варн (300 KLC)", callback_data="buy_unwarn")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🛒 **МАГАЗИН БОНУСОВ KRYLOXA:**", reply_markup=reply_markup)

async def shop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка покупок в магазине"""
    query = update.callback_query
    user_id = str(query.from_user.id)
    current_balance = user_balance.get(user_id, 0)

    if query.data == "buy_vip":
        if current_balance >= 500:
            user_balance[user_id] -= 500
            save_json(ECONOMY_FILE, user_balance)
            await query.answer("✅ VIP успешно приобретен!", show_alert=True)
        else:
            await query.answer("❌ Недостаточно коинов (нужно 500 KLC)", show_alert=True)

    elif query.data == "buy_unwarn":
        user_warns = warns.get(user_id, 0)
        if current_balance >= 300 and user_warns > 0:
            user_balance[user_id] -= 300
            warns[user_id] -= 1
            save_json(ECONOMY_FILE, user_balance)
            save_json(WARNS_FILE, warns)
            await query.answer("✅ Варн успешно аннулирован!", show_alert=True)
        else:
            await query.answer("❌ Либо у тебя нет варнов, либо мало денег.", show_alert=True)

# ================================================================
# --- РУССКАЯ РУЛЕТКА (ПОЛНАЯ МЕХАНИКА 3 ЖИЗНИ) ---
# ================================================================

async def roulette_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Инициализация игры"""
    chat_id = update.effective_chat.id
    
    if chat_id in roulette_games:
        return await update.message.reply_text("⚠️ Ошибка: Игра уже запущена в этом чате!")

    # Создаем объект игры
    roulette_games[chat_id] = {
        'player1_id': update.effective_user.id,
        'player1_name': update.effective_user.first_name,
        'player2_id': None,
        'player2_name': None,
        'bet_type': 'klc',
        'lives': {},
        'chamber': [],
        'is_active': False
    }

    # Кнопки выбора ставок
    keyboard = [
        [
            InlineKeyboardButton("💰 100 KLC", callback_data="rbet_klc"),
            InlineKeyboardButton("🤫 Мут (1ч)", callback_data="rbet_mute")
        ],
        [
            InlineKeyboardButton("⚠️ Варн", callback_data="rbet_warn"),
            InlineKeyboardButton("🚫 Бан (1д)", callback_data="rbet_ban")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🎲 **{update.effective_user.first_name} вызывает кого-то на дуэль!**\n"
        "Выбери ставку, на которую будете играть:",
        reply_markup=reply_markup
    )

async def roulette_bet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор ставки инициатором"""
    query = update.callback_query
    game = roulette_games.get(query.message.chat_id)
    
    if not game or query.from_user.id != game['player1_id']:
        return await query.answer("Это не твоя дуэль!", show_alert=True)

    # Устанавливаем тип ставки
    game['bet_type'] = query.data.replace("rbet_", "")
    
    join_kb = [[InlineKeyboardButton("⚔️ ПРИНЯТЬ ВЫЗОВ", callback_data="r_join")]]
    
    await query.edit_message_text(
        f"⚔️ **ДУЭЛЬ ОБЪЯВЛЕНА!**\n"
        f"Инициатор: {game['player1_name']}\n"
        f"Ставка: **{game['bet_type'].upper()}**\n\n"
        "Кто осмелится нажать на курок?",
        reply_markup=InlineKeyboardMarkup(join_kb)
    )

async def roulette_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Логика входа в игру и выстрелов"""
    query = update.callback_query
    chat_id = query.message.chat_id
    game = roulette_games.get(chat_id)
    
    if not game:
        return

    # ВХОД ВТОРОГО ИГРОКА
    if query.data == "r_join":
        if query.from_user.id == game['player1_id']:
            return await query.answer("Ты не можешь стреляться сам с собой!", show_alert=True)
        
        # Настраиваем игру для двоих
        game['player2_id'] = query.from_user.id
        game['player2_name'] = query.from_user.first_name
        game['lives'] = {game['player1_id']: 3, game['player2_id']: 3}
        game['chamber'] = [0, 0, 0, 0, 0, 1] # 1 пуля из 6
        random.shuffle(game['chamber'])
        game['is_active'] = True
        
        shoot_kb = [[InlineKeyboardButton("💥 СПУСТИТЬ КУРОК", callback_data="r_shoot")]]
        
        await query.edit_message_text(
            f"🔫 **Пистолет заряжен!**\n\n"
            f"👤 {game['player1_name']} [3❤️]\n"
            f"👤 {game['player2_name']} [3❤️]\n\n"
            "Очередь за тем, кто первым нажмет на кнопку!",
            reply_markup=InlineKeyboardMarkup(shoot_kb)
        )

    # ЛОГИКА ВЫСТРЕЛА
    elif query.data == "r_shoot":
        shooter_id = query.from_user.id
        
        if shooter_id not in [game['player1_id'], game['player2_id']]:
            return await query.answer("Ты не участник этой дуэли!", show_alert=True)
        
        # Если пули кончились, перезаряжаем
        if not game['chamber']:
            game['chamber'] = [0, 0, 0, 0, 0, 1]
            random.shuffle(game['chamber'])
        
        bullet = game['chamber'].pop()
        shooter_name = query.from_user.first_name
        
        if bullet == 1:
            # ПОПАДАНИЕ
            game['lives'][shooter_id] -= 1
            result_msg = f"💥 **БА-БАХ!** Пуля прошла навылет! {shooter_name} теряет жизнь!"
            # Перезарядка после попадания
            game['chamber'] = [0, 0, 0, 0, 0, 1]
            random.shuffle(game['chamber'])
        else:
            # ПРОМАХ
            result_msg = f"💨 *Щелчок...* {shooter_name} выжил в этот раз."

        # ПРОВЕРКА НА ОКОНЧАНИЕ ИГРЫ (смерть одного из игроков)
        if any(life <= 0 for life in game['lives'].values()):
            winner_id = game['player1_id'] if game['lives'][game['player2_id']] <= 0 else game['player2_id']
            loser_id = game['player2_id'] if winner_id == game['player1_id'] else game['player1_id']
            
            winner_name = game['player1_name'] if winner_id == game['player1_id'] else game['player2_name']
            loser_name = game['player2_name'] if winner_id == game['player1_id'] else game['player1_name']
            
            # ПРИМЕНЕНИЕ НАКАЗАНИЯ
            bet = game['bet_type']
            punish_result = ""
            
            try:
                if bet == "klc":
                    user_balance[str(loser_id)] = user_balance.get(str(loser_id), 0) - 100
                    user_balance[str(winner_id)] = user_balance.get(str(winner_id), 0) + 100
                    punish_result = f"💰 {loser_name} выплатил 100 KLC победителю!"
                
                elif bet == "mute":
                    await context.bot.restrict_chat_member(
                        chat_id, loser_id, 
                        permissions={"can_send_messages": False}, 
                        until_date=datetime.now() + timedelta(hours=1)
                    )
                    punish_result = f"🤫 {loser_name} замолчал на 1 час!"
                
                elif bet == "warn":
                    user_id_str = str(loser_id)
                    warns[user_id_str] = warns.get(user_id_str, 0) + 1
                    punish_result = f"⚠️ {loser_name} получил системный варн!"
                
                elif bet == "ban":
                    await context.bot.ban_chat_member(
                        chat_id, loser_id, 
                        until_date=datetime.now() + timedelta(days=1)
                    )
                    punish_result = f"🚫 {loser_name} изгнан из чата на сутки!"
                
                # Сохраняем изменения в базу
                save_json(ECONOMY_FILE, user_balance)
                save_json(WARNS_FILE, warns)
                
            except Exception as e:
                punish_result = f"⚠️ Не удалось выдать наказание: {e}"

            await query.edit_message_text(
                f"{result_msg}\n\n"
                f"💀 **ДУЭЛЬ ОКОНЧЕНА!**\n"
                f"🏆 Победитель: {winner_name}\n"
                f"🧨 Наказание для проигравшего: {punish_result}"
            )
            
            # Удаляем игру из памяти чата
            del roulette_games[chat_id]
            
        else:
            # ПРОДОЛЖЕНИЕ ИГРЫ
            status_text = (
                f"{result_msg}\n\n"
                f"❤️ {game['player1_name']}: {game['lives'][game['player1_id']]} жизней\n"
                f"❤️ {game['player2_name']}: {game['lives'][game['player2_id']]} жизней\n\n"
                "Кто следующий нажмет на курок?"
            )
            
            next_kb = [[InlineKeyboardButton("💥 ВЫСТРЕЛИТЬ", callback_data="r_shoot")]]
            await query.edit_message_text(status_text, reply_markup=InlineKeyboardMarkup(next_kb))

# ================================================================
# --- ГЛАВНЫЙ ОБРАБОТЧИК СООБЩЕНИЙ (ТЕКСТ + МОДЕРАЦИЯ) ---
# ================================================================

async def message_dispatcher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Функция, которая разгребает всё, что пишут люди"""
    text = update.message.text
    if not text:
        return
    
    user_id = str(update.effective_user.id)
    chat_id = update.effective_chat.id
    msg_low = text.lower()

    # --- 1. СИСТЕМА ЭКОНОМИКИ (Доход за общение) ---
    if user_id not in user_balance:
        user_balance[user_id] = 0
    
    user_balance[user_id] += 1
    save_json(ECONOMY_FILE, user_balance)

    # --- 2. КОМАНДА БАЛАНС ---
    if msg_low == "баланс":
        return await update.message.reply_text(
            f"💰 Твой текущий счет: **{user_balance[user_id]} KLC**", 
            parse_mode="Markdown"
        )

    # --- 3. ДЕТЕКТОР GARTIC PHONE ---
    if "garticphone.com" in msg_low:
        # Пытаемся вытащить ссылку из текста
        urls = re.findall(r'(https?://garticphone\.com/[^\s]+)', text)
        if urls:
            status_msg = await update.message.reply_text("🛰 *Проверяю статус комнаты...*", parse_mode="Markdown")
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(urls[0])
                    if response.status_code == 200:
                        await status_msg.edit_text("✅ **Комната жива! Можно залетать.**", parse_mode="Markdown")
                    else:
                        await status_msg.edit_text("❌ **Комната не найдена или закрыта.**", parse_mode="Markdown")
            except:
                await status_msg.edit_text("⚠️ **Ошибка при проверке ссылки.**")

    # --- 4. СИСТЕМА МОДЕРАЦИИ С ПРИЧИНАМИ (ЧЕРЕЗ РЕПЛАЙ) ---
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        target_id_str = str(target_user.id)

        # Вызываем наш парсер для отделения команды от причины (абзаца)
        cmd_parts, reason = parse_punishment(text)
        main_cmd = cmd_parts[0].lower()

        # ЛОГИКА МУТА
        if main_cmd in ["мут", "молчи"]:
            try:
                # Пытаемся понять время
                amount = int(cmd_parts[1]) if len(cmd_parts) > 1 else 60
                unit = cmd_parts[2].lower() if len(cmd_parts) > 2 else "минут"
                
                # Конвертация в секунды
                seconds = amount * 60
                if "час" in unit: seconds = amount * 3600
                if "ден" in unit: seconds = amount * 86400
                
                await context.bot.restrict_chat_member(
                    chat_id, target_user.id, 
                    permissions={"can_send_messages": False},
                    until_date=datetime.now() + timedelta(seconds=seconds)
                )
                
                response_text = f"🤫 **{target_user.first_name}** отправлен в мут на {amount} {unit}."
                if reason:
                    response_text += f"\n📝 **Причина:** {reason}"
                
                await update.message.reply_text(response_text, parse_mode="Markdown")
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка при выдаче мута: {e}")

        # ЛОГИКА ВАРНА
        elif main_cmd == "варн":
            warns[target_id_str] = warns.get(target_id_str, 0) + 1
            save_json(WARNS_FILE, warns)
            
            response_text = f"⚠️ **{target_user.first_name}** получил предупреждение ({warns[target_id_str]}/3)."
            if reason:
                response_text += f"\n📝 **Причина:** {reason}"
            
            await update.message.reply_text(response_text, parse_mode="Markdown")
            
            # Если 3 варна - бан
            if warns[target_id_str] >= 3:
                await context.bot.ban_chat_member(chat_id, target_user.id)
                await update.message.reply_text(f"🛑 Пользователь {target_user.first_name} достиг лимита варнов и был забанен.")
                warns[target_id_str] = 0
                save_json(WARNS_FILE, warns)

        # ЛОГИКА БАНА
        elif main_cmd == "бан":
            try:
                await context.bot.ban_chat_member(chat_id, target_user.id)
                response_text = f"🚫 **{target_user.first_name}** был навсегда исключен из чата."
                if reason:
                    response_text += f"\n📝 **Причина:** {reason}"
                
                await update.message.reply_text(response_text, parse_mode="Markdown")
            except Exception as e:
                await update.message.reply_text(f"❌ Не удалось забанить: {e}")

# ================================================================
# --- ТОЧКА ВХОДА И ЗАПУСК ---
# ================================================================

if __name__ == "__main__":
    # Создаем приложение бота
    application = ApplicationBuilder().token(TOKEN).request(HTTPXRequest(connect_timeout=20)).build()

    # Регистрация обработчиков команд
    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("magaz", magaz_cmd))
    
    # Регистрация обработчиков кнопок (callback)
    application.add_handler(CallbackQueryHandler(shop_callback, pattern="^buy_"))
    application.add_handler(CallbackQueryHandler(roulette_bet_callback, pattern="^rbet_"))
    application.add_handler(CallbackQueryHandler(roulette_action_callback, pattern="^r_"))
    
    # Регистрация обработчика текста (рулетка и сообщения)
    # Рулетка запускается по кодовому слову "Рулетка"
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^[Рр]улетка$"), roulette_start))
    
    # Все остальные текстовые сообщения
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_dispatcher))

    # Запуск бота в режиме опроса (Polling)
    print(">>> Kryloxa Bot v0.9.6 УСПЕШНО ЗАПУЩЕН И ГОТОВ К РАБОТЕ!")
    application.run_polling(drop_pending_updates=True)
