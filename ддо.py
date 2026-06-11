import asyncio
import logging
import os
import random
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).with_name(".env"))
except Exception:
    pass

# === НАСТРОЙКИ ===
BOT_TOKEN = os.getenv("BOT_TOKEN", "8868403309:AAG_pQP6eRMXvA3CAP3vDuVL3r9DK6f4IPY")
PROMO_CODE = "УМАР КРУТОЙ ЗУР"
PROMO_BONUS_PCT = 50  # +50% к сумме выигрыша
DB_PATH = str(Path(__file__).with_name("giveaways.db"))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("giveaway-bot")
router = Router()


# === БАЗА ДАННЫХ ===
def db_init():
    with sqlite3.connect(DB_PATH) as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS giveaways (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL, chat_id INTEGER NOT NULL,
            chat_title TEXT, message_id INTEGER,
            prize_text TEXT NOT NULL, prize_amount REAL NOT NULL,
            winners_count INTEGER NOT NULL, max_participants INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            giveaway_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            username TEXT, full_name TEXT,
            promo_applied INTEGER NOT NULL DEFAULT 0, joined_at TEXT NOT NULL,
            UNIQUE (giveaway_id, user_id));
        CREATE TABLE IF NOT EXISTS winners (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            giveaway_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            won_amount REAL NOT NULL);""")


def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def now_iso():
    return datetime.now(timezone.utc).isoformat()


class CreateGA(StatesGroup):
    chat = State()
    prize_text = State()
    prize_amount = State()
    winners_count = State()
    max_participants = State()
    confirm = State()


class JoinGA(StatesGroup):
    promo = State()


def fmt_amount(a):
    return str(int(a)) if a == int(a) else f"{a:.2f}"


def main_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Создать конкурс", callback_data="ga:new")],
        [InlineKeyboardButton(text="📋 Мои конкурсы", callback_data="ga:list")],
    ])


def cancel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✖️ Отмена", callback_data="ga:cancel")]])


def join_button(bot_username, ga_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎉 Участвовать",
                              url=f"https://t.me/{bot_username}?start=g_{ga_id}")]])


def promo_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ У меня есть промокод", callback_data="join:promo_yes")],
        [InlineKeyboardButton(text="🚀 Участвовать без промокода", callback_data="join:promo_no")],
    ])


@router.message(CommandStart(deep_link=True))
async def start_deeplink(message, command, state, bot):
    payload = (command.args or "").strip()
    if not payload.startswith("g_"):
        return await start_plain(message, state)
    try:
        ga_id = int(payload[2:])
    except ValueError:
        return await start_plain(message, state)

    await state.clear()
    with db() as con:
        ga = con.execute("SELECT * FROM giveaways WHERE id = ?", (ga_id,)).fetchone()
    if not ga:
        return await message.answer("⚠️ Такого конкурса не существует.")
    if ga["status"] != "active":
        return await message.answer("⏳ Этот конкурс уже завершён.")

    with db() as con:
        already = con.execute(
            "SELECT 1 FROM participants WHERE giveaway_id = ? AND user_id = ?",
            (ga_id, message.from_user.id)).fetchone()
    if already:
        return await message.answer("✅ Ты уже участвуешь в этом конкурсе. Удачи!")

    await state.update_data(joining_ga_id=ga_id)
    await message.answer(
        f"🎁 <b>Конкурс</b>\nПриз: <b>{ga['prize_text']}</b>\n"
        f"Сумма выигрыша: <b>{fmt_amount(ga['prize_amount'])}</b>\n"
        f"Победителей: <b>{ga['winners_count']}</b>\n\n"
        f"Хочешь применить промокод? Он даёт <b>+{PROMO_BONUS_PCT}%</b> к сумме выигрыша.",
        reply_markup=promo_kb())


@router.message(CommandStart())
async def start_plain(message, state):
    await state.clear()
    await message.answer(
        "👋 Привет! Я — бот для проведения <b>конкурсов</b> в каналах и группах.\n\n"
        "Как пользоваться:\n"
        "1. Добавь меня в свой канал / группу <b>администратором</b>.\n"
        "2. Нажми «Создать конкурс» и следуй подсказкам.\n"
        "3. Я опубликую пост с кнопкой «Участвовать».\n\n"
        ,
        reply_markup=main_menu_kb())


@router.callback_query(F.data == "ga:new")
async def ga_new(cb, state):
    await state.clear()
    await state.set_state(CreateGA.chat)
    await cb.message.answer(
        "📡 <b>Шаг 1/5.</b> Перешли мне любое сообщение из своего канала/группы "
        "<i>или</i> отправь @username канала.\n\n⚠️ Я должен быть там админом.",
        reply_markup=cancel_kb())
    await cb.answer()


@router.callback_query(F.data == "ga:cancel")
async def ga_cancel(cb, state):
    await state.clear()
    await cb.message.answer("❌ Отменено.", reply_markup=main_menu_kb())
    await cb.answer()


@router.message(CreateGA.chat)
async def ga_step_chat(message, state, bot):
    chat_id = None
    chat_title = None
    if message.forward_from_chat:
        chat_id = message.forward_from_chat.id
        chat_title = message.forward_from_chat.title or str(chat_id)
    elif message.text and message.text.startswith("@"):
        try:
            chat = await bot.get_chat(message.text.strip())
            chat_id, chat_title = chat.id, chat.title or chat.username
        except TelegramBadRequest:
            return await message.answer("⚠️ Не нашёл такой чат.")
    elif message.text and message.text.lstrip("-").isdigit():
        try:
            chat = await bot.get_chat(int(message.text))
            chat_id, chat_title = chat.id, chat.title or str(chat_id)
        except TelegramBadRequest:
            return await message.answer("⚠️ Не нашёл чат по этому id.")
    else:
        return await message.answer("Пришли пересылку из канала, @username или id чата.")

    try:
        me = await bot.me()
        member = await bot.get_chat_member(chat_id, me.id)
        if member.status not in ("administrator", "creator"):
            return await message.answer("⚠️ Я не админ в этом чате.")
    except (TelegramBadRequest, TelegramForbiddenError):
        return await message.answer("⚠️ Нет доступа. Добавь меня админом.")

    await state.update_data(chat_id=chat_id, chat_title=chat_title)
    await state.set_state(CreateGA.prize_text)
    await message.answer(
        f"✅ Чат: <b>{chat_title}</b>\n\n🎁 <b>Шаг 2/5.</b> Опиши приз одной строкой.",
        reply_markup=cancel_kb())


@router.message(CreateGA.prize_text)
async def ga_step_prize_text(message, state):
    if not message.text or len(message.text) > 200:
        return await message.answer("Введи текст до 200 символов.")
    await state.update_data(prize_text=message.text.strip())
    await state.set_state(CreateGA.prize_amount)
    await message.answer("💰 <b>Шаг 3/5.</b> Сумма выигрыша (число).", reply_markup=cancel_kb())


@router.message(CreateGA.prize_amount)
async def ga_step_prize_amount(message, state):
    try:
        amount = float((message.text or "").replace(",", ".").strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        return await message.answer("Введи положительное число.")
    await state.update_data(prize_amount=amount)
    await state.set_state(CreateGA.winners_count)
    await message.answer("🏆 <b>Шаг 4/5.</b> Сколько победителей? (целое ≥ 1)",
                         reply_markup=cancel_kb())


@router.message(CreateGA.winners_count)
async def ga_step_winners(message, state):
    try:
        n = int((message.text or "").strip())
        if n < 1:
            raise ValueError
    except ValueError:
        return await message.answer("Введи целое число ≥ 1.")
    await state.update_data(winners_count=n)
    await state.set_state(CreateGA.max_participants)
    await message.answer(
        "👥 <b>Шаг 5/5.</b> Максимум участников?\n"
        "Когда наберётся это число — конкурс завершится автоматически.",
        reply_markup=cancel_kb())


@router.message(CreateGA.max_participants)
async def ga_step_max(message, state, bot):
    try:
        n = int((message.text or "").strip())
        if n < 1:
            raise ValueError
    except ValueError:
        return await message.answer("Введи целое число ≥ 1.")
    data = await state.get_data()
    if n < data["winners_count"]:
        return await message.answer(
            f"Максимум ({n}) должен быть ≥ числа победителей ({data['winners_count']}).")
    await state.update_data(max_participants=n)
    data["max_participants"] = n
    await state.set_state(CreateGA.confirm)
    await message.answer(
        f"🔍 <b>Проверь конкурс:</b>\n\nЧат: <b>{data['chat_title']}</b>\n"
        f"Приз: <b>{data['prize_text']}</b>\n"
        f"Сумма: <b>{fmt_amount(data['prize_amount'])}</b>\n"
        f"Победителей: <b>{data['winners_count']}</b>\n"
        f"Максимум участников: <b>{data['max_participants']}</b>\n\nОпубликовать?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Опубликовать", callback_data="ga:publish")],
            [InlineKeyboardButton(text="✖️ Отмена", callback_data="ga:cancel")]]))


@router.callback_query(CreateGA.confirm, F.data == "ga:publish")
async def ga_publish(cb, state, bot):
    data = await state.get_data()
    me = await bot.me()
    with db() as con:
        cur = con.execute(
            """INSERT INTO giveaways
            (owner_id, chat_id, chat_title, prize_text, prize_amount,
             winners_count, max_participants, status, created_at)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (cb.from_user.id, data["chat_id"], data["chat_title"],
             data["prize_text"], data["prize_amount"], data["winners_count"],
             data["max_participants"], "active", now_iso()))
        ga_id = cur.lastrowid
        con.commit()

    text = (f"🎉 <b>КОНКУРС!</b> 🎉\n\n🎁 Приз: <b>{data['prize_text']}</b>\n"
            f"💰 Сумма выигрыша: <b>{fmt_amount(data['prize_amount'])}</b>\n"
            f"🏆 Победителей: <b>{data['winners_count']}</b>\n\n"
            f"Жми кнопку ниже, чтобы участвовать 👇")
    try:
        msg = await bot.send_message(data["chat_id"], text,
                                     reply_markup=join_button(me.username, ga_id))
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        await cb.message.answer(f"❌ Не удалось опубликовать: {e}")
        with db() as con:
            con.execute("DELETE FROM giveaways WHERE id = ?", (ga_id,))
            con.commit()
        await state.clear()
        return await cb.answer()

    with db() as con:
        con.execute("UPDATE giveaways SET message_id = ? WHERE id = ?",
                    (msg.message_id, ga_id))
        con.commit()
    await cb.message.answer(
        f"✅ Конкурс #{ga_id} опубликован.\nЗавершить вручную: <code>/end {ga_id}</code>")
    await state.clear()
    await cb.answer()


@router.callback_query(F.data.in_(("join:promo_yes", "join:promo_no")))
async def join_promo_choice(cb, state, bot):
    data = await state.get_data()
    ga_id = data.get("joining_ga_id")
    if not ga_id:
        return await cb.answer("Сессия истекла, открой ссылку из конкурса заново.",
                               show_alert=True)
    if cb.data == "join:promo_yes":
        await state.set_state(JoinGA.promo)
        await cb.message.answer("🎟 Введи промокод одним сообщением.")
        return await cb.answer()
    await _register_participant(bot, cb.message, cb.from_user, ga_id, False)
    await state.clear()
    await cb.answer()


@router.message(JoinGA.promo)
async def join_promo_text(message, state, bot):
    data = await state.get_data()
    ga_id = data.get("joining_ga_id")
    if not ga_id:
        await message.answer("Сессия истекла.")
        return await state.clear()
    code = (message.text or "").strip().upper()
    promo_ok = code == PROMO_CODE.upper()
    if not promo_ok:
        await message.answer("❌ Неверный промокод. Регистрирую без бонуса.")
    await _register_participant(bot, message, message.from_user, ga_id, promo_ok)
    await state.clear()


async def _register_participant(bot, message, user, ga_id, promo_applied):
    with db() as con:
        ga = con.execute("SELECT * FROM giveaways WHERE id = ?", (ga_id,)).fetchone()
        if not ga or ga["status"] != "active":
            return await message.answer("⏳ Конкурс уже завершён.")
        try:
            con.execute(
                """INSERT INTO participants
                (giveaway_id, user_id, username, full_name, promo_applied, joined_at)
                VALUES (?,?,?,?,?,?)""",
                (ga_id, user.id, user.username, user.full_name,
                 1 if promo_applied else 0, now_iso()))
            con.commit()
        except sqlite3.IntegrityError:
            return await message.answer("✅ Ты уже участвуешь в этом конкурсе.")
        count = con.execute(
            "SELECT COUNT(*) FROM participants WHERE giveaway_id = ?",
            (ga_id,)).fetchone()[0]

    bonus = f"\n🎟 Промокод применён: <b>+{PROMO_BONUS_PCT}%</b>!" if promo_applied else ""
    await message.answer(
        f"✅ Ты участвуешь в конкурсе!\n🎁 Приз: <b>{ga['prize_text']}</b>{bonus}\n\n"
        "Ожидай результатов 🙌")
    if count >= ga["max_participants"]:
        await finish_giveaway(bot, ga_id)


@router.message(Command("end"))
async def cmd_end(message, command, bot):
    if not command.args or not command.args.strip().isdigit():
        return await message.answer("Использование: <code>/end &lt;id&gt;</code>")
    ga_id = int(command.args.strip())
    with db() as con:
        ga = con.execute("SELECT * FROM giveaways WHERE id = ?", (ga_id,)).fetchone()
    if not ga:
        return await message.answer("Не нашёл такой конкурс.")
    if ga["owner_id"] != message.from_user.id:
        return await message.answer("Это не твой конкурс.")
    if ga["status"] != "active":
        return await message.answer("Конкурс уже завершён.")
    await finish_giveaway(bot, ga_id, True)
    await message.answer(f"✅ Конкурс #{ga_id} завершён.")


async def finish_giveaway(bot, ga_id, forced=False):
    with db() as con:
        ga = con.execute("SELECT * FROM giveaways WHERE id = ?", (ga_id,)).fetchone()
        if not ga or ga["status"] != "active":
            return
        parts = con.execute("SELECT * FROM participants WHERE giveaway_id = ?",
                            (ga_id,)).fetchall()
        con.execute("UPDATE giveaways SET status = 'finished' WHERE id = ?", (ga_id,))
        con.commit()

    n = min(ga["winners_count"], len(parts))
    chosen = random.sample(list(parts), n) if n else []
    base = ga["prize_amount"]
    lines = []
    with db() as con:
        for w in chosen:
            won = base * (1 + PROMO_BONUS_PCT / 100) if w["promo_applied"] else base
            con.execute("INSERT INTO winners (giveaway_id, user_id, won_amount) VALUES (?,?,?)",
                        (ga_id, w["user_id"], won))
            mention = (f"@{w['username']}" if w["username"]
                       else f"<a href='tg://user?id={w['user_id']}'>{w['full_name']}</a>")
            tag = f" 🎟+{PROMO_BONUS_PCT}%" if w["promo_applied"] else ""
            lines.append(f"• {mention} — <b>{fmt_amount(won)}</b>{tag}")
        con.commit()

    if lines:
        result = (f"🏁 <b>Конкурс завершён!</b>\n\n🎁 Приз: <b>{ga['prize_text']}</b>\n"
                  f"💰 Сумма: <b>{fmt_amount(base)}</b>\n\n🏆 <b>Победители:</b>\n"
                  + "\n".join(lines))
    else:
        result = f"🏁 Конкурс завершён.\n🎁 {ga['prize_text']}\nПобедителей нет."

    try:
        await bot.send_message(ga["chat_id"], result)
    except (TelegramBadRequest, TelegramForbiddenError):
        pass
    if ga["message_id"]:
        try:
            await bot.edit_message_reply_markup(ga["chat_id"], ga["message_id"], reply_markup=None)
        except TelegramBadRequest:
            pass
    try:
        await bot.send_message(
            ga["owner_id"],
            f"✅ Конкурс #{ga_id} завершён "
            f"({'вручную' if forced else 'набран лимит'}). Победителей: {len(lines)}")
    except (TelegramBadRequest, TelegramForbiddenError):
        pass
    for w in chosen:
        won = base * (1 + PROMO_BONUS_PCT / 100) if w["promo_applied"] else base
        bl = f"\n🎟 Промокод дал +{PROMO_BONUS_PCT}%!" if w["promo_applied"] else ""
        try:
            await bot.send_message(
                w["user_id"],
                f"🎉 Поздравляем, ты победил!\n🎁 Приз: <b>{ga['prize_text']}</b>\n"
                f"💰 Сумма: <b>{fmt_amount(won)}</b>{bl}\n\nСвяжись с организатором.")
        except (TelegramBadRequest, TelegramForbiddenError):
            pass


@router.callback_query(F.data == "ga:list")
async def ga_list(cb):
    with db() as con:
        rows = con.execute(
            "SELECT * FROM giveaways WHERE owner_id = ? ORDER BY id DESC LIMIT 20",
            (cb.from_user.id,)).fetchall()
    if not rows:
        await cb.message.answer("У тебя пока нет конкурсов.")
        return await cb.answer()
    lines = ["📋 <b>Твои конкурсы:</b>\n"]
    for r in rows:
        st = "🟢 активен" if r["status"] == "active" else "⚪️ завершён"
        lines.append(f"#{r['id']} — {r['prize_text']} — {st}\n"
                     f"   чат: {r['chat_title']}, победителей: {r['winners_count']}")
    lines.append("\nЗавершить вручную: <code>/end &lt;id&gt;</code>")
    await cb.message.answer("\n".join(lines))
    await cb.answer()


async def main():
    db_init()
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    me = await bot.me()
    log.info("Bot started as @%s", me.username)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Bot stopped")