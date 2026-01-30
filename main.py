import os
import re
import asyncio
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
import aiosqlite

load_dotenv()

# ENV'dan o'qiladi (Render'da Environment Variables yoki local .env)
BOT_TOKEN = os.getenv("8252174899:AAFceWh6aWmI6-LmpuAnz7iOtty69TAw30s")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi. .env yoki Render Env Vars ga qo'ying.")

CHANNEL_ID_RAW = os.getenv("-1003762590246")
if not CHANNEL_ID_RAW:
    raise RuntimeError("CHANNEL_ID topilmadi. .env yoki Render Env Vars ga qo'ying.")
CHANNEL_ID = int(CHANNEL_ID_RAW)

# Render'da disk bo'lsa shu yo'lga berib qo'yasan. Yo'q bo'lsa oddiy fayl bo'ladi.
DB_PATH = os.getenv("DB_PATH", "movies.db")

HASHTAG_RE = re.compile(r"#(\d+)\b")

dp = Dispatcher()


def extract_code_from_text(text: str | None) -> str | None:
    if not text:
        return None
    m = HASHTAG_RE.search(text)
    return m.group(1) if m else None


def normalize_user_code(text: str) -> str | None:
    t = (text or "").strip()
    if t.startswith("#"):
        t = t[1:].strip()
    return t if t.isdigit() else None


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS movies (
                code TEXT PRIMARY KEY,
                message_id INTEGER NOT NULL
            )
        """)
        await db.commit()


async def save_code(code: str, message_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO movies(code, message_id) VALUES(?, ?) "
            "ON CONFLICT(code) DO UPDATE SET message_id=excluded.message_id",
            (code, message_id),
        )
        await db.commit()


async def get_message_id(code: str) -> int | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT message_id FROM movies WHERE code=?", (code,)) as cur:
            row = await cur.fetchone()
            return int(row[0]) if row else None


# Kanalga post tushganda (matn yoki caption ichidan #123 ni topib DB ga yozadi)
@dp.channel_post()
async def on_channel_post(message: Message, bot: Bot):
    code = extract_code_from_text(message.text) or extract_code_from_text(message.caption)
    # Diagnostika (Render logsda ko'rasan)
    print("CHANNEL_POST:", "code=", code, "msg_id=", message.message_id)

    if not code:
        return
    await save_code(code, message.message_id)


# Kanal posti edit qilinsa ham DB yangilanadi
@dp.edited_channel_post()
async def on_edited_channel_post(message: Message, bot: Bot):
    code = extract_code_from_text(message.text) or extract_code_from_text(message.caption)
    print("EDITED_CHANNEL_POST:", "code=", code, "msg_id=", message.message_id)

    if not code:
        return
    await save_code(code, message.message_id)


# User private chatda raqam yuborsa, kanal postini copy qiladi
@dp.message(F.chat.type == "private")
async def on_user_message(message: Message, bot: Bot):
    code = normalize_user_code(message.text)
    if not code:
        await message.answer("Raqam yuboring. Masalan: 1 yoki #1")
        return

    # Kechikish bo'lsa deb 3 marta tekshiradi (0s, 1s, 2s)
    mid = None
    for delay in (0, 1, 2):
        if delay:
            await asyncio.sleep(delay)
        mid = await get_message_id(code)
        if mid:
            break

    if not mid:
        await message.answer(
            f"#{code} topilmadi.\n"
            "✅ Tekshir:\n"
            "1) Kanal postida aynan #"
            f"{code} yozilganmi?\n"
            "2) Bot kanalda ADMINmi?\n"
            "3) Postni 1 marta EDIT qilib ko'r (nuqta qo'shib/o'chirib)."
        )
        return

    try:
        await bot.copy_message(
            chat_id=message.chat.id,
            from_chat_id=CHANNEL_ID,
            message_id=mid,
        )
    except Exception as e:
        # Asl xato ko'rinsin (keyin tuzatish oson bo'ladi)
        await message.answer(f"Xato: {type(e).__name__}\n{e}\n\n"
                             "Tekshir: bot kanalda adminmi va huquqlari bormi?")


async def main():
    await init_db()
    async with Bot(token=BOT_TOKEN) as bot:
        print("Bot started. DB_PATH =", DB_PATH, "CHANNEL_ID =", CHANNEL_ID)
        await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
