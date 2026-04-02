import logging
import json
import os
import random
import httpx
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CommandHandler, CallbackQueryHandler
from telegram.request import HTTPXRequest

# --- НАСТРОЙКИ ---
TOKEN = "8548759774:AAGynBbPfNS58sE-HJf-TEZ4HNw50fQMZBw"
OWNER_ID = 5679520675
ECONOMY_FILE = "economy.json"
WARNS_FILE = "warns.json"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- РАБОТА С ДАННЫМИ ---
def load_json(filename, default):
    if os.path.exists(filename):
        with open(filename, "r") as f:
            try: return json.load(f)
            except: return default
    return default

def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

user_balance = load_json(ECONOMY_FILE, {})
warns = load_json(WARNS_FILE, {})
roulette_games = {}

def parse_punishment(text):
    parts = text.split('\n', 1)
    first_line = parts[0].split()
    reason = parts[1].strip() if len(parts) > 1 else None
    return first_line, reason

# --- КОМАНДЫ ---
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🦾 **Kryloxa Bot v0.9.6-beta запущен!**\nНапиши 'Помощь' для списка команд.")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📜 **Команды Kryloxa Bot:**\n"
        "• `Рулетка` — игра на выживание\n"
        "• `Баланс` — твои монеты KLC\n"
        "• `Магаз` — лавка бонусов\n\n"
        "⚒ **Модерация (ответом на сообщение):**\n"
        "• `Мут [время] [ед]` + абзац (причина)\n"
        "• `Варн` + абзац (причина)\n"
        "• `Бан` + абзац (причина)\n\n"
        "🔍 **Фишка:** Кинь ссылку на Gartic Phone — я проверю комнату!"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

# --- МАГАЗИН ---
async def magaz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💎 VIP Роль - 500 KLC", callback_data="buy_vip")],
        [InlineKeyboardButton("🃏 Анти-Варн - 300 KLC", callback_data="buy_unwarn")]
    ]
    await update.message.reply_text("🛒 **Магазин Kryloxa:**", reply_markup=InlineKeyboardMarkup(keyboard))

async def shop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    balance = user_balance.get(user_id, 0)
    
    if query.data == "buy_vip":
        if balance >= 500:
            user_balance[user_id] -= 500
            save_json(ECONOMY_FILE, user_balance)
            await query.answer("✅ Успешно куплено!")
        else:
            await query.answer("❌ Недостаточно KLC!", show_alert=True)

# --- РУЛЕТКА ---
async def roulette_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in roulette_games:
        return await update.message.reply_text("⚠️ Игра уже идет!")
    
    roulette_games[chat_id] = {
        'chamber': [0, 0, 0, 0, 0, 1],
        'players': [],
        'active': False
    }
    random.shuffle(roulette_games[chat_id]['chamber'])
    
    kb = [[InlineKeyboardButton("Участвовать", callback_data="rt_join")]]
    await update.message.reply_text("🎰 **Русская рулетка!**\nКто рискнет?", reply_markup=InlineKeyboardMarkup(kb))

async def rt_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat_id
    if chat_id not in roulette_games: return
    
    g = roulette_games[chat_id]
    if query.data == "rt_join":
        if query.from_user.id not in g['players']:
            g['players'].append(query.from_user.id)
            await query.answer("Ты в игре!")
            if len(g['players']) >= 2:
                g['active'] = True
                kb = [[InlineKeyboardButton("💥 Нажать на курок", callback_data="rt_shoot")]]
                await query.edit_message_text("🔫 **Игра началась! Жми на курок...**", reply_markup=InlineKeyboardMarkup(kb))

    elif query.data == "rt_shoot":
        bullet = g['chamber'].pop()
        if bullet == 1:
            await query.edit_message_text(f"💀 **БА-БАХ!** {query.from_user.first_name} выбывает!")
            del roulette_games[chat_id]
        else:
            await query.answer("Click... Тебе повезло.")
            if not g['chamber']: 
                 g['chamber'] = [0, 0, 0, 0, 0, 1]
                 random.shuffle(g['chamber'])

# --- ОСНОВНОЙ ОБРАБОТЧИК ТЕКСТА ---
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text: return
    user_id = str(update.effective_user.id)
    msg_lower = text.lower()

    # Экономика
    if user_id not in user_balance: user_balance[user_id] = 0
    user_balance[user_id] += 1
    save_json(ECONOMY_FILE, user_balance)

    if msg_lower == "баланс":
        await update.message.reply_text(f"💰 Баланс: **{user_balance[user_id]} KLC**", parse_mode="Markdown")
        return

    # Gartic Phone
    if "garticphone.com" in msg_lower:
        url = next((w for w in text.split() if "garticphone.com" in w), "")
        if url:
            status_msg = await update.message.reply_text("🔎 *Сканирую...*")
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(url, headers={'User-Agent': 'Mozilla/5.0'})
                    res = "✅ **Комната работает!**" if resp.status_code == 200 else "❌ **Комната не найдена.**"
            except: res = "⚠️ **Ошибка связи.**"
            await status_msg.edit_text(res, parse_mode="Markdown")

    # Модерация (Реплаем)
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        target_id = str(target_user.id)

        if msg_lower.startswith(("молчи", "мут")):
            first_line, reason = parse_punishment(text)
            try:
                val = int(first_line[1])
                unit = first_line[2].lower() if len(first_line) > 2 else "минут"
                sec = val * 60
                if "час" in unit: sec = val * 3600
                elif "ден" in unit: sec = val * 86400
            except: val, unit, sec = 1, "час", 3600

            try:
                await context.bot.restrict_chat_member(update.effective_chat.id, int(target_id), 
                    permissions={"can_send_messages": False}, until_date=datetime.now() + timedelta(seconds=sec))
                res = f"🤫 **{target_user.first_name} в муте на {val} {unit}.**"
                if reason: res += f"\n📝 **Причина:** {reason}"
                await update.message.reply_text(res, parse_mode="Markdown")
            except: await update.message.reply_text("⚠️ Ошибка прав.")

        elif msg_lower.startswith(("варн", "пред")):
            _, reason = parse_punishment(text)
            warns[target_id] = warns.get(target_id, 0) + 1
            save_json(WARNS_FILE, warns)
            res = f"⚠️ **{target_user.first_name} получил варн ({warns[target_id]}/3).**"
            if reason: res += f"\n📝 **Причина:** {reason}"
            await update.message.reply_text(res, parse_mode="Markdown")
            if warns[target_id] >= 3:
                try: await context.bot.ban_chat_member(update.effective_chat.id, int(target_id))
                except: pass

        elif msg_lower.startswith(("бан", "удали")):
            _, reason = parse_punishment(text)
            try:
                await context.bot.ban_chat_member(update.effective_chat.id, int(target_id))
                res = f"🚫 **{target_user.first_name} забанен.**"
                if reason: res += f"\n📝 **Причина:** {reason}"
                await update.message.reply_text(res, parse_mode="Markdown")
            except: await update.message.reply_text("⚠️ Ошибка прав.")

# --- ЗАПУСК ---
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).request(HTTPXRequest(connect_timeout=20)).build()
    
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("magaz", magaz_cmd))
    app.add_handler(CallbackQueryHandler(shop_callback, pattern="^buy_"))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^[Рр]улетка$"), roulette_start))
    app.add_handler(CallbackQueryHandler(rt_action_callback, pattern="^rt_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    print("Kryloxa Bot v0.9.6 запущен успешно!")
    app.run_polling(drop_pending_updates=True)
