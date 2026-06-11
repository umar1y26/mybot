# -*- coding: utf-8 -*-
"""
Объединенный Telegram бот:
1. Игровой спин (1 раз в день + промокоды)
2. Система вопросов пользователей → ответы админов
3. Админ-панель с статистикой

Запуск: pip install python-telegram-bot
       python bot.py
"""
import logging
import random
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Set, Any
from dataclasses import dataclass, field, asdict
from enum import Enum

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, User
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)

# === НАСТРОЙКИ ===
BOT_TOKEN = "8573569768:AAEgmdZ7xsUcbeR-s75jKb5nSZTs16pLdPU"
ADMIN_PASSWORD = "umar"

# === ЛОГИРОВАНИЕ ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# === КОНСТАНТЫ ===
ADMIN_PASSWORD_INPUT, PROMOCODE_INPUT, QUESTION_INPUT = range(3)

# === СТРУКТУРЫ ДАННЫХ ===

# Промокоды
PROMOCODES = {
    "ali": {"spins": 3, "used_by": set()},  # 3 бесплатных спина
    "free": {"spins": 1, "used_by": set()},  # 1 бесплатный спин
    "bonus": {"spins": 2, "used_by": set()}  # 2 бесплатных спина
}


# Структура для хранения данных о победах
@dataclass
class WinRecord:
    user_id: int
    username: str
    timestamp: datetime
    win_amount: str = "777"

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "username": self.username,
            "timestamp": self.timestamp.isoformat(),
            "win_amount": self.win_amount
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            user_id=data["user_id"],
            username=data["username"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            win_amount=data.get("win_amount", "777")
        )


# Структура для хранения данных пользователя
@dataclass
class UserData:
    user_id: int
    last_spin_date: Optional[datetime] = None
    available_spins: int = 0  # 0 = использовал дневной спин, >0 = есть дополнительные спины
    used_promocodes: Set[str] = field(default_factory=set)

    def can_spin(self) -> bool:
        """Проверяет, может ли пользователь крутить спин"""
        if self.available_spins > 0:
            return True

        if self.last_spin_date is None:
            return True

        # Проверяем, прошло ли 24 часа с последнего спина
        time_since_last_spin = datetime.now() - self.last_spin_date
        return time_since_last_spin >= timedelta(hours=24)

    def use_spin(self) -> None:
        """Использование спина"""
        if self.available_spins > 0:
            self.available_spins -= 1
        else:
            self.last_spin_date = datetime.now()

    def add_spins(self, count: int) -> None:
        """Добавляет дополнительные спины"""
        self.available_spins += count

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "last_spin_date": self.last_spin_date.isoformat() if self.last_spin_date else None,
            "available_spins": self.available_spins,
            "used_promocodes": list(self.used_promocodes)
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            user_id=data["user_id"],
            last_spin_date=datetime.fromisoformat(data["last_spin_date"]) if data["last_spin_date"] else None,
            available_spins=data["available_spins"],
            used_promocodes=set(data["used_promocodes"])
        )


# Структура для хранения вопросов
@dataclass
class Question:
    question_id: int
    user_id: int
    user_name: str
    username: str
    text: str
    timestamp: datetime
    answered: bool = False
    answer_text: Optional[str] = None
    answer_admin: Optional[str] = None
    answer_time: Optional[datetime] = None

    def to_dict(self):
        return {
            "question_id": self.question_id,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "username": self.username,
            "text": self.text,
            "timestamp": self.timestamp.isoformat(),
            "answered": self.answered,
            "answer_text": self.answer_text,
            "answer_admin": self.answer_admin,
            "answer_time": self.answer_time.isoformat() if self.answer_time else None
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            question_id=data["question_id"],
            user_id=data["user_id"],
            user_name=data["user_name"],
            username=data["username"],
            text=data["text"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            answered=data.get("answered", False),
            answer_text=data.get("answer_text"),
            answer_admin=data.get("answer_admin"),
            answer_time=datetime.fromisoformat(data["answer_time"]) if data.get("answer_time") else None
        )


# === ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ===
admin_users: Set[int] = set()
win_records: List[WinRecord] = []
user_data_dict: Dict[int, UserData] = {}
questions: List[Question] = []
pending_replies: Dict[
    Tuple[int, int], Tuple[int, int, int]] = {}  # (admin_id, msg_id) -> (user_id, chat_id, question_id)
question_counter: int = 0

# === ФАЙЛЫ ДЛЯ СОХРАНЕНИЯ ===
DATA_FILE = "bot_data.json"
USERS_FILE = "users_data.json"
QUESTIONS_FILE = "questions_data.json"


# === ЗАГРУЗКА И СОХРАНЕНИЕ ДАННЫХ ===
def load_data():
    """Загружает данные из файлов"""
    global win_records, user_data_dict, questions, question_counter

    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                win_records = [WinRecord.from_dict(record) for record in data.get("win_records", [])]
    except Exception as e:
        logger.error(f"Ошибка загрузки данных: {e}")
        win_records = []

    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                user_data_dict = {int(uid): UserData.from_dict(user_data) for uid, user_data in data.items()}
    except Exception as e:
        logger.error(f"Ошибка загрузки данных пользователей: {e}")
        user_data_dict = {}

    try:
        if os.path.exists(QUESTIONS_FILE):
            with open(QUESTIONS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                questions = [Question.from_dict(q) for q in data.get("questions", [])]
                if questions:
                    question_counter = max(q.question_id for q in questions) + 1
    except Exception as e:
        logger.error(f"Ошибка загрузки вопросов: {e}")
        questions = []
        question_counter = 0


def save_data():
    """Сохраняет данные в файлы"""
    try:
        # Сохраняем записи о победах
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            data = {
                "win_records": [record.to_dict() for record in win_records]
            }
            json.dump(data, f, ensure_ascii=False, indent=2)

        # Сохраняем данные пользователей
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            data = {str(uid): user_data.to_dict() for uid, user_data in user_data_dict.items()}
            json.dump(data, f, ensure_ascii=False, indent=2)

        # Сохраняем вопросы
        with open(QUESTIONS_FILE, 'w', encoding='utf-8') as f:
            data = {
                "questions": [q.to_dict() for q in questions]
            }
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения данных: {e}")


def get_user_data(user_id: int) -> UserData:
    """Получает или создает данные пользователя"""
    if user_id not in user_data_dict:
        user_data_dict[user_id] = UserData(user_id=user_id)
    return user_data_dict[user_id]


# === КЛАВИАТУРЫ ===
def get_main_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Основная клавиатура"""
    user_data = get_user_data(user_id)

    buttons = []

    # Проверяем, может ли пользователь крутить спин
    if user_data.can_spin():
        spin_text = "🎰 Крутить спин"
        if user_data.available_spins > 0:
            spin_text += f" ({user_data.available_spins} доступно)"
        buttons.append([InlineKeyboardButton(spin_text, callback_data="spin")])
    else:
        # Показываем время до следующего спина
        if user_data.last_spin_date:
            next_spin_time = user_data.last_spin_date + timedelta(hours=24)
            time_left = next_spin_time - datetime.now()
            hours = int(time_left.total_seconds() // 3600)
            minutes = int((time_left.total_seconds() % 3600) // 60)
            buttons.append([InlineKeyboardButton(f"⏳ Следующий спин через {hours}ч {minutes}м", callback_data="wait")])

    buttons.extend([
        [InlineKeyboardButton("🎁 Промокод", callback_data="promocode")],
        [InlineKeyboardButton("❓ Задать вопрос", callback_data="ask_question")],
        [InlineKeyboardButton("🔐 Взять администратора", callback_data="admin")]
    ])

    return InlineKeyboardMarkup(buttons)


def get_admin_menu_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для администратора"""
    keyboard = [
        [InlineKeyboardButton("🏆 Награды", callback_data="rewards")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("👥 Пользователи", callback_data="users")],
        [InlineKeyboardButton("📝 Вопросы", callback_data="view_questions")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для возврата в меню"""
    keyboard = [
        [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_promocode_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для промокодов"""
    keyboard = [
        [InlineKeyboardButton("🎁 Ввести промокод", callback_data="enter_promo")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_questions_menu_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для вопросов"""
    keyboard = [
        [InlineKeyboardButton("📋 Список вопросов", callback_data="list_questions")],
        [InlineKeyboardButton("❓ Новые вопросы", callback_data="new_questions")],
        [InlineKeyboardButton("✅ Отвеченные", callback_data="answered_questions")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)


# === ФУНКЦИИ ДЛЯ РАБОТЫ С ПОБЕДАМИ ===
def add_win_record(user_id: int, username: str) -> None:
    """Добавляет запись о победе"""
    win_records.append(WinRecord(
        user_id=user_id,
        username=username,
        timestamp=datetime.now()
    ))
    # Ограничиваем количество записей (последние 100)
    if len(win_records) > 100:
        win_records.pop(0)
    save_data()


def get_formatted_rewards() -> str:
    """Возвращает отформатированный список наград"""
    if not win_records:
        return "🏆 Пока никто не выиграл 777!"

    result = "🏆 **История выигрышей 777:**\n\n"
    for i, record in enumerate(reversed(win_records[-10:]), 1):
        time_str = record.timestamp.strftime("%d.%m.%Y %H:%M")
        result += f"{i}. @{record.username} - {time_str}\n"

    return result


# === ФУНКЦИИ ДЛЯ РАБОТЫ С ПРОМОКОДАМИ ===
def use_promocode(promocode: str, user_id: int, username: str) -> Tuple[bool, str, int]:
    """Активация промокода"""
    promocode = promocode.lower().strip()

    if promocode not in PROMOCODES:
        return False, "❌ Такого промокода не существует!", 0

    promo_data = PROMOCODES[promocode]

    if user_id in promo_data["used_by"]:
        return False, "❌ Вы уже использовали этот промокод!", 0

    # Получаем данные пользователя
    user_data = get_user_data(user_id)

    if promocode in user_data.used_promocodes:
        return False, "❌ Вы уже использовали этот промокод!", 0

    # Активируем промокод
    spins = promo_data["spins"]
    user_data.add_spins(spins)
    user_data.used_promocodes.add(promocode)
    promo_data["used_by"].add(user_id)

    save_data()

    return True, f"✅ Промокод активирован! Вы получили {spins} дополнительных {'спин' if spins == 1 else 'спина' if spins in [2, 3, 4] else 'спинов'}!", spins


# === ФУНКЦИИ ДЛЯ РАБОТЫ С ВОПРОСАМИ ===
def add_question(user_id: int, user_name: str, username: str, text: str) -> int:
    """Добавляет новый вопрос"""
    global question_counter

    question = Question(
        question_id=question_counter,
        user_id=user_id,
        user_name=user_name,
        username=username,
        text=text,
        timestamp=datetime.now()
    )

    questions.append(question)
    question_counter += 1

    # Ограничиваем количество вопросов (последние 100)
    if len(questions) > 100:
        questions.pop(0)

    save_data()

    return question.question_id


def answer_question(question_id: int, answer_text: str, admin_name: str) -> Optional[Question]:
    """Отвечает на вопрос"""
    for question in questions:
        if question.question_id == question_id:
            question.answered = True
            question.answer_text = answer_text
            question.answer_admin = admin_name
            question.answer_time = datetime.now()

            save_data()
            return question

    return None


def get_unanswered_questions() -> List[Question]:
    """Возвращает список неотвеченных вопросов"""
    return [q for q in questions if not q.answered]


def get_answered_questions() -> List[Question]:
    """Возвращает список отвеченных вопросов"""
    return [q for q in questions if q.answered]


def get_question_by_id(question_id: int) -> Optional[Question]:
    """Находит вопрос по ID"""
    for question in questions:
        if question.question_id == question_id:
            return question
    return None


# === ОБРАБОТЧИКИ КОМАНД ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start"""
    user = update.effective_user
    user_data = get_user_data(user.id)

    welcome_text = (
        f"Привет, {user.first_name}! 👋\n\n"
        "🎰 **Игровой бот со слотами**\n"
        "❓ **Система вопросов и ответов**\n\n"
        f"📊 **Ваша статистика:**\n"
        f"• Доступных спинов: {user_data.available_spins}\n"
        f"• Использованных промокодов: {len(user_data.used_promocodes)}\n\n"
        "Выберите действие:"
    )

    await update.message.reply_text(
        welcome_text,
        reply_markup=get_main_keyboard(user.id)
    )


async def admin_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик кнопки 'Взять администратора'"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    if user_id in admin_users:
        await query.edit_message_text(
            "Вы уже администратор!",
            reply_markup=get_admin_menu_keyboard()
        )
        return ConversationHandler.END

    await query.edit_message_text(
        "🔐 **Введите пароль администратора:**",
        reply_markup=None
    )
    return ADMIN_PASSWORD_INPUT


async def check_admin_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Проверка пароля администратора"""
    user = update.message.from_user
    password = update.message.text.strip()

    if password == ADMIN_PASSWORD:
        admin_users.add(user.id)
        await update.message.reply_text(
            "✅ **Пароль верный!**\n"
            "Теперь вы администратор.\n\n"
            "📋 **Меню администратора:**",
            reply_markup=get_admin_menu_keyboard()
        )
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "❌ **Неверный пароль!**\n"
            "Попробуйте еще раз или вернитесь в главное меню.",
            reply_markup=get_main_keyboard(user.id)
        )
        return ConversationHandler.END


async def spin_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик кнопки 'Крутить спин'"""
    query = update.callback_query
    await query.answer()

    user = query.from_user
    user_data = get_user_data(user.id)

    # Проверяем, может ли пользователь крутить спин
    if not user_data.can_spin():
        if user_data.last_spin_date:
            next_spin_time = user_data.last_spin_date + timedelta(hours=24)
            time_left = next_spin_time - datetime.now()
            hours = int(time_left.total_seconds() // 3600)
            minutes = int((time_left.total_seconds() % 3600) // 60)

            await query.edit_message_text(
                f"⏳ **Вы уже использовали дневной спин!**\n\n"
                f"Следующий спин будет доступен через:\n"
                f"**{hours} часов {minutes} минут**\n\n"
                f"🎁 Используйте промокод для дополнительных спинов!",
                reply_markup=get_main_keyboard(user.id)
            )
        return

    # Используем спин
    user_data.use_spin()

    symbols = ["🍒", "🍋", "🍊", "🍉", "⭐", "7️⃣"]

    # Генерация результата
    result = random.choices(symbols, k=3)
    spin_result = "🎰 " + " | ".join(result) + " 🎰"

    # Проверка на выигрыш 777
    is_win = result == ["7️⃣", "7️⃣", "7️⃣"]

    if is_win:
        win_text = "🎉 **ДЖЕКПОТ! 777!** 🎉"
        add_win_record(user.id, user.username or user.first_name)

        # Уведомление администраторов
        await notify_admins_about_win(context, user)
    else:
        win_text = "Попробуйте еще раз! 🍀"

    # Обновляем статистику
    remaining_spins = user_data.available_spins
    spin_info = ""
    if remaining_spins > 0:
        spin_info = f"\n\n🎁 Осталось дополнительных спинов: **{remaining_spins}**"
    elif user_data.last_spin_date:
        next_spin_time = user_data.last_spin_date + timedelta(hours=24)
        time_left = next_spin_time - datetime.now()
        hours = int(time_left.total_seconds() // 3600)
        minutes = int((time_left.total_seconds() % 3600) // 60)
        spin_info = f"\n\n⏳ Следующий дневной спин через: **{hours}ч {minutes}м**"

    message_text = f"{spin_result}\n\n{win_text}{spin_info}"

    await query.edit_message_text(
        message_text,
        reply_markup=get_main_keyboard(user.id)
    )

    save_data()


async def promocode_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик кнопки 'Промокод'"""
    query = update.callback_query
    await query.answer()

    user = query.from_user
    user_data = get_user_data(user.id)

    promocode_text = (
        "🎁 **Система промокодов**\n\n"
        f"📊 **Ваша статистика:**\n"
        f"• Использовано промокодов: {len(user_data.used_promocodes)}\n"
        f"• Доступные промокоды: ali, free, bonus\n\n"
        "🎯 **Промокод 'ali' дает 3 бесплатных спина!**\n\n"
        "Выберите действие:"
    )

    await query.edit_message_text(
        promocode_text,
        reply_markup=get_promocode_keyboard()
    )


async def enter_promocode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запрос ввода промокода"""
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "🎁 **Введите промокод:**\n\n"
        "Доступные промокоды:\n"
        "• **ali** - 3 бесплатных спина\n"
        "• **free** - 1 бесплатный спин\n"
        "• **bonus** - 2 бесплатных спина",
        reply_markup=None
    )

    return PROMOCODE_INPUT


async def check_promocode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Проверка промокода"""
    user = update.message.from_user
    promocode = update.message.text.strip()

    success, message, spins = use_promocode(promocode, user.id, user.username or user.first_name)

    if success:
        user_data = get_user_data(user.id)
        additional_info = f"\n\n📊 **Ваша статистика:**\n• Всего спинов: {user_data.available_spins}\n• Использовано промокодов: {len(user_data.used_promocodes)}"
        message += additional_info

    await update.message.reply_text(
        message,
        reply_markup=get_main_keyboard(user.id)
    )

    return ConversationHandler.END


async def ask_question_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик кнопки 'Задать вопрос'"""
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "❓ **Задайте свой вопрос:**\n\n"
        "Ваш вопрос будет отправлен администраторам. "
        "Ответ придет вам в этот чат.",
        reply_markup=None
    )

    return QUESTION_INPUT


async def handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка вопроса от пользователя"""
    user = update.message.from_user
    question_text = update.message.text.strip()

    if not question_text:
        await update.message.reply_text(
            "❌ Вопрос не может быть пустым. Попробуйте еще раз.",
            reply_markup=get_main_keyboard(user.id)
        )
        return ConversationHandler.END

    # Добавляем вопрос
    question_id = add_question(
        user_id=user.id,
        user_name=user.full_name or "Без имени",
        username=user.username or "—",
        text=question_text
    )

    # Формируем текст вопроса для администраторов
    question_for_admin = (
        f"📩 **Новый вопрос #{question_id}**\n\n"
        f"👤 От: {user.full_name or 'Без имени'}\n"
        f"🆔 User ID: {user.id}\n"
        f"📱 Username: @{user.username or '—'}\n\n"
        f"❓ Вопрос:\n{question_text}\n\n"
        f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}\n\n"
        f"💬 **Ответьте на это сообщение, чтобы ответить пользователю.**"
    )

    # Отправляем вопрос администраторам
    sent_to_admins = False
    for admin_id in admin_users:
        try:
            msg = await context.bot.send_message(
                chat_id=admin_id,
                text=question_for_admin
            )
            pending_replies[(admin_id, msg.message_id)] = (user.id, update.message.chat.id, question_id)
            sent_to_admins = True
        except Exception as e:
            logger.warning(f"Не удалось отправить вопрос админу {admin_id}: {e}")

    if sent_to_admins:
        await update.message.reply_text(
            "✅ Ваш вопрос отправлен администраторам. Ответ придет вам в этот чат.",
            reply_markup=get_main_keyboard(user.id)
        )
    else:
        await update.message.reply_text(
            "⚠️ Сейчас нет активных администраторов. Попробуйте позже.",
            reply_markup=get_main_keyboard(user.id)
        )

    return ConversationHandler.END


async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка ответа администратора на вопрос"""
    user = update.message.from_user

    if user.id not in admin_users:
        return

    if not update.message.reply_to_message:
        return

    # Проверяем, является ли это ответом на вопрос
    key = (update.message.chat.id, update.message.reply_to_message.message_id)

    if key in pending_replies:
        target_user_id, target_chat_id, question_id = pending_replies.pop(key)
        answer_text = update.message.text.strip()

        # Находим вопрос
        question = get_question_by_id(question_id)

        if question:
            # Отмечаем вопрос как отвеченный
            answered_question = answer_question(
                question_id=question_id,
                answer_text=answer_text,
                admin_name=user.full_name or "Админ"
            )

            if answered_question:
                # Формируем ответ для пользователя
                reply_text = (
                    f"📨 **Ответ от администратора ({user.full_name or 'Админ'}):**\n\n"
                    f"{answer_text}\n\n"
                    f"⏰ Время ответа: {datetime.now().strftime('%H:%M:%S')}"
                )

                try:
                    await context.bot.send_message(
                        chat_id=target_user_id,
                        text=reply_text
                    )
                    await update.message.reply_text("✅ Ответ отправлен пользователю.")
                except Exception as e:
                    logger.error(f"Не удалось отправить ответ пользователю {target_user_id}: {e}")
                    await update.message.reply_text(
                        "❌ Не удалось отправить ответ. Возможно, пользователь заблокировал бота.")
                    # Возвращаем в pending_replies
                    pending_replies[key] = (target_user_id, target_chat_id, question_id)
            else:
                await update.message.reply_text("❌ Вопрос не найден.")
        else:
            await update.message.reply_text("❌ Вопрос не найден.")


async def notify_admins_about_win(context: ContextTypes.DEFAULT_TYPE, user: User) -> None:
    """Отправляет уведомление администраторам о выигрыше"""
    # Получаем полное имя пользователя
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    if not full_name:
        full_name = 'Без имени'

    notification = (
        f"🎉 **НОВЫЙ ВЫИГРЫШ 777!** 🎉\n\n"
        f"👤 Имя: {full_name}\n"
        f"🆔 User ID: {user.id}\n"
        f"📱 Username: @{user.username or '—'}\n\n"
        f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}"
    )

    for admin_id in admin_users:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=notification
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление админу {admin_id}: {e}")


async def rewards_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик кнопки 'Награды' в админ-меню"""
    query = update.callback_query
    await query.answer()

    rewards_text = get_formatted_rewards()

    await query.edit_message_text(
        rewards_text,
        reply_markup=get_admin_menu_keyboard()
    )


async def stats_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик кнопки 'Статистика' в админ-меню"""
    query = update.callback_query
    await query.answer()

    # Статистика
    total_users = len(user_data_dict)
    total_wins = len(win_records)
    total_questions = len(questions)
    unanswered_questions = len(get_unanswered_questions())

    # Активные пользователи (те, кто использовал спин за последние 7 дней)
    active_users = 0
    week_ago = datetime.now() - timedelta(days=7)
    for user_data in user_data_dict.values():
        if user_data.last_spin_date and user_data.last_spin_date >= week_ago:
            active_users += 1

    # Последний выигрыш
    last_win_str = "—"
    if win_records:
        last_win_str = win_records[-1].timestamp.strftime('%d.%m.%Y %H:%M')

    stats_text = (
        "📊 **Статистика бота:**\n\n"
        f"👥 **Пользователи:**\n"
        f"• Всего пользователей: {total_users}\n"
        f"• Активных (за 7 дней): {active_users}\n\n"
        f"🎰 **Игровая статистика:**\n"
        f"• Всего выигрышей 777: {total_wins}\n"
        f"• Последний выигрыш: {last_win_str}\n\n"
        f"❓ **Вопросы:**\n"
        f"• Всего вопросов: {total_questions}\n"
        f"• Новых вопросов: {unanswered_questions}\n"
        f"• Отвеченных: {total_questions - unanswered_questions}\n\n"
        f"🔄 **Последнее обновление:** {datetime.now().strftime('%H:%M:%S')}"
    )

    await query.edit_message_text(
        stats_text,
        reply_markup=get_admin_menu_keyboard()
    )


async def users_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик кнопки 'Пользователи' в админ-меню"""
    query = update.callback_query
    await query.answer()

    if not user_data_dict:
        await query.edit_message_text(
            "👥 **Нет данных о пользователях.**",
            reply_markup=get_admin_menu_keyboard()
        )
        return

    # Сортируем пользователей по дате последнего спина
    sorted_users = sorted(
        user_data_dict.items(),
        key=lambda x: x[1].last_spin_date if x[1].last_spin_date else datetime.min,
        reverse=True
    )

    users_text = "👥 **Последние активные пользователи:**\n\n"

    for i, (user_id, user_data) in enumerate(sorted_users[:10], 1):
        last_spin = user_data.last_spin_date.strftime("%d.%m %H:%M") if user_data.last_spin_date else "никогда"
        spins = user_data.available_spins
        promocodes = len(user_data.used_promocodes)

        users_text += f"{i}. ID: {user_id}\n"
        users_text += f"   • Последний спин: {last_spin}\n"
        users_text += f"   • Доп. спины: {spins}\n"
        users_text += f"   • Промокодов: {promocodes}\n\n"

    users_text += f"📊 Всего пользователей: {len(user_data_dict)}"

    await query.edit_message_text(
        users_text,
        reply_markup=get_admin_menu_keyboard()
    )

    async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Возврат в главное меню"""
        query = update.callback_query
        await query.answer()

        user = query.from_user
        user_data = get_user_data(user.id)

        welcome_text = (
            f"Привет, {user.first_name}! 👋\n\n"
            "🎰 **Игровой бот со слотами**\n"
            "❓ **Система вопросов и ответов**\n\n"
            f"📊 **Ваша статистика:**\n"
            f"• Доступных спинов: {user_data.available_spins}\n"
            f"• Использованных промокодов: {len(user_data.used_promocodes)}\n\n"
            "Выберите действие:"
        )

        await query.edit_message_text(
            welcome_text,
            reply_markup=get_main_keyboard(user.id)
        )

    async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Возврат в меню администратора"""
        query = update.callback_query
        await query.answer()

        user = query.from_user

        if user.id in admin_users:
            await query.edit_message_text(
                "📋 **Меню администратора:**",
                reply_markup=get_admin_menu_keyboard()
            )
        else:
            await query.edit_message_text(
                "🔐 **Вы не администратор.**",
                reply_markup=get_main_keyboard(user.id)
            )

    async def view_questions_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик кнопки 'Вопросы' в админ-меню"""
        query = update.callback_query
        await query.answer()

        unanswered_count = len(get_unanswered_questions())
        answered_count = len(get_answered_questions())

        questions_text = (
            f"📝 **Управление вопросами**\n\n"
            f"📊 Статистика:\n"
            f"• ❓ Новых вопросов: {unanswered_count}\n"
            f"• ✅ Отвеченных: {answered_count}\n"
            f"• 📈 Всего: {len(questions)}\n\n"
            f"Выберите действие:"
        )

        await query.edit_message_text(
            questions_text,
            reply_markup=get_questions_menu_keyboard()
        )

    async def list_questions_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Показывает список всех вопросов"""
        query = update.callback_query
        await query.answer()

        if not questions:
            await query.edit_message_text(
                "📝 **Список вопросов пуст.**",
                reply_markup=get_questions_menu_keyboard()
            )
            return

        questions_text = "📝 **Все вопросы:**\n\n"

        for i, q in enumerate(reversed(questions[-10:]), 1):
            status = "✅" if q.answered else "❓"
            time_str = q.timestamp.strftime("%d.%m %H:%M")
            questions_text += f"{i}. {status} #{q.question_id} от @{q.username} - {time_str}\n"

        questions_text += f"\n📊 Всего вопросов: {len(questions)}"

        await query.edit_message_text(
            questions_text,
            reply_markup=get_questions_menu_keyboard()
        )

    async def new_questions_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Показывает новые вопросы"""
        query = update.callback_query
        await query.answer()

        unanswered = get_unanswered_questions()

        if not unanswered:
            await query.edit_message_text(
                "❓ **Нет новых вопросов.**",
                reply_markup=get_questions_menu_keyboard()
            )
            return

        questions_text = "❓ **Новые вопросы:**\n\n"

        for i, q in enumerate(reversed(unanswered[-10:]), 1):
            time_str = q.timestamp.strftime("%d.%m %H:%M")
            questions_text += f"{i}. #{q.question_id} от @{q.username} - {time_str}\n"
            questions_text += f"   Вопрос: {q.text[:50]}...\n\n"

        questions_text += f"📊 Новых вопросов: {len(unanswered)}"

        await query.edit_message_text(
            questions_text,
            reply_markup=get_questions_menu_keyboard()
        )

    async def answered_questions_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Показывает отвеченные вопросы"""
        query = update.callback_query
        await query.answer()

        answered = get_answered_questions()

        if not answered:
            await query.edit_message_text(
                "✅ **Нет отвеченных вопросов.**",
                reply_markup=get_questions_menu_keyboard()
            )
            return

        questions_text = "✅ **Отвеченные вопросы:**\n\n"

        for i, q in enumerate(reversed(answered[-10:]), 1):
            time_str = q.timestamp.strftime("%d.%m %H:%M")
            answer_time = q.answer_time.strftime("%d.%m %H:%M") if q.answer_time else "—"
            questions_text += f"{i}. #{q.question_id} от @{q.username} - {time_str}\n"
            questions_text += f"   Ответил: {q.answer_admin} ({answer_time})\n\n"

        questions_text += f"📊 Отвеченных вопросов: {len(answered)}"

        await query.edit_message_text(
            questions_text,
            reply_markup=get_questions_menu_keyboard()
        )

    async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Отмена текущего действия"""
        user = update.message.from_user

        await update.message.reply_text(
            "Действие отменено.",
            reply_markup=get_main_keyboard(user.id)
        )

        return ConversationHandler.END

    async def handle_wait(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик кнопки ожидания"""
        query = update.callback_query
        await query.answer()

        user = query.from_user
        user_data = get_user_data(user.id)

        if user_data.can_spin():
            await query.edit_message_text(
                "🎰 **Теперь вы можете крутить спин!**",
                reply_markup=get_main_keyboard(user.id)
            )
        else:
            if user_data.last_spin_date:
                next_spin_time = user_data.last_spin_date + timedelta(hours=24)
                time_left = next_spin_time - datetime.now()
                hours = int(time_left.total_seconds() // 3600)
                minutes = int((time_left.total_seconds() % 3600) // 60)

                await query.edit_message_text(
                    f"⏳ **Вы уже использовали дневной спин!**\n\n"
                    f"Следующий спин будет доступен через:\n"
                    f"**{hours} часов {minutes} минут**\n\n"
                    f"🎁 Используйте промокод для дополнительных спинов!",
                    reply_markup=get_main_keyboard(user.id)
                )

    # === ОСНОВНАЯ ФУНКЦИЯ ===
    def main() -> None:
        """Запуск бота"""
        # Загружаем данные
        load_data()

        # Создаем приложение
        application = Application.builder().token(BOT_TOKEN).build()

        # Создаем ConversationHandler для администратора
        admin_conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(admin_button, pattern="^admin$")],
            states={
                ADMIN_PASSWORD_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_admin_password)]
            },
            fallbacks=[CommandHandler("cancel", cancel)]
        )

        # Создаем ConversationHandler для промокодов
        promocode_conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(enter_promocode, pattern="^enter_promo$")],
            states={
                PROMOCODE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_promocode)]
            },
            fallbacks=[CommandHandler("cancel", cancel)]
        )

        # Создаем ConversationHandler для вопросов
        question_conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(ask_question_button, pattern="^ask_question$")],
            states={
                QUESTION_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question)]
            },
            fallbacks=[CommandHandler("cancel", cancel)]
        )

        # Добавляем обработчики команд
        application.add_handler(CommandHandler("start", start))

        # Добавляем ConversationHandler
        application.add_handler(admin_conv_handler)
        application.add_handler(promocode_conv_handler)
        application.add_handler(question_conv_handler)

        # Добавляем обработчики кнопок
        application.add_handler(CallbackQueryHandler(spin_button, pattern="^spin$"))
        application.add_handler(CallbackQueryHandler(promocode_button, pattern="^promocode$"))
        application.add_handler(CallbackQueryHandler(view_questions_button, pattern="^view_questions$"))
        application.add_handler(CallbackQueryHandler(rewards_button, pattern="^rewards$"))
        application.add_handler(CallbackQueryHandler(stats_button, pattern="^stats$"))
        application.add_handler(CallbackQueryHandler(users_button, pattern="^users$"))
        application.add_handler(CallbackQueryHandler(list_questions_button, pattern="^list_questions$"))
        application.add_handler(CallbackQueryHandler(new_questions_button, pattern="^new_questions$"))
        application.add_handler(CallbackQueryHandler(answered_questions_button, pattern="^answered_questions$"))
        application.add_handler(CallbackQueryHandler(back_to_main, pattern="^back_to_main$"))
        application.add_handler(CallbackQueryHandler(back_to_menu, pattern="^back_to_menu$"))
        application.add_handler(CallbackQueryHandler(handle_wait, pattern="^wait$"))

        # Обработчик ответов администраторов на вопросы
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_reply))

        # Запускаем бота
        logger.info("Бот запущен...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)

    if __name__ == "__main__":
        main()