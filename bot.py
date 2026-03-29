import os
import json
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

# Данные (ОСТАВЛЯЕМ ТВОИ)
TOKEN = "8641381095:AAGLY3W93LQGfq_Ygm1OIfAMwlhb6SlQrXE"
OWNER_ID = 5679520675 
FRIEND_ID = 782585931
RANKS_FILE = "ranks.json"

# Вспомогательные функции (Ранги, сохранения и т.д. — без изменений)
def load_ranks():
    if os.path.exists(RANKS_FILE):
        try:
            with open(RANKS_FILE, "r") as f:
                data = json.load(f)
                return {int(k): v for k, v in data.items()}
        except: pass
    return {OWNER_ID: 4, FRIEND_ID: 3}

user_ranks = load_ranks()
warns = {}
roulette_games = {} # Здесь теперь храним состояние магазина и жизни

def get_rank(user_id):
    return user_ranks.get(user_id, 0)

# --- Стандартные команды (Start/Help/Text) оставляем как в прошлом коде ---
# ... (пропускаю для краткости, вставь их из прошлого сообщения) ...

# ===================== НОВАЯ РУЛЕТКА С ЖИЗНЯМИ И ПАТРОНАМИ =====================

async def roulette_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.reply_to_message
    if not msg or update.effective_user.id == msg.from_user.id:
        return await update.message.reply_text("Ответь на сообщение противника!")
    
    p1, p2 = update.effective_user, msg.from_user
    game_id = f"g_{update.message.message_id}"
    
    # Генерация патронов: всего 6, боевых от 1 до 5 (рандом)
    live_bullets_count = random.randint(1, 5)
    chamber = [True] * live_bullets_count + [False] * (6 - live_bullets_count)
    random.shuffle(chamber)
    
    roulette_games[game_id] = {
        "p1": p1.id, "p1_n": p1.first_name,
        "p2": p2.id, "p2_n": p2.first_name,
        "lives": {p1.id: 2, p2.id: 2},
        "chamber": chamber,
        "turn": p2.id, # Первый ход делает тот, кого вызвали
        "mode": None,
        "bullets_info": f"боевых: {live_bullets_count}, холостых: {6 - live_bullets_count}"
    }
    
    rules = (
        f"⚠️ **ПРАВИЛА ДУЭЛИ** ⚠️\n"
        f"В дробовике 6 патронов ({roulette_games[game_id]['bullets_info']}).\n"
        f"У каждого игрока по **2 жизни**.\n"
        f"Стреляете по очереди. Проиграет тот, кто первым потеряет обе жизни!\n\n"
        f"👊 {p2.first_name}, выбирай ставку:"
    )
    
    keyboard = [[
        InlineKeyboardButton("Варн", callback_data=f"setup_warn_{game_id}"),
        InlineKeyboardButton("Мут (10м)", callback_data=f"setup_mute_{game_id}"),
        InlineKeyboardButton("Бан (1д)", callback_data=f"setup_ban_{game_id}")
    ]]
    await update.message.reply_text(rules, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def roulette_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.split("_")
    action, val, game_id = data[0], data[1], data[2]
    
    if game_id not in roulette_games:
        return await query.answer("Игра окончена.", show_alert=True)
    
    g = roulette_games[game_id]
    user_id = query.from_user.id

    # 1. Выбор ставки (только p2 может выбрать в начале)
    if action == "setup":
        if user_id != g['p2']:
            return await query.answer("Ставку выбирает тот, кого вызвали!", show_alert=True)
        g['mode'] = val
        await start_turn_message(query, g, game_id)
        return

    # 2. Логика выстрела
    if action == "shoot":
        if user_id != g['turn']:
            return await query.answer("Сейчас не твой ход!", show_alert=True)
        
        await query.answer("Нажимаем на курок...")
        is_live = g['chamber'].pop(0) # Достаем первый патрон
        
        if is_live:
            g['lives'][user_id] -= 1
            result_icon = "💥 БАХ! Боевой!"
        else:
            result_icon = "💨 Щелчок... Холостой."

        # Проверка на смерть
        if g['lives'][user_id] <= 0:
            return await finish_game(query, g, user_id, game_id, context)

        # Если патроны кончились, а все живы — перебор (но с 2 жизнями и 6 пулями это редко)
        if not g['chamber']:
            await query.edit_message_text("Патроны кончились! Ничья.")
            del roulette_games[game_id]
            return

        # Смена хода
        g['turn'] = g['p2'] if g['turn'] == g['p1'] else g['p1']
        await start_turn_message(query, g, game_id, last_action=result_icon)

async def start_turn_message(query, g, game_id, last_action=""):
    turn_name = g['p1_n'] if g['turn'] == g['p1'] else g['p2_n']
    text = (
        f"{last_action}\n\n"
        f"👤 **{g['p1_n']}**: {'❤️' * g['lives'][g['p1']]}\n"
        f"👤 **{g['p2_n']}**: {'❤️' * g['lives'][g['p2']]}\n"
        f"📦 Патронов в стволе: {len(g['chamber'])}\n\n"
        f"👉 Ход игрока: **{turn_name}**"
    )
    kb = [[InlineKeyboardButton("🔥 ВЫСТРЕЛ", callback_data=f"shoot_0_{game_id}")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def finish_game(query, g, loser_id, game_id, context):
    loser_name = g['p1_n'] if loser_id == g['p1'] else g['p2_n']
    mode = g['mode']
    final_text = f"💀 **{loser_name} ПОГИБ!**\nНаказание: {mode.capitalize()}"
    
    # Выдача наказания (логика как в твоем прошлом коде)
    try:
        chat_id = query.message.chat_id
        if mode == "mute":
            await context.bot.restrict_chat_member(chat_id, loser_id, permissions={"can_send_messages": False}, until_date=datetime.now() + timedelta(minutes=10))
        elif mode == "ban":
            await context.bot.ban_chat_member(chat_id, loser_id, until_date=datetime.now() + timedelta(days=1))
        elif mode == "warn":
            warns[loser_id] = warns.get(loser_id, 0) + 1
            if warns[loser_id] >= 3:
                warns[loser_id] = 0
                await context.bot.restrict_chat_member(chat_id, loser_id, permissions={"can_send_messages": False}, until_date=datetime.now() + timedelta(days=1))
                final_text += "\n🛑 3/3 варна! Мут на 1 день!"
    except:
        final_text += "\n(Бот не смог выдать наказание)"

    await query.edit_message_text(final_text, parse_mode="Markdown")
    del roulette_games[game_id]

# --- ОСТАЛЬНОЙ КОД (ЗАПУСК) ---
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^[Рр]улетка$"), roulette_command))
    app.add_handler(CallbackQueryHandler(roulette_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.run_polling()
