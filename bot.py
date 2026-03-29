import os
import asyncio
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TOKEN")

bot = Bot(TOKEN)
dp = Dispatcher()

# Настройки
OWNER_ID = 123456789 # Твой ID
admins = {OWNER_ID: 4}
warns = {}

def check_rank(user_id, required_rank):
    return admins.get(user_id, 0) >= required_rank

# Универсальный мут
async def mute_user(chat_id, user_id, minutes):
    until_date = datetime.now() + timedelta(minutes=minutes)
    await bot.restrict_chat_member(
        chat_id,
        user_id,
        permissions=types.ChatPermissions(can_send_messages=False),
        until_date=until_date
    )

@dp.message(Command("mute"))
async def mute(message: types.Message):
    if not check_rank(message.from_user.id, 1): return
    if not message.reply_to_message:
        return await message.reply("⚠️ Ответьте на сообщение пользователя")

    # Пробуем достать время из команды /mute 10
    args = message.text.split()
    minutes = int(args[1]) if len(args) > 1 and args[1].isdigit() else 60
    
    user = message.reply_to_message.from_user
    await mute_user(message.chat.id, user.id, minutes)
    await message.reply(f"🔇 {user.full_name} замучен на {minutes} мин.")

@dp.message(Command("ban"))
async def ban(message: types.Message):
    if not check_rank(message.from_user.id, 2): return
    if not message.reply_to_message: return

    user = message.reply_to_message.from_user
    await bot.ban_chat_member(message.chat.id, user.id)
    await message.reply(f"✈️ {user.full_name} забанен.")

@dp.message(Command("warn"))
async def warn(message: types.Message):
    if not check_rank(message.from_user.id, 1): return
    if not message.reply_to_message: return

    chat_id = message.chat.id
    user = message.reply_to_message.from_user
    user_id = user.id

    warns.setdefault(chat_id, {}).setdefault(user_id, 0)
    warns[chat_id][user_id] += 1
    
    count = warns[chat_id][user_id]
    if count >= 3:
        await mute_user(chat_id, user_id, 30)
        warns[chat_id][user_id] = 0
        await message.reply(f"🚫 {user.full_name} получил 3-й варн и мут на 30 мин.")
    else:
        await message.reply(f"⚠️ {user.full_name} получил варн ({count}/3)")

@dp.message(Command("unmute"))
async def unmute(message: types.Message):
    if not check_rank(message.from_user.id, 1): return
    if not message.reply_to_message: return
    
    await bot.restrict_chat_member(
        message.chat.id,
        message.reply_to_message.from_user.id,
        permissions=types.ChatPermissions(
            can_send_messages=True, 
            can_send_other_messages=True,
            can_send_polls=True,
            can_send_photos=True,
            can_send_videos=True,
            can_send_audios=True,
            can_send_documents=True
        )
    )
    await message.reply("🔊 Ограничения сняты.")

# Запуск
async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
