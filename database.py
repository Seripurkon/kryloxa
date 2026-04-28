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
        pass

    # ==================== USERS ====================
    async def ensure_user(self, user_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO users (user_id, balance, rank, warns)
                VALUES ($1, 0, 0, 0)
                ON CONFLICT (user_id) DO NOTHING
                """,
                user_id
            )

    async def get_balance(self, user_id: int) -> int:
        async with self.pool.acquire() as conn:
            balance = await conn.fetchval(
                "SELECT balance FROM users WHERE user_id = $1", user_id
            )
            return balance or 0

    async def update_balance(self, user_id: int, amount: int):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET balance = balance + $1 WHERE user_id = $2",
                amount, user_id
            )

    async def get_rank(self, user_id: int) -> int:
        async with self.pool.acquire() as conn:
            rank = await conn.fetchval(
                "SELECT rank FROM users WHERE user_id = $1", user_id
            )
            return rank or 0

    async def get_warns(self, user_id: int) -> int:
        async with self.pool.acquire() as conn:
            warns = await conn.fetchval(
                "SELECT warns FROM users WHERE user_id = $1", user_id
            )
            return warns or 0

    # ==================== PROMOS ====================
    async def use_promo(self, code: str, user_id: int) -> bool:
        code = code.upper()
        async with self.pool.acquire() as conn:
            # Проверяем, использовал ли уже
            used = await conn.fetchval(
                "SELECT 1 FROM promo_uses WHERE promo_code = $1 AND user_id = $2",
                code, user_id
            )
            if used:
                return False

            promo = await conn.fetchrow(
                "SELECT amount FROM promos WHERE code = $1", code
            )
            if not promo:
                return False

            # Добавляем использование
            await conn.execute(
                "INSERT INTO promo_uses (promo_code, user_id) VALUES ($1, $2)",
                code, user_id
            )

            # Начисляем баланс
            await self.update_balance(user_id, promo['amount'])
            return True


# Глобальный объект
db = Database()
