[29.03.2026 15:35] Xlmn Protectionlokab: from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from dotenv import load_dotenv
import os
import asyncio

# =======================
# Загрузка токена
# =======================
load_dotenv()
TOKEN = os.getenv("TOKEN")

bot = Bot(TOKEN)
dp = Dispatcher()

# =======================
# Настройки админки
# =======================
OWNER_ID = 123456789  # Замените на свой Telegram ID
admins = {OWNER_ID: 4}  # user_id -> ранг (1-4)

# Словарь варнов: chat_id -> user_id -> количество варнов
warns = {}

# =======================
# Проверка ранга
# =======================
def check_rank(user_id, required_rank):
    return admins.get(user_id, 0) >= required_rank

# =======================
# Функции наказаний
# =======================
async def handle_mute(message: types.Message, duration_minutes: int = 60):
    if not check_rank(message.from_user.id, 1):
        await message.reply("❌ У вас нет прав")
        return
    if not message.reply_to_message:
        await message.reply("⚠️ Ответьте на сообщение пользователя, чтобы использовать /mute")
        return

    user = message.reply_to_message.from_user
    username = f"@{user.username}" if user.username else user.full_name

    chat_id = message.chat.id
    user_id = user.id

    await bot.restrict_chat_member(
        chat_id,
        user_id,
        permissions=types.ChatPermissions(can_send_messages=False),
        until_date=None  # None = навсегда; можно поставить время через datetime
    )

    await message.reply(f"Данный пользователь {username} успешно замучен на {duration_minutes} минут.\nВыдано администратором")

async def handle_ban(message: types.Message):
    if not check_rank(message.from_user.id, 1):
        await message.reply("❌ У вас нет прав")
        return
    if not message.reply_to_message:
        await message.reply("⚠️ Ответьте на сообщение пользователя, чтобы использовать /ban")
        return

    user = message.reply_to_message.from_user
    username = f"@{user.username}" if user.username else user.full_name

    chat_id = message.chat.id
    user_id = user.id

    await bot.ban_chat_member(chat_id, user_id)
    await message.reply(f"Данный пользователь {username} успешно забанен.\nВыдано администратором")

async def handle_warn(message: types.Message):
    if not check_rank(message.from_user.id, 1):
        await message.reply("❌ У вас нет прав")
        return
    if not message.reply_to_message:
        await message.reply("⚠️ Ответьте на сообщение пользователя, чтобы использовать /warn")
        return

    chat_id = message.chat.id
    user = message.reply_to_message.from_user
    user_id = user.id
    username = f"@{user.username}" if user.username else user.full_name

    if chat_id not in warns:
        warns[chat_id] = {}
    if user_id not in warns[chat_id]:
        warns[chat_id][user_id] = 0

    warns[chat_id][user_id] += 1
    current_warns = warns[chat_id][user_id]

    if current_warns >= 3:
        await message.reply(f"❌ Пользователь {username} получил 3 варна и замучен на 30 минут! 🔇")
        warns[chat_id][user_id] = 0  # сброс варнов после “мут”
    else:
        await message.reply(f"⚠️ Пользователь {username} получил варн {current_warns}/3")

# =======================
# Команды
# =======================
@dp.message(Command("mute"))
async def mute(message: types.Message):
    await handle_mute(message, duration_minutes=60)

@dp.message(Command("ban"))
async def ban(message: types.Message):
    await handle_ban(message)

@dp.message(Command("warn"))
async def warn(message: types.Message):
    await handle_warn(message)

@dp.message(Command("addadmin"))
async def add_admin(message: types.Message):
    if not check_rank(message.from_user.id, 4):
        await message.reply("❌ Только владелец может выдавать админку")
[29.03.2026 15:35] Xlmn Protectionlokab: return
    try:
        username = message.text.split()[1]
        rank = int(message.text.split()[2])
        user_id = int(username.replace("@", ""))  # для теста через Reply можно потом переделать
        admins[user_id] = rank
        await message.reply(f"✅ Пользователь {username} получил админку ранг {rank}")
    except:
        await message.reply("⚠️ Использование: /addadmin @username <ранг>")

@dp.message(Command("removeadmin"))
async def remove_admin(message: types.Message):
    if not check_rank(message.from_user.id, 4):
        await message.reply("❌ Только владелец может удалять админов")
        return
    try:
        username = message.text.split()[1]
        user_id = int(username.replace("@", ""))  # для теста через Reply
        if user_id in admins:
            del admins[user_id]
            await message.reply(f"❌ Пользователь {username} больше не админ")
    except:
        await message.reply("⚠️ Использование: /removeadmin @username")

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "Привет! Я админ-бот Kryloxa. 👋\n"
        "Используй /help для списка команд.\n"
        "Добавь меня в группу и дай права администратора для работы наказаний."
    )

@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    await message.answer(
        "/start - приветствие\n"
        "/help - список команд\n"
        "/mute - замутить пользователя (через Reply)\n"
        "/ban - забанить (через Reply)\n"
        "/warn - выдать варн (через Reply, 3 варна = 30 мин мут)\n"
        "/addadmin @username <ранг> - выдать админку (только владелец)\n"
        "/removeadmin @username - убрать админку (только владелец)"
    )

# =======================
# Запуск бота
# =======================
async def main():
    print("Админ-бот Kryloxa запущен 🚀")
    await dp.start_polling(bot)

asyncio.run(main())
