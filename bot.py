from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from dotenv import load_dotenv
import os

load_dotenv()
TOKEN = os.getenv("TOKEN")

bot = Bot(TOKEN)
dp = Dispatcher()

# Владелец бота
OWNER_ID = 5679520675

# Словарь админов: user_id -> ранг (1-4)
admins = {OWNER_ID: 4}

# Проверка прав
def check_rank(user_id, required_rank):
    return admins.get(user_id, 0) >= required_rank

# Функция наказаний
async def handle_punish(message: types.Message, action: str):
    if not check_rank(message.from_user.id, 1):
        await message.reply("❌ У вас нет прав")
        return
    if not message.reply_to_message:
        await message.reply(f"⚠️ Ответьте на сообщение пользователя, чтобы использовать /{action}")
        return
    user = message.reply_to_message.from_user
    username = f"@{user.username}" if user.username else user.full_name
    await message.reply(f"Данный пользователь {username} успешно {action}.\nВыдано администратором")

@dp.message(Command("mute"))
async def mute(message: types.Message):
    await handle_punish(message, "замучен")

@dp.message(Command("ban"))
async def ban(message: types.Message):
    await handle_punish(message, "забанен")

@dp.message(Command("warn"))
async def warn(message: types.Message):
    await handle_punish(message, "предупреждён")

# Выдача админки
@dp.message(Command("addadmin"))
async def add_admin(message: types.Message):
    if not check_rank(message.from_user.id, 4):
        await message.reply("❌ Только владелец может выдавать админку")
        return
    try:
        username = message.text.split()[1]
        rank = int(message.text.split()[2])
        user_id = int(username.replace("@", ""))  # для теста можно потом через Reply
        admins[user_id] = rank
        await message.reply(f"✅ Пользователь {username} получил админку ранг {rank}")
    except:
        await message.reply("⚠️ Использование: /addadmin @username <ранг>")

# Старт
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("Привет! Я админ-бот. Используй /help для списка команд.")

# Помощь
@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    await message.answer(
        "/start - приветствие\n/help - список команд\n/mute - замутить\n/ban - забанить\n/warn - выдать варн\n"
        "/addadmin @username <ранг> - выдать админку (только владелец)"
    )

import asyncio
async def main():
    print("Админ-бот Kryloxa запущен 🚀")
    await dp.start_polling(bot)

asyncio.run(main())
