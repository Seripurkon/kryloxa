import os
from telegram.ext import ApplicationBuilder

# ВСТАВЬ СВОЙ ТОКЕН СЮДА В КАВЫЧКИ ДЛЯ ТЕСТА
TOKEN = "8641381095:AAGLY3W93LQGfq_Ygm1OIfAMwlhb6SlQrXE" 

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    print("🚀 Бот запустился напрямую!")
    app.run_polling()
