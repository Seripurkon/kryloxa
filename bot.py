[29.03.2026 15:28] Xlmn Protectionlokab: from aiogram import Bot, Dispatcher, types
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
OWNER_ID = 5679520675  # замените на свой Telegram ID
admins = {OWNER_ID: 4}  # user_id -> ранг (1-4)

# =======================
# Проверка ранга
# =======================
def check_rank(user_id, required_rank):
    return admins.get(user_id, 0) >= required_rank

# =======================
# Функция наказаний
# =======================
async def handle_punish(message: types.Message, action: str):
    if not check_rank(message.from_user.id, 1):
        await message.reply("❌ У вас нет прав")
        return

    if not message.reply_to_message:
        await message.reply(f"⚠️ Ответьте на сообщение пользователя, чтобы использовать /{action}")
        return

    user = message.reply_to_message.from_user
    username = f"@{user.username}" if user.username else user.full_name
    chat_id = message.chat.id
    user_id = user.id

    if action == "замучен":
        # Замут на 1 час
        await bot.restrict_chat_member(
            chat_id,
            user_id,
            permissions=types.ChatPermissions(can_send_messages=False),
            until_date=None  # None = навсегда, можно поставить время
        )
    elif action == "забанен":
        await bot.ban_chat_member(chat_id, user_id)
    elif action == "предупреждён":
        pass  # только визуальное предупреждение

    await message.reply(f"Данный пользователь {username} успешно {action}.\nВыдано администратором")

# =======================
# Команды наказаний
# =======================
@dp.message(Command("mute"))
async def mute(message: types.Message):
    await handle_punish(message, "замучен")

@dp.message(Command("ban"))
async def ban(message: types.Message):
    await handle_punish(message, "забанен")

@dp.message(Command("warn"))
async def warn(message: types.Message):
    await handle_punish(message, "предупреждён")

# =======================
# Команды админки
# =======================
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

@dp.message(Command("removeadmin"))
async def remove_admin(message: types.Message):
    if not check_rank(message.from_user.id, 4):
        await message.reply("❌ Только владелец может удалять админов")
        return
    try:
        username = message.text.split()[1]
        user_id = int(username.replace("@", ""))  # для теста можно потом через Reply
        if user_id in admins:
            del admins[user_id]
            await message.reply(f"❌ Пользователь {username} больше не админ")
    except:
        await message.reply("⚠️ Использование: /removeadmin @username")

# =======================
# Старт и помощь
# =======================
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "Привет! Я админ-бот Kryloxa. 👋\n"
        "Используй /help для списка команд.\n"
        "Добавь меня в группу и дай права администратора для работы наказаний."
    )

@dp.message(Command("help"))
async def help_cmd(message: types.Message):
[29.03.2026 15:28] Xlmn Protectionlokab: await message.answer(
        "/start - приветствие\n"
        "/help - список команд\n"
        "/mute - замутить пользователя (через Reply)\n"
        "/ban - забанить (через Reply)\n"
        "/warn - выдать варн (через Reply)\n"
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
