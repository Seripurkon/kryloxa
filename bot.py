import os
import asyncio
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

# Твои данные
TOKEN = "8641381095:AAGLY3W93LQGfq_Ygm1OIfAMwlhb6SlQrXE"
admins = {5679520675} 

warns = {}
roulette_games = {}

def is_admin(user_id):
    return user_id in admins

# ===================== Админ-команды =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Бот запущен!\n\n"
        "Команды (ответом на сообщение):\n"
        "/mute [мин] — замутить\n"
        "/warn — выдать варн (3 = мут 30м)\n"
        "/ban [дней] — забанить\n"
        "/unmute, /unwarn, /unban — снять наказание\n\n"
        "🎮 Для игры ответь юзеру словом 'Рулетка'"
    )

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    msg = update.message.reply_to_message
    if not msg: return await update.message.reply_text("Ответь на сообщение.")
    
    m = int(context.args[0]) if context.args and context.args[0].isdigit() else 60
    until = datetime.now() + timedelta(minutes=m)
    try:
        await context.bot.restrict_chat_member(update.effective_chat.id, msg.from_user.id, permissions={"can_send_messages": False}, until_date=until)
        await update.message.reply_text(f"🔇 {msg.from_user.first_name} в муте на {m} мин.")
    except Exception as e: await update.message.reply_text(f"Ошибка: {e}")

async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    msg = update.message.reply_to_message
    if not msg: return
    uid = msg.from_user.id
    warns[uid] = warns.get(uid, 0) + 1
    if warns[uid] >= 3:
        warns[uid] = 0
        until = datetime.now() + timedelta(minutes=30)
        await context.bot.restrict_chat_member(update.effective_chat.id, uid, permissions={"can_send_messages": False}, until_date=until)
        await update.message.reply_text(f"⚠️ 3/3 варна! {msg.from_user.first_name} в муте на 30м.")
    else:
        await update.message.reply_text(f"⚠️ Варн {msg.from_user.first_name}: {warns[uid]}/3")

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    msg = update.message.reply_to_message
    if not msg: return
    d = int(context.args[0]) if context.args and context.args[0].isdigit() else 1
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, msg.from_user.id, until_date=datetime.now() + timedelta(days=d))
        await update.message.reply_text(f"🚫 {msg.from_user.first_name} забанен на {d} дн.")
    except Exception as e: await update.message.reply_text(f"Ошибка: {e}")

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    msg = update.message.reply_to_message
    if not msg: return
    try:
        await context.bot.restrict_chat_member(update.effective_chat.id, msg.from_user.id, permissions={"can_send_messages": True, "can_send_polls": True, "can_send_other_messages": True, "can_add_web_page_previews": True})
        await update.message.reply_text(f"🔊 Мут с {msg.from_user.first_name} снят.")
    except Exception as e: await update.message.reply_text(f"Ошибка: {e}")

async def unwarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    msg = update.message.reply_to_message
    if not msg: return
    uid = msg.from_user.id
    warns[uid] = max(0, warns.get(uid, 0) - 1)
    await update.message.reply_text(f"✅ Варн снят. У {msg.from_user.first_name} теперь {warns[uid]}/3")

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    msg = update.message.reply_to_message
    if not msg: return
    try:
        await context.bot.unban_chat_member(update.effective_chat.id, msg.from_user.id, only_if_banned=True)
        await update.message.reply_text(f"✅ {msg.from_user.first_name} разбанен.")
    except Exception as e: await update.message.reply_text(f"Ошибка: {e}")

# ===================== Русская Рулетка =====================

async def roulette_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.reply_to_message
    if not msg: return await update.message.reply_text("Ответь на сообщение оппонента!")
    p1, p2 = update.effective_user, msg.from_user
    if p1.id == p2.id: return await update.message.reply_text("Нельзя играть с собой.")
    roulette_games[p2.id] = {"p1": p1.id, "p1_n": p1.first_name, "p2": p2.id, "p2_n": p2.first_name}
    keyboard = [[
        InlineKeyboardButton("Варн", callback_data="r_warn"),
        InlineKeyboardButton("Мут", callback_data="r_mute"),
        InlineKeyboardButton("Бан (1д)", callback_data="r_ban")
    ]]
    await update.message.reply_text(f"🎮 {p2.first_name}, дуэль от {p1.first_name}!\nВыбери ставку:", reply_markup=InlineKeyboardMarkup(keyboard))

async def roulette_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    if uid not in roulette_games: return await query.answer("Не твоя игра!", show_alert=True)
    g = roulette_games[uid]
    mode = query.data.replace("r_", "")
    fate = random.choice([True, False])
    l_id = g['p2'] if fate else g['p1']
    l_n = g['p2_n'] if fate else g['p1_n']
    await query.edit_message_text(f"💥 БАХ! {l_n} проиграл и получает {mode}!")
    try:
        if mode == "mute":
            await context.bot.restrict_chat_member(update.effective_chat.id, l_id, permissions={"can_send_messages": False}, until_date=datetime.now() + timedelta(minutes=10))
        elif mode == "ban":
            await context.bot.ban_chat_member(update.effective_chat.id, l_id, until_date=datetime.now() + timedelta(days=1))
        else:
            warns[l_id] = warns.get(l_id, 0) + 1
    except: await query.message.reply_text("Бот не смог наказать проигравшего (права?)")
    del roulette_games[uid]

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("warn", warn))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("unmute", unmute))
    app.add_handler(CommandHandler("unwarn", unwarn))
    app.add_handler(CommandHandler("unban", unban))
    app.add_handler(MessageHandler(filters.REPLY & filters.Regex(r"(?i)^Рулетка$"), roulette_command))
    app.add_handler(CallbackQueryHandler(roulette_callback, pattern="^r_"))
    print("🚀 Бот запущен!")
    app.run_polling()
