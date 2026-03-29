import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from dotenv import load_dotenv

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
OWNER_ID = 5679520675  
admins = {OWNER_ID: 4}  # user_id -> ранг (1-4)
warns = {} # chat_id -> user_id -> count

# =======================
# Проверка ранга
# =======================
def check_rank(user_id, required_rank):
    return admins.get(user_id, 0) >= required_rank

# =======================
# Команды наказаний
# =======================
@dp.message(Command("mute"))
async def mute(message: types.Message):
    if not check_rank(message.from_user.id, 1):
        return await message.reply("❌ У вас нет прав")
    
    if not message.reply_to_message:
        return await message.reply("⚠️ Ответьте на сообщение пользователя")

    user = message.reply_to_message.from_user
    await bot.restrict_chat_member(
        message.chat.id,
        user.id,
        permissions=types.ChatPermissions(can_send_messages=False)
    )
    await message.reply(f"🔇 Пользователь {user.full_name} замучен.")

@dp.message(Command("ban"))
async def ban(message: types.Message):
    if not check_rank(message.from_user.id, 2):
        return await message.reply("❌ У вас нет прав (нужен ранг 2+)")
    
    if not message.reply_to_message:
        return await message.reply("⚠️ Ответьте на сообщение пользователя")

    user = message.reply_to_message.from_user
    await bot.ban_chat_member(message.chat.id, user.id)
    await message.reply(f"🔨 Пользователь {user.full_name} забанен.")

@dp.message(Command("warn"))
async def warn(message: types.Message):
    if not check_rank(message.from_user.id, 1):
        return await message.reply("❌ У вас нет прав")
    
    if not message.reply_to_message:
        return await message.reply("⚠️ Ответьте на сообщение")

    chat_id = message.chat.id
    user_id = message.reply_to_message.from_user.id
    
    warns.setdefault(chat_id, {})
    warns[chat_id][user_id] = warns[chat_id].get(user_id, 0) + 1
    
    count = warns[chat_id][user_id]
    if count >= 3:
        await bot.restrict_chat_member(chat_id, user_id, permissions=types.ChatPermissions(can_send_messages=False))
        warns[chat_id][user_id] = 0
        await message.reply(f"🚫 3/3 варна. Мут выдан.")
    else:
        await message.reply(f"⚠️ Варн выдан ({count}/3)")

# =======================
# Управление админами
# =======================
@dp.message(Command("addadmin"))
async def add_admin(message: types.Message):
    if not check_rank(message.from_user.id, 4):
        return await message.reply("❌ Только владелец может это делать")
    
    try:
        args = message.text.split()
        new_admin_id = int(args[1])
        rank = int(args[2])
        admins[new_admin_id] = rank
        await message.reply(f"✅ ID {new_admin_id} теперь админ {rank} ранга")
    except (IndexError, ValueError):
        await message.reply("Использование: `/addadmin ID ранг` (ID должен быть числом)")

@dp.message(Command("removeadmin"))
async def remove_admin(message: types.Message):
    if not check_rank(message.from_user.id, 4):
        return await message.reply("❌ Только владелец может это делать")
    
    try:
        target_id = int(message.text.split()[1])
        if target_id in admins:
            del admins[target_id]
            await message.reply(f"❌ Админ {target_id} удален")
    except:
        await message.reply("Использование: `/removeadmin ID`")

# =======================
# Базовые команды
# =======================
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("Бот запущен. Команды: /help")

@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    await message.answer(
        "🛡 Команды:\n"
        "/mute, /ban, /warn — через Reply\n"
        "/addadmin ID Rank — добавить админа\n"
        "/removeadmin ID — убрать админа"
    )

# =======================
# Запуск
# =======================
async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
