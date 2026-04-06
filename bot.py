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
# НАСТРОЙКИ БОТА
# ==========================================
TOKEN = "8641381095:AAH44UdW5z66BkX0rO5qKHOcdESAoghso_g"
OWNER_ID = 5679520675

FILES = {
    "economy": "economy.json", 
    "donators": "donators.json", 
    "ranks": "ranks.json",
    "promos": "promos.json"
}

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)

# ==========================================
# СИСТЕМА СОХРАНЕНИЯ ДАННЫХ
# ==========================================
def load_json(file_key, default_value):
    filepath = FILES[file_key]
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as file:
                data = json.load(file)
                # Восстанавливаем ID пользователей как числа
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

# ==========================================
# ИНИЦИАЛИЗАЦИЯ БАЗ ДАННЫХ В ПАМЯТИ
# ==========================================
user_balance = load_json("economy", {})
donators_list = load_json("donators", [])
user_ranks = load_json("ranks", {OWNER_ID: 4})

# Временные данные (сбрасываются при перезапуске бота)
warns = {}
roulette_games = {}
work_timers = {}
bonus_timers = {}

def get_user_rank(user_id):
    """Возвращает уровень прав пользователя (4 - Владелец, 0 - Обычный)"""
    if user_id == OWNER_ID:
        return 4
    return user_ranks.get(user_id, 0)

# ==========================================
# ПАРСЕР ВРЕМЕНИ ДЛЯ МУТА
# ==========================================
def parse_time(text):
    text = text.lower().strip()
    match = re.search(r"(\d+)\s*([мчдг])", text)
    if not match:
        return 3600, "1 час" # По умолчанию 1 час
    
    amount = int(match.group(1))
    unit = match.group(2)
    
    if unit == 'м': 
        return amount * 60, f"{amount} мин."
    if unit == 'ч': 
        return amount * 3600, f"{amount} ч."
    if unit == 'д': 
        return amount * 86400, f"{amount} дн."
    if unit == 'г': 
        return amount * 31536000, f"{amount} лет."
    
    return 3600, "1 час"

# ==========================================
# ИГРОВЫЕ МЕХАНИКИ: СЛОТЫ
# ==========================================
async def play_slots(user_id, bet):
    # Жесткий лимит ставки
    if bet > 1000:
        return "❌ Ошибка! Максимальная ставка в слотах — **1000 KLC**.", False
    
    current_balance = user_balance.get(user_id, 0)
    
    # Проверка баланса (владелец играет бесплатно)
    if user_id != OWNER_ID:
        if current_balance < bet:
            return f"❌ Недостаточно средств! У вас {current_balance} KLC.", False
        # Списываем ставку
        user_balance[user_id] -= bet
    
    symbols = ["🍒", "🍋", "🔔", "💎", "7️⃣"]
    result = [random.choice(symbols) for _ in range(3)]
    
    win_amount = 0
    # Логика выигрыша
    if result[0] == result[1] == result[2]:
        if result[0] == "7️⃣":
            win_amount = bet * 200
        elif result[0] == "💎":
            win_amount = bet * 50
        else:
            win_amount = bet * 15
    elif result[0] == result[1] or result[1] == result[2]:
        win_amount = int(bet * 1.5)
        
    if win_amount > 0:
        if user_id != OWNER_ID:
            user_balance[user_id] += win_amount
        save_json("economy", user_balance)
        return f"🎰 `[ {result[0]} | {result[1]} | {result[2]} ]` \n\n✅ **ПОБЕДА!** Вы выиграли **{win_amount} KLC**", True
    
    save_json("economy", user_balance)
    return f"🎰 `[ {result[0]} | {result[1]} | {result[2]} ]` \n\n❌ **ПРОИГРЫШ!**", True

# ==========================================
# БАЗОВЫЕ КОМАНДЫ БОТА
# ==========================================
async def command_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 **ПОЛНЫЙ СПРАВОЧНИК KRYLOXA BOT**\n\n"
        "💰 **Экономика и Фарм:**\n"
        "• `баланс` или `б` — проверить свой кошелек\n"
        "• `работа` — заработать KLC (раз в 30 секунд)\n"
        "• `бонус` — ежедневная награда\n"
        "• `передать [сумма]` — скинуть деньги реплаем\n"
        "• `вывод [сумма]` — заявка на вывод средств\n\n"
        "🎰 **Азартные игры:**\n"
        "• `слоты [сумма]` — казино (макс. ставка 1000 KLC)\n"
        "• `рулетка` — дуэль на мут/варн (реплаем)\n\n"
        "🛡 **Модерация (для админов):**\n"
        "• `бан` — заблокировать юзера (реплаем)\n"
        "• `молчи [время]` — выдать мут\n"
        "• `варн` — выдать предупреждение\n"
        "• `скажи` — снять все ограничения\n\n"
        "💎 **Донат:**\n"
        "• `/donate` — магазин привилегий и валюты"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def command_donate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    shop_text = (
        "💎 **ОФИЦИАЛЬНЫЙ МАГАЗИН KRYLOXA**\n\n"
        "Выберите желаемый товар ниже. Статус донатера "
        "позволяет выводить средства без комиссии (0%)."
    )
    keyboard = [
        [InlineKeyboardButton("💎 Статус Донатера (0% комиссия) — 100 руб.", callback_data="buy_status")],
        [InlineKeyboardButton("💰 5.000 KLC — 300 руб.", callback_data="buy_5k")],
        [InlineKeyboardButton("💳 10.000 KLC — 550 руб.", callback_data="buy_10k")],
        [InlineKeyboardButton("👨‍💻 Связаться с владельцем", url="https://t.me/твой_ник")]
    ]
    await update.message.reply_text(
        shop_text, 
        reply_markup=InlineKeyboardMarkup(keyboard), 
        parse_mode="Markdown"
    )

async def command_add_donator(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message = update.message
    
    if user_id != OWNER_ID:
        return
        
    if not message.reply_to_message:
        await message.reply_text("❌ Ответьте на сообщение пользователя, чтобы выдать статус.")
        return
        
    target_id = message.reply_to_message.from_user.id
    if target_id not in donators_list:
        donators_list.append(target_id)
        save_json("donators", donators_list)
        await message.reply_text("✅ Пользователь успешно добавлен в список донатеров!")
    else:
        await message.reply_text("⚠️ Этот пользователь уже является донатером.")

# ==========================================
# ОБРАБОТЧИК ТЕКСТОВЫХ СООБЩЕНИЙ
# ==========================================
async def handle_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
        
    user = update.effective_user
    chat_id = update.effective_chat.id
    reply_msg = update.message.reply_to_message
    raw_text = update.message.text
    text = raw_text.lower().strip()
    args = text.split()
    user_id = user.id

    # --- ЭКОНОМИКА: БАЛАНС ---
    if text in ["баланс", "б"]:
        balance = "Бесконечно" if user_id == OWNER_ID else user_balance.get(user_id, 0)
        await update.message.reply_text(f"👤 Профиль {user.first_name}:\n💰 Баланс: **{balance} KLC**", parse_mode="Markdown")
        return

    # --- ЭКОНОМИКА: ПРОФИЛЬ / ИНФА ---
    if text in ["инфа", "профиль"]:
        target_user = reply_msg.from_user if reply_msg else user
        target_id = target_user.id
        balance = "Бесконечно" if target_id == OWNER_ID else user_balance.get(target_id, 0)
        rank_name = "Владелец 👑" if target_id == OWNER_ID else ("Донатер 💎" if target_id in donators_list else "Игрок 🎮")
        warn_count = warns.get(target_id, 0)
        
        profile_text = (
            f"👤 **Профиль {target_user.first_name}**:\n"
            f"🆔 ID: `{target_id}`\n"
            f"⭐️ Статус: {rank_name}\n"
            f"💰 Баланс: {balance} KLC\n"
            f"⚠️ Предупреждения: {warn_count}/3"
        )
        await update.message.reply_text(profile_text, parse_mode="Markdown")
        return

    # --- ЭКОНОМИКА: ПЕРЕДАТЬ ---
    if args[0] == "передать" and len(args) > 1 and reply_msg:
        try:
            amount = int(args[1])
            if amount <= 0:
                return await update.message.reply_text("❌ Сумма должна быть больше нуля.")
                
            if user_id != OWNER_ID and user_balance.get(user_id, 0) < amount:
                return await update.message.reply_text("❌ На балансе недостаточно средств!")
                
            target_id = reply_msg.from_user.id
            if user_id == target_id:
                return await update.message.reply_text("❌ Нельзя перевести деньги самому себе.")
                
            if user_id != OWNER_ID:
                user_balance[user_id] -= amount
            user_balance[target_id] = user_balance.get(target_id, 0) + amount
            save_json("economy", user_balance)
            
            await update.message.reply_text(f"💸 Вы успешно перевели **{amount} KLC** пользователю {reply_msg.from_user.first_name}.", parse_mode="Markdown")
        except ValueError:
            pass
        return

    # --- ЭКОНОМИКА: РАБОТА ---
    if text == "работа":
        current_time = datetime.now()
        
        if user_id in work_timers:
            time_passed = (current_time - work_timers[user_id]).total_seconds()
            if time_passed < 30:
                wait_time = int(30 - time_passed)
                await update.message.reply_text(f"⏳ Вы устали. Подождите еще {wait_time} сек.")
                return
                
        earned_amount = random.randint(50, 150)
        user_balance[user_id] = user_balance.get(user_id, 0) + earned_amount
        work_timers[user_id] = current_time
        save_json("economy", user_balance)
        
        await update.message.reply_text(f"⚒ Вы отлично поработали и заработали **{earned_amount} KLC**!", parse_mode="Markdown")
        return

    # --- ЭКОНОМИКА: БОНУС ---
    if text == "бонус":
        current_time = datetime.now()
        
        if user_id in bonus_timers:
            time_passed = (current_time - bonus_timers[user_id]).total_seconds()
            if time_passed < 86400: # 24 часа
                hours_left = int((86400 - time_passed) // 3600)
                await update.message.reply_text(f"❌ Ежедневный бонус уже получен. Возвращайтесь через {hours_left} ч.")
                return
                
        bonus_amount = random.randint(500, 1500)
        user_balance[user_id] = user_balance.get(user_id, 0) + bonus_amount
        bonus_timers[user_id] = current_time
        save_json("economy", user_balance)
        
        await update.message.reply_text(f"🎁 Вы получили свой ежедневный бонус: **{bonus_amount} KLC**!", parse_mode="Markdown")
        return

    # --- ЭКОНОМИКА: ВЫВОД ---
    if args[0] == "вывод" and len(args) > 1:
        try:
            amount = int(args[1])
            if amount <= 0:
                return
                
            current_balance = user_balance.get(user_id, 0)
            if user_id != OWNER_ID and current_balance < amount:
                await update.message.reply_text(f"❌ У вас недостаточно средств для вывода. Баланс: {current_balance} KLC.")
                return
            
            # Расчет комиссии (65% для обычных, 0% для донатеров)
            is_donator = user_id in donators_list or user_id == OWNER_ID
            fee_percentage = 0 if is_donator else 65
            final_amount = int(amount * (1 - fee_percentage / 100))
            
            # Списание с баланса
            if user_id != OWNER_ID:
                user_balance[user_id] -= amount
            save_json("economy", user_balance)
            
            # Уведомление пользователю
            receipt_text = (
                f"✅ **Заявка на вывод успешно создана!**\n\n"
                f"Сумма списания: {amount} KLC\n"
                f"Комиссия системы: {fee_percentage}%\n"
                f"К получению чистыми: **{final_amount} KLC**\n\n"
                f"Ожидайте обработки администратором."
            )
            await update.message.reply_text(receipt_text, parse_mode="Markdown")
            
            # Уведомление Владельцу бота (Тебе)
            admin_text = (
                f"💰 **НОВЫЙ ЗАПРОС НА ВЫВОД!**\n\n"
                f"👤 От: {user.full_name} (@{user.username})\n"
                f"🆔 ID пользователя: `{user_id}`\n\n"
                f"Запрошено к списанию: {amount} KLC\n"
                f"Сумма к выплате: **{final_amount} KLC**"
            )
            await context.bot.send_message(chat_id=OWNER_ID, text=admin_text, parse_mode="Markdown")
            
        except ValueError:
            pass
        return

    # --- ИГРЫ: СЛОТЫ ---
    if args[0] == "слоты" and len(args) > 1:
        try:
            bet_amount = int(args[1])
            if bet_amount <= 0:
                return
                
            result_text, is_success = await play_slots(user_id, bet_amount)
            
            keyboard = None
            if is_success:
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🎰 Крутить снова", callback_data=f"casino_{bet_amount}")
                ]])
                
            await update.message.reply_text(result_text, reply_markup=keyboard, parse_mode="Markdown")
        except ValueError:
            pass
        return

    # --- ИГРЫ: РУЛЕТКА (ВЫЗОВ НА ДУЭЛЬ) ---
    if text == "рулетка" and reply_msg:
        target_user = reply_msg.from_user
        
        if target_user.id == user_id:
            await update.message.reply_text("❌ Нельзя играть в рулетку с самим собой.")
            return
            
        if target_user.is_bot:
            await update.message.reply_text("❌ Боты не играют в рулетку.")
            return

        game_id = f"duel_{user_id}_{target_user.id}_{random.randint(1000, 9999)}"
        
        roulette_games[game_id] = {
            "player1_id": user_id,
            "player1_name": user.first_name,
            "player2_id": target_user.id,
            "player2_name": target_user.first_name,
        }
        
        duel_text = (
            f"🎲 **РУССКАЯ РУЛЕТКА**\n\n"
            f"{user.first_name} вызывает {target_user.first_name} на смертельную дуэль!\n\n"
            f"👉 {target_user.first_name}, выберите ставку (наказание для проигравшего):"
        )
        
        buttons = [
            [
                InlineKeyboardButton("Выдать Варн", callback_data=f"roulette_{game_id}_warn"),
                InlineKeyboardButton("Мут на 1 час", callback_data=f"roulette_{game_id}_mute")
            ]
        ]
        
        await update.message.reply_text(
            duel_text, 
            reply_markup=InlineKeyboardMarkup(buttons), 
            parse_mode="Markdown"
        )
        return

    # --- МОДЕРАЦИЯ ---
    if reply_msg and args[0] in ["бан", "молчи", "варн", "скажи"]:
        # Проверка прав (минимум 1 уровень)
        if get_user_rank(user_id) < 1:
            return
            
        target_id = reply_msg.from_user.id
        target_name = reply_msg.from_user.first_name
        
        # Защита от модерации админов
        if get_user_rank(target_id) >= get_user_rank(user_id) and user_id != OWNER_ID:
            await update.message.reply_text("❌ Вы не можете наказать пользователя с равными или более высокими правами.")
            return

        try:
            if args[0] == "молчи":
                seconds, time_str = parse_time(raw_text)
                until_time = datetime.now() + timedelta(seconds=seconds)
                
                await context.bot.restrict_chat_member(
                    chat_id, 
                    target_id, 
                    permissions=ChatPermissions(can_send_messages=False), 
                    until_date=until_time
                )
                await update.message.reply_text(f"🤫 Пользователь {target_name} получил мут на {time_str}.")
                
            elif args[0] == "бан":
                await context.bot.ban_chat_member(chat_id, target_id)
                await update.message.reply_text(f"🚫 Пользователь {target_name} был заблокирован в чате.")
                
            elif args[0] == "варн":
                current_warns = warns.get(target_id, 0) + 1
                warns[target_id] = current_warns
                
                if current_warns >= 3:
                    await context.bot.ban_chat_member(chat_id, target_id)
                    await update.message.reply_text(f"⛔️ {target_name} получил 3/3 варнов и был забанен.")
                    warns[target_id] = 0 # Сброс после бана
                else:
                    await update.message.reply_text(f"⚠️ {target_name} получил предупреждение ({current_warns}/3).")
                    
            elif args[0] == "скажи":
                all_permissions = ChatPermissions(
                    can_send_messages=True, 
                    can_send_photos=True, 
                    can_send_videos=True, 
                    can_send_other_messages=True
                )
                await context.bot.restrict_chat_member(chat_id, target_id, permissions=all_permissions)
                await update.message.reply_text(f"🔊 Все ограничения с пользователя {target_name} сняты.")
                
        except Exception as e:
            logging.error(f"Ошибка модерации: {e}")
            await update.message.reply_text("❌ Произошла ошибка. Проверьте права бота в чате.")

# ==========================================
# ОБРАБОТЧИК КНОПОК (CALLBACKS)
# ==========================================
async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    # --- Кнопки магазина ---
    if query.data.startswith("buy_"):
        if query.data == "buy_status":
            await query.answer("Цена: 100 руб. Напишите владельцу бота для оплаты!", show_alert=True)
        elif query.data == "buy_5k":
            await query.answer("Цена: 300 руб. Напишите владельцу бота для оплаты!", show_alert=True)
        elif query.data == "buy_10k":
            await query.answer("Цена: 550 руб. Напишите владельцу бота для оплаты!", show_alert=True)
        return

    # --- Кнопка повтора слотов ---
    if query.data.startswith("casino_"):
        try:
            bet_amount = int(query.data.split("_")[1])
            result_text, is_success = await play_slots(user_id, bet_amount)
            
            keyboard = None
            if is_success:
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🎰 Крутить снова", callback_data=f"casino_{bet_amount}")
                ]])
                
            await query.message.edit_text(
                text=result_text, 
                reply_markup=keyboard, 
                parse_mode="Markdown"
            )
        except Exception as e:
            await query.answer(f"Ошибка: {e}", show_alert=True)
        return

    # --- Логика Рулетки ---
    if query.data.startswith("roulette_"):
        parts = query.data.split("_")
        game_id = f"{parts[0]}_{parts[1]}_{parts[2]}_{parts[3]}"
        bet_type = parts[4] # "warn" или "mute"
        
        if game_id not in roulette_games:
            await query.answer("Эта игра уже завершена или не существует.", show_alert=True)
            return
            
        game_data = roulette_games[game_id]
        
        # Нажать кнопку выбора наказания может только тот, кого вызвали (Player 2)
        if user_id != game_data["player2_id"]:
            await query.answer("Не ваша очередь! Ставку выбирает вызванный игрок.", show_alert=True)
            return
            
        # Логика выстрела (1 шанс из 6 умереть)
        chamber = ["💥", "💨", "💨", "💨", "💨", "💨"]
        shot_result = random.choice(chamber)
        
        if shot_result == "💥":
            # Вызванный игрок застрелился
            loser_id = game_data["player2_id"]
            loser_name = game_data["player2_name"]
            winner_name = game_data["player1_name"]
            
            result_text = (
                f"💀 **БАБАХ!** Барабан провернулся...\n\n"
                f"Игрок {loser_name} проигрывает дуэль!\n"
                f"Победитель: {winner_name}\n\n"
                f"Наказание: **{'Выдан ВАРН' if bet_type == 'warn' else 'Выдан МУТ на 1 час'}**"
            )
            
            # Применяем наказание
            try:
                if bet_type == "mute":
                    until_time = datetime.now() + timedelta(hours=1)
                    await context.bot.restrict_chat_member(
                        query.message.chat_id, 
                        loser_id, 
                        permissions=ChatPermissions(can_send_messages=False), 
                        until_date=until_time
                    )
                elif bet_type == "warn":
                    warns[loser_id] = warns.get(loser_id, 0) + 1
            except Exception as e:
                logging.error(f"Ошибка наказания в рулетке: {e}")
                
            await query.message.edit_text(result_text, parse_mode="Markdown")
            
            # Удаляем игру из памяти
            del roulette_games[game_id]
            
        else:
            # Вызванный игрок выжил
            result_text = (
                f"💨 **ЩЕЛЧОК!** Осечка...\n\n"
                f"Игрок {game_data['player2_name']} выживает!\n"
                f"По правилам простой дуэли, он побеждает, так как не застрелился."
            )
            await query.message.edit_text(result_text, parse_mode="Markdown")
            del roulette_games[game_id]

# ==========================================
# ТОЧКА ВХОДА (ЗАПУСК БОТА)
# ==========================================
if __name__ == "__main__":
    # Создаем приложение
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Регистрируем команды
    app.add_handler(CommandHandler("help", command_help))
    app.add_handler(CommandHandler("donate", command_donate))
    app.add_handler(CommandHandler("add_donator", command_add_donator))
    
    # Регистрируем обработчик кнопок
    app.add_handler(CallbackQueryHandler(handle_callbacks))
    
    # Регистрируем основной обработчик текста (должен быть последним)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_all_messages))
    
    print("========================================")
    print("🚀 СИСТЕМА KRYLOXA BOT УСПЕШНО ЗАПУЩЕНА 🚀")
    print("========================================")
    
    # Запуск
    app.run_polling()
