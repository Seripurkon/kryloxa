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
    ChatPermissions
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

TOKEN = "8548759774:AAGdsv1JThkVBonbFgYURkKFHvJP6juc8CE"
OWNER_ID = 5679520675

ECONOMY_FILE = "economy.json"
WARNS_FILE = "warns.json"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================================================================
# --- МЕХАНИКА РАБОТЫ С ДАННЫМИ (JSON СИСТЕМА) ---
# ================================================================

def load_json(filename, default):
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding='utf-8') as file:
                return json.load(file)
        except Exception as error:
            logger.error(f"Ошибка при чтении {filename}: {error}")
            return default
    return default

def save_json(filename, data):
    try:
        with open(filename, "w", encoding='utf-8') as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
    except Exception as error:
        logger.error(f"Ошибка при сохранении {filename}: {error}")

user_balance = load_json(ECONOMY_FILE, {})
warns = load_json(WARNS_FILE, {})
roulette_games = {}

# --- ПАРСЕР ПРИЧИН ---
def parse_punishment(text):
    parts = text.split('\n', 1)
    first_line_words = parts[0].split()
    reason_text = parts[1].strip() if len(parts) > 1 else None
    return first_line_words, reason_text

# ================================================================
# --- ОБРАБОТЧИКИ КОМАНД (ПРИОРИТЕТ 1) ---
# ================================================================

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🦾 **Kryloxa Bot v0.9.6-beta ОНЛАЙН!**\n\n"
        "Обработчики команд перенастроены. Теперь всё должно работать.\n"
        "Напиши `Помощь`, чтобы увидеть список функций.",
        parse_mode="Markdown"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        "• `Бан` + [абзац] + [причина]"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def magaz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💎 VIP Статус (500 KLC)", callback_data="buy_vip")],
        [InlineKeyboardButton("🃏 Снять 1 варн (300 KLC)", callback_data="buy_unwarn")]
    ]
    await update.message.reply_text("🛒 **МАГАЗИН БОНУСОВ KRYLOXA:**", reply_markup=InlineKeyboardMarkup(keyboard))

# ================================================================
# --- КНОПКИ И МАГАЗИН ---
# ================================================================

async def shop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(query.from_user.id)
    bal = user_balance.get(uid, 0)

    if query.data == "buy_vip":
        if bal >= 500:
            user_balance[uid] -= 500
            save_json(ECONOMY_FILE, user_balance)
            await query.answer("✅ VIP успешно приобретен!", show_alert=True)
        else:
            await query.answer("❌ Недостаточно KLC", show_alert=True)
    elif query.data == "buy_unwarn":
        if bal >= 300 and warns.get(uid, 0) > 0:
            user_balance[uid] -= 300
            warns[uid] -= 1
            save_json(ECONOMY_FILE, user_balance); save_json(WARNS_FILE, warns)
            await query.answer("✅ Варн снят!", show_alert=True)
        else:
            await query.answer("❌ Нет варнов или мало KLC", show_alert=True)

# ================================================================
# --- РУССКАЯ РУЛЕТКА (3 ЖИЗНИ) ---
# ================================================================

async def roulette_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in roulette_games:
        return await update.message.reply_text("⚠️ Ошибка: Игра уже идет!")

    roulette_games[chat_id] = {
        'player1_id': update.effective_user.id,
        'player1_name': update.effective_user.first_name,
        'bet_type': 'klc',
        'lives': {}, 'chamber': [], 'is_active': False
    }

    keyboard = [
        [InlineKeyboardButton("💰 100 KLC", callback_data="rbet_klc"), InlineKeyboardButton("🤫 Мут (1ч)", callback_data="rbet_mute")],
        [InlineKeyboardButton("⚠️ Варн", callback_data="rbet_warn"), InlineKeyboardButton("🚫 Бан (1д)", callback_data="rbet_ban")]
    ]
    await update.message.reply_text(f"🎲 **{update.effective_user.first_name} вызывает на дуэль!**", reply_markup=InlineKeyboardMarkup(keyboard))

async def roulette_bet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    game = roulette_games.get(query.message.chat_id)
    if not game or query.from_user.id != game['player1_id']: return
    game['bet_type'] = query.data.replace("rbet_", "")
    await query.edit_message_text(f"⚔️ **Ставка: {game['bet_type'].upper()}**\nКто примет вызов?", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚔️ ПРИНЯТЬ", callback_data="r_join")]]))

async def roulette_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat_id
    game = roulette_games.get(chat_id)
    if not game: return

    if query.data == "r_join":
        if query.from_user.id == game['player1_id']: return
        game.update({'player2_id': query.from_user.id, 'player2_name': query.from_user.first_name, 'lives': {game['player1_id']: 3, query.from_user.id: 3}, 'chamber': [0,0,0,0,0,1], 'is_active': True})
        random.shuffle(game['chamber'])
        await query.edit_message_text(f"🔫 **Дуэль!** {game['player1_name']} vs {game['player2_name']}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💥 ОГОНЬ!", callback_data="r_shoot")]]))

    elif query.data == "r_shoot":
        sid = query.from_user.id
        if sid not in [game['player1_id'], game['player2_id']]: return
        if not game['chamber']: game['chamber'] = [0,0,0,0,0,1]; random.shuffle(game['chamber'])
        
        bullet = game['chamber'].pop()
        if bullet == 1:
            game['lives'][sid] -= 1
            res = "💥 **ПОПАДАНИЕ!**"
            game['chamber'] = [0,0,0,0,0,1]; random.shuffle(game['chamber'])
        else: res = "💨 *Промах!*"

        if any(l <= 0 for l in game['lives'].values()):
            win_id = game['player1_id'] if game['lives'][game['player2_id']] <= 0 else game['player2_id']
            los_id = game['player2_id'] if win_id == game['player1_id'] else game['player1_id']
            try:
                bet = game['bet_type']
                if bet == "klc":
                    user_balance[str(los_id)] = user_balance.get(str(los_id), 0) - 100
                    user_balance[str(win_id)] = user_balance.get(str(win_id), 0) + 100
                elif bet == "mute": await context.bot.restrict_chat_member(chat_id, los_id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now() + timedelta(hours=1))
                elif bet == "warn": warns[str(los_id)] = warns.get(str(los_id), 0) + 1
                elif bet == "ban": await context.bot.ban_chat_member(chat_id, los_id, until_date=datetime.now() + timedelta(days=1))
                save_json(ECONOMY_FILE, user_balance); save_json(WARNS_FILE, warns)
            except: pass
            await query.edit_message_text(f"{res}\n\n🏆 Победил: **{game['player1_name'] if win_id==game['player1_id'] else game['player2_name']}**")
            del roulette_games[chat_id]
        else:
            status = f"{res}\n\n❤️ {game['lives'][game['player1_id']]} : {game['lives'][game['player2_id']]}"
            await query.edit_message_text(status, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💥 ОГОНЬ!", callback_data="r_shoot")]]))

# ================================================================
# --- ОБРАБОТЧИК ТЕКСТА (ПРИОРИТЕТ 2) ---
# ================================================================

async def message_dispatcher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text: return
    uid, chat_id = str(update.effective_user.id), update.effective_chat.id
    msg_low = text.lower()

    user_balance[uid] = user_balance.get(uid, 0) + 1
    save_json(ECONOMY_FILE, user_balance)

    if msg_low == "баланс":
        return await update.message.reply_text(f"💰 Баланс: **{user_balance[uid]} KLC**", parse_mode="Markdown")

    if "garticphone.com" in msg_low:
        urls = re.findall(r'(https?://garticphone\.com/[^\s]+)', text)
        if urls:
            try:
                async with httpx.AsyncClient(timeout=5.0) as cl:
                    r = await cl.get(urls[0])
                    await update.message.reply_text("✅ Живая!" if r.status_code == 200 else "❌ Закрыта.")
            except: pass

    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
        cmd_parts, reason = parse_punishment(text)
        main_cmd = cmd_parts[0].lower()
        try:
            if main_cmd in ["мут", "молчи"]:
                amount = int(cmd_parts[1]) if len(cmd_parts) > 1 else 60
                unit = cmd_parts[2].lower() if len(cmd_parts) > 2 else "мин"
                sec = amount * 60 if "мин" in unit else amount * 3600
                await context.bot.restrict_chat_member(chat_id, target.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now() + timedelta(seconds=sec))
                out = f"🤫 **{target.first_name}** в муте на {amount} {unit}."
            elif main_cmd == "варн":
                warns[str(target.id)] = warns.get(str(target.id), 0) + 1
                save_json(WARNS_FILE, warns)
                out = f"⚠️ **{target.first_name}** получил варн ({warns[str(target.id)]}/3)."
            elif main_cmd == "бан":
                await context.bot.ban_chat_member(chat_id, target.id)
                out = f"🚫 **{target.first_name}** забанен."
            else: return
            if reason: out += f"\n📝 **Причина:** {reason}"
            await update.message.reply_text(out, parse_mode="Markdown")
        except: await update.message.reply_text("❌ Ошибка прав.")

# ================================================================
# --- ЗАПУСК (СТРОГИЙ ПОРЯДОК) ---
# ================================================================

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).request(HTTPXRequest(connect_timeout=20)).build()

    # Сначала команды
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("magaz", magaz_cmd))
    
    # Кнопки
    app.add_handler(CallbackQueryHandler(shop_callback, pattern="^buy_"))
    app.add_handler(CallbackQueryHandler(roulette_bet_callback, pattern="^rbet_"))
    app.add_handler(CallbackQueryHandler(roulette_action_callback, pattern="^r_"))
    
    # Специальное слово для рулетки
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^[Рр]улетка$"), roulette_start))
    
    # Весь остальной текст (НЕ команды)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_dispatcher))
    
    print(">>> Kryloxa Bot v0.9.6 УСПЕШНО ЗАПУЩЕН!")
    app.run_polling(drop_pending_updates=True)
