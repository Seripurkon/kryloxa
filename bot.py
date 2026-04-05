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
from telegram.request import HTTPXRequest

# ==========================================
# 1. КОНФИГУРАЦИЯ И НАСТРОЙКИ
# ==========================================
TOKEN = "8641381095:AAH44UdW5z66BkX0rO5qKHOcdESAoghso_g"
OWNER_ID = 5679520675
TESTER_ID = 782585931
HELPER_ID = 8475300408

CARD_NUMBER = "2202 2084 1533 2171"
SUPPORT_BOT_NAME = "kryloxaHelper_bot"
MIN_WITHDRAW_KLC = 4000 
CURRENCY_RATE = 0.06 

ECONOMY_FILE = "economy.json"
RANKS_FILE = "ranks.json"
PROMOS_FILE = "promos.json" 
ACTIVATED_PROMOS_FILE = "activated_promos.json"
DONATORS_FILE = "donators.json"

# Состояния для диалога создания промокода
PROMO_NAME, PROMO_TIME, PROMO_REWARD = range(3)

# Настройки Казино
SLOTS_SYMBOLS = ["🍋", "🍒", "🔔", "💎", "7️⃣"]
SLOTS_WEIGHTS = [50, 30, 15, 4.9, 0.1] 
MIN_BET_SLOTS = 500

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)

# ==========================================
# 2. РАБОТА С БАЗОЙ ДАННЫХ (JSON)
# ==========================================
def load_json(filename, default):
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Превращаем строковые ID обратно в числа для удобства
                return {int(k) if k.isdigit() else k: v for k, v in data.items()}
        except Exception as e:
            logging.error(f"Ошибка загрузки {filename}: {e}")
            return default
    return default

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# Инициализация данных
user_ranks = load_json(RANKS_FILE, {OWNER_ID: 4, TESTER_ID: 4, HELPER_ID: -1})
user_balance = load_json(ECONOMY_FILE, {})
active_promos = load_json(PROMOS_FILE, {})
used_promo_db = load_json(ACTIVATED_PROMOS_FILE, {}) 
donators = load_json(DONATORS_FILE, [])

# Временные данные (очищаются при перезагрузке)
warns = {}
work_timers = {}
bonus_timers = {}
withdraw_requests = {}

# ==========================================
# 3. ВСПОМОГАТЕЛЬНАЯ ЛОГИКА
# ==========================================
def get_user_stats(u_id):
    if u_id not in user_balance:
        user_balance[u_id] = {"main": 500, "bonus": 0}
    # Конвертация из старого формата (если была просто цифра)
    if isinstance(user_balance[u_id], int):
        val = user_balance[u_id]
        user_balance[u_id] = {"main": val, "bonus": 0}
    return user_balance[u_id]

def update_balance(u_id, amount, b_type="main"):
    if u_id == OWNER_ID and amount < 0:
        return 
    stats = get_user_stats(u_id)
    stats[b_type] += amount
    if stats[b_type] < 0:
        stats[b_type] = 0
    save_json(ECONOMY_FILE, user_balance)

def get_rank(user_id):
    if user_id == OWNER_ID:
        return 4
    return user_ranks.get(user_id, 0)

def parse_time(text):
    """Парсинг времени типа '1д', '5ч', '30м'"""
    text = text.lower().strip()
    match = re.search(r"(\d+)\s*([мчдг])", text)
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2)
    if unit == 'м': return amount * 60
    if unit == 'ч': return amount * 3600
    if unit == 'д': return amount * 86400
    if unit == 'г': return amount * 31536000
    return None

# ==========================================
# 4. ИГРОВЫЕ ФУНКЦИИ (СЛОТЫ)
# ==========================================
async def run_slots_logic(u_id, bet):
    stats = get_user_stats(u_id)
    total = stats["main"] + stats["bonus"]
    
    if total < bet:
        return "❌ Недостаточно KLC на балансе!", False

    # Списание: сначала бонусы, потом чистые
    if stats["bonus"] >= bet:
        update_balance(u_id, -bet, "bonus")
    else:
        rem = bet - stats["bonus"]
        update_balance(u_id, -stats["bonus"], "bonus")
        update_balance(u_id, -rem, "main")

    res = [random.choices(SLOTS_SYMBOLS, weights=SLOTS_WEIGHTS)[0] for _ in range(3)]
    win = 0

    # Логика выигрыша
    if res[0] == res[1] == res[2]:
        if res[0] == "7️⃣": win = bet * 100
        elif res[0] == "💎": win = bet * 50
        else: win = bet * 15
    elif (res[0] == res[1] or res[1] == res[2] or res[0] == res[2]):
        if random.random() > 0.7: # 30% шанс на малый выигрыш при паре
            win = int(bet * 2)

    if win > 0:
        update_balance(u_id, win, "main") # Выигрыш всегда в чистые
        return f"🎰 `[ {' | '.join(res)} ]` \n\n🔥 **ПОБЕДА!**\nВы выиграли: +{win} KLC (Чистые)", True
    
    return f"🎰 `[ {' | '.join(res)} ]` \n\n💀 **ПРОИГРЫШ**\nПопробуйте снова!", True

# ==========================================
# 5. КОМАНДЫ ПОЛЬЗОВАТЕЛЯ
# ==========================================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Kryloxa System v1.2.5 готова к работе!\nНапиши /help для списка команд.")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📜 **СПИСОК КОМАНД**\n\n"
        "💰 **Экономика:**\n"
        "• `баланс` (или `б`) — твой кошелек\n"
        "• `бонус` — ежедневный подарок\n"
        "• `тп [сумма] [реплай]` — передать KLC\n"
        "• `вывод [сумма] [карта]` — снять деньги\n\n"
        "🎰 **Развлечения:**\n"
        "• `слоты [ставка]` — казино\n"
        "• `работа` — заработок бонусов в ЛС\n\n"
        "🛍 **Магазин и Инфо:**\n"
        "• `/magaz` — купить снятие мута/варна\n"
        "• `/donate` — купить KLC\n"
        "• `/donators` — список почетных игроков\n\n"
        "🛡 **Модерация (для админов):**\n"
        "• `инфа`, `молчи`, `скажи`, `бан`, `варн`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def donators_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not donators:
        return await update.message.reply_text("📜 Список донатеров пока пуст.")
    
    text = "💎 **ПОЧЕТНЫЕ ДОНАТЕРЫ ПРОЕКТА:**\n\n"
    for i, name in enumerate(donators, 1):
        text += f"{i}. {name}\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def donate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "<b>🏦 ПОПОЛНЕНИЕ БАЛАНСА</b>\n\n"
        f"💳 Карта для оплаты: <code>{CARD_NUMBER}</code>\n\n"
        "📦 <b>Прайс-лист:</b>\n"
        "• 5,000 KLC — 300₽\n"
        "• 10,000 KLC — 550₽\n\n"
        f"⚠️ После оплаты скиньте чек в @{SUPPORT_BOT_NAME}"
    )
    kb = [[InlineKeyboardButton("📥 Отправить чек", url=f"https://t.me/{SUPPORT_BOT_NAME}")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def magaz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u_id = update.effective_user.id
    stats = get_user_stats(u_id)
    total = stats["main"] + stats["bonus"]
    
    text = f"🛒 **МАГАЗИН KRYLOXA**\n💰 Твой баланс: {total} KLC\n\nВыбери товар:"
    kb = [
        [InlineKeyboardButton("🚫 Снять мут (1000 KLC)", callback_data="buy_unmute")],
        [InlineKeyboardButton("⚠️ Снять варн (500 KLC)", callback_data="buy_unwarn")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))

# ==========================================
# 6. ТЕКСТОВЫЙ ОБРАБОТЧИК (ОСНОВНАЯ ЛОГИКА)
# ==========================================
async def main_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    raw_text = update.message.text
    text = raw_text.lower().strip()
    user = update.effective_user
    u_id = user.id
    stats = get_user_stats(u_id)

    # --- БАЛАНС ---
    if text in ["баланс", "б"]:
        m_bal = "∞" if u_id == OWNER_ID else stats['main']
        await update.message.reply_text(
            f"👤 {user.first_name}, твой счет:\n"
            f"💳 Чистые: {m_bal} KLC\n"
            f"🎁 Бонусы: {stats['bonus']} KLC"
        )

    # --- ЕЖЕДНЕВНЫЙ БОНУС ---
    elif text == "бонус":
        now = datetime.now()
        if u_id in bonus_timers and now < bonus_timers[u_id] + timedelta(days=1):
            delta = (bonus_timers[u_id] + timedelta(days=1)) - now
            hours = delta.seconds // 3600
            return await update.message.reply_text(f"❌ Бонус будет доступен через {hours}ч.")
        
        amt = random.randint(150, 500)
        update_balance(u_id, amt, "bonus")
        bonus_timers[u_id] = now
        await update.message.reply_text(f"🎁 Ты получил {amt} бонусных KLC!")

    # --- ПЕРЕДАЧА ДЕНЕГ (ТП) ---
    elif text.startswith("тп "):
        try:
            parts = text.split()
            amount = int(parts[1])
            if not update.message.reply_to_message:
                return await update.message.reply_text("❌ Ответь на сообщение того, кому хочешь передать!")
            
            target_id = update.message.reply_to_message.from_user.id
            if stats["main"] < amount:
                return await update.message.reply_text("❌ У тебя нет столько 'чистых' KLC!")
            
            update_balance(u_id, -amount, "main")
            update_balance(target_id, amount, "main")
            await update.message.reply_text(f"✅ Ты передал {amount} KLC пользователю {update.message.reply_to_message.from_user.first_name}")
        except:
            await update.message.reply_text("❌ Ошибка. Пиши: `тп [сумма]` (реплаем)")

    # --- КАЗИНО (СЛОТЫ) ---
    elif text.startswith("слоты "):
        try:
            bet = int(text.split()[1])
            if bet < MIN_BET_SLOTS:
                return await update.message.reply_text(f"❌ Мин. ставка: {MIN_BET_SLOTS}")
            
            res_txt, success = await run_slots_logic(u_id, bet)
            kb = None
            if success:
                kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🎰 Снова", callback_data=f"spin_{bet}"),
                    InlineKeyboardButton("🛑 Стоп", callback_data="stop_game")
                ]])
            await update.message.reply_text(res_txt, reply_markup=kb, parse_mode="Markdown")
        except:
            await update.message.reply_text("❌ Пиши: `слоты [ставка]`")

    # --- ВЫВОД СРЕДСТВ ---
    elif text.startswith("вывод "):
        try:
            parts = raw_text.split()
            amount = int(parts[1])
            card_info = " ".join(parts[2:])
            
            if amount < MIN_WITHDRAW_KLC:
                return await update.message.reply_text(f"❌ Минимальный вывод: {MIN_WITHDRAW_KLC} KLC")
            
            if (stats["main"] + stats["bonus"]) < amount:
                return await update.message.reply_text("❌ Недостаточно средств!")

            # Списание
            b_part = min(amount, stats["bonus"])
            m_part = amount - b_part
            update_balance(u_id, -m_part, "main")
            update_balance(u_id, -b_part, "bonus")

            # Расчет в рублях
            rub = int(((m_part * CURRENCY_RATE) * 0.4) + ((b_part * CURRENCY_RATE) * 0.6))
            req_id = random.randint(1000, 9999)
            withdraw_requests[req_id] = {"u_id": u_id, "rub": rub, "m": m_part, "b": b_part}

            await update.message.reply_text(f"✅ Заявка #{req_id} на {rub}₽ создана и отправлена админу.")
            
            # Уведомление админу
            admin_text = (
                f"💰 **НОВАЯ ЗАЯВКА НА ВЫВОД #{req_id}**\n"
                f"👤 Игрок: {user.first_name} (ID: {u_id})\n"
                f"💵 Сумма: {rub}₽\n"
                f"💳 Карта: `{card_info}`"
            )
            kb = [[
                InlineKeyboardButton("✅ Оплачено", callback_data=f"adm_pay_{req_id}"),
                InlineKeyboardButton("❌ Отказ", callback_data=f"adm_rej_{req_id}")
            ]]
            await context.bot.send_message(OWNER_ID, admin_text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        except:
            await update.message.reply_text("❌ Формат: `вывод [сумма] [номер карты]`")

    # --- МОДЕРАЦИЯ ---
    elif text == "инфа":
        target = update.message.reply_to_message.from_user if update.message.reply_to_message else user
        t_stats = get_user_stats(target.id)
        t_rank = get_rank(target.id)
        info = (
            f"👤 **ИНФОРМАЦИЯ: {target.first_name}**\n"
            f"🆔 ID: `{target.id}`\n"
            f"⭐ Ранг: {t_rank}\n"
            f"💳 Чистые: {t_stats['main']} KLC\n"
            f"🎁 Бонусы: {t_stats['bonus']} KLC\n"
            f"⚠️ Варны: {warns.get(target.id, 0)}/3"
        )
        await update.message.reply_text(info, parse_mode="Markdown")

    elif text.startswith("молчи"):
        if get_rank(u_id) < 1: return
        if not update.message.reply_to_message: return
        
        target = update.message.reply_to_message.from_user
        seconds = parse_time(text.replace("молчи", ""))
        if not seconds: seconds = 3600
        
        try:
            until = datetime.now() + timedelta(seconds=seconds)
            await context.bot.restrict_chat_member(
                update.message.chat_id, 
                target.id, 
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until
            )
            await update.message.reply_text(f"🔇 {target.first_name} отправлен в мут.")
        except:
            await update.message.reply_text("❌ Ошибка прав.")

# ==========================================
# 7. ОБРАБОТКА НАЖАТИЙ (CALLBACK)
# ==========================================
async def query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    u_id = q.from_user.id
    data = q.data

    # Игровые кнопки
    if data.startswith("spin_"):
        bet = int(data.split("_")[1])
        res_txt, success = await run_slots_logic(u_id, bet)
        kb = None
        if success:
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🎰 Снова", callback_data=f"spin_{bet}"),
                InlineKeyboardButton("🛑 Стоп", callback_data="stop_game")
            ]])
        await q.edit_message_text(res_txt, reply_markup=kb, parse_mode="Markdown")

    elif data == "stop_game":
        await q.edit_message_text("🛑 Игра окончена. Твой баланс в безопасности!")

    # Работа
    elif data == "do_work":
        now = datetime.now()
        if u_id in work_timers and now < work_timers[u_id] + timedelta(seconds=40):
            return await q.answer("⏳ Ты еще не отдохнул! Подожди немного.", show_alert=True)
        
        update_balance(u_id, 75, "bonus")
        work_timers[u_id] = now
        await q.answer("⚒ Отработано! +75 Бонусных KLC")
        await q.edit_message_text(
            "⚒ Смена закончена. Приходи через 40 секунд!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚒ Начать еще раз", callback_data="do_work")]])
        )

    # Админка вывода
    elif data.startswith("adm_"):
        _, action, rid = data.split("_")
        rid = int(rid)
        req = withdraw_requests.get(rid)
        if not req: return
        
        if action == "pay":
            await context.bot.send_message(req["u_id"], f"✅ Ваша выплата {req['rub']}₽ была отправлена на карту!")
            await q.edit_message_text(q.message.text + "\n\n✅ СТАТУС: ОПЛАЧЕНО")
        else:
            update_balance(req["u_id"], req["m"], "main")
            update_balance(req["u_id"], req["b"], "bonus")
            await context.bot.send_message(req["u_id"], "❌ Админ отклонил вашу заявку. KLC вернулись на баланс.")
            await q.edit_message_text(q.message.text + "\n\n❌ СТАТУС: ОТКЛОНЕНО")
        
        del withdraw_requests[rid]

# ==========================================
# 8. ЗАПУСК БОТА
# ==========================================
if __name__ == "__main__":
    # Создаем приложение
    app = ApplicationBuilder().token(TOKEN).request(HTTPXRequest(connect_timeout=30)).build()

    # Добавляем команды
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("donate", donate_cmd))
    app.add_handler(CommandHandler("magaz", magaz_cmd))
    app.add_handler(CommandHandler("donators", donators_cmd))
    
    # Работа (через слово в чате)
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^[Рр]абота$"), 
        lambda u, c: u.message.reply_text("⚒ Нажми кнопку, чтобы начать смену:", 
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚒ Работать", callback_data="do_work")]]))))

    # Коллбэки и Текст
    app.add_handler(CallbackQueryHandler(query_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, main_text_handler))
    
    print(">>> Kryloxa System v1.2.5: ПОЛНЫЙ ЗАПУСК <<<")
    app.run_polling()
