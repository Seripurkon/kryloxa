from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from dotenv import load_dotenv
import os
import asyncio
from datetime import datetime, timedelta

load_dotenv()
TOKEN = os.getenv("TOKEN")

bot = Bot(TOKEN)
dp = Dispatcher()

OWNER_ID = 5679520675
admins = {OWNER_ID: 4}
warns = {}

# =======================
# Проверка админа
# =======================
def is_admin(user_id):
    return admins.get(user_id, 0) > 0

# =======================
# Парсинг времени
# =======================
def parse_time(parts):
    try:
        if len(parts) == 0:
            return None

        if len(parts) == 1:
            return int(parts[0])

        num = int(parts[0])
        unit = parts[1].lower()

        if "мин" in unit:
            return num
        elif "час" in unit:
            return num * 60
        elif "день" in unit:
            return num * 1440
        elif "недел" in unit:
            return num * 10080
        elif "месяц" in unit:
            return num * 43200
        elif "год" in unit:
            return num * 525600
    except:
        return None

    return None

# =======================
# START / HELP
# =======================
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("Привет! Я Kryloxa бот 🤖")

@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    await message.reply(
        "Команды:\n"
        "мут 1 минута\n"
        "бан 1 день\n"
        "варн 1 минута\n\n"
        "Используй ответом на сообщение!"
    )

# =======================
# ОСНОВНЫЕ КОМАНДЫ
# =======================
@dp.message()
async def text_commands(message: types.Message):
    text = message.text.lower()
    parts = text.split()

    # ===== МУТ =====
    if parts[0] == "мут":
        if not is_admin(message.from_user.id):
            return

        if not message.reply_to_message:
            await message.reply("⚠️ Ответь на сообщение.")
            return

        target = message.reply_to_message.from_user

        minutes = parse_time(parts[1:]) or 60

        until_date = datetime.utcnow() + timedelta(minutes=minutes)

        await bot.restrict_chat_member(
            message.chat.id,
            target.id,
            permissions=types.ChatPermissions(can_send_messages=False),
            until_date=until_date
        )

        await message.reply(
            f"🔇 {target.full_name} замучен на {minutes} минут."
        )

    # ===== БАН =====
    elif parts[0] == "бан":
        if not is_admin(message.from_user.id):
            return

        if not message.reply_to_message:
            await message.reply("⚠️ Ответь на сообщение.")
            return

        target = message.reply_to_message.from_user

        minutes = parse_time(parts[1:])

        until_date = datetime.utcnow() + timedelta(minutes=minutes) if minutes else None

        await bot.ban_chat_member(message.chat.id, target.id, until_date=until_date)

        await message.reply(
            f"🚫 {target.full_name} заблокирован."
        )

    # ===== ВАРН =====
    elif parts[0] == "варн":
        if not is_admin(message.from_user.id):
            return

        if not message.reply_to_message:
            await message.reply("⚠️ Ответь на сообщение.")
            return

        target = message.reply_to_message.from_user

        minutes = parse_time(parts[1:]) or 1

        chat_warns = warns.setdefault(message.chat.id, {})
        user_warns = chat_warns.setdefault(target.id, [])

        now = datetime.utcnow()
        user_warns[:] = [w for w in user_warns if w > now]

        expire = now + timedelta(minutes=minutes)
        user_warns.append(expire)

        if len(user_warns) >= 3:
            mute_until = datetime.utcnow() + timedelta(minutes=30)

            await bot.restrict_chat_member(
                message.chat.id,
                target.id,
                permissions=types.ChatPermissions(can_send_messages=False),
                until_date=mute_until
            )

            chat_warns[target.id] = []

            await message.reply(
                f"⚠️ {target.full_name} получил 3 варна → мут 30 минут!"
            )
        else:
            await message.reply(
                f"⚠️ {target.full_name} получает предупреждение {len(user_warns)}/3."
            )

# =======================
# ЗАПУСК
# =======================
async def main():
    print("Бот запущен 🚀")
    await dp.start_polling(bot)

asyncio.run(main())
