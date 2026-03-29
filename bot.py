from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from dotenv import load_dotenv
import os
import asyncio
from datetime import datetime, timedelta

# =======================
# Загрузка токена
# =======================
load_dotenv()
TOKEN = os.getenv("TOKEN")

bot = Bot(TOKEN)
dp = Dispatcher()

# =======================
# Настройки
# =======================
OWNER_ID = 5679520675
admins = {OWNER_ID: 4}
warns = {}

# =======================
# Проверка ранга
# =======================
def check_rank(user_id, required_rank):
    return admins.get(user_id, 0) >= required_rank

# =======================
# Парсинг времени
# =======================
def parse_time(parts):
    try:
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
# Получение пользователя
# =======================
async def get_target(message, parts):
    if message.reply_to_message:
        return message.reply_to_message.from_user

    if len(parts) >= 2:
        username = parts[1].replace("@", "")
        try:
            member = await bot.get_chat_member(message.chat.id, username)
            return member.user
        except:
            return None

    return None

# =======================
# МУТ
# =======================
@dp.message(Command("mute"))
async def cmd_mute(message: types.Message):
    if not check_rank(message.from_user.id, 1):
        await message.reply("❌ Нет прав.")
        return

    parts = message.text.split()
    target = await get_target(message, parts)

    if not target:
        await message.reply("⚠️ Ответь на сообщение пользователя.")
        return

    # время
    time_parts = parts[2:] if not message.reply_to_message else parts[1:]
    minutes = parse_time(time_parts) or 60

    until_date = datetime.utcnow() + timedelta(minutes=minutes)

    await bot.restrict_chat_member(
        message.chat.id,
        target.id,
        permissions=types.ChatPermissions(can_send_messages=False),
        until_date=until_date
    )

    await message.reply(f"🔇 {target.full_name} замучен на {minutes} минут.")

# =======================
# БАН
# =======================
@dp.message(Command("ban"))
async def cmd_ban(message: types.Message):
    if not check_rank(message.from_user.id, 1):
        await message.reply("❌ Нет прав.")
        return

    parts = message.text.split()
    target = await get_target(message, parts)

    if not target:
        await message.reply("⚠️ Ответь на сообщение пользователя.")
        return

    time_parts = parts[2:] if not message.reply_to_message else parts[1:]
    minutes = parse_time(time_parts)

    until_date = datetime.utcnow() + timedelta(minutes=minutes) if minutes else None

    await bot.ban_chat_member(message.chat.id, target.id, until_date=until_date)

    await message.reply(f"🚫 {target.full_name} забанен.")

# =======================
# ВАРН
# =======================
@dp.message(Command("warn"))
async def cmd_warn(message: types.Message):
    if not check_rank(message.from_user.id, 1):
        await message.reply("❌ Нет прав.")
        return

    parts = message.text.split()
    target = await get_target(message, parts)

    if not target:
        await message.reply("⚠️ Ответь на сообщение пользователя.")
        return

    time_parts = parts[2:] if not message.reply_to_message else parts[1:]
    minutes = parse_time(time_parts) or 1

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

        await message.reply(f"⚠️ {target.full_name} получил 3 варна → мут 30 минут!")
    else:
        await message.reply(f"⚠️ {target.full_name} варн {len(user_warns)}/3 ({minutes} мин).")

# =======================
# АДМИНЫ
# =======================
@dp.message(Command("addadmin"))
async def cmd_addadmin(message: types.Message):
    if message.from_user.id != OWNER_ID:
        await message.reply("❌ Только владелец.")
        return

    parts = message.text.split()
    target = await get_target(message, parts)

    if not target:
        await message.reply("⚠️ Ответь на сообщение.")
        return

    rank = int(parts[2]) if len(parts) > 2 else 1
    admins[target.id] = rank

    await message.reply(f"✅ {target.full_name} теперь админ {rank}.")

@dp.message(Command("removeadmin"))
async def cmd_removeadmin(message: types.Message):
    if message.from_user.id != OWNER_ID:
        await message.reply("❌ Только владелец.")
        return

    parts = message.text.split()
    target = await get_target(message, parts)

    if target and target.id in admins:
        del admins[target.id]
        await message.reply(f"❌ {target.full_name} больше не админ.")

# =======================
# СТАРТ / ХЕЛП
# =======================
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("Привет! Я Kryloxa бот 🤖")

@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    await message.reply(
        "/mute - мут (ответ или @user + время)\n"
        "/ban - бан\n"
        "/warn - варн (3 = мут)\n"
        "/addadmin - выдать админку\n"
        "/removeadmin - снять админку"
    )

# =======================
# ЗАПУСК
# =======================
async def main():
    print("Бот запущен 🚀")
    await dp.start_polling(bot)

asyncio.run(main())
