import os
import json
import random
import logging
import re
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import (
    ApplicationBuilder, ContextTypes, MessageHandler, filters, 
    CallbackQueryHandler, CommandHandler, ConversationHandler
)
from telegram.request import HTTPXRequest

# ==========================================
# КОНФИГУРАЦИЯ И НАСТРОЙКИ
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
BOT_VERSION = "1.2.0"

# Состояния для создания промокода
PROMO_NAME, PROMO_TIME, PROMO_REWARD = range(3)

# Настройки Казино
SLOTS_SYMBOLS = ["🍋", "🍒", "🔔", "💎", "7️⃣"]
SLOTS_WEIGHTS = [50, 30, 15, 4.9, 0.1] 
MIN_BET_SLOTS = 500

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# ==========================================
# РАБОТА С ДАННЫМИ (JSON)
# ==========================================
def load_json(filename, default):
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Конвертируем ключи в int, если это ID пользователя
                return {int(k) if k.isdigit() else k: v for k, v in data.items()}
        except Exception as e:
            logging.error(f"Ошибка загрузки {filename}: {e}")
            return default
    return default

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# Загрузка БД
user_ranks = load_json(RANKS_FILE, {OWNER_ID: 4, TESTER_ID: 4, HELPER_ID: -1})
user_balance = load_json(ECONOMY_FILE, {})
active_promos = load_json(PROMOS_FILE, {})
used_promo_db = load_json(ACTIVATED_PROMOS_FILE, {}) 
donators = load_json(DONATORS_FILE, [])

# Оперативные данные (в памяти)
warns = {}
roulette_games = {}
bonus_timers = {}
work_timers = {}
withdraw_requests = {}

# ==========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================
def get_rank(user_id):
    if user_id == OWNER_ID:
        return 4
    return user_ranks.get(user_id, 0)

def get_user_stats(u_id):
    if u_id not in user_balance:
        user_balance[u_id] = {"main": 500, "bonus": 0}
    # Если данные старого формата (просто число)
    if isinstance(user_balance[u_id], int):
        val = user_balance[u_id]
        user_balance[u_id] = {"main": val, "bonus": 0}
    return user_balance[u_id]

def update_balance(u_id, amount, b_type="main"):
    if u_id == OWNER_ID and amount < 0:
        return # У овнера не отнимаем
    stats = get_user_stats(u_id)
    stats[b_type] += amount
    if stats[b_type] < 0:
        stats[b_type] = 0
    save_json(ECONOMY_FILE, user_balance)

def decline_word(number, titles):
    cases = [2, 0, 1, 1, 1, 2]
    return titles[0 if number % 100 > 4 and number % 100 < 20 else cases[min(number % 10, 5)]]

def parse_kryloxa_time(text):
    text = text.lower().strip()
    if "навсегда" in text:
        return -1, "навсегда 💀"
    match = re.search(r"(\d+)\s*([мчдг])", text)
    if not match:
        return None, None
    amount = int(match.group(1))
    unit = match.group(2)
    if unit == 'м': return amount * 60, f"{amount} {decline_word(amount, ['минуту', 'минуты', 'минут'])}"
    if unit == 'ч': return amount * 3600, f"{amount} {decline_word(amount, ['час', 'часа', 'часов'])}"
    if unit == 'д': return amount * 86400, f"{amount} {decline_word(amount, ['день', 'дня', 'дней'])}"
    if unit == 'г': return amount * 31536000, f"{amount} {decline_word(amount, ['год', 'года', 'лет'])}"
    return None, None

# ==========================================
# ЛОГИКА ИГР (РУЛЕТКА И СЛОТЫ)
# ==========================================
async def run_slots(u_id, bet):
    stats = get_user_stats(u_id)
    total = stats["main"] + stats["bonus"]
    
    if total < bet:
        return "❌ Недостаточно KLC!", False

    # Сначала списываем бонусы, потом основу
    if stats["bonus"] >= bet:
        update_balance(u_id, -bet, "bonus")
    else:
        remainder = bet - stats["bonus"]
        update_balance(u_id, -stats["bonus"], "bonus")
        update_balance(u_id, -remainder, "main")

    res = [random.choices(SLOTS_SYMBOLS, weights=SLOTS_WEIGHTS)[0] for _ in range(3)]
    win = 0

    if res[0] == res[1] == res[2]:
        if res[0] == "7️⃣": win = bet * 200
        elif res[0] == "💎": win = bet * 25
        else: win = bet * 10
    elif (res[0] == res[1] or res[1] == res[2] or res[0] == res[2]) and random.random() > 0.6:
        win = int(bet * 1.5)

    if win > 0:
        update_balance(u_id, win, "main")
        return f"🎰 `[ {res[0]} | {res[1]} | {res[2]} ]` \n\n✅ **ВИН!** +{win} KLC", True
    
    return f"🎰 `[ {res[0]} | {res[1]} | {res[2]} ]` \n\n❌ **Мимо!**", True

def reload_roulette_chamber(game):
    chamber = [True, True, True, False, False, False]
    random.shuffle(chamber)
    game['chamber'] = chamber

# ==========================================
# КОМАНДЫ И ОБРАБОТЧИКИ
# ==========================================
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        f"📜 **Kryloxa System v{BOT_VERSION}**\n\n"
        "**🎮 ИГРЫ:**\n"
        "• `слоты [ставка]` — испытать удачу\n"
        "• `рулетка [ставка]` — дуэль с игроком\n"
        "• `работа` — заработать бонус в ЛС\n\n"
        "**💰 ЭКОНОМИКА:**\n"
        "• `баланс` или `б` — твой кошелек\n"
        "• `бонус` — ежедневный подарок\n"
        "• `тп [сумма] [ID/реплай]` — передать KLC\n"
        "• `вывод [сумма] [карта]` — создать заявку\n\n"
        "**🛡 МОДЕРАЦИЯ:**\n"
        "• `инфа` — данные о пользователе\n"
        "• `молчи [время]` — мут\n"
        "• `скажи` — размут\n"
        "• `бан` / `варн` — наказания\n\n"
        "**🛒 МАГАЗИН:** /magaz, /donate"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def donate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "<b>🏦 Kryloxa Shop & Exchange</b>\n\n"
        "💳 <b>Реквизиты для оплаты:</b>\n"
        f"<code>{CARD_NUMBER}</code>\n\n"
        "📦 <b>Пакеты KLC:</b>\n"
        "• 5,000 KLC — 300₽\n"
        "• 10,000 KLC — 550₽\n\n"
        f"После оплаты скиньте чек в @{SUPPORT_BOT_NAME}"
    )
    kb = [[InlineKeyboardButton("📥 Отправить чек", url=f"https://t.me/{SUPPORT_BOT_NAME}")],
          [InlineKeyboardButton("📤 Заказать вывод", url=f"https://t.me/{SUPPORT_BOT_NAME}")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def magaz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    stats = get_user_stats(user.id)
    total = stats["main"] + stats["bonus"]
    text = f"🛒 **Магазин услуг**\n💰 Баланс: {total} KLC"
    kb = [
        [InlineKeyboardButton("🚫 Снять мут (1000 KLC)", callback_data="buy_unmute")],
        [InlineKeyboardButton("⚠️ Снять варн (500 KLC)", callback_data="buy_unwarn")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

# ==========================================
# ГЛАВНЫЙ ОБРАБОТЧИК ТЕКСТА (ЛОГИКА)
# ==========================================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    
    raw_text = update.message.text
    text = raw_text.lower().strip()
    user = update.effective_user
    u_id = user.id
    stats = get_user_stats(u_id)

    # --- ПЕРЕДАЧА ДЕНЕГ (ТП) ---
    if text.startswith("тп "):
        parts = text.split()
        if len(parts) >= 2:
            try:
                amount = int(parts[1])
                target_user = None
                if update.message.reply_to_message:
                    target_user = update.message.reply_to_message.from_user
                elif len(parts) == 3:
                    target_user_id = int(parts[2])
                    target_user = await context.bot.get_chat_member(update.message.chat_id, target_user_id)
                    target_user = target_user.user
                
                if not target_user or target_user.id == u_id:
                    return await update.message.reply_text("❌ Кому передаем?")
                
                if stats["main"] < amount:
                    return await update.message.reply_text("❌ Недостаточно чистых KLC!")
                
                update_balance(u_id, -amount, "main")
                update_balance(target_user.id, amount, "main")
                await update.message.reply_text(f"✅ Передано {amount} KLC пользователю {target_user.first_name}")
            except:
                await update.message.reply_text("❌ Ошибка. Пример: `тп 1000` (в ответ на сообщение)")

    # --- БАЛАНС И БОНУС ---
    elif text in ["баланс", "б"]:
        bal_main = "∞" if u_id == OWNER_ID else stats['main']
        await update.message.reply_text(f"💰 {user.first_name}, твой счет:\n💳 Чистые: {bal_main} KLC\n🎁 Бонусы: {stats['bonus']} KLC")

    elif text == "бонус":
        now = datetime.now()
        if u_id in bonus_timers and now < bonus_timers[u_id] + timedelta(days=1):
            diff = (bonus_timers[u_id] + timedelta(days=1)) - now
            return await update.message.reply_text(f"⏳ Бонус будет доступен через {diff.seconds // 3600}ч.")
        
        amt = random.randint(200, 700)
        update_balance(u_id, amt, "bonus")
        bonus_timers[u_id] = now
        await update.message.reply_text(f"🎁 Получено {amt} бонусных KLC!")

    # --- МОДЕРАЦИЯ ---
    elif text == "инфа":
        target = update.message.reply_to_message.from_user if update.message.reply_to_message else user
        t_stats = get_user_stats(target.id)
        t_rank = get_rank(target.id)
        info = (
            f"👤 **Инфо: {target.first_name}**\n"
            f"🆔 ID: `{target.id}`\n"
            f"⭐️ Ранг: {t_rank}\n"
            f"💳 Баланс: {t_stats['main'] + t_stats['bonus']} KLC\n"
            f"⚠️ Варны: {warns.get(target.id, 0)}/3"
        )
        await update.message.reply_text(info, parse_mode="Markdown")

    elif text.startswith("молчи"):
        if get_rank(u_id) < 1: return
        target = update.message.reply_to_message
        if not target: return
        
        time_sec, time_str = parse_kryloxa_time(text.replace("молчи", ""))
        if not time_sec: time_sec = 3600; time_str = "1 час"
        
        try:
            until = datetime.now() + timedelta(seconds=time_sec) if time_sec > 0 else datetime.now() + timedelta(days=365)
            await context.bot.restrict_chat_member(update.message.chat_id, target.from_user.id, 
                permissions=ChatPermissions(can_send_messages=False), until_date=until)
            await update.message.reply_text(f"🔇 {target.from_user.first_name} замолчал на {time_str}")
        except:
            await update.message.reply_text("❌ Не хватает прав.")

    # --- КАЗИНО ---
    elif text.startswith("слоты "):
        parts = text.split()
        if len(parts) == 2 and parts[1].isdigit():
            bet = int(parts[1])
            if bet < MIN_BET_SLOTS:
                return await update.message.reply_text(f"❌ Минимум {MIN_BET_SLOTS} KLC!")
            res_text, success = await run_slots(u_id, bet)
            kb = None
            if success:
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("🎰 Снова", callback_data=f"c_spin_{bet}"), 
                                             InlineKeyboardButton("🛑 Стоп", callback_data="c_stop")]])
            await update.message.reply_text(res_text, reply_markup=kb, parse_mode="Markdown")

    # --- ВЫВОД ---
    elif text.startswith("вывод "):
        parts = raw_text.split()
        if len(parts) >= 3:
            try:
                amt = int(parts[1])
                card = " ".join(parts[2:])
                if amt < MIN_WITHDRAW_KLC:
                    return await update.message.reply_text(f"❌ Минимум {MIN_WITHDRAW_KLC} KLC!")
                
                total_user = stats["main"] + stats["bonus"]
                if total_user < amt:
                    return await update.message.reply_text("❌ Недостаточно средств!")
                
                # Списываем
                f_bonus = min(amt, stats["bonus"])
                f_main = amt - f_bonus
                update_balance(u_id, -f_main, "main")
                update_balance(u_id, -f_bonus, "bonus")
                
                # Считаем выплату в рублях (бонусы дешевле)
                rub = int(((f_main * CURRENCY_RATE) * 0.4) + ((f_bonus * CURRENCY_RATE) * 0.6))
                rid = random.randint(100000, 999999)
                withdraw_requests[rid] = {"u_id": u_id, "rub": rub, "m": f_main, "b": f_bonus}
                
                await update.message.reply_text(f"✅ Заявка #{rid} создана. Ожидайте проверки.")
                admin_msg = f"💰 **ЗАЯВКА НА ВЫВОД #{rid}**\nОт: {user.first_name} ({u_id})\nСумма: {rub}₽\nКарта: `{card}`"
                kb = [[InlineKeyboardButton("✅ Оплачено", callback_data=f"adm_win_{rid}"),
                       InlineKeyboardButton("❌ Отказ", callback_data=f"adm_rej_{rid}")]]
                await context.bot.send_message(OWNER_ID, admin_msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
            except:
                await update.message.reply_text("❌ Формат: `вывод [сумма] [номер карты]`")

# ==========================================
# CALLBACK HANDLER (КНОПКИ)
# ==========================================
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    u_id = q.from_user.id
    data = q.data

    if data.startswith("c_spin_"):
        bet = int(data.split("_")[2])
        res_text, success = await run_slots(u_id, bet)
        kb = None
        if success:
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🎰 Снова", callback_data=f"c_spin_{bet}"), 
                                         InlineKeyboardButton("🛑 Стоп", callback_data="c_stop")]])
        await q.edit_message_text(res_text, reply_markup=kb, parse_mode="Markdown")

    elif data == "c_stop":
        await q.edit_message_text("🛑 Игра закончена. Баланс сохранен.")

    elif data == "do_work":
        now = datetime.now()
        if u_id in work_timers and now < work_timers[u_id] + timedelta(seconds=40):
            return await q.answer("⏳ Ты еще не отдохнул от прошлой смены!", show_alert=True)
        
        update_balance(u_id, 80, "bonus")
        work_timers[u_id] = now
        await q.answer("⚒ Отработано! +80 Бонусов")
        await q.edit_message_text("⚒ Смена закончена. Приходи позже!", 
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚒ Работать еще", callback_data="do_work")]]))

    elif data.startswith("adm_"):
        # Логика админки (выплаты)
        _, action, rid = data.split("_")
        rid = int(rid)
        req = withdraw_requests.get(rid)
        if not req: return
        
        if action == "win":
            await context.bot.send_message(req["u_id"], f"✅ Ваша выплата {req['rub']}₽ была успешно отправлена!")
            await q.edit_message_text(q.message.text + "\n\nСТАТУС: ✅ ОПЛАЧЕНО")
        else:
            update_balance(req["u_id"], req["m"], "main")
            update_balance(req["u_id"], req["b"], "bonus")
            await context.bot.send_message(req["u_id"], "❌ Заявка на вывод отклонена. Средства вернулись на баланс.")
            await q.edit_message_text(q.message.text + "\n\nСТАТУС: ❌ ОТКАЗАНО")
        del withdraw_requests[rid]

# ==========================================
# ИНИЦИАЛИЗАЦИЯ И ЗАПУСК
# ==========================================
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).request(HTTPXRequest(connect_timeout=30)).build()

    # Промокоды (диалог)
    promo_handler = ConversationHandler(
        entry_points=[CommandHandler("createpm", lambda u, c: (u.message.reply_text("Имя промо?"), PROMO_NAME)[1])],
        states={
            PROMO_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: (c.user_data.update({'pn': u.message.text}), u.message.reply_text("Время? (1д, 5ч)"), PROMO_TIME)[2])],
            PROMO_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: (c.user_data.update({'pt': u.message.text}), u.message.reply_text("Награда?"), PROMO_REWARD)[2])],
            PROMO_REWARD: [MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: (active_promos.update({c.user_data['pn']: {'reward': int(u.message.text), 'expire': (datetime.now() + timedelta(seconds=parse_kryloxa_time(c.user_data['pt'])[0])).isoformat()}}), save_json(PROMOS_FILE, active_promos), u.message.reply_text("Готово!"), ConversationHandler.END)[3])]
        },
        fallbacks=[]
    )

    app.add_handler(promo_handler)
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("donate", donate_cmd))
    app.add_handler(CommandHandler("shop", donate_cmd))
    app.add_handler(CommandHandler("magaz", magaz_cmd))
    app.add_handler(CommandHandler("start", lambda u, c: u.message.reply_text("Kryloxa System в строю! Напиши /help")))
    
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    print(">>> Kryloxa System v1.2.0: FULL POWER ON <<<")
    app.run_polling()
