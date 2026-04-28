# database.py
import logging
from typing import Optional, Dict

import asyncpg

logging.basicConfig(level=logging.INFO)

class Database:
    def __init__(self):
        self.dsn = "postgresql://bothost_db_b8add9412f76:90908060@node1.pghost.ru:15614/bothost_db_b8add9412f76"
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        try:
            self.pool = await asyncpg.create_pool(
                self.dsn,
                min_size=2,
                max_size=10,
                timeout=60,
                command_timeout=60
            )
            logging.info("✅ Успешное подключение к PostgreSQL")
            await self.init_db()
        except Exception as e:
            logging.error(f"❌ Ошибка подключения к БД: {e}")
            raise

    async def close(self):
        if self.pool:
            await self.pool.close()
            logging.info("✅ Подключение к БД закрыто")

    async def init_db(self):
        """Создание всех необходимых таблиц"""
        async with self.pool.acquire() as conn:
            # Таблица пользователей
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    balance INTEGER DEFAULT 100,
                    rank INTEGER DEFAULT 0,
                    warns INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)

            # Таблица промокодов
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS promos (
                    code VARCHAR(50) PRIMARY KEY,
                    amount INTEGER NOT NULL,
                    max_uses INTEGER DEFAULT 1,
                    used_count INTEGER DEFAULT 0,
                    expires_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)

            # Таблица использованных промокодов
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS promo_uses (
                    id SERIAL PRIMARY KEY,
                    promo_code VARCHAR(50) REFERENCES promos(code) ON DELETE CASCADE,
                    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
                    used_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(promo_code, user_id)
                )
            """)

            # Создаём тестовые промокоды (если их нет)
            await conn.execute("""
                INSERT INTO promos (code, amount, max_uses) VALUES
                ('START100', 100, 999),
                ('WELCOME', 50, 999),
                ('BONUS200', 200, 999)
                ON CONFLICT (code) DO NOTHING
            """)

            # Создаём владельца бота
            await conn.execute("""
                INSERT INTO users (user_id, balance, rank, warns)
                VALUES (5679520675, 999999, 4, 0)
                ON CONFLICT (user_id) DO UPDATE 
                SET rank = 4, balance = 999999
            """)

            logging.info("✅ Таблицы БД созданы/проверены")

    # ==================== USERS ====================
    async def ensure_user(self, user_id: int):
        """Гарантирует наличие пользователя в БД"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO users (user_id, balance, rank, warns)
                VALUES ($1, 100, 0, 0)
                ON CONFLICT (user_id) DO NOTHING
                """,
                user_id
            )

    async def get_balance(self, user_id: int) -> int:
        """Получить баланс пользователя"""
        async with self.pool.acquire() as conn:
            balance = await conn.fetchval(
                "SELECT balance FROM users WHERE user_id = $1", user_id
            )
            return balance or 0

    async def update_balance(self, user_id: int, amount: int) -> int:
        """Обновить баланс (может быть отрицательным для списания)"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow(
                "UPDATE users SET balance = balance + $1 WHERE user_id = $2 RETURNING balance",
                amount, user_id
            )
            return result['balance'] if result else 0

    async def set_balance(self, user_id: int, amount: int):
        """Установить точный баланс"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET balance = $1 WHERE user_id = $2",
                amount, user_id
            )

    async def get_rank(self, user_id: int) -> int:
        """Получить ранг пользователя"""
        async with self.pool.acquire() as conn:
            rank = await conn.fetchval(
                "SELECT rank FROM users WHERE user_id = $1", user_id
            )
            return rank or 0

    async def set_rank(self, user_id: int, rank: int):
        """Установить ранг"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET rank = $1 WHERE user_id = $2",
                rank, user_id
            )

    async def get_warns(self, user_id: int) -> int:
        """Получить количество варнов"""
        async with self.pool.acquire() as conn:
            warns = await conn.fetchval(
                "SELECT warns FROM users WHERE user_id = $1", user_id
            )
            return warns or 0

    async def update_warns(self, user_id: int, delta: int) -> int:
        """Обновить количество варнов (положительное или отрицательное число)"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow(
                "UPDATE users SET warns = warns + $1 WHERE user_id = $2 RETURNING warns",
                delta, user_id
            )
            new_warns = result['warns'] if result else 0
            # Если варны стали отрицательными, сбрасываем на 0
            if new_warns < 0:
                await conn.execute(
                    "UPDATE users SET warns = 0 WHERE user_id = $1",
                    user_id
                )
                return 0
            return new_warns

    async def reset_warns(self, user_id: int):
        """Сбросить варны в 0"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET warns = 0 WHERE user_id = $1",
                user_id
            )

    # ==================== PROMOS ====================
    async def use_promo(self, code: str, user_id: int) -> bool:
        """Активировать промокод"""
        code = code.upper()
        async with self.pool.acquire() as conn:
            # Проверяем, использовал ли уже пользователь этот промокод
            used = await conn.fetchval(
                "SELECT 1 FROM promo_uses WHERE promo_code = $1 AND user_id = $2",
                code, user_id
            )
            if used:
                return False

            # Получаем информацию о промокоде
            promo = await conn.fetchrow(
                "SELECT amount, max_uses, used_count FROM promos WHERE code = $1",
                code
            )
            if not promo:
                return False

            # Проверяем лимит использований
            if promo['used_count'] >= promo['max_uses']:
                return False

            # Добавляем использование
            await conn.execute(
                "INSERT INTO promo_uses (promo_code, user_id) VALUES ($1, $2)",
                code, user_id
            )

            # Обновляем счётчик использований промокода
            await conn.execute(
                "UPDATE promos SET used_count = used_count + 1 WHERE code = $1",
                code
            )

            # Начисляем баланс
            await self.update_balance(user_id, promo['amount'])
            return True

    async def get_promo_amount(self, code: str) -> int:
        """Получить сумму промокода"""
        async with self.pool.acquire() as conn:
            amount = await conn.fetchval(
                "SELECT amount FROM promos WHERE code = $1", code.upper()
            )
            return amount or 0

    async def create_promo(self, code: str, amount: int, max_uses: int = 1) -> bool:
        """Создать новый промокод"""
        code = code.upper()
        async with self.pool.acquire() as conn:
            try:
                await conn.execute(
                    """
                    INSERT INTO promos (code, amount, max_uses, used_count)
                    VALUES ($1, $2, $3, 0)
                    """,
                    code, amount, max_uses
                )
                return True
            except Exception:
                return False

    # ==================== ADMIN ====================
    async def get_all_users(self, limit: int = 100) -> list:
        """Получить список пользователей (для админа)"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT user_id, balance, rank, warns 
                FROM users 
                ORDER BY balance DESC 
                LIMIT $1
                """,
                limit
            )
            return [dict(row) for row in rows]

    async def get_top_balance(self, limit: int = 10) -> list:
        """Топ по балансу"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT user_id, balance 
                FROM users 
                ORDER BY balance DESC 
                LIMIT $1
                """,
                limit
            )
            return [dict(row) for row in rows]

# Глобальный объект
db = Database()
