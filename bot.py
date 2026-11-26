import asyncio
import logging
import random
from datetime import datetime, timedelta, date
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import aiosqlite

# ====== НАСТРОЙКИ ======
BOT_TOKEN = "9165100041:AAEd8SKZsW0Xd6iWlRcG-DyZzjnRzmnGZEw"
DB_PATH = "planner.db"
REMINDER_HOUR = 19
REMINDER_MINUTE = 30
CYCLE_DAYS = 7

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

# ====== СПИСОК МИКРО-ПРИВЫЧЕК ======
HABITS = [
    {
        "name": "Стакан воды утром",
        "text": "Выпей стакан воды сразу после пробуждения.",
        "unit": "стаканов воды",
        "result": "стакан воды утром",
    },
    {
        "name": "Прогулка 10 минут",
        "text": "Выйди на 10 минут прогулки — без цели, просто пройтись.",
        "unit": "прогулок",
        "result": "10-минутная прогулка",
    },
    {
        "name": "Один приём пищи без телефона",
        "text": "Съешь один приём пищи без телефона и экрана.",
        "unit": "приёмов пищи без телефона",
        "result": "приём пищи без телефона",
    },
    {
        "name": "Записать, что съел",
        "text": "Запиши, что ты съел за день. Без оценок и критики.",
        "unit": "дней с записями",
        "result": "запись того, что съел",
    },
    {
        "name": "Порция овощей",
        "text": "Съешь одну порцию овощей — любых, в любом виде.",
        "unit": "порций овощей",
        "result": "порция овощей",
    },
]

# ====== ЦИТАТЫ ======
QUOTES = [
    "«Путь в тысячу ли начинается с одного шага». — Лао-цзы",
    "«Вода камень точит». — китайская пословица",
    "«Не важно, как медленно ты идёшь, главное — не останавливаешься». — Конфуций",
    "«Тысяча вдохов — один шаг». — дзенская поговорка",
    "«Совершенство — не в действии, а в привычке». — Аристотель",
    "«Маленькие дела делаются малыми шагами». — восточная мудрость",
]

PRAISE = [
    "✅ Записано. Ты молодец. Маленький шаг — это тоже шаг.",
    "✅ Есть! Сегодня ты сделал это для себя.",
    "✅ Отлично. Так держать — без надрыва, но регулярно.",
    "✅ Готово. Один шаг сегодня — это уже движение.",
]

# ====== БАЗА ДАННЫХ ======
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                start_date TEXT,
                habit_index INTEGER DEFAULT 0,
                last_quote_date TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS checkins (
                user_id INTEGER,
                date TEXT,
                habit_index INTEGER,
                PRIMARY KEY (user_id, date)
            )
        """)
        await db.commit()

async def add_user(user_id, username):
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username, start_date) VALUES (?, ?, ?)",
            (user_id, username, today)
        )
        await db.commit()

async def get_user(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT user_id, start_date, habit_index, last_quote_date FROM users WHERE user_id = ?",
            (user_id,)
        )
        return await cursor.fetchone()

async def mark_done(user_id):
    today = date.today().isoformat()
    user = await get_user(user_id)
    if not user:
        return False, None
    habit_index = user[2]
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM checkins WHERE user_id = ? AND date = ?",
            (user_id, today)
        )
        if await cursor.fetchone():
            return False, "already"
        await db.execute(
            "INSERT INTO checkins (user_id, date, habit_index) VALUES (?, ?, ?)",
            (user_id, today, habit_index)
        )
        await db.commit()
    return True, "ok"

async def get_week_stats(user_id, habit_index):
    user = await get_user(user_id)
    if not user:
        return 0
    start = datetime.fromisoformat(user[1]).date()
    # текущая неделя цикла
    days_passed = (date.today() - start).days
    cycle_start = start + timedelta(days=(days_passed // CYCLE_DAYS) * CYCLE_DAYS)
    cycle_end = cycle_start + timedelta(days=CYCLE_DAYS - 1)
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM checkins WHERE user_id = ? AND habit_index = ? AND date >= ? AND date <= ?",
            (user_id, habit_index, cycle_start.isoformat(), cycle_end.isoformat())
        )
        row = await cursor.fetchone()
        return row[0] if row else 0

async def get_streak(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT date FROM checkins WHERE user_id = ? ORDER BY date DESC",
            (user_id,)
        )
        rows = await cursor.fetchall()
    if not rows:
        return 0
    dates = [datetime.fromisoformat(r[0]).date() for r in rows]
    streak = 0
    check = date.today()
    for d in dates:
        if d == check:
            streak += 1
            check -= timedelta(days=1)
        elif d < check:
            break
    return streak

async def get_all_users():
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT user_id FROM users")
        rows = await cursor.fetchall()
        return [r[0] for r in rows]

async def update_habit_index(user_id, new_index):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET habit_index = ? WHERE user_id = ?",
            (new_index, user_id)
        )
        await db.commit()

async def get_quote_for_today(user_id):
    today = date.today().isoformat()
    user = await get_user(user_id)
    if not user:
        return None
    if user[3] == today:
        return None  # уже была цитата сегодня
    quote = random.choice(QUOTES)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET last_quote_date = ? WHERE user_id = ?",
            (today, user_id)
        )
        await db.commit()
    return quote

# ====== РАССЫЛКА ======
async def send_daily_reminder():
    users = await get_all_users()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Сделано", callback_data="done_today")]
    ])
    for uid in users:
        user = await get_user(uid)
        if not user:
            continue
        habit_index = user[2] % len(HABITS)
        habit = HABITS[habit_index]
        try:
            await bot.send_message(
                uid,
                f"🌙 Напоминание на сегодня:\n\n"
                f"*{habit['name']}*\n"
                f"{habit['text']}\n\n"
                f"Когда сделаешь — нажми кнопку ниже.",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        except Exception:
            pass

async def send_weekly_summary():
    """Проверяем, у кого сегодня заканчивается 7-дневный цикл, и шлём итог."""
    users = await get_all_users()
    today = date.today()
    for uid in users:
        user = await get_user(uid)
        if not user:
            continue
        start = datetime.fromisoformat(user[1]).date()
        days_passed = (today - start).days
        # день 7, 14, 21... (индекс 6, 13, 20...)
        if days_passed > 0 and (days_passed + 1) % CYCLE_DAYS == 0:
            habit_index = user[2] % len(HABITS)
            habit = HABITS[habit_index]
            count = await get_week_stats(uid, habit_index)
            next_index = (habit_index + 1) % len(HABITS)
            next_habit = HABITS[next_index]
            quote = random.choice(QUOTES)
            text = (
                f"🎉 *Итог недели*\n\n"
                f"Ты отметился *{count} из {CYCLE_DAYS}* дней.\n"
                f"Это *{count} {habit['unit']}* — маленькое действие, которое ты сделал для себя.\n\n"
                f"Без надрыва, но регулярно. Так и формируется привычка.\n\n"
                f"_{quote}_\n\n"
                f"Завтра начинаем новую микро-привычку:\n"
                f"*{next_habit['name']}* — {next_habit['text']}\n\n"
                f"Не важно, какой завтра день. Главное — продолжить."
            )
            try:
                await bot.send_message(uid, text, parse_mode="Markdown")
            except Exception:
                pass
            await update_habit_index(uid, user[2] + 1)

# ====== ХЕНДЛЕРЫ ======
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await add_user(message.from_user.id, message.from_user.username)
    user = await get_user(message.from_user.id)
    habit_index = user[2] % len(HABITS) if user else 0
    habit = HABITS[habit_index]
    await message.answer(
        "Привет! Я твой планировщик маленьких шагов.\n\n"
        "Ты начал *сегодня*. Не важно, какой это день недели — важно, что ты начал.\n\n"
        f"Первая микро-привычка:\n*{habit['name']}*\n{habit['text']}\n\n"
        f"Каждый день в 19:30 я буду напоминать. Когда сделаешь — нажми кнопку.\n\n"
        "Команды:\n"
        "/week — твоя серия и результат\n"
        "/done — отметить, что сделал сегодня\n"
        "/start — это сообщение",
        parse_mode="Markdown"
    )

@dp.message(Command("week"))
async def cmd_week(message: types.Message):
    user = await get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала нажми /start.")
        return
    habit_index = user[2] % len(HABITS)
    habit = HABITS[habit_index]
    count = await get_week_stats(message.from_user.id, habit_index)
    streak = await get_streak(message.from_user.id)
    await message.answer(
        f"📊 *Твоя неделя*\n\n"
        f"Текущая привычка: *{habit['name']}*\n"
        f"Отметок за цикл: *{count} из {CYCLE_DAYS}*\n"
        f"Серия подряд: *{streak}* дн.\n\n"
        f"{'🔥 Отлично, продолжай!' if count >= 5 else 'Ничего страшного. Главное — не бросать.'}",
        parse_mode="Markdown"
    )

@dp.message(Command("done"))
async def cmd_done(message: types.Message):
    ok, status = await mark_done(message.from_user.id)
    if not ok and status == "already":
        await message.answer("Ты уже отметился сегодня. Молодец — но давай не спешить. Завтра продолжим.")
        return
    if not ok:
        await message.answer("Сначала нажми /start.")
        return
    praise = random.choice(PRAISE)
    quote = await get_quote_for_today(message.from_user.id)
    text = praise
    if quote:
        text += f"\n\n_{quote}_"
    await message.answer(text, parse_mode="Markdown")

@dp.callback_query(lambda c: c.data == "done_today")
async def callback_done(callback: types.CallbackQuery):
    ok, status = await mark_done(callback.from_user.id)
    if not ok and status == "already":
        await callback.answer("Ты уже отметился сегодня. Молодец!", show_alert=False)
        return
    if not ok:
        await callback.answer("Сначала нажми /start.", show_alert=True)
        return
    praise = random.choice(PRAISE)
    quote = await get_quote_for_today(callback.from_user.id)
    text = praise
    if quote:
        text += f"\n\n_{quote}_"
    await callback.message.edit_text(text, parse_mode="Markdown")
    await callback.answer()

# ====== ЗАПУСК ======
async def main():
    await init_db()
    scheduler.add_job(send_daily_reminder, "cron", hour=REMINDER_HOUR, minute=REMINDER_MINUTE)
    scheduler.add_job(send_weekly_summary, "cron", hour=20, minute=0)
    scheduler.start()
    logging.info("Бот запущен, планировщик работает")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
