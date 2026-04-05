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

# --- НАСТРОЙКИ ---
TOKEN = "8641381095:AAH44UdW5z66BkX0rO5qKHOcdESAoghso_g"
OWNER_ID = 5679520675
TESTER_ID = 782585931
HELPER_ID = 8475300408
ECONOMY_FILE = "economy.json"
RANKS_FILE = "ranks.json"
PROMOS_FILE = "promos.json" 
ACTIVATED_PROMOS_FILE = "activated_promos.json" # Новая БД для защиты
BOT_VERSION = "0.9.8" # ECONOMY 2.0 FULL FIXED

# Состояния для промокода
PROMO_NAME, PROMO_TIME, PROMO_REWARD = range(3)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- ПАРСЕР ВРЕМЕНИ ---
def decline_word(number, titles):
    cases = [2, 0, 1, 1, 1, 2]
    return titles[0 if number % 100 > 4 and number % 100 < 20 else cases[min(number % 10, 5)]]

def parse_kryloxa_time(text):
    text = text.lower().strip()
    if "навсегда" in text: return -1, "навсегда 💀"
    match = re.search(r"(\d+)\s*([мчдг])", text)
    if not match: return None, None
    amount = int(match.group(1))
    unit = match.group(2)
    if unit == 'м': return amount * 60, f"{amount} {decline_word(amount, ['минуту', 'минуты', 'минут'])}"
    if unit == 'ч': return amount * 3600, f"{amount} {decline_word(amount, ['час', 'часа', 'часов'])}"
    if unit == 'д': return amount * 86400, f"{amount} {decline_word(amount, ['день', 'дня', 'дней'])}"
    if unit == 'г': return amount * 31536000, f"{amount} {decline_word(amount, ['год', 'года', 'лет'])}"
    return None, None

# --- БАЗА ДАННЫХ ---
def load_json(filename, default):
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {int(k) if isinstance(k, str) and k.isdigit() else k: v for k, v in data.items()}
        except: return default
    return default

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

user_ranks = load_json(RANKS_FILE, {OWNER_ID: 4, TESTER_ID: 4, HELPER_ID: -1})
user_balance = load_json(ECONOMY_FILE, {})
active_promos = load_json(PROMOS_FILE, {})
# Структура: {"название_промо": [id_user1, id_user2]}
used_promo_db = load_json(ACTIVATED_PROMOS_FILE, {}) 
warns = {}
roulette_games = {}
daily_stats = {}
bonus_timers = {}
work_timers = {}

def get_rank(user_id):
    if user_id == OWNER_ID: return 4
    return user_ranks.get(user_id, 0)

def reload_chamber(g):
    chamber = [True, True, True, False, False, False]
    random.shuffle(chamber)
    g['chamber'] = chamber

# --- ПРОФИЛЬ ---
async def show_profile(update: Update, user):
    u_id = user.id
    rank = str(get_rank(u_id))
    bal_text = "∞ (Owner)" if u_id == OWNER_ID else f"{user_balance.get(u_id, 0)} KLC"
    if u_id == HELPER_ID: rank += " Tester"
    elif u_id == TESTER_ID: rank += " The Main Tester"

    text = (
        f"👤 Профиль пользователя {user.first_name}:\n"
        f"🆔 ID: `{u_id}`\n"
        f"⭐️ Ранг: {rank}\n"
        f"💰 Баланс: {bal_text}\n"
        f"⚠️ Варны: {warns.get(u_id, 0)}/3\n"
        f"────────────────\n"
        f"🤖 Версия: `{BOT_VERSION}`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# --- КОМАНДЫ ---
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Бот запущен! Напиши /help.")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        f"📜 **СПИСОК КОМАНД ({BOT_VERSION})**\n\n"
        "🕹 **Меню:** /start, /help, /magaz\n"
        "💰 **Экономика 2.0:** баланс, бонус, тп, обо мне, передать [сумма]\n"
        "⚒ **Фарм:** `работа` (только в ЛС бота)\n"
        "🎫 **Промо:** `Промо: [код]`\n"
        "🛡 **Модер:** инфа, молчи, скажи, бан, варн\n"
        "🎲 **Игра:** Рулетка (ответом)"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def magaz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    bal = user_balance.get(user.id, 0) if user.id != OWNER_ID else "∞"
    text = f"🛒 **Kryloxa Shop**\n💰 Баланс: {bal} KLC\nВыберите услугу:"
    kb = [[InlineKeyboardButton("🚫 Снять мут (1000 KLC)", callback_data="buy_unmute")],
          [InlineKeyboardButton("⚠️ Снять варн (500 KLC)", callback_data="buy_unwarn")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

# --- СОЗДАНИЕ ПРОМОКОДА (/createpm) ---
async def promo_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return ConversationHandler.END
    await update.message.reply_text("Здравствуй владелец,\n1) Как вы хотите назвать промокод?")
    return PROMO_NAME

async def promo_get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['temp_promo_name'] = update.message.text.strip()
    await update.message.reply_text("2) На сколько вы хотите сделать промокод (по времени)? Максимум 30 дней. (Пример: 1д, 5ч)")
    return PROMO_TIME

async def promo_get_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    seconds, time_text = parse_kryloxa_time(update.message.text)
    if not seconds or (seconds > 2592000 and seconds != -1):
        await update.message.reply_text("❌ Ошибка времени. Максимум 30д. Попробуйте еще раз:")
        return PROMO_TIME
    context.user_data['temp_promo_expire'] = (datetime.now() + timedelta(seconds=seconds)).isoformat()
    context.user_data['temp_promo_timetext'] = time_text
    await update.message.reply_text("3) Сколько KLC будут выдано активаторам?")
    return PROMO_REWARD

async def promo_get_reward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        reward = int(update.message.text)
        name = context.user_data['temp_promo_name']
        active_promos[name] = {"reward": reward, "expire": context.user_data['temp_promo_expire']}
        # Создаем пустой список использовавших в БД
        used_promo_db[name] = [] 
        save_json(PROMOS_FILE, active_promos)
        save_json(ACTIVATED_PROMOS_FILE, used_promo_db)
        await update.message.reply_text(f"✅ Поздравляю вы создали промокод \"{name}\"\n⏳ Действует данный промокод: {context.user_data['temp_promo_timetext']}\n💰 Количество KLC за активацию: {reward}")
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ Введите числовое значение.")
        return PROMO_REWARD

# --- РАБОТА В ЛС ---
async def work_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return await update.message.reply_text("❌ Команда 'работа' работает только в личных сообщениях со мной!")
    kb = [[InlineKeyboardButton("⚒ Начать смену", callback_data="do_work")]]
    await update.message.reply_text("🏭 Завод ждет! Нажимай на кнопку, чтобы заработать KLC:", reply_markup=InlineKeyboardMarkup(kb))

# --- ОБРАБОТКА ВСЕХ КНОПОК ---
async def all_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    u_id = q.from_user.id
    
    # Кнопка работы
    if q.data == "do_work":
        now = datetime.now()
        last_work = work_timers.get(u_id)
        if last_work and now < last_work + timedelta(seconds=30):
            wait = int((last_work + timedelta(seconds=30) - now).total_seconds())
            return await q.answer(f"⏳ Слишком рано! Жди еще {wait} сек.", show_alert=True)
        user_balance[u_id] = user_balance.get(u_id, 0) + 50
        work_timers[u_id] = now
        save_json(ECONOMY_FILE, user_balance)
        await q.answer("💰 +50 KLC заработано!")
        return await q.edit_message_text("⚒ Смена отработана! Ты заработал 50 KLC.\nСледующая доступна через 30 секунд.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚒ Работать еще", callback_data="do_work")]]))

    # Магазин
    if q.data.startswith("buy_"):
        bal = user_balance.get(u_id, 0)
        full_perms = ChatPermissions(can_send_messages=True, can_send_audios=True, can_send_documents=True, can_send_photos=True, can_send_videos=True, can_send_video_notes=True, can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True, can_add_web_page_previews=True, can_change_info=True, can_invite_users=True, can_pin_messages=True, can_manage_topics=True)
        if q.data == "buy_unmute":
            if u_id == OWNER_ID or bal >= 1000:
                if u_id != OWNER_ID: user_balance[u_id] -= 1000
                save_json(ECONOMY_FILE, user_balance)
                try:
                    await context.bot.restrict_chat_member(q.message.chat_id, u_id, permissions=full_perms)
                    await q.answer("✅ Ограничения сняты (Full)!", show_alert=True)
                except: await q.answer("❌ Ошибка прав.")
            else: await q.answer("❌ Недостаточно KLC!", show_alert=True)
        elif q.data == "buy_unwarn":
            if u_id == OWNER_ID or bal >= 500:
                if warns.get(u_id, 0) > 0:
                    if u_id != OWNER_ID: user_balance[u_id] -= 500
                    warns[u_id] -= 1
                    save_json(ECONOMY_FILE, user_balance)
                    await q.answer("✅ Варн снят!", show_alert=True)
                else: await q.answer("❌ У вас нет варнов.")
            else: await q.answer("❌ Недостаточно KLC!", show_alert=True)
        return

    # Рулетка ставки
    if q.data.startswith("rbet_"):
        _, b, g_id = q.data.split("_", 2)
        if g_id not in roulette_games or u_id != roulette_games[g_id]['p2']: return
        roulette_games[g_id]['bet_type'] = b
        reload_chamber(roulette_games[g_id])
        return await update_ui(q, g_id, "🔥 БОЙ НАЧАЛСЯ!")

    # Рулетка ход
    if q.data.startswith("rt_"):
        _, act, g_id = q.data.split("_", 2)
        if g_id not in roulette_games or u_id != roulette_games[g_id]['turn']: return
        g = roulette_games[g_id]
        hit = g['chamber'].pop(0)
        curr, opp = g['turn'], (g['p2'] if g['turn'] == g['p1'] else g['p1'])
        if act == "opp":
            if hit: g['lives'][opp] -= 1; msg_txt = "💥 БАХ!"
            else: msg_txt = "💨 Холостой!"; g['turn'] = opp
        else:
            if hit: g['lives'][curr] -= 1; msg_txt = "💥 БАХ! Самострел!"; g['turn'] = opp
            else: msg_txt = "💨 Холостой! Доп. ход."
        
        if any(l <= 0 for l in g['lives'].values()):
            winner_id = g['p1'] if g['lives'][g['p2']] <= 0 else g['p2']
            loser_id = g['p2'] if winner_id == g['p1'] else g['p1']
            w_name, l_name = (g['p1_n'], g['p2_n']) if winner_id == g['p1'] else (g['p2_n'], g['p1_n'])
            bet, pun = g['bet_type'], ""
            try:
                if bet == "warn":
                    warns[loser_id] = warns.get(loser_id, 0) + 1
                    pun = f"⚠️ {l_name} получает ВАРН!"
                elif bet == "mute":
                    await context.bot.restrict_chat_member(q.message.chat_id, loser_id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now() + timedelta(hours=1))
                    pun = f"🤫 {l_name} в МУТЕ на час!"
                elif bet == "ban":
                    await context.bot.ban_chat_member(q.message.chat_id, loser_id, until_date=datetime.now() + timedelta(days=1))
                    pun = f"🚫 {l_name} ЗАБАНЕН на день!"
                elif bet == "klc":
                    if loser_id != OWNER_ID: user_balance[loser_id] = user_balance.get(loser_id, 0) - 100
                    user_balance[winner_id] = user_balance.get(winner_id, 0) + 100
                    save_json(ECONOMY_FILE, user_balance)
                    pun = f"💰 {l_name} теряет 100 KLC, а {w_name} их забирает!"
            except: pun = "⚠️ Ошибка прав."
            await q.edit_message_text(f"{msg_txt}\n\n🏆 **Победил {w_name}!**\n{pun}", parse_mode="Markdown")
            del roulette_games[g_id]
        else:
            if not g['chamber']: reload_chamber(g)
            await update_ui(q, g_id, msg_txt)

async def update_ui(q, g_id, status):
    g = roulette_games[g_id]
    t_n = g['p1_n'] if g['turn'] == g['p1'] else g['p2_n']
    l, bl = g['chamber'].count(True), g['chamber'].count(False)
    txt = f"🎰 Ставка: {g['bet_type'].upper()}\n🔫 Патроны: {len(g['chamber'])} (🔥 {l} | ❄️ {bl})\n\n📢 {status}\n👤 {g['p1_n']}: {'❤️' * g['lives'][g['p1']]}\n👤 {g['p2_n']}: {'❤️' * g['lives'][g['p2']]}\n👉 Ход: {t_n}"
    kb = [[InlineKeyboardButton("🎯 Оппонент", callback_data=f"rt_opp_{g_id}"), InlineKeyboardButton("🔫 Себя", callback_data=f"rt_self_{g_id}")]]
    await q.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(kb))

# --- ГЛАВНЫЙ ТЕКСТОВЫЙ ОБРАБОТЧИК ---
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return

    full_text = update.message.text
    lines = full_text.split('\n', 1)
    first_line = lines[0].strip().lower()
    reason = lines[1].strip() if len(lines) > 1 else "Не указана"
    cmd_parts = first_line.split()
    main_cmd = cmd_parts[0] if cmd_parts else ""

    user, chat_id, msg = update.effective_user, update.effective_chat.id, update.message.reply_to_message

    if user.id not in daily_stats: daily_stats[user.id] = {"name": user.first_name, "count": 0}
    daily_stats[user.id]["count"] += 1

    # АКТИВАЦИЯ ПРОМОКОДА (С ЗАЩИТОЙ ОТ ПОВТОРНОГО ИСПОЛЬЗОВАНИЯ)
    if first_line.startswith("промо:"):
        code = full_text.replace("Промо:", "").replace("промо:", "").strip()
        u_id = user.id
        
        if code in active_promos:
            # Инициализация списка в новой БД, если он пуст (для старых кодов)
            if code not in used_promo_db:
                used_promo_db[code] = []
                save_json(ACTIVATED_PROMOS_FILE, used_promo_db)
            
            # ПРОВЕРКА: Активировал ли этот юзер код ранее?
            if u_id in used_promo_db[code]:
                return await update.message.reply_text("❌ Брат, халява только один раз! Ты уже получил KLC по этому коду.")

            data = active_promos[code]
            # Проверка времени жизни кода
            if datetime.now() < datetime.fromisoformat(data['expire']):
                # ВЫДАЧА НАГРАДЫ
                user_balance[u_id] = user_balance.get(u_id, 0) + data['reward']
                # ЗАПИСЬ АКТИВАЦИИ: Добавляем юзера в список
                used_promo_db[code].append(u_id)
                
                # Сохранение всех БД
                save_json(ECONOMY_FILE, user_balance)
                save_json(ACTIVATED_PROMOS_FILE, used_promo_db)
                
                await update.message.reply_text(f"🎫 Промокод активирован! Вы получили {data['reward']} KLC 💰")
            else:
                del active_promos[code]
                # Можно удалить и список юзеров, чтобы не засорять БД
                if code in used_promo_db: del used_promo_db[code]
                
                save_json(PROMOS_FILE, active_promos)
                save_json(ACTIVATED_PROMOS_FILE, used_promo_db)
                await update.message.reply_text("❌ Промокод истек.")
        else:
            await update.message.reply_text("❌ Такого промокода не существует.")
        return

    # ТОПЫ
    if first_line == "тп":
        top_list = sorted(daily_stats.items(), key=lambda x: x[1]['count'], reverse=True)[:10]
        res = "📊 **ТОП ОБЩИТЕЛЬНЫХ:**\n\n"
        for i, (uid, data) in enumerate(top_list, 1):
            res += f"{i}. {data['name']} — {data['count']} сообщ.\n"
        return await update.message.reply_text(res, parse_mode="Markdown")

    if first_line == "обо мне": return await show_profile(update, user)

    if first_line in ["баланс", "б"]:
        bal = "∞" if user.id == OWNER_ID else user_balance.get(user.id, 0)
        return await update.message.reply_text(f"💰 Баланс {user.first_name}: {bal} KLC")

    if first_line == "бонус":
        now = datetime.now()
        if user.id in bonus_timers and now < bonus_timers[user.id] + timedelta(days=1):
            return await update.message.reply_text("❌ Бонус доступен раз в 24 часа!")
        amt = random.randint(150, 600)
        if user.id != OWNER_ID: user_balance[user.id] = user_balance.get(user.id, 0) + amt
        bonus_timers[user.id] = now
        save_json(ECONOMY_FILE, user_balance)
        return await update.message.reply_text(f"🎁 Ежедневный бонус: +{amt} KLC!")

    if msg:
        t_id = msg.from_user.id
        c_rank, t_rank = get_rank(user.id), get_rank(t_id)

        # ПЕРЕДАЧА ДЕНЕГ
        if main_cmd == "передать":
            try:
                amount = int(cmd_parts[1])
                if user.id != OWNER_ID and user_balance.get(user.id, 0) < amount:
                    return await update.message.reply_text("❌ Недостаточно KLC")
                if user.id != OWNER_ID: user_balance[user.id] -= amount
                user_balance[t_id] = user_balance.get(t_id, 0) + amount
                save_json(ECONOMY_FILE, user_balance)
                await update.message.reply_text(f"✅ Передано {amount} KLC пользователю {msg.from_user.first_name}")
            except: await update.message.reply_text("❌ Формат: передать 100")
            return

        if main_cmd == "инфа": return await show_profile(update, msg.from_user)

        # МОДЕРАЦИЯ
        if c_rank >= 1 and (t_rank < c_rank or user.id == OWNER_ID):
            seconds, time_text = parse_kryloxa_time(full_text)
            if not seconds: seconds, time_text = 3600, "1 час"

            try:
                if main_cmd == "молчи":
                    until = datetime.now() + (timedelta(seconds=seconds) if seconds != -1 else timedelta(days=36500))
                    await context.bot.restrict_chat_member(chat_id, t_id, permissions=ChatPermissions(can_send_messages=False), until_date=until)
                    await update.message.reply_text(f"🤫 Тишина на {time_text}.\n📝 Причина: {reason}")
                
                elif main_cmd == "бан":
                    until = datetime.now() + (timedelta(seconds=seconds) if seconds != -1 else timedelta(days=36500))
                    await context.bot.ban_chat_member(chat_id, t_id, until_date=until)
                    await update.message.reply_text(f"🚫 Бан на {time_text}.\n📝 Причина: {reason}")
                
                elif main_cmd == "варн":
                    warns[t_id] = warns.get(t_id, 0) + 1
                    if warns[t_id] >= 3:
                        warns[t_id] = 0
                        until = datetime.now() + timedelta(days=1)
                        await context.bot.restrict_chat_member(chat_id, t_id, permissions=ChatPermissions(can_send_messages=False), until_date=until)
                        await update.message.reply_text(f"🤐 Пользователь {msg.from_user.first_name} набрал 3/3 варна и получает МУТ на 1 день!")
                    else:
                        await update.message.reply_text(f"⚠️ Варн выдан ({warns[t_id]}/3)\n📝 Причина: {reason}")
                
                elif main_cmd == "скажи":
                    full_access = ChatPermissions(can_send_messages=True, can_send_audios=True, can_send_documents=True, can_send_photos=True, can_send_videos=True, can_send_video_notes=True, can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True, can_add_web_page_previews=True, can_change_info=True, can_invite_users=True, can_pin_messages=True, can_manage_topics=True)
                    await context.bot.restrict_chat_member(chat_id, t_id, permissions=full_access)
                    await update.message.reply_text("🔊 Пользователь полностью разблокирован!")
            except: pass

# --- РУЛЕТКА ЗАПУСК ---
async def roulette_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.reply_to_message
    if not msg or update.effective_user.id == msg.from_user.id: return
    p1, p2 = update.effective_user, msg.from_user
    g_id = f"{p1.id}_{p2.id}_{random.randint(100, 999)}"
    roulette_games[g_id] = {"p1": p1.id, "p1_n": p1.first_name, "p2": p2.id, "p2_n": p2.first_name, "lives": {p1.id: 2, p2.id: 2}, "turn": p2.id, "bet_type": None}
    text = f"🎲 **ДУЭЛЬ!**\n\n👤 {p1.first_name} VS {p2.first_name}\n🔫 Барабан: 6 патронов\n\n👉 {p2.first_name}, выбирай ставку:"
    kb = [[InlineKeyboardButton("Варн", callback_data=f"rbet_warn_{g_id}"), InlineKeyboardButton("Мут", callback_data=f"rbet_mute_{g_id}")],
          [InlineKeyboardButton("Бан (1д)", callback_data=f"rbet_ban_{g_id}"), InlineKeyboardButton("100 KLC", callback_data=f"rbet_klc_{g_id}")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

# --- ЗАПУСК БОТА ---
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).request(HTTPXRequest(connect_timeout=20)).build()
    
    promo_conv = ConversationHandler(
        entry_points=[CommandHandler("createpm", promo_start)],
        states={
            PROMO_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, promo_get_name)],
            PROMO_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, promo_get_time)],
            PROMO_REWARD: [MessageHandler(filters.TEXT & ~filters.COMMAND, promo_get_reward)],
        },
        fallbacks=[]
    )

    app.add_handler(promo_conv)
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("magaz", magaz_cmd))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^[Рр]абота$"), work_command))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^[Рр]улетка$"), roulette_start))
    app.add_handler(CallbackQueryHandler(all_callbacks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    print(f"Kryloxa System v{BOT_VERSION} ЗАПУЩЕН! ЗАЩИТА ОТ ДЮПА ПРОМО ВКЛЮЧЕНА.")
    app.run_polling(drop_pending_updates=True)
