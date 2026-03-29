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
# Настройки админки
# =======================
OWNER_ID = 5679520675  # Твой Telegram ID
admins = {OWNER_ID: 4}  # user_id -> ранг (1-4)

# Варны: chat_id -> user_id -> список варнов с таймером
warns = {}

# =======================
# Конвертация времени
# =======================
TIME_UNITS = {
    "минута": 1,
    "минуты": 1,
    "минут": 1,
    "час": 60,
    "часа": 60,
    "часы": 60,
    "день": 1440,
    "дня": 1440,
    "дней": 1440,
    "неделя": 10080,
    "недели": 10080,
    "месяц": 43200,
    "год": 525600
}

def parse_time(time_str):
    try:
        parts = time_str.split()
        if len(parts) == 1:
            # число без слова, считаем минуты
            return int(parts[0])
        elif len(parts) == 2:
            num = int(parts[0])
            unit = parts[1].lower()
            return num * TIME_UNITS.get(unit, 1)
    except:
        return None
    return None

# =======================
# Проверка ранга
# =======================
def check_rank(user_id, required_rank):
    return admins.get(user_id, 0) >= required_rank

# =======================
# Наказания
# =======================
async def handle_mute(message: types.Message, time_minutes=60):
    target = await get_target_user(message)
    if not target:
        return

    until_date = datetime.utcnow() + timedelta(minutes=time_minutes)
    await bot.restrict_chat_member(
        message.chat.id,
        target.id,
        permissions=types.ChatPermissions(can_send_messages=False),
        until_date=until_date
    )
    await message.reply(f"Пользователь {target.full_name} замучен на {time_minutes} минут.\nВыдано администратором.")

async def handle_ban(message: types.Message, time_minutes=None):
    target = await get_target_user(message)
    if not target:
        return

    if time_minutes:
        until_date = datetime.utcnow() + timedelta(minutes=time_minutes)
    else:
        until_date = None

    await bot.ban_chat_member(message.chat.id, target.id, until_date=until_date)
    await message.reply(f"Пользователь {target.full_name} забанен.\nВыдано администратором.")

async def handle_warn(message: types.Message, time_minutes=1):
    target = await get_target_user(message)
    if not target:
        return

    chat_warns = warns.setdefault(message.chat.id, {})
    user_warns = chat_warns.setdefault(target.id, [])

    # Удаляем старые варны, истёкшие по времени
    now = datetime.utcnow()
    user_warns[:] = [w for w in user_warns if w > now]

    # Добавляем новый варн
    expire = now + timedelta(minutes=time_minutes)
    user_warns.append(expire)

    # Проверяем, если 3 варна в сроке
    if len(user_warns) >= 3:
        await handle_mute(message, time_minutes=30)
        chat_warns[target.id] = []
        await message.reply(f"Пользователь {target.full_name} получил 3 варна и замучен на 30 минут!")
    else:
        await message.reply(f"Пользователь {target.full_name} получил варн {len(user_warns)}/3. Действует {time_minutes} минут.")

# =======================
# Получение пользователя по reply или username
# =======================
async def get_target_user(message: types.Message):
    if not check_rank(message.from_user.id, 1):
        await message.reply("❌ У вас нет прав для использования этой команды.")
        return None

    target = None
    if message.reply_to_message:
        target = message.reply_to_message.from_user
    elif len(message.text.split()) > 1:
        username = message.text.split()[1].replace("@", "")
        try:
            member = await bot.get_chat_member(message.chat.id, username)
            target = member.user
        except:
            await message.reply("⚠️ Не удалось найти пользователя по username.")
            return None
    else:
        await message.reply("⚠️ Ответьте на сообщение пользователя или укажите @username.")
        return None
    return target

# =======================
# Команды
# =======================
@dp.message(Command("mute"))
async def cmd_mute(message: types.Message):
    minutes = 60
    if len(message.text.split()) > 2:
        minutes = parse_time(" ".join(message.text.split()[2:])) or 60
    await handle_mute(message, time_minutes=minutes)

@dp.message(Command("ban"))
async def cmd_ban(message: types.Message):
    minutes = 1440  # по умолчанию 1 день
    if len(message.text.split()) > 2:
        minutes = parse_time(" ".join(message.text.split()[2:])) or 1440
    await handle_ban(message, time_minutes=minutes)

@dp.message(Command("warn"))
async def cmd_warn(message: types.Message):
    minutes = 1
    if len(message.text.split()) > 2:
        minutes = parse_time(" ".join(message.text.split()[2:])) or 1
    await handle_warn(message, time_minutes=minutes)

@dp.message(Command("addadmin"))
async def cmd_addadmin(message: types.Message):
    if message.from_user.id != OWNER_ID:
        await message.reply("❌ Только владелец может выдавать админку.")
        return

    target = await get_target_user(message)
    if not target:
        return

    rank = int(message.text.split()[2]) if len(message.text.split()) > 2 else 1
    admins[target.id] = rank
    await message.reply(f"✅ Пользователь {target.full_name} получил админку ранг {rank}.")

@dp.message(Command("removeadmin"))
async def cmd_removeadmin(message: types.Message):
    if message.from_user.id != OWNER_ID:
        await message.reply("❌ Только владелец может снимать админку.")
        return

    target = await get_target_user(message)
    if not target:
        return

    if target.id in admins:
        del admins[target.id]
        await message.reply(f"❌ Пользователь {target.full_name} больше не админ.")

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я админ-бот Kryloxa. 👋\n"
        "Используй /help для списка команд.\n"
        "Добавь меня в группу и дай права администратора для работы наказаний."
    )

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.reply(
        "/start - приветствие\n"
        "/help - список команд\n"
        "/mute - замутить пользователя (по reply или @username) + время: /mute @user 1 день\n"
        "/ban - забанить пользователя (по reply или @username) + время: /ban @user 1 неделя\n"
        "/warn - выдать варн (по reply или @username) + время: /warn @user 1 минута\n"
        "/addadmin - выдать админку (только владелец, по reply или @username)\n"
        "/removeadmin - снять админку (только владелец, по reply или @username)"
    )

# =======================
# Запуск бота
# =======================
async def main():
    print("Админ-бот Kryloxa с таймерами запущен 🚀")
    await dp.start_polling(bot)

asyncio.run(main())
