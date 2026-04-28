# database.py
import asyncio
import logging
from datetime import datetime
import asyncpg
from typing import Optional, Dict, Any

logging.basicConfig(level=logging.INFO)

class Database:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        """Подключение к базе данных"""
        try:
            self.pool = await asyncpg.create_pool(
                self.dsn,
                min_size=2,
                max_size=10,
                command_timeout=60,
                timeout=30
            )
            logging.info("✅ Успешное подключение к PostgreSQL")
            await self.init_db()
        except Exception as e:
            logging.error(f"❌ Ошибка подключения к БД: {e}")
            raise

    async def close(self):
        """Закрытие пула соединений"""
        if self.pool:
            await self.pool.close()
            logging.info("✅ Подключение к БД закрыто")

    async def init_db(self):
        """Дополнительная инициализация (если нужно)"""
        pass

    # ==================== USERS ====================

    async def get_user(self, user_id: int) -> Dict:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE user_id = $1", user_id
            )
            return dict(row) if row else None

    async def ensure_user(self, user_id: int) -> Dict:
        """Создаёт пользователя если его нет и возвращает данные"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO users (user_id, balance, rank, warns)
                VALUES ($1, 0, 0, 0)
                ON CONFLICT (user_id) 
                DO UPDATE SET last_work = NOW()
                RETURNING *
                """, 
                user_id
            )
            return dict(row)

    async def update_balance(self, user_id: int, amount: int):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET balance = balance + $1 WHERE user_id = $2",
                amount, user_id
            )

    async def set_rank(self, user_id: int, rank: int):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET rank = $1 WHERE user_id = $2",
                rank, user_id
            )

    async def add_warn(self, user_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET warns = warns + 1 WHERE user_id = $1",
                user_id
            )

    async def reset_warns(self, user_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET warns = 0 WHERE user_id = $1",
                user_id
            )

    async def get_balance(self, user_id: int) -> int:
        async with self.pool.acquire() as conn:
            balance = await conn.fetchval(
                "SELECT balance FROM users WHERE user_id = $1", user_id
            )
            return balance or 0

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

    async def get_promo(self, code: str):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM promos WHERE code = $1", code.upper()
            )
            return dict(row) if row else None

    async def use_promo(self, code: str, user_id: int) -> bool:
        """Пытается активировать промокод"""
        async with self.pool.acquire() as conn:
            # Проверяем, использовал ли уже пользователь этот промо
            used = await conn.fetchval(
                "SELECT 1 FROM promo_uses WHERE promo_code = $1 AND user_id = $2",
                code.upper(), user_id
            )
            if used:
                return False

            promo = await self.get_promo(code)
            if not promo:
                return False

            # Добавляем запись об использовании
            await conn.execute(
                "INSERT INTO promo_uses (promo_code, user_id) VALUES ($1, $2)",
                code.upper(), user_id
            )

            # Начисляем баланс
            await self.update_balance(user_id, promo['amount'])
            return True

# ==================== ГЛОБАЛЬНЫЙ ОБЪЕКТ ====================

db = Database("postgresql://bothost_db_b8add9412f76:dJ1RwB7B9NiEeCYMsAH4ZJa40sMYk9DHdTJQNfcrL2k@node1.pghost.ru:15614/bothost_db_b8add9412f76")
