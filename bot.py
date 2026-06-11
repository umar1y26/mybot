# -*- coding: utf-8 -*-
"""
Telegram бот: слоты с кнопками "Взять администратора" и "Крутить спин".
Пароль админа: umar. При 777 — уведомление админу. Награды в меню админа.
При спине бот отправляет телеграм-стикер (нужно один раз отправить боту стикер 🎰).
"""

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.error import NetworkError, TimedOut
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ============== НАСТРОЙКИ ==============

BOT_TOKEN = os.environ.get(
    "TELEGRAM_BOT_TOKEN",
    "8213322562:AAHiCG068sysLORWj7X0fKyQOw8F62epBB0",
)
TELEGRAM_PROXY = os.environ.get("TELEGRAM_PROXY", "").strip() or None
CONNECT_TIMEOUT = float(os.environ.get("TELEGRAM_CONNECT_TIMEOUT", "30"))
READ_TIMEOUT = float(os.environ.get("TELEGRAM_READ_TIMEOUT", "30"))
WRITE_TIMEOUT = float(os.environ.get("TELEGRAM_WRITE_TIMEOUT", "30"))

ADMIN_PASSWORD = "umar"
MANAGER_PASSWORD = "umarali"
PROMO_CODE = "ali"
SPIN_COOLDOWN_SEC = 3  # кулдаун между спинами (секунды); меняйте здесь
SLOT_JACKPOT_VALUE = 64  # dice value 64 = 777 в слоте Telegram

STICKER_FILE = Path(__file__).resolve().parent / "slot_sticker_id.txt"

# ============== СОСТОЯНИЕ (в памяти) ==============

admins: set[int] = set()
managers: set[int] = set()
waiting_password: set[int] = set()
waiting_manager_password: set[int] = set()
waiting_promo: set[int] = set()
waiting_question: set[int] = set()
reply_map: dict[tuple[int, int], int] = {}
winners: list[dict] = []
spins_log: list[dict] = []
last_spin_time: dict[int, datetime] = {}
activated_promos: set[int] = set()
free_spins: dict[int, int] = {}
slot_sticker_file_id: Optional[str] = None


# ============== СТИКЕР ==============

def load_slot_sticker_id() -> Optional[str]:
    if not STICKER_FILE.exists():
        return None
    try:
        return STICKER_FILE.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def save_slot_sticker_id(file_id: str) -> None:
    try:
        STICKER_FILE.write_text(file_id, encoding="utf-8")
    except OSError:
        pass


# ============== КЛАВИАТУРЫ ==============

def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("👑 Взять администратора"), KeyboardButton("🎰 Крутить спин")],
            [KeyboardButton("🎁 Промокод"), KeyboardButton("❓ Задать вопрос")],
            [KeyboardButton("👤 Менеджер по вопросам")],
        ],
        resize_keyboard=True,
    )


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🏆 Награды", callback_data="admin_rewards")],
            [InlineKeyboardButton("📋 Все спины", callback_data="admin_all_spins")],
        ]
    )


def admin_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🏆 Награды"), KeyboardButton("📋 Все спины")],
            [KeyboardButton("🎰 Крутить спин"), KeyboardButton("👑 Взять администратора")],
            [KeyboardButton("🎁 Промокод"), KeyboardButton("❓ Задать вопрос")],
            [KeyboardButton("👤 Менеджер по вопросам")],
        ],
        resize_keyboard=True,
    )


def format_user_display(username: str, user_id: int, first_name: str = "") -> str:
    if username and username != "без юзернейма":
        return f"@{username}"
    if first_name:
        return f"{first_name} (id: {user_id})"
    return f"id: {user_id}"


def format_cooldown_period() -> str:
    if SPIN_COOLDOWN_SEC >= 60:
        mins = SPIN_COOLDOWN_SEC // 60
        secs = SPIN_COOLDOWN_SEC % 60
        if secs:
            return f"{mins} мин {secs} сек"
        return f"{mins} мин"
    return f"{SPIN_COOLDOWN_SEC} сек"


def format_cooldown_left(left_sec: int) -> str:
    mins = left_sec // 60
    secs = left_sec % 60
    if mins and secs:
        return f"{mins} мин {secs} сек"
    if mins:
        return f"{mins} мин"
    return f"{secs} сек"


async def send_admin_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    is_callback: bool = False,
) -> None:
    chat_id = update.effective_chat.id if update.effective_chat else None
    if not chat_id:
        return
    if is_callback:
        await context.bot.send_message(chat_id=chat_id, text=text)
    else:
        await update.message.reply_text(text)


# ============== ОБРАБОТЧИКИ ==============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Привет! Выбери действие:", reply_markup=main_keyboard())


async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if query.data == "admin_rewards":
        await show_rewards(update, context, is_callback=True)
    elif query.data == "admin_all_spins":
        await show_all_spins(update, context, is_callback=True)


async def show_rewards(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    is_callback: bool = False,
) -> None:
    user_id = update.effective_user.id if update.effective_user else 0
    if user_id not in admins:
        await send_admin_text(update, context, "Доступ только для администратора.", is_callback)
        return

    if not winners:
        text = "🏆 Награды\n\nПобедителей пока нет."
    else:
        lines = ["🏆 Награды\n"]
        for w in reversed(winners[-50:]):
            display = format_user_display(
                w.get("username", ""),
                w.get("user_id", 0),
                w.get("first_name", ""),
            )
            date = w.get("date", "")
            result = w.get("result", "777")
            lines.append(f"• {display} — {result} — {date}")
        text = "\n".join(lines)

    await send_admin_text(update, context, text, is_callback)


async def show_all_spins(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    is_callback: bool = False,
) -> None:
    user_id = update.effective_user.id if update.effective_user else 0
    if user_id not in admins:
        await send_admin_text(update, context, "Доступ только для администратора.", is_callback)
        return

    if not spins_log:
        text = "📋 Все спины\n\nПока никого не было."
    else:
        lines = ["📋 Все спины (кто когда крутил)\n"]
        for s in reversed(spins_log[-80:]):
            display = format_user_display(
                s.get("username", ""),
                s.get("user_id", 0),
                s.get("first_name", ""),
            )
            date = s.get("date", "")
            lines.append(f"• {display} — {date}")
        text = "\n".join(lines)

    await send_admin_text(update, context, text, is_callback)


async def sticker_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global slot_sticker_file_id
    if not update.message or not update.message.sticker:
        return
    file_id = update.message.sticker.file_id
    save_slot_sticker_id(file_id)
    slot_sticker_file_id = file_id
    await update.message.reply_text(
        "✅ Стикер сохранён! Теперь при нажатии «Крутить спин» "
        "бот будет отправлять этот стикер."
    )


async def do_spin(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    username: str,
    first_name: str = "",
) -> None:
    now = datetime.now()
    last = last_spin_time.get(user_id)
    if last is not None:
        elapsed = (now - last).total_seconds()
        if elapsed < SPIN_COOLDOWN_SEC:
            left_sec = max(1, int(SPIN_COOLDOWN_SEC - elapsed))
            await update.message.reply_text(
                f"Крутить можно раз в {format_cooldown_period()}.\n\n"
                f"До следующего спина осталось: {format_cooldown_left(left_sec)}.",
                reply_markup=admin_reply_keyboard() if user_id in admins else main_keyboard(),
            )
            return

    last_spin_time[user_id] = now
    now_str = now.strftime("%d.%m.%Y %H:%M")
    spins_log.append({
        "user_id": user_id,
        "username": username,
        "first_name": first_name,
        "date": now_str,
    })

    used_free = False
    if free_spins.get(user_id, 0) > 0:
        free_spins[user_id] -= 1
        used_free = True
    left = free_spins.get(user_id, 0)

    sent = await update.message.reply_dice(emoji="🎰")
    is_777 = bool(sent.dice and sent.dice.value == SLOT_JACKPOT_VALUE)

    free_msg = ""
    if used_free:
        if left > 0:
            free_msg = f"\nБесплатных спинов осталось: {left}."
        else:
            free_msg = "\nБесплатные спины закончились."

    if is_777:
        await update.message.reply_text(f"🎉 Джекпот! Выпало: 777{free_msg}")
        winners.append({
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
            "date": now_str,
            "result": "777",
        })
        display = format_user_display(username, user_id, first_name)
        for admin_id in admins:
            try:
                await context.bot.send_message(
                    admin_id,
                    f"🔔 Джекпот! {display} выиграл 777.",
                )
            except Exception:
                pass
    else:
        await update.message.reply_text(
            f"Найс трай, но тебе скоро повезёт. Испытай удачу ещё раз 🎰{free_msg}"
        )


async def text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.message.text or "").strip()
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id if update.effective_chat else user_id
    username = (update.effective_user.username or "").strip() or "без юзернейма"
    first_name = (update.effective_user.first_name or "").strip()

    if user_id in managers and update.message.reply_to_message:
        reply_to = update.message.reply_to_message
        if reply_to.from_user and reply_to.from_user.is_bot:
            key = (chat_id, reply_to.message_id)
            if key in reply_map:
                asker_id = reply_map[key]
                try:
                    await context.bot.send_message(
                        asker_id,
                        f"💬 Ответ на ваш вопрос:\n\n{text}",
                    )
                    await update.message.reply_text("✅ Ответ отправлен пользователю.")
                except Exception:
                    await update.message.reply_text("Не удалось отправить ответ.")
                return

    if user_id in waiting_question:
        waiting_question.discard(user_id)
        if not text:
            await update.message.reply_text(
                "Вопрос не может быть пустым. Напишите ваш вопрос:",
                reply_markup=main_keyboard(),
            )
            return
        if not managers:
            await update.message.reply_text(
                "Сейчас нет менеджеров. Попробуйте позже.",
                reply_markup=main_keyboard(),
            )
            return
        question_text = f"❓ Вопрос от @{username} (id: {user_id}):\n\n{text}"
        for mid in managers:
            try:
                sent = await context.bot.send_message(mid, question_text)
                reply_map[(mid, sent.message_id)] = user_id
            except Exception:
                pass
        await update.message.reply_text(
            "Вопрос отправлен менеджерам. Ожидайте ответа.",
            reply_markup=main_keyboard(),
        )
        return

    if user_id in waiting_promo:
        waiting_promo.discard(user_id)
        if text.lower() == PROMO_CODE:
            if user_id in activated_promos:
                await update.message.reply_text(
                    "❌ Вы уже активировали промокод.",
                    reply_markup=main_keyboard(),
                )
            else:
                activated_promos.add(user_id)
                free_spins[user_id] = free_spins.get(user_id, 0) + 3
                await update.message.reply_text(
                    "✅ Промокод принят. Вам начислено 3 бесплатных спина.",
                    reply_markup=main_keyboard(),
                )
        else:
            await update.message.reply_text("Неверный промокод.", reply_markup=main_keyboard())
        return

    if user_id in waiting_manager_password:
        waiting_manager_password.discard(user_id)
        if text == MANAGER_PASSWORD:
            managers.add(user_id)
            await update.message.reply_text(
                "✅ Вы вошли как менеджер по вопросам. Вам будут приходить вопросы; "
                "ответьте на сообщение бота, чтобы ответить пользователю.",
                reply_markup=main_keyboard(),
            )
        else:
            await update.message.reply_text("❌ Неверный пароль.", reply_markup=main_keyboard())
        return

    if user_id in waiting_password:
        waiting_password.discard(user_id)
        if text == ADMIN_PASSWORD:
            admins.add(user_id)
            await update.message.reply_text(
                "✅ Вы вошли как администратор. Меню:",
                reply_markup=admin_reply_keyboard(),
            )
            await update.message.reply_text(
                "Или выберите в меню:",
                reply_markup=admin_menu_keyboard(),
            )
        else:
            await update.message.reply_text("❌ Неверный пароль.", reply_markup=main_keyboard())
        return

    if text == "🏆 Награды":
        await show_rewards(update, context)
        return

    if text == "📋 Все спины":
        await show_all_spins(update, context)
        return

    if text == "👑 Взять администратора":
        if user_id in admins:
            await update.message.reply_text("Меню:", reply_markup=admin_reply_keyboard())
            await update.message.reply_text(
                "Или выберите в меню:",
                reply_markup=admin_menu_keyboard(),
            )
            return
        waiting_password.add(user_id)
        await update.message.reply_text("Введите пароль:")
        return

    if text == "🎰 Крутить спин":
        await do_spin(update, context, user_id, username, first_name)
        return

    if text == "🎁 Промокод":
        waiting_promo.add(user_id)
        await update.message.reply_text("Введите промокод:")
        return

    if text == "❓ Задать вопрос":
        waiting_question.add(user_id)
        await update.message.reply_text("Напишите ваш вопрос:")
        return

    if text == "👤 Менеджер по вопросам":
        if user_id in managers:
            await update.message.reply_text(
                "Вы уже менеджер по вопросам.",
                reply_markup=main_keyboard(),
            )
            return
        waiting_manager_password.add(user_id)
        await update.message.reply_text("Введите пароль:")
        return

    await update.message.reply_text("Выбери действие:", reply_markup=main_keyboard())


# ============== ЗАПУСК ==============

def _print_proxy_help() -> None:
    print(
        "Не удалось подключиться к api.telegram.org.\n"
        "В России/CIS Telegram API часто заблокирован — нужен прокси/VPN.\n\n"
        "Установите переменную окружения TELEGRAM_PROXY, например:\n"
        "  PowerShell: $env:TELEGRAM_PROXY = 'socks5://127.0.0.1:1080'\n"
        "  CMD:        set TELEGRAM_PROXY=socks5://127.0.0.1:1080\n"
        "  HTTP-прокси: socks5://127.0.0.1:1080 или http://127.0.0.1:7890\n\n"
        "Для socks5 установите зависимости: pip install \"python-telegram-bot[socks]\"\n"
        "Убедитесь, что VPN/прокси-клиент (Clash, V2Ray, etc.) запущен."
    )


def _build_application() -> Application:
    builder = (
        Application.builder()
        .token(BOT_TOKEN)
        .connect_timeout(CONNECT_TIMEOUT)
        .read_timeout(READ_TIMEOUT)
        .write_timeout(WRITE_TIMEOUT)
        .get_updates_connect_timeout(CONNECT_TIMEOUT)
        .get_updates_read_timeout(READ_TIMEOUT)
        .get_updates_write_timeout(WRITE_TIMEOUT)
    )

    if TELEGRAM_PROXY:
        if TELEGRAM_PROXY.startswith("socks"):
            try:
                import socks  # noqa: F401
            except ImportError:
                print(
                    "TELEGRAM_PROXY использует socks, но PySocks не установлен.\n"
                    "Выполните: pip install \"python-telegram-bot[socks]\""
                )
                sys.exit(1)
        builder = builder.proxy(TELEGRAM_PROXY).get_updates_proxy(TELEGRAM_PROXY)
        print(f"Прокси: {TELEGRAM_PROXY}")
    else:
        print(
            "TELEGRAM_PROXY не задан. Прямое подключение к api.telegram.org.\n"
            "Если будет таймаут — задайте TELEGRAM_PROXY (socks5:// или http://)."
        )

    return builder.build()


def main() -> None:
    global slot_sticker_file_id
    slot_sticker_file_id = load_slot_sticker_id()

    app = _build_application()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_click))
    app.add_handler(MessageHandler(filters.Sticker.ALL, sticker_received))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message))

    try:
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    except (TimedOut, NetworkError):
        _print_proxy_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
