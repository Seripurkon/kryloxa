import logging
import json
import os
import random
import httpx
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CommandHandler, CallbackQueryHandler
from telegram.request import HTTPXRequest

# --- КОНФИГУРАЦИЯ ---
TOKEN = "8548759774:AAGynBbPfNS58sE-HJf-TEZ4HNw50fQMZBw"
OWNER_ID = 5679520675
ECONOMY_FILE = "economy.json"
WARNS_FILE = "warns.json"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- РАБОТА С ФАЙЛАМИ ---
def load_json(filename, default):
    if os.path.exists(filename):
        with open(filename, "r", encoding='utf-8') as f:
            try:
                return json.load(f)
            except:
                return default
    return default

def save_json(filename, data):
    with open(filename, "w", encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# Загрузка данных
user_balance = load_json(ECONOMY_FILE, {})
warns = load_json(WARNS_FILE, {})
roulette_games = {}

# --- ПАРСЕР ПРИЧИН (АБЗАЦ) ---
def parse_punishment(text):
    """Разделяет текст: первая строка — команда, остальное — причина"""
    parts = text.split('\n', 1)
    first_line = parts[0].split()
    reason = parts[1].strip() if len(parts) > 1 else None
    return first_line, reason

# --- КОМАНДЫ ---
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🦾 **Kryloxa Bot v0.9.6-beta запущен!**\nВсе системы (Рулетка, Магазин, Модерация) активны.")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📜 **Команды Kryloxa Bot:**\n"
        "• `Рулетка` — дуэль на выживание (3 жизни)\n"
        "• `Баланс` — проверка KLC\n"
        "• `/magaz` — магазин бонусов\n\n"
        "⚒ **Модерация (реплаем):**\n"
        "• `Мут [число] [мин/час/день]` + абзац (причина)\n"
        "• `Варн` + абзац (причина)\n"
        "• `Бан` + абзац (причина)\n\n"
        "🎮 **Gartic:** Скинь ссылку, и я проверю комнату."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

# --- МАГАЗИН ---
async def magaz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("💎 VIP Роль (500 KLC)", callback_data="buy_vip")],
        [InlineKeyboardButton("🃏 Снять варн (300 KLC)", callback_data="buy_unwarn")]
    ]
    await update.message.reply_text("🛒 **Магазин Kryloxa:**", reply_markup=InlineKeyboardMarkup(kb))

async def shop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = str(q.from_user.id)
    bal = user_balance.get(uid, 0)
    
    if q.data == "buy_vip":
        if bal >= 500:
            user_balance[uid] -= 500
            save_json(ECONOMY_FILE, user_balance)
            await q.answer("✅ VIP статус куплен!", show_alert=True)
        else:
            await q.answer("❌ Недостаточно KLC!", show_alert=True)
    
    elif q.data == "buy_unwarn":
        if bal >= 300 and warns.get(uid, 0) > 0:
            user_balance[uid] -= 300
            warns[uid] -= 1
            save_json(ECONOMY_FILE, user_balance)
            save_json(WARNS_FILE, warns)
            await q.answer("✅ Один варн снят!", show_alert=True)
        else:
            await q.answer("❌ Ошибка: нет варнов или мало KLC.", show_alert=True)

# --- РУССКАЯ РУЛЕТКА (ПОЛНАЯ ЛОГИКА) ---
async def roulette_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in roulette_games:
        return await update.message.reply_text("⚠️ Игра уже идет!")
    
    roulette_games[chat_id] = {
        'p1': update.effective_user.id,
        'p1_n': update.effective_user.first_name,
        'active': False,
        'bet_type': 'klc'
    }
    
    kb = [
        [InlineKeyboardButton("💰 100 KLC", callback_data="rbet_klc"), 
         InlineKeyboardButton("🤫 Мут (1ч)", callback_data="rbet_mute")],
        [InlineKeyboardButton("⚠️ Варн", callback_data="rbet_warn"), 
         InlineKeyboardButton("🚫 Бан (1д)", callback_data="rbet_ban")]
    ]
    await update.message.reply_text("🎲 **Ставка для дуэли:**", reply_markup=InlineKeyboardMarkup(kb))

async def rt_bet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    g = roulette_games.get(q.message.chat_id)
    if not g or q.from_user.id != g['p1']: return
    
    g['bet_type'] = q.data.replace("rbet_", "")
    kb = [[InlineKeyboardButton("Принять вызов", callback_data="rt_join")]]
    await q.edit_message_text(
        f"⚔️ **{g['p1_n']}** ставит на **{g['bet_type'].upper()}**!\nКто готов рискнуть жизнью?",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def rt_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    g_id = q.message.chat_id
    g = roulette_games.get(g_id)
    if not g: return

    if q.data == "rt_join":
        if q.from_user.id == g['p1']: return
        g.update({
            'p2': q.from_user.id,
            'p2_n': q.from_user.first_name,
            'lives': {g['p1']: 3, q.from_user.id: 3},
            'chamber': [0, 0, 0, 0, 0, 1],
            'active': True
        })
        random.shuffle(g['chamber'])
        kb = [[InlineKeyboardButton("💥 Нажать на курок", callback_data="rt_shoot")]]
        await q.edit_message_text(
            f"🔫 **Дуэль началась!**\n{g['p1_n']} [3❤️] vs {g['p2_n']} [3❤️]",
            reply_markup=InlineKeyboardMarkup(kb)
        )

    elif q.data == "rt_shoot":
        u_id = q.from_user.id
        if u_id not in [g['p1'], g['p2']]: return
        
        bullet = g['chamber'].pop()
        name = q.from_user.first_name
        
        if bullet == 1:
            g['lives'][u_id] -= 1
            res = f"💥 **БА-БАХ! {name} ранен!**"
            g['chamber'] = [0, 0, 0, 0, 0, 1]
            random.shuffle(g['chamber'])
        else:
            res = f"💨 {name}: *Щелчок... Пусто.*"
        
        if any(l <= 0 for l in g['lives'].values()):
            win_id = g['p1'] if g['lives'][g['p2']] <= 0 else g['p2']
            los_id = g['p2'] if win_id == g['p1'] else g['p1']
            l_name = g['p2_n'] if win_id == g['p1'] else g['p1_n']
            w_name = g['p1_n'] if win_id == g['p1'] else g['p2_n']
            
            bet = g['bet_type']
            pun = ""
            try:
                if bet == "warn":
                    warns[str(los_id)] = warns.get(str(los_id), 0) + 1
                    pun = f"⚠️ {l_name} получает ВАРН!"
                elif bet == "mute":
                    await context.bot.restrict_chat_member(g_id, los_id, permissions={"can_send_messages":False}, until_date=datetime.now()+timedelta(hours=1))
                    pun = f"🤫 {l_name} замолчит на час!"
                elif bet == "ban":
                    await context.bot.ban_chat_member(g_id, los_id, until_date=datetime.now()+timedelta(days=1))
                    pun = f"🚫 {l_name} изгнан на день!"
                elif bet == "klc":
                    user_balance[str(los_id)] = user_balance.get(str(los_id), 0) - 100
                    user_balance[str(win_id)] = user_balance.get(str(win_id), 0) + 100
                    pun = f"💰 {l_name} теряет 100 KLC в пользу победителя!"
            except: pun = "⚠️ Ошибка: боту не хватает прав."
            
            save_json(ECONOMY_FILE, user_balance); save_json(WARNS_FILE, warns)
            await q.edit_message_text(f"{res}\n\n🏆 **Победил {w_name}!**\n{pun}", parse_mode="Markdown")
            del roulette_games[g_id]
        else:
            status = f"\n\n❤️ {g['p1_n']}: {g['lives'][g['p1']]} | {g['p2_n']}: {g['lives'][g['p2']]}"
            kb = [[InlineKeyboardButton("💥 Следующий выстрел", callback_data="rt_shoot")]]
            await q.edit_message_text(res + status, reply_markup=InlineKeyboardMarkup(kb))

# --- ОБРАБОТЧИК ТЕКСТА ---
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text: return
    user_id = str(update.effective_user.id)
    msg_lower = text.lower()

    # Экономика
    user_balance[user_id] = user_balance.get(user_id, 0) + 1
    save_json(ECONOMY_FILE, user_balance)

    if msg_lower == "баланс":
        return await update.message.reply_text(f"💰 Твой баланс: **{user_balance[user_id]} KLC**", parse_mode="Markdown")

    # Gartic Phone
    if "garticphone.com" in msg_lower:
        url = next((w for w in text.split() if "garticphone.com" in w), "")
        try:
            async with httpx.AsyncClient() as cl:
                r = await cl.get(url, timeout=5)
                res = "✅ **Комната активна!**" if r.status_code == 200 else "❌ **Комната закрыта.**"
                await update.message.reply_text(res, parse_mode="Markdown")
        except: pass

    # МОДЕРАЦИЯ С ПРИЧИНАМИ
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
        target_id = str(target.id)

        if msg_lower.startswith(("молчи", "мут", "варн", "бан")):
            first_line, reason = parse_punishment(text)
            out = ""
            try:
                # МУТ
                if "мут" in msg_lower or "молчи" in msg_lower:
                    val = int(first_line[1]) if len(first_line) > 1 else 1
                    unit = first_line[2].lower() if len(first_line) > 2 else "час"
                    sec = val * 60 if "мин" in unit else val * 3600
                    if "ден" in unit: sec = val * 86400
                    
                    await context.bot.restrict_chat_member(update.effective_chat.id, target.id, 
                        permissions={"can_send_messages": False}, until_date=datetime.now() + timedelta(seconds=sec))
                    out = f"🤫 **{target.first_name} в муте на {val} {unit}.**"
                
                # ВАРН
                elif "варн" in msg_lower:
                    warns[target_id] = warns.get(target_id, 0) + 1
                    save_json(WARNS_FILE, warns)
                    out = f"⚠️ **Варн для {target.first_name} ({warns[target_id]}/3).**"
                    if warns[target_id] >= 3:
                        await context.bot.ban_chat_member(update.effective_chat.id, target.id)
                        out += "\n🛑 Авто-бан за 3/3 варнов!"
                        warns[target_id] = 0
                
                # БАН
                elif "бан" in msg_lower:
                    await context.bot.ban_chat_member(update.effective_chat.id, target.id)
                    out = f"🚫 **{target.first_name} забанен.**"
                
                if reason: out += f"\n📝 **Причина:** {reason}"
                if out: await update.message.reply_text(out, parse_mode="Markdown")
                
            except Exception as e:
                await update.message.reply_text(f"⚠️ Ошибка прав: {e}")

# --- ТОЧКА ВХОДА ---
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).request(HTTPXRequest(connect_timeout=20)).build()
    
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("magaz", magaz_cmd))
    app.add_handler(CallbackQueryHandler(shop_callback, pattern="^buy_"))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^[Рр]улетка$"), roulette_start))
    app.add_handler(CallbackQueryHandler(rt_bet_callback, pattern="^rbet_"))
    app.add_handler(CallbackQueryHandler(rt_action_callback, pattern="^rt_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    print(">>> Kryloxa Bot v0.9.6 УСПЕШНО ЗАПУЩЕН!")
    app.run_polling(drop_pending_updates=True)
