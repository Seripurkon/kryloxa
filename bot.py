import asyncio
import os
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
import datetime
from dotenv import load_dotenv

# Загружаем токен из .env
load_dotenv()
TOKEN = os.getenv("TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()

users = {}
daily_claim = {}

# Клавиатура
keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="💰 Баланс")],
        [KeyboardButton(text="🗓 Ежедневная награда"), KeyboardButton(text="💼 Работа")],
    ],
    resize_keyboard=True
)

@dp.message(Command("start"))
async def start(message: types.Message):
    if message.from_user.id not in users:
        users[message.from_user.id] = 100
    await message.answer(
        "👋 Добро пожаловать в Kryloxa!\nТебе выдано 100 монет!",
        reply_markup=keyboard
    )

@dp.message()
async def buttons(message: types.Message):
    user_id = message.from_user.id

    if message.text == "💰 Баланс":
        money = users.get(user_id, 0)
        await message.answer(f"💰 У тебя: {money} монет")
    elif message.text == "🗓 Ежедневная награда":
        today = datetime.date.today()
        last_claim = daily_claim.get(user_id)

        if last_claim == today:
            await message.answer("⏳ Ты уже забрал награду сегодня!")
        else:
            users[user_id] = users.get(user_id, 0) + 50
            daily_claim[user_id] = today
            await message.answer("🎉 Ты забрал ежедневную награду — 50 монет!")
    elif message.text == "💼 Работа":
        users[user_id] = users.get(user_id, 0) + 30
        await message.answer("💼 Ты поработал и заработал 30 монет!")
    else:
        await message.answer("❌ Неизвестная команда")

async def main():
    print("Бот Kryloxa запущен 🚀")
    await dp.start_polling(bot)

asyncio.run(main())
