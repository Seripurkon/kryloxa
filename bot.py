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

# --- КОНФИГУРАЦИЯ ---
TOKEN = "8641381095:AAH44UdW5z66BkX0rO5qKHOcdESAoghso_g"
OWNER_ID = 5679520675
ECONOMY_FILE = "economy.json"
WARNS_FILE = "warns.json"

logging.basicConfig(level=logging.INFO)

# --- ДАННЫЕ ---
def load_json(f, d):
    if os.path.exists(f):
        with open(f, "r", encoding='utf-8') as file: return json.load(file)
    return d

def save_json(f, data):
    with open(f, "w", encoding='utf-8') as file: json.dump(data, file, ensure_ascii=False, indent=4)

user_balance = load_json(ECONOMY_FILE, {})
warns = load_json(WARNS_FILE, {})
roulette_games = {}

# --- ПАРСЕР ПРИЧИН ---
def parse_punishment(text):
    parts = text.split('\n', 1)
    cmd_parts = parts[0].split()
    reason = parts[1].strip() if len(parts) > 1 else None
    return cmd_parts, reason

# --- КОМАНДЫ ---
async def start_cmd(update, context):
    await update.message.reply_text("🦾 Kryloxa v0.9.6 Online!")

async def help_cmd(update, context):
    await update.message.reply_text("Команды:\nРулетка\nБаланс\n/magaz\nМодерация (Мут/Варн/Бан + причина через Enter)")

async def magaz_cmd(update, context):
    kb = [[InlineKeyboardButton("💎 VIP (500)", callback_data="buy_vip")], [InlineKeyboardButton("🃏 Снять варн (300)", callback_data="buy_unwarn")]]
    await update.message.reply_text("🛒 Магазин:", reply_markup=InlineKeyboardMarkup(kb))

async def shop_callback(update, context):
    q = update.callback_query
    uid = str(q.from_user.id)
    if q.data == "buy_vip" and user_balance.get(uid, 0) >= 500:
        user_balance[uid] -= 500
        save_json(ECONOMY_FILE, user_balance)
        await q.answer("Куплено!")
    elif q.data == "buy_unwarn" and user_balance.get(uid, 0) >= 300 and warns.get(uid, 0) > 0:
        user_balance[uid] -= 300
        warns[uid] -= 1
        save_json(ECONOMY_FILE, user_balance); save_json(WARNS_FILE, warns)
        await q.answer("Варн снят!")
    else: await q.answer("Ошибка или мало KLC", show_alert=True)

# --- РУЛЕТКА (БЕЗ ИЗМЕНЕНИЙ ЛОГИКИ) ---
async def roulette_start(update, context):
    g_id = update.effective_chat.id
    if g_id in roulette_games: return
    roulette_games[g_id] = {'p1': update.effective_user.id, 'p1_n': update.effective_user.first_name, 'bet_type': 'klc', 'lives': {}}
    kb = [[InlineKeyboardButton("💰 KLC", callback_data="rbet_klc"), InlineKeyboardButton("🤫 Мут", callback_data="rbet_mute")],
          [InlineKeyboardButton("⚠️ Варн", callback_data="rbet_warn"), InlineKeyboardButton("🚫 Бан", callback_data="rbet_ban")]]
    await update.message.reply_text("🎲 Выбери ставку:", reply_markup=InlineKeyboardMarkup(kb))

async def rt_bet_callback(update, context):
    q = update.callback_query
    g = roulette_games.get(q.message.chat_id)
    if not g or q.from_user.id != g['p1']: return
    g['bet_type'] = q.data.replace("rbet_", "")
    await q.edit_message_text(f"⚔️ Ставка: {g['bet_type']}\nКто примет?", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚔️ ПРИНЯТЬ", callback_data="rt_join")]]))

async def rt_action_callback(update, context):
    q = update.callback_query
    g_id = q.message.chat_id
    g = roulette_games.get(g_id)
    if not g: return
    
    if q.data == "rt_join" and q.from_user.id != g['p1']:
        g.update({'p2': q.from_user.id, 'p2_n': q.from_user.first_name, 'lives': {g['p1']: 2, q.from_user.id: 2}, 'chamber': [0,0,0,0,0,1]})
        random.shuffle(g['chamber'])
        await q.edit_message_text(f"🔫 Дуэль! {g['p1_n']} vs {g['p2_n']}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💥 ОГОНЬ!", callback_data="rt_shoot")]]))
    
    elif q.data == "rt_shoot":
        if q.from_user.id not in [g['p1'], g['p2']]: return
        if not g['chamber']: g['chamber'] = [0,0,0,0,0,1]; random.shuffle(g['chamber'])
        bullet = g['chamber'].pop()
        msg = "💥 ПОПАДАНИЕ!" if bullet == 1 else "💨 Промах!"
        if bullet == 1: 
            g['lives'][q.from_user.id] -= 1
            g['chamber'] = [0,0,0,0,0,1]; random.shuffle(g['chamber'])
        
        # ТВОЙ БЛОК КОДА
        if any(l <= 0 for l in g['lives'].values()):
            winner_id = g['p1'] if g['lives'][g['p2']] <= 0 else g['p2']
            loser_id = g['p2'] if winner_id == g['p1'] else g['p1']
            w_name, l_name = (g['p1_n'], g['p2_n']) if winner_id == g['p1'] else (g['p2_n'], g['p1_n'])
            bet, pun = g['bet_type'], ""
            try:
                if bet == "warn":
                    warns[str(loser_id)] = warns.get(str(loser_id), 0) + 1
                    save_json(WARNS_FILE, warns)
                    pun = f"⚠️ {l_name} получает ВАРН!"
                elif bet == "mute":
                    await context.bot.restrict_chat_member(g_id, loser_id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(hours=1))
                    pun = f"🤫 {l_name} в МУТЕ на час!"
                elif bet == "ban":
                    await context.bot.ban_chat_member(g_id, loser_id, until_date=datetime.now()+timedelta(days=1))
                    pun = f"🚫 {l_name} ЗАБАНЕН на день!"
                elif bet == "klc":
                    if loser_id != OWNER_ID: user_balance[str(loser_id)] = user_balance.get(str(loser_id), 0) - 100
                    user_balance[str(winner_id)] = user_balance.get(str(winner_id), 0) + 100
                    save_json(ECONOMY_FILE, user_balance)
                    pun = f"💰 {l_name} теряет 100 KLC, а {w_name} их забирает!"
            except: pun = "⚠️ Ошибка прав."
            await q.edit_message_text(f"{msg}\n\n🏆 **Победил {w_name}!**\n{pun}", parse_mode="Markdown")
            del roulette_games[g_id]
        else:
            status = f"{msg}\n\n❤️ {g['p1_n']}: {g['lives'][g['p1']]} | {g['p2_n']}: {g['lives'][g['p2']]}"
            await q.edit_message_text(status, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💥 ОГОНЬ!", callback_data="rt_shoot")]]))

# --- ХЕНДЛЕР ТЕКСТА (СИСТЕМА ПРИЧИН) ---
async def text_handler(update, context):
    text = update.message.text
    uid, cid = str(update.effective_user.id), update.effective_chat.id
    user_balance[uid] = user_balance.get(uid, 0) + 1
    
    if text.lower() == "баланс":
        await update.message.reply_text(f"💰 KLC: {user_balance[uid]}")
        save_json(ECONOMY_FILE, user_balance)
        return

    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
        cmd_parts, reason = parse_punishment(text)
        cmd = cmd_parts[0].lower()
        out = ""
        try:
            if cmd in ["мут", "молчи"]:
                tm = int(cmd_parts[1]) if len(cmd_parts) > 1 else 60
                await context.bot.restrict_chat_member(cid, target.id, permissions=ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(minutes=tm))
                out = f"🤫 {target.first_name} в муте на {tm} мин."
            elif cmd == "варн":
                warns[str(target.id)] = warns.get(str(target.id), 0) + 1
                save_json(WARNS_FILE, warns)
                out = f"⚠️ {target.first_name} получил варн."
            elif cmd == "бан":
                await context.bot.ban_chat_member(cid, target.id)
                out = f"🚫 {target.first_name} забанен."
            
            if out:
                if reason: out += f"\n📝 Причина: {reason}"
                await update.message.reply_text(out)
        except: pass

# --- ЗАПУСК ---
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
    app.run_polling(drop_pending_updates=True)
