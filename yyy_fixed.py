import asyncio
import logging
import os
import random
import time
from html import escape
from typing import Optional
from aiohttp import web

from aiogram.filters import Command, CommandStart, StateFilter
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BotCommand, BotCommandScopeChat, BotCommandScopeDefault,
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message,
)
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

# ============= КОНФИГ =============
BOT_TOKEN = ""
ADMINS = {6654986539, 8441673923, 869665716}
ADMIN_PASSWORD = "aecandryshka"
ADMIN_SESSIONS: set[int] = set()
BLOCKED_ADMINS: set[int] = set()
BANNED_USERS: set[int] = set()  # юзеры, заблокированные в боте
SUPPORT_ADMIN_ID = 6654986539  # куда отправлять сообщения поддержки

CHANNELS = ["@andrew_gifts1", "@agifts2", "@andrewgiftschat"]
DONATE_CHANNEL = "https://t.me/Andrew_portal"

MONGO_URL = "mongodb+srv://murka120:murruruaia29303@cluster7987.o574doz.mongodb.net/?appName=Cluster7987"
DB_NAME = os.environ.get("DB_NAME", "andrusho_cards")

CARD_TRIGGERS = {
    "andrusho", "card sir", "card, sir", "card, sir.",
    "andryusho", "andryusha", "andrysh",
}
COMMAND_PREFIXES = ("andrusho", "andryusho", "andryusha", "andrysh", "card sir", "card, sir")

RARITIES = {
    "common":    {"emoji": "💙", "name": "Обычная",       "chance": 50, "points": 1000,  "s": 5},
    "rare":      {"emoji": "💚", "name": "Редкая",        "chance": 33, "points": 2000,  "s": 10},
    "epic":      {"emoji": "💜", "name": "Эпическая",     "chance": 10, "points": 5000,  "s": 25},
    "mythic":    {"emoji": "❤️", "name": "Мифическая",    "chance": 4,  "points": 10000, "s": 50},
    "legendary": {"emoji": "💛", "name": "Легендарная",   "chance": 2,  "points": 20000, "s": 100},
    "limited":   {"emoji": "🖤", "name": "Лимитированная" ,"chance": 1,  "points": 40000, "s": 200},
}

MARKET_PRICES = {
    "common": 15, "rare": 50, "epic": 150,
    "mythic": 400, "legendary": 1000, "limited": 3000,
}

CARD_COOLDOWN = 60 * 60
PREMIUM_CARD_COOLDOWN = 30 * 60
BONUS_COOLDOWN = 3 * 60 * 60
DICE_COOLDOWN = 5 * 60
PREMIUM_DICE_COOLDOWN = 3 * 60

_CHESTS = {
    "common_": {
        "name": "Обычный сундук", "emoji": "🎁",
        "price": 15, "field": "common__chests",
        "weights": {"common": 100},
    },
    "rare_": {
        "name": "Редкий сундук", "emoji": "💚",
        "price": 30, "field": "rare__chests",
        "weights": {"rare": 85, "epic": 15},
    },
    "mythic_": {
        "name": "Мифический сундук", "emoji": "❤️",
        "price": 400, "field": "mythic__chests",
        "weights": {"mythic": 80, "legendary": 17, "limited": 3},
    },
}

CHEST_FIELDS = {
    "bonus": "bonus_chests",
    "epic": "epic_chests",
    "legend": "legend_chests",
    "common_": "common__chests",
    "rare_": "rare__chests",
    "mythic_": "mythic__chests",
}

STAR_CHEST_WEIGHTS = {
    "bonus": {"common": 60, "rare": 30, "epic": 10},
    "epic": {"rare": 40, "epic": 50, "mythic": 10},
    "legend": {"epic": 25, "mythic": 40, "legendary": 30, "limited": 5},
}

AUTO_CHEST_BINDINGS = {
    "common": ["common_", "bonus"],
    "rare": ["rare_", "bonus", "epic"],
    "epic": ["epic", "legend"],
    "mythic": ["mythic_", "epic", "legend"],
    "legendary": ["mythic_", "legend"],
}

ALL_CHEST_TYPES = list(CHEST_FIELDS.keys())
CHEST_LABELS = {
    "bonus": "🎁 Бонусный (звёзды)",
    "epic": "💜 Эпический (звёзды)",
    "legend": "💛 Легендарный (звёзды)",
    "common_": "🎁 Обычный (монеты)",
    "rare_": "💚 Редкий (монеты)",
    "mythic_": "❤️ Мифик (монеты)",
}

RESOURCE_FIELDS = {
    "s":              {"label": "💰 Монеты",            "is_int": True},
    "points":         {"label": "✨ Очки",              "is_int": True},
    "bonus_chests":   {"label": "🎁 Бонусный сундук",   "is_int": True},
    "epic_chests":    {"label": "💜 Эпич сундук (⭐)",  "is_int": True},
    "legend_chests":  {"label": "💛 Лег сундук (⭐)",   "is_int": True},
    "common__chests": {"label": "🎁 Обычный (монеты)",  "is_int": True},
    "rare__chests":   {"label": "💚 Редкий (монеты)",   "is_int": True},
    "mythic__chests": {"label": "❤️ Мифик (монеты)",    "is_int": True},
    "luck_charges":   {"label": "🍀 Заряды удачи",      "is_int": True},
    "premium":        {"label": "🚀 Премиум (дней)",    "is_int": True},
}

ALL_CHEST_FIELDS_LIST = list(CHEST_FIELDS.values())

logging.basicConfig(level=logging.INFO, format="%(asctime)s — %(levelname)s — %(message)s")
log = logging.getLogger("andrusho")

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]
users_col = db["users"]
cards_col = db["cards"]
inventory_col = db["inventory"]
marriages_col = db["marriages"]
proposals_col = db["proposals"]
market_col = db["market"]
logs_col = db["logs"]
admin_logs_col = db["admin_logs"]
chest_cards_col = db["chest_cards"]
banned_col = db["banned_users"]

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)


# ============= УТИЛИТЫ =============
def now_ts() -> int:
    return int(time.time())


def fmt_time_left(seconds: int) -> str:
    seconds = max(0, int(seconds))
    h, m, s = seconds // 3600, (seconds % 3600) // 60, seconds % 60
    parts = []
    if h: parts.append(f"{h}ч.")
    if m: parts.append(f"{m}мин.")
    if s or not parts: parts.append(f"{s}сек.")
    return " ".join(parts)


def get_title(points: int) -> str:
    if points >= 1_000_000: return "Легенда"
    if points >= 500_000: return "Мастер"
    if points >= 100_000: return "Эксперт"
    if points >= 50_000: return "Профи"
    if points >= 10_000: return "Любитель"
    return "Новичок"


def is_admin(uid: int) -> bool:
    if uid in BLOCKED_ADMINS:
        return False
    return uid in ADMINS or uid in ADMIN_SESSIONS


def is_premium(user: dict) -> bool:
    return user.get("premium_until", 0) > now_ts()


def is_banned(uid: int) -> bool:
    return uid in BANNED_USERS


def user_mention(u: dict) -> str:
    uname = u.get("username") or ""
    nick = escape(u.get("nickname") or f"User{u['user_id']}")
    if uname:
        return f"@{uname}"
    return f'<a href="tg://user?id={u["user_id"]}">{nick}</a>'


def tg_user_mention(tg_user) -> str:
    if tg_user.username:
        return f"@{tg_user.username}"
    name = escape(tg_user.first_name or f"User{tg_user.id}")
    return f'<a href="tg://user?id={tg_user.id}">{name}</a>'


async def log_action(user_id: int, action: str, details: str = ""):
    try:
        await logs_col.insert_one({"user_id": user_id, "action": action, "details": details, "ts": now_ts()})
    except Exception as e:
        log.warning("log err: %s", e)


async def admin_log(admin_id: int, action: str, target_id: int = 0, details: str = ""):
    try:
        await admin_logs_col.insert_one({
            "admin_id": admin_id, "target_id": target_id,
            "action": action, "details": details, "ts": now_ts(),
        })
    except Exception as e:
        log.warning("admin_log err: %s", e)


async def load_banned():
    try:
        async for doc in banned_col.find({}):
            BANNED_USERS.add(doc["user_id"])
    except Exception as e:
        log.warning("load_banned err: %s", e)


async def get_or_create_user(tg_user) -> dict:
    user = await users_col.find_one({"user_id": tg_user.id})
    if user:
        upd = {}
        if (tg_user.username or "") != user.get("username", ""):
            upd["username"] = tg_user.username or ""
        if upd:
            await users_col.update_one({"user_id": tg_user.id}, {"$set": upd})
            user.update(upd)
        return user
    new_user = {
        "user_id": tg_user.id,
        "username": tg_user.username or "",
        "nickname": tg_user.first_name or f"User{tg_user.id}",
        "points": 0, "s": 0, "cards_count": 0,
        "favorite_card_id": None,
        "last_card_ts": 0, "last_bonus_ts": 0, "last_dice_ts": 0,
        "bonus_chests": 0, "epic_chests": 0, "legend_chests": 0,
        "common__chests": 0, "rare__chests": 0, "mythic__chests": 0,
        "luck_charges": 0, "premium_until": 0,
        "created_at": now_ts(),
    }
    await users_col.insert_one(new_user)
    await log_action(tg_user.id, "register", f"@{tg_user.username or ''}")
    return new_user


async def find_user_by_query(query: str) -> Optional[dict]:
    query = query.strip()
    if query.startswith("@"):
        query = query[1:]
    try:
        uid = int(query)
        u = await users_col.find_one({"user_id": uid})
        if u:
            return u
    except Exception:
        pass
    return await users_col.find_one({"username": query})


async def roll_card(rarity_override: Optional[str] = None) -> Optional[dict]:
    if rarity_override:
        chosen = rarity_override
    else:
        r = random.random() * 100
        cumulative = 0
        chosen = "common"
        for rarity, data in RARITIES.items():
            cumulative += data["chance"]
            if r < cumulative:
                chosen = rarity
                break
    cards = await cards_col.find({"rarity": chosen}).to_list(length=None)
    if not cards:
        cards = await cards_col.find({}).to_list(length=None)
    return random.choice(cards) if cards else None


async def roll_chest_card(chest_type: str) -> Optional[dict]:
    links = await chest_cards_col.find({"chest_type": chest_type}).to_list(length=None)
    if links:
        ids = []
        for l in links:
            try:
                ids.append(ObjectId(l["card_id"]))
            except Exception:
                pass
        if ids:
            pool = await cards_col.find({"_id": {"$in": ids}}).to_list(length=None)
            if pool:
                return random.choice(pool)

    if chest_type in _CHESTS:
        weights = _CHESTS[chest_type]["weights"]
    elif chest_type in STAR_CHEST_WEIGHTS:
        weights = STAR_CHEST_WEIGHTS[chest_type]
    else:
        weights = {"common": 100}

    rarities = list(weights.keys())
    weights_list = list(weights.values())
    chosen = random.choices(rarities, weights=weights_list)[0]
    return await roll_card(chosen)


async def give_card_to_user(user_id: int, card: dict, premium_bonus: bool = False):
    rd = RARITIES[card["rarity"]]
    points = rd["points"]
    s = int(rd["s"] * 1.5) if premium_bonus else rd["s"]
    existing = await inventory_col.find_one({"user_id": user_id, "card_id": str(card["_id"])})
    if existing:
        await inventory_col.update_one({"_id": existing["_id"]}, {"$inc": {"count": 1}})
    else:
        await inventory_col.insert_one({
            "user_id": user_id, "card_id": str(card["_id"]),
            "count": 1, "obtained_at": now_ts(),
        })
        await users_col.update_one({"user_id": user_id}, {"$inc": {"cards_count": 1}})
    await users_col.update_one(
        {"user_id": user_id},
        {"$inc": {"points": points, "s": s},
         "$set": {"last_card_ts": now_ts()}},
    )
    await log_action(user_id, "card_received", f"{card['name']} +{points}/+{s}")
    u = await users_col.find_one({"user_id": user_id})
    return u["points"], u["s"], points, s


async def take_card_from_user(user_id: int, card_id: str) -> bool:
    inv = await inventory_col.find_one({"user_id": user_id, "card_id": card_id})
    if not inv:
        return False
    if inv["count"] > 1:
        await inventory_col.update_one({"_id": inv["_id"]}, {"$inc": {"count": -1}})
    else:
        await inventory_col.delete_one({"_id": inv["_id"]})
        await users_col.update_one({"user_id": user_id}, {"$inc": {"cards_count": -1}})
    return True


async def wipe_all_cards(user_id: int) -> int:
    """Удалить ВСЕ карты юзера. Возвращает кол-во удалённых записей."""
    res = await inventory_col.delete_many({"user_id": user_id})
    await users_col.update_one({"user_id": user_id}, {"$set": {"cards_count": 0, "favorite_card_id": None}})
    return res.deleted_count


async def wipe_all_chests(user_id: int):
    set_zero = {f: 0 for f in ALL_CHEST_FIELDS_LIST}
    await users_col.update_one({"user_id": user_id}, {"$set": set_zero})


async def wipe_resource(user_id: int, field: str):
    await users_col.update_one({"user_id": user_id}, {"$set": {field: 0}})


async def auto_add_card_to_chests(card_id: str, card_name: str, rarity: str):
    if rarity not in AUTO_CHEST_BINDINGS:
        return []
    added_to = []
    for chest_type in AUTO_CHEST_BINDINGS[rarity]:
        existing = await chest_cards_col.find_one({"chest_type": chest_type, "card_id": card_id})
        if not existing:
            await chest_cards_col.insert_one({
                "chest_type": chest_type, "card_id": card_id,
                "auto_added": True, "created_at": now_ts(),
            })
            added_to.append(chest_type)
    return added_to


async def auto_add_card_to_market(card: dict):
    rarity = card["rarity"]
    if rarity not in MARKET_PRICES:
        return False
    price = MARKET_PRICES[rarity]
    card_id = str(card["_id"])
    existing = await market_col.find_one({"card_id": card_id})
    if existing:
        return False
    await market_col.insert_one({
        "card_id": card_id, "name": card["name"], "rarity": rarity,
        "photo_id": card.get("photo_id"), "price": price,
        "auto_added": True, "created_at": now_ts(),
    })
    return True


# ============= СОСТОЯНИЯ =============
class AddCardFSM(StatesGroup):
    rarity = State()
    name = State()
    photo = State()


class AdminLogin(StatesGroup):
    waiting_password = State()


class BlockAdminFSM(StatesGroup):
    target_id = State()


class BanUserFSM(StatesGroup):
    target = State()
    unban_target = State()


class SupportFSM(StatesGroup):
    waiting_message = State()


class ResourceFSM(StatesGroup):
    resource_type = State()
    card_rarity = State()
    card_pick = State()
    amount = State()
    target_choice = State()
    target_query = State()


def _is_cmd(msg: Message) -> bool:
    return bool(msg.text and msg.text.startswith("/"))


# ============= БАН-ГВАРД =============
@router.message(F.func(lambda m: m.from_user and is_banned(m.from_user.id)))
async def banned_msg(msg: Message, state: FSMContext):
    await state.clear()
    try:
        await msg.reply("🚫 Вы заблокированы в боте.")
    except Exception:
        pass


@router.callback_query(F.func(lambda c: c.from_user and is_banned(c.from_user.id)))
async def banned_cb(cq: CallbackQuery):
    await cq.answer("🚫 Вы заблокированы в боте.", show_alert=True)


# ============= /start =============
@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    await get_or_create_user(msg.from_user)
    await log_action(msg.from_user.id, "start", "")
    text = (
        "👋 <b>Привет!</b> Тут ты собираешь карточки <b>Andrusho</b>\n\n"
        "<b>Как получить карточки?</b>\n"
        "<blockquote>Отправь <code>andrusho</code> в чат</blockquote>\n\n"
        "Все команды — /help"
    )
    rows = [
        [InlineKeyboardButton(text="📋 Помощь", callback_data="help")],
        [InlineKeyboardButton(text="📞 Поддержка", callback_data="support")],
    ]
    if not is_admin(msg.from_user.id):
        rows.append([InlineKeyboardButton(text="🔑 Взять администратора", callback_data="take_admin")])
    else:
        rows.append([InlineKeyboardButton(text="👑 Админ-панель", callback_data="open_admin")])
    await msg.reply(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data == "help")
async def cb_help(cq: CallbackQuery):
    await cmd_help(cq.message)
    await cq.answer()


@router.message(Command("help"))
async def cmd_help(msg: Message):
    triggers = "\n".join([f"• <code>{t}</code>" for t in sorted(CARD_TRIGGERS)])
    text = (
        "<b>Команды</b>\n<blockquote>"
        "👤 /profile — профиль\n"
        "🃏 /andrusho — искать карту\n"
        "🏆 /top — топ\n"
        "🎁 /bonus — бонусный сундук\n"
        "🛍 /shop — магазин\n"
        "🚀 /premium — премиум\n"
        "🎲 /diceplay — кости\n"
        "🎭 /roleplay — РП\n"
        "💍 /marriage — брак\n"
        "🏪 /market — маркет\n"
        "📜 /index — индекс карт\n"
        "✨ /name [ник] — сменить ник\n"
        "📞 /support — поддержка\n"
        "🆔 /myid — мой ID"
        "</blockquote>\n\n"
        f"<b>Триггеры карты</b>\n<blockquote>{triggers}</blockquote>"
    )
    await msg.reply(text)


@router.message(Command("myid"))
async def cmd_myid(msg: Message):
    await msg.reply(f"Ваш ID: <code>{msg.from_user.id}</code>")


# ============= ПОДДЕРЖКА =============
@router.callback_query(F.data == "support")
async def cb_support(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(SupportFSM.waiting_message)
    await cq.message.reply(
        "📞 <b>Поддержка</b>\n\nНапишите ваше сообщение одним сообщением — оно будет отправлено администратору.\n"
        "Для отмены — /cancel"
    )
    await cq.answer()


@router.message(Command("support"))
async def cmd_support(msg: Message, state: FSMContext):
    await state.clear()
    await state.set_state(SupportFSM.waiting_message)
    await msg.reply(
        "📞 <b>Поддержка</b>\n\nНапишите ваше сообщение одним сообщением — оно будет отправлено администратору.\n"
        "Для отмены — /cancel"
    )


@router.message(SupportFSM.waiting_message)
async def fsm_support_msg(msg: Message, state: FSMContext):
    if _is_cmd(msg):
        await state.clear()
        return
    text = (msg.text or msg.caption or "").strip()
    if not text:
        await msg.reply("Пришлите текстом, пожалуйста, или /cancel")
        return
    u = await get_or_create_user(msg.from_user)
    forward = (
        f"📞 <b>Поддержка</b> от {tg_user_mention(msg.from_user)}\n"
        f"🆔 <code>{msg.from_user.id}</code> · ник: <b>{escape(u.get('nickname' ,''))}</b>\n\n"
        f"<blockquote>{escape(text)}</blockquote>\n\n"
        f"Ответить: <code>/replyuser {msg.from_user.id} текст</code>"
    )
    try:
        await bot.send_message(SUPPORT_ADMIN_ID, forward)
        await msg.reply("✅ Ваше сообщение отправлено в поддержку. Ответ придёт сюда же.")
        await log_action(msg.from_user.id, "support", text[:200])
    except Exception as e:
        log.warning("support send err: %s", e)
        await msg.reply("❌ Не удалось отправить. Попробуйте позже.")
    await state.clear()


@router.message(Command("replyuser"))
async def cmd_replyuser(msg: Message):
    if msg.from_user.id != SUPPORT_ADMIN_ID and not is_admin(msg.from_user.id):
        return
    parts = msg.text.split(maxsplit=2)
    if len(parts) < 3:
        await msg.reply("Формат: <code>/replyuser user_id текст</code>")
        return
    try:
        uid = int(parts[1])
    except Exception:
        await msg.reply("❌ Неверный user_id")
        return
    text = parts[2]
    try:
        await bot.send_message(uid, f"📞 <b>Ответ поддержки:</b>\n\n<blockquote>{escape(text)}</blockquote>")
        await msg.reply("✅ Отправлено")
    except Exception as e:
        await msg.reply(f"❌ Ошибка: {e}")


# ============= /profile =============
@router.message(Command("profile"))
async def cmd_profile(msg: Message):
    user = await get_or_create_user(msg.from_user)
    total_cards = await cards_col.count_documents({})
    fav_text, fav_photo = "—", None
    if user.get("favorite_card_id"):
        try:
            fav = await cards_col.find_one({"_id": ObjectId(user["favorite_card_id"])})
            if fav:
                fav_text = fav["name"]
                fav_photo = fav.get("photo_id")
        except Exception:
            pass
    prem_mark = " 💎" if is_premium(user) else ""
    text = (
        f"<b>Профиль «{escape(user['nickname'])}»{prem_mark}</b> ({tg_user_mention(msg.from_user)})\n\n<blockquote>"
        f"🔎 ID • <code>{user['user_id']}</code>\n"
        f"🃏 Карт • <b>{user.get('cards_count' ,0)}</b> из <b>{total_cards}</b>\n"
        f"✨ Очки • <b>{user.get('points' ,0):,}</b>\n"
        f"💰 Монеты • <b>{user.get('s' ,0)}</b>\n"
        f"🏆 Титул • <b>{get_title(user.get('points' ,0))}</b>\n"
        f"❤️ Любимая карта • <b>{escape(fav_text)}</b>"
        f"{chr(10) + '🚀 PREMIUM до ' + time.strftime('%d.%m.%Y', time.localtime(user['premium_until'])) if is_premium(user) else ''}"
        f"</blockquote>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎒 Инвентарь", callback_data="inventory")],
        [InlineKeyboardButton(text="🃏 Мои карты", callback_data=f"mc:{msg.from_user.id}:0")],
        [InlineKeyboardButton(text="📦 Мои сундуки", callback_data="open_chests")],
    ])
    if fav_photo:
        try:
            await msg.reply_photo(fav_photo, caption=text, reply_markup=kb)
            return
        except Exception:
            pass
    await msg.reply(text, reply_markup=kb)


@router.message(Command("name"))
async def cmd_name(msg: Message):
    parts = msg.text.split(maxsplit=1)
    if len(parts) < 2:
        await msg.reply("<b>Использование:</b> /name [ник]")
        return
    new_name = parts[1].strip()[:32]
    await get_or_create_user(msg.from_user)
    await users_col.update_one({"user_id": msg.from_user.id}, {"$set": {"nickname": new_name}})
    await msg.reply(f"✅ Никнейм: <b>{escape(new_name)}</b>")


@router.callback_query(F.data == "inventory")
async def cb_inventory(cq: CallbackQuery):
    user = await get_or_create_user(cq.from_user)
    text = (
        f"🎒 <b>Инвентарь</b> ({tg_user_mention(cq.from_user)})\n\n<blockquote>"
        f"💰 Монеты • {user.get('s' ,0)}\n"
        f"✨ Очки • {user.get('points' ,0):,}\n"
        f"🎁 Бонусный сундук • {user.get('bonus_chests' ,0)}\n"
        f"💜 Эпический сундук • {user.get('epic_chests' ,0)}\n"
        f"💛 Легендарный сундук • {user.get('legend_chests' ,0)}\n"
        f"🎁 Обычный (монеты) • {user.get('common__chests' ,0)}\n"
        f"💚 Редкий (монеты) • {user.get('rare__chests' ,0)}\n"
        f"❤️ Мифический (монеты) • {user.get('mythic__chests' ,0)}\n"
        f"🍀 Удача (зарядов) • {user.get('luck_charges' ,0)}\n"
        f"🚀 Premium • {'до ' + time.strftime('%d.%m.%Y', time.localtime(user['premium_until'])) if is_premium(user) else 'нет'}"
        f"</blockquote>"
    )
    await cq.message.reply(text)
    await cq.answer()


# ============= МОИ КАРТЫ — пагинация, без фото, только владелец =============
PER_PAGE_MYCARDS = 20


async def _build_mycards_page(owner_id: int, page: int):
    items = await inventory_col.find({"user_id": owner_id}).to_list(length=None)
    if not items:
        return None, None
    # Подгружаем карты и сортируем по редкости
    rarity_order = list(RARITIES.keys())
    enriched = []
    for it in items:
        try:
            c = await cards_col.find_one({"_id": ObjectId(it["card_id"])})
            if c:
                enriched.append((c, it["count"]))
        except Exception:
            continue
    enriched.sort \
        (key=lambda x: (rarity_order.index(x[0]["rarity"]) if x[0]["rarity"] in rarity_order else 99, x[0]["name"]))
    total = len(enriched)
    total_pages = max(1, (total - 1) // PER_PAGE_MYCARDS + 1)
    page = max(0, min(page, total_pages - 1))
    chunk = enriched[page * PER_PAGE_MYCARDS:(page + 1) * PER_PAGE_MYCARDS]
    lines = [f"🃏 <b>Мои карты</b> ({total}) — стр. {page +1}/{total_pages}\n"]
    for c, cnt in chunk:
        rd = RARITIES.get(c["rarity"], {"emoji": "❔", "name": "?"})
        lines.append(f"{rd['emoji']} <b>{escape(c['name'])}</b> ×{cnt}")

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"mc:{owner_id}:{page -1}"))
    if (page + 1) < total_pages:
        nav.append(InlineKeyboardButton(text="Дальше ▶️", callback_data=f"mc:{owner_id}:{page +1}"))
    rows = []
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="❤️ Сделать любимой", callback_data=f"favpick:{owner_id}:0")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    return "\n".join(lines), kb


@router.callback_query(F.data.startswith("mc:"))
async def cb_mycards_page(cq: CallbackQuery):
    parts = cq.data.split(":")
    owner_id = int(parts[1])
    page = int(parts[2])
    if cq.from_user.id != owner_id:
        await cq.answer("❌ Это не ваше меню", show_alert=True)
        return
    text, kb = await _build_mycards_page(owner_id, page)
    if text is None:
        await cq.answer("У вас пока нет карт. Напишите «andrusho» в чат.", show_alert=True)
        return
    # Удаляем предыдущее и присылаем новое (только если это не первое открытие из профиля)
    if page > 0 or "Дальше" in (cq.message.text or "") or "стр." in (cq.message.text or ""):
        try:
            await cq.message.delete()
        except Exception:
            pass
        await bot.send_message(cq.message.chat.id, text, reply_markup=kb)
    else:
        await cq.message.reply(text, reply_markup=kb)
    await cq.answer()


# ----- Выбор любимой карты -----
PER_PAGE_FAVPICK = 20


@router.callback_query(F.data.startswith("favpick:"))
async def cb_fav_pick(cq: CallbackQuery):
    parts = cq.data.split(":")
    owner_id = int(parts[1])
    page = int(parts[2])
    if cq.from_user.id != owner_id:
        await cq.answer("❌ Это не ваше меню", show_alert=True)
        return
    items = await inventory_col.find({"user_id": owner_id}).to_list(length=None)
    if not items:
        await cq.answer("У вас нет карт", show_alert=True)
        return
    rarity_order = list(RARITIES.keys())
    enriched = []
    for it in items:
        try:
            c = await cards_col.find_one({"_id": ObjectId(it["card_id"])})
            if c:
                enriched.append(c)
        except Exception:
            continue
    enriched.sort(key=lambda c: (rarity_order.index(c["rarity"]) if c["rarity"] in rarity_order else 99, c["name"]))
    total = len(enriched)
    total_pages = max(1, (total - 1) // PER_PAGE_FAVPICK + 1)
    page = max(0, min(page, total_pages - 1))
    chunk = enriched[page * PER_PAGE_FAVPICK:(page + 1) * PER_PAGE_FAVPICK]

    rows = []
    for c in chunk:
        rd = RARITIES.get(c["rarity"], {"emoji": "❔"})
        rows.append([InlineKeyboardButton(
            text=f"{rd['emoji']} {c['name'][:40]}",
            callback_data=f"favset:{owner_id}:{c['_id']}"
        )])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"favpick:{owner_id}:{page -1}"))
    if (page + 1) < total_pages:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"favpick:{owner_id}:{page +1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="🚫 Убрать любимую", callback_data=f"favset:{owner_id}:none")])

    try:
        await cq.message.delete()
    except Exception:
        pass
    await bot.send_message(
        cq.message.chat.id,
        f"❤️ <b>Выберите любимую карту</b> — стр. {page +1}/{total_pages}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await cq.answer()


@router.callback_query(F.data.startswith("favset:"))
async def cb_fav_set(cq: CallbackQuery):
    parts = cq.data.split(":")
    owner_id = int(parts[1])
    card_id = parts[2]
    if cq.from_user.id != owner_id:
        await cq.answer("❌ Это не ваше меню", show_alert=True)
        return
    if card_id == "none":
        await users_col.update_one({"user_id": owner_id}, {"$set": {"favorite_card_id": None}})
        await cq.answer("✅ Любимая карта снята", show_alert=True)
        try:
            await cq.message.delete()
        except Exception:
            pass
        return
    try:
        c = await cards_col.find_one({"_id": ObjectId(card_id)})
    except Exception:
        c = None
    if not c:
        await cq.answer("❌ Карта не найдена", show_alert=True)
        return
    # Проверяем, что эта карта есть в инвентаре
    inv = await inventory_col.find_one({"user_id": owner_id, "card_id": card_id})
    if not inv:
        await cq.answer("❌ Этой карты нет у вас в инвентаре", show_alert=True)
        return
    await users_col.update_one({"user_id": owner_id}, {"$set": {"favorite_card_id": card_id}})
    await cq.answer(f"✅ Любимая: {c['name']}", show_alert=True)
    try:
        await cq.message.delete()
    except Exception:
        pass


# ============= ПОЛУЧЕНИЕ КАРТЫ =============
async def try_give_card(msg: Message):
    user = await get_or_create_user(msg.from_user)
    cd = PREMIUM_CARD_COOLDOWN if is_premium(user) else CARD_COOLDOWN
    now = now_ts()

    # АТОМАРНАЯ проверка + установка кулдауна.
    # Обновится ТОЛЬКО если с прошлого раза реально прошло >= cd секунд.
    locked = await users_col.find_one_and_update(
        {"user_id": msg.from_user.id, "last_card_ts": {"$lte": now - cd}},
        {"$set": {"last_card_ts": now}},
    )
    if not locked:
        fresh = await users_col.find_one({"user_id": msg.from_user.id})
        left = cd - (now - fresh.get("last_card_ts", 0))
        await msg.reply(
            f"Вы посмотрели, но <b>Andrusho</b> не было рядом 🙈\n\n⏳ <b>{fmt_time_left(left)}</b>"
        )
        return

    rarity_override = None
    if user.get("luck_charges", 0) > 0:
        rarity_override = random.choices(
            ["rare", "epic", "mythic", "legendary", "limited"],
            weights=[45, 30, 15, 8, 2],
        )[0]
        await users_col.update_one(
            {"user_id": msg.from_user.id, "luck_charges": {"$gt": 0}},
            {"$inc": {"luck_charges": -1}},
        )

    card = await roll_card(rarity_override)
    if not card:
        # откатим кулдаун — карты в базе нет, нечестно жечь его
        await users_col.update_one(
            {"user_id": msg.from_user.id},
            {"$set": {"last_card_ts": user.get("last_card_ts", 0)}},
        )
        await msg.reply("😿 Карт в базе нет")
        return

    new_p, new_c, gp, gc = await give_card_to_user(
        msg.from_user.id, card, premium_bonus=is_premium(user)
    )
    rd = RARITIES[card["rarity"]]
    caption = (
        f"👻 <b>«{escape(card['name'])}»</b> для {tg_user_mention(msg.from_user)}\n\n<blockquote>"
        f"💎 {rd['emoji']} {rd['name']}\n"
        f"✨ +{gp:,} [{new_p:,}]\n"
        f"💰 +{gc} [{new_c}]"
        f"</blockquote>\n\n🎁 /bonus раз в 3ч"
    )
    try:
        if card.get("photo_id"):
            await msg.reply_photo(card["photo_id"], caption=caption)
        else:
            await msg.reply(caption)
    except Exception:
        await msg.reply(caption)


# ============= ПОДПИСКА / BONUS =============
async def check_subs(user_id: int) -> list:
    not_subbed = []
    for ch in CHANNELS:
        try:
            m = await bot.get_chat_member(ch, user_id)
            if m.status in ("left", "kicked"):
                not_subbed.append(ch)
        except Exception as e:
            log.info("check_subs %s: %s", ch, e)
    return not_subbed


@router.message(Command("bonus"))
async def cmd_bonus(msg: Message):
    user = await get_or_create_user(msg.from_user)
    not_subbed = await check_subs(msg.from_user.id)
    if not_subbed:
        rows = [[InlineKeyboardButton(text=f"📢 {ch}", url=f"https://t.me/{ch.lstrip('@')}")] for ch in not_subbed]
        rows.append([InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_subs")])
        await msg.reply(
            "🎁 <b>Подпишись и получи бонусный сундук!</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
        return

    now = now_ts()
    amount = 2 if is_premium(user) else 1

    # АТОМАРНО: проверка кулдауна + начисление сундуков + апдейт ts одной операцией
    locked = await users_col.find_one_and_update(
        {"user_id": msg.from_user.id, "last_bonus_ts": {"$lte": now - BONUS_COOLDOWN}},
        {"$set": {"last_bonus_ts": now}, "$inc": {"bonus_chests": amount}},
    )
    if not locked:
        fresh = await users_col.find_one({"user_id": msg.from_user.id})
        left = BONUS_COOLDOWN - (now - fresh.get("last_bonus_ts", 0))
        await msg.reply(f"🎁 Следующий бонус через <b>{fmt_time_left(left)}</b>")
        return

    await log_action(msg.from_user.id, "bonus", f"+{amount}")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Открыть сундуки", callback_data="open_chests")]
    ])
    await msg.reply(
        f"🎉 {tg_user_mention(msg.from_user)} получил <b>{amount}</b> бонусный сундук!",
        reply_markup=kb,
    )


@router.callback_query(F.data == "check_subs")
async def cb_check_subs(cq: CallbackQuery):
    not_subbed = await check_subs(cq.from_user.id)
    if not_subbed:
        await cq.answer("❌ Ты ещё не подписан", show_alert=True)
        return
    await cq.answer("✅ Подписка ок! Жми /bonus", show_alert=True)


# ============= ТОП =============
@router.message(Command("top"))
async def cmd_top(msg: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✨ По очкам", callback_data=f"top:points:{msg.from_user.id}")],
        [InlineKeyboardButton(text="🃏 По картам", callback_data=f"top:cards_count:{msg.from_user.id}")],
        [InlineKeyboardButton(text="💰 По монетам", callback_data=f"top:s:{msg.from_user.id}")],
    ])
    await msg.reply("🏆 <b>Топ 10</b>\nВыберите критерий:", reply_markup=kb)


@router.callback_query(F.data.startswith("top:"))
async def cb_top(cq: CallbackQuery):
    parts = cq.data.split(":")
    field = parts[1]
    owner_id = int(parts[2]) if len(parts) > 2 else cq.from_user.id
    if cq.from_user.id != owner_id:
        await cq.answer("❌ Это не ваше меню", show_alert=True)
        return
    if field not in ("points", "cards_count", "s"):
        await cq.answer("❌", show_alert=True)
        return
    try:
        users = await users_col.find({field: {"$gt": 0}}).sort(field, -1).limit(10).to_list(length=10)
    except Exception:
        log.exception("top error")
        await cq.message.reply("❌ Ошибка получения топа")
        await cq.answer()
        return
    if not users:
        await cq.message.reply("Топ пуст")
        await cq.answer()
        return
    titles = {"points": "по очкам ✨", "cards_count": "по картам 🃏", "s": "по монетам 💰"}
    lines = [f"🏆 <b>Топ 10 {titles[field]}</b>\n"]
    medals = ["🥇", "🥈", "🥉"] + [f"<b>{i}.</b>" for i in range(4, 11)]
    for i, u in enumerate(users):
        val = u.get(field, 0)
        if field == "points":
            val = f"{val:,}"
        prem = " 💎" if is_premium(u) else ""
        lines.append(f"{medals[i]} {user_mention(u)}{prem} • {val}")
    await cq.message.reply("\n".join(lines))
    await cq.answer()


# ============= МАГАЗИН =============
@router.message(Command("shop"))
async def cmd_shop(msg: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Сундуки (⭐)", callback_data="shop:chests")],
        [InlineKeyboardButton(text="🪙 Сундуки (монеты)", callback_data="shop:_chests")],
        [InlineKeyboardButton(text="⚡ Бустеры (монеты)", callback_data="shop:items")],
        [InlineKeyboardButton(text="🚀 Premium (⭐)", callback_data="shop:premium")],
    ])
    await msg.reply("🛍 <b>Магазин</b>", reply_markup=kb)


@router.callback_query(F.data == "shop:chests")
async def cb_shop_chests(cq: CallbackQuery):
    text = (
        "📦 <b>Сундуки за звёзды</b>\n\n<blockquote>"
        "💜 Эпический — <b>15 ⭐</b>\n"
        "💛 Легендарный — <b>50 ⭐</b>\n\n"
        f"Чтобы купить — отправьте <b>звёзды</b> на канал {DONATE_CHANNEL}"
        "</blockquote>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💜 Эпический [⭐15]", callback_data="star_buy")],
        [InlineKeyboardButton(text="💛 Легендарный [⭐50]", callback_data="star_buy")],
        [InlineKeyboardButton(text="🔗 Перейти в канал", url=DONATE_CHANNEL)],
    ])
    await cq.message.reply(text, reply_markup=kb)
    await cq.answer()


@router.callback_query(F.data == "shop:_chests")
async def cb_shop__chests(cq: CallbackQuery):
    user = await get_or_create_user(cq.from_user)
    text = (
        "🪙 <b>Сундуки за монеты</b>\n\n<blockquote>"
        f"🎁 Обычный — <b>{_CHESTS['common_']['price']}</b> монет\n"
        f"💚 Редкий — <b>{_CHESTS['rare_']['price']}</b> монет\n"
        f"❤️ Мифический — <b>{_CHESTS['mythic_']['price']}</b> монет\n\n"
        f"💰 Баланс: <b>{user['s']}</b>"
        "</blockquote>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🎁 Обычный [{_CHESTS['common_']['price']}💰]", callback_data="buy__chest:common_")],
        [InlineKeyboardButton(text=f"💚 Редкий [{_CHESTS['rare_']['price']}💰]", callback_data="buy__chest:rare_")],
        [InlineKeyboardButton(text=f"❤️ Мифический [{_CHESTS['mythic_']['price']}💰]", callback_data="buy__chest:mythic_")],
    ])
    await cq.message.reply(text, reply_markup=kb)
    await cq.answer()


@router.callback_query(F.data.startswith("buy__chest:"))
async def cb_buy__chest(cq: CallbackQuery):
    chest_type = cq.data.split(":", 1)[1]
    if chest_type not in _CHESTS:
        await cq.answer("❌", show_alert=True)
        return
    chest = _CHESTS[chest_type]
    user = await get_or_create_user(cq.from_user)
    if user["s"] < chest["price"]:
        await cq.answer(f"❌ Нужно {chest['price']} монет", show_alert=True)
        return
    result = await users_col.update_one(
        {"user_id": cq.from_user.id, "s": {"$gte": chest["price"]}},
        {"$inc": {"s": -chest["price"], chest["field"]: 1}}
    )
    if result.modified_count == 0:
        await cq.answer("❌ Недостаточно монет", show_alert=True)
        return
    await log_action(cq.from_user.id, "buy__chest", f"{chest_type} -{chest['price']}")
    await cq.answer(f"✅ {chest['name']} куплен!", show_alert=True)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📦 Открыть", callback_data="open_chests")]])
    await cq.message.reply(f"🎉 {tg_user_mention(cq.from_user)} купил <b>{chest['name']}</b>!", reply_markup=kb)


@router.callback_query(F.data == "shop:items")
async def cb_shop_items(cq: CallbackQuery):
    user = await get_or_create_user(cq.from_user)
    text = (
        f"⚡ <b>Бустеры за монеты</b>\n\n<blockquote>"
        f"⏱ Ускоритель — <b>80</b> монет (сброс кулдауна карты)\n"
        f"🍀 Удача — <b>25</b> монет (повышенная редкость)\n\n"
        f"💰 Баланс: <b>{user['s']}</b></blockquote>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏱ Ускоритель [80💰]", callback_data="buy_item:speed")],
        [InlineKeyboardButton(text="🍀 Удача [25💰]", callback_data="buy_item:luck")],
    ])
    await cq.message.reply(text, reply_markup=kb)
    await cq.answer()


@router.callback_query(F.data.startswith("buy_item:"))
async def cb_buy_item(cq: CallbackQuery):
    item = cq.data.split(":", 1)[1]
    prices = {"speed": 80, "luck": 25}
    price = prices[item]
    user = await get_or_create_user(cq.from_user)
    if user["s"] < price:
        await cq.answer(f"❌ Нужно {price} монет", show_alert=True)
        return
    if item == "speed":
        await users_col.update_one({"user_id": cq.from_user.id},
                                   {"$inc": {"s": -price}, "$set": {"last_card_ts": 0}})
        await cq.answer("⏱ Кулдаун сброшен!", show_alert=True)
    else:
        await users_col.update_one({"user_id": cq.from_user.id},
                                   {"$inc": {"s": -price, "luck_charges": 1}})
        await cq.answer("🍀 Удача активирована!", show_alert=True)
    await log_action(cq.from_user.id, "buy_item", item)


@router.callback_query(F.data == "shop:premium")
async def cb_shop_premium(cq: CallbackQuery):
    await cmd_premium(cq.message)
    await cq.answer()


@router.message(Command("premium"))
async def cmd_premium(msg: Message):
    text = (
        "🚀 <b>Premium — 30 ⭐</b>\n\n<blockquote>"
        "1. ⏳ Карта раз в <b>30 мин</b>\n"
        "2. 🎲 Кости раз в <b>3 минуты</b>\n"
        "3. 💎 Алмаз рядом с ником в топе\n"
        "4. 🎁 Двойной бонус: <b>2 сундука</b> при /bonus\n"
        "5. 🍀 Повышенный шанс легендарок\n"
        "6. 🌟 Отметка <b>PREMIUM</b> в профиле\n"
        "7. 💰 <b>+50%</b> монет за карту\n\n"
        "Срок: <b>30 дней</b>\n"
        f"💳 Чтобы купить — отправьте <b>30 ⭐</b> на канал {DONATE_CHANNEL}"
        "</blockquote>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Купить Premium [⭐30]", callback_data="star_buy")],
        [InlineKeyboardButton(text="🔗 Перейти в канал", url=DONATE_CHANNEL)],
    ])
    await msg.reply(text, reply_markup=kb)


@router.callback_query(F.data == "star_buy")
async def cb_star_buy(cq: CallbackQuery):
    await cq.answer("❌ Пока недоступно", show_alert=True)


# ============= СУНДУКИ =============
@router.callback_query(F.data == "open_chests")
async def cb_open_chests(cq: CallbackQuery):
    user = await get_or_create_user(cq.from_user)
    text_parts = [f"📦 <b>Твои сундуки</b> ({tg_user_mention(cq.from_user)})\n\n<blockquote>"]
    for key, field in CHEST_FIELDS.items():
        n = user.get(field, 0)
        text_parts.append(f"{CHEST_LABELS[key]}: <b>{n}</b>")
    text_parts.append("</blockquote>")
    text = "\n".join(text_parts)
    rows = []
    for key, field in CHEST_FIELDS.items():
        n = user.get(field, 0)
        if n > 0:
            rows.append([InlineKeyboardButton(text=f"{CHEST_LABELS[key]} ({n})", callback_data=f"open_chest:{key}")])
    rows.append([InlineKeyboardButton(text="🛒 Купить (монеты)", callback_data="shop:_chests")])
    rows.append([InlineKeyboardButton(text="🛒 Купить (⭐)", url=DONATE_CHANNEL)])
    await cq.message.reply(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await cq.answer()


@router.callback_query(F.data.startswith("open_chest:"))
async def cb_open_chest(cq: CallbackQuery):
    kind = cq.data.split(":", 1)[1]
    if kind not in CHEST_FIELDS:
        await cq.answer("❌", show_alert=True)
        return
    field = CHEST_FIELDS[kind]
    user = await get_or_create_user(cq.from_user)
    if user.get(field, 0) < 1:
        await cq.answer("❌ Нет таких сундуков", show_alert=True)
        return
    card = await roll_chest_card(kind)
    if not card:
        await cq.answer("❌ В сундуке нет карт", show_alert=True)
        return
    await users_col.update_one({"user_id": cq.from_user.id}, {"$inc": {field: -1}})
    await give_card_to_user(cq.from_user.id, card, premium_bonus=is_premium(user))
    rd = RARITIES[card["rarity"]]
    caption = (
        f"📦 <b>Из сундука выпало для {tg_user_mention(cq.from_user)}:</b>\n\n<b>«{escape(card['name'])}»</b>\n<blockquote>"
        f"💎 {rd['emoji']} {rd['name']}\n✨ +{rd['points']:,}\n💰 +{rd['s']}</blockquote>"
    )
    if card.get("photo_id"):
        await cq.message.reply_photo(card["photo_id"], caption=caption)
    else:
        await cq.message.reply(caption)
    await cq.answer()


# ============= ИНДЕКС =============
# idx:<key>:<page>:<owner_id>  — открыть/листать. Только owner может листать
@router.message(Command("index"))
async def cmd_index(msg: Message):
    rows = [
        [InlineKeyboardButton(text=f"{d['emoji']} {d['name']}", callback_data=f"idx:{r}:0:{msg.from_user.id}")]
        for r, d in RARITIES.items()
    ]
    rows.append([InlineKeyboardButton(text="📜 Все (список)", callback_data=f"idx:all:0:{msg.from_user.id}")])
    total = await cards_col.count_documents({})
    await msg.reply(f"📜 <b>Индекс карт</b> ({total})\nВыберите редкость:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("idx:"))
async def cb_index(cq: CallbackQuery):
    parts = cq.data.split(":")
    key = parts[1]
    page = int(parts[2]) if len(parts) > 2 else 0
    owner_id = int(parts[3]) if len(parts) > 3 else cq.from_user.id
    if cq.from_user.id != owner_id:
        await cq.answer("❌ Это не ваше меню", show_alert=True)
        return

    per_page = 30
    if key == "all":
        cards = await cards_col.find({}).sort("rarity", 1).to_list(length=None)
        title_emoji, title_name = "📜", "Все карты"
    else:
        if key not in RARITIES:
            await cq.answer("❌", show_alert=True)
            return
        cards = await cards_col.find({"rarity": key}).to_list(length=None)
        rd = RARITIES[key]
        title_emoji, title_name = rd["emoji"], f"{rd['name']} карты"
    if not cards:
        await cq.answer(f"В категории {title_name} карт нет", show_alert=True)
        return

    total = len(cards)
    total_pages = max(1, (total - 1) // per_page + 1)
    page = max(0, min(page, total_pages - 1))
    chunk = cards[page * per_page:(page + 1) * per_page]

    lines = [f"{title_emoji} <b>{title_name} ({total})</b> — стр. {page +1}/{total_pages}\n"]
    for c in chunk:
        rd = RARITIES.get(c["rarity"], {"emoji": "❔"})
        lines.append(f"{rd['emoji']} <b>{escape(c['name'])}</b>")

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"idx:{key}:{page-1}:{owner_id}"))
    if (page + 1) < total_pages:
        nav.append(InlineKeyboardButton(text="Дальше ▶️", callback_data=f"idx:{key}:{page+1}:{owner_id}"))
    kb = InlineKeyboardMarkup(inline_keyboard=[nav]) if nav else None

    # Если это листание (page > 0 или меняем категорию из прошлого списка) — удаляем предыдущее
    is_paginate = page > 0 or ("стр." in (cq.message.text or ""))
    if is_paginate:
        try:
            await cq.message.delete()
        except Exception:
            pass
        await bot.send_message(cq.message.chat.id, "\n".join(lines), reply_markup=kb)
    else:
        await cq.message.reply("\n".join(lines), reply_markup=kb)
    await cq.answer()


# ============= МАРКЕТ =============
@router.message(Command("market"))
async def cmd_market(msg: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{d['emoji']} {d['name']}", callback_data=f"mk:{r}:{msg.from_user.id}")]
        for r, d in RARITIES.items()
    ])
    await msg.reply("🏪 <b>Маркетплейс</b>\nВыберите редкость:", reply_markup=kb)


@router.callback_query(F.data.startswith("mk:"))
async def cb_market(cq: CallbackQuery):
    parts = cq.data.split(":")
    rarity = parts[1]
    owner_id = int(parts[2]) if len(parts) > 2 else cq.from_user.id
    if cq.from_user.id != owner_id:
        await cq.answer("❌ Это не ваше меню", show_alert=True)
        return
    if rarity not in RARITIES:
        await cq.answer("❌", show_alert=True)
        return
    items = await market_col.find({"rarity": rarity}).to_list(length=30)
    if not items:
        await cq.message.reply(f"{tg_user_mention(cq.from_user)}, в <b>{RARITIES[rarity]['name']}</b> пусто")
        await cq.answer()
        return
    rd = RARITIES[rarity]
    await cq.message.reply(f"🏪 <b>Маркет ({rd['emoji']} {rd['name']})</b> для {tg_user_mention(cq.from_user)}")
    for it in items:
        cap = f"{rd['emoji']} <b>{escape(it['name'])}</b>\n💰 <b>{it['price']}</b> монет"
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=f"🛒 Купить [{it['price']}💰]", callback_data=f"mkbuy:{it['_id']}")
        ]])
        if it.get("photo_id"):
            try:
                await cq.message.reply_photo(it["photo_id"], caption=cap, reply_markup=kb)
            except Exception:
                await cq.message.reply(cap, reply_markup=kb)
        else:
            await cq.message.reply(cap, reply_markup=kb)
    await cq.answer()


@router.callback_query(F.data.startswith("mkbuy:"))
async def cb_market_buy(cq: CallbackQuery):
    try:
        item = await market_col.find_one({"_id": ObjectId(cq.data.split(":", 1)[1])})
    except Exception:
        item = None
    if not item:
        await cq.answer("❌ Лот удалён", show_alert=True)
        return
    user = await get_or_create_user(cq.from_user)
    if user["s"] < item["price"]:
        await cq.answer(f"❌ Нужно {item['price']} монет", show_alert=True)
        return
    card = await cards_col.find_one({"_id": ObjectId(item["card_id"])})
    if not card:
        await cq.answer("❌ Карта не найдена", show_alert=True)
        return
    await users_col.update_one({"user_id": cq.from_user.id}, {"$inc": {"s": -item["price"]}})
    await give_card_to_user(cq.from_user.id, card)
    await market_col.delete_one({"_id": item["_id"]})
    await log_action(cq.from_user.id, "market_buy", f"{item['name']} -{item['price']}")
    await cq.message.reply(f"✅ {tg_user_mention(cq.from_user)} купил <b>{escape(card['name'])}</b>!")
    await cq.answer()


# ============= КОСТИ =============
@router.message(Command("diceplay"))
async def cmd_diceplay(msg: Message):
    user = await get_or_create_user(msg.from_user)
    cd = PREMIUM_DICE_COOLDOWN if is_premium(user) else DICE_COOLDOWN
    if user["s"] < 1:
        await msg.reply("💸 Нет монет")
        return

    now = now_ts()
    locked = await users_col.find_one_and_update(
        {"user_id": msg.from_user.id, "last_dice_ts": {"$lte": now - cd}},
        {"$set": {"last_dice_ts": now}},
    )
    if not locked:
        fresh = await users_col.find_one({"user_id": msg.from_user.id})
        left = cd - (now - fresh.get("last_dice_ts", 0))
        await msg.reply(f"🎲 Доступно через <b>{fmt_time_left(left)}</b>")
        return

    player_msg = await msg.reply_dice(emoji="🎲")
    user_roll = player_msg.dice.value
    await asyncio.sleep(2)
    bot_msg = await msg.reply_dice(emoji="🎲")
    bot_roll = bot_msg.dice.value
    await asyncio.sleep(3.5)
    if user_roll > bot_roll:
        win = random.randint(3, 10)
        await users_col.update_one({"user_id": msg.from_user.id}, {"$inc": {"s": win}})
        result = f"🎉 {tg_user_mention(msg.from_user)} победил! +<b>{win}</b> монет"
    elif user_roll < bot_roll:
        loss = min(user["s"], random.randint(1, 5))
        await users_col.update_one({"user_id": msg.from_user.id}, {"$inc": {"s": -loss}})
        result = f"😿 {tg_user_mention(msg.from_user)} проиграл! -<b>{loss}</b> монет"
    else:
        result = f"🤝 Ничья ({tg_user_mention(msg.from_user)})"
    await msg.reply(f"🎲 Игрок: <b>{user_roll}</b> / Бот: <b>{bot_roll}</b>\n{result}")


# ============= РП / БРАК =============
RP_ACTIONS = {
    "поцеловать": ("💋", "{a} поцеловал(а) {b}"),
    "обнять": ("🤗", "{a} обнял(а) {b}"),
    "ударить": ("👊", "{a} ударил(а) {b}"),
    "укусить": ("😬", "{a} укусил(а) {b}"),
    "погладить": ("✋", "{a} погладил(а) {b}"),
    "пнуть": ("🦵", "{a} пнул(а) {b}"),
    "лизнуть": ("👅", "{a} лизнул(а) {b}"),
    "шлепнуть": ("✋", "{a} шлёпнул(а) {b}"),
    "обнимашки": ("🫂", "{a} крепко обнял(а) {b}"),
    "потанцевать": ("💃", "{a} танцует с {b}"),
}


@router.message(Command("roleplay"))
async def cmd_roleplay(msg: Message):
    acts = "\n".join([f"• <code>andrusho {k}</code> {v[0]}" for k, v in RP_ACTIONS.items()])
    await msg.reply(f"🎭 <b>РП</b> (в ответ на сообщение):\n<blockquote>{acts}</blockquote>")


@router.message(Command("marriage"))
async def cmd_marriage(msg: Message):
    user = await get_or_create_user(msg.from_user)
    m = await marriages_col.find_one({
        "$or": [{"user1_id": user["user_id"]}, {"user2_id": user["user_id"]}],
        "status": "active",
    })
    text = ("💍 <b>Брак</b>\n<blockquote>"
            "• <code>andrusho создать брак</code> (ответом)\n"
            "• <code>andrusho принять</code>\n"
            "• <code>andrusho отклонить</code>\n"
            "• <code>andrusho развод</code></blockquote>")
    if m:
        pid = m["user2_id"] if m["user1_id"] == user["user_id"] else m["user1_id"]
        p = await users_col.find_one({"user_id": pid})
        if p:
            text += f"\n💑 В браке с <b>{escape(p['nickname'])}</b>"
    await msg.reply(text)


async def handle_rp(msg: Message, action: str):
    if not msg.reply_to_message or not msg.reply_to_message.from_user:
        await msg.reply("Ответьте на сообщение игрока")
        return
    target = msg.reply_to_message.from_user
    if target.id == msg.from_user.id:
        await msg.reply("Себя нельзя 😉")
        return
    action = action.strip().lower()
    for key, (emoji, tpl) in RP_ACTIONS.items():
        if action.startswith(key):
            a = tg_user_mention(msg.from_user)
            b = tg_user_mention(target)
            await msg.reply(f"{emoji} " + tpl.format(a=a, b=b))
            return
    await msg.reply("Неизвестное действие. /roleplay")


async def handle_marriage(msg: Message, action: str):
    action = action.strip().lower()
    uid = msg.from_user.id
    await get_or_create_user(msg.from_user)
    if action.startswith("создать брак") or action == "брак":
        if not msg.reply_to_message or not msg.reply_to_message.from_user:
            await msg.reply("Ответьте на сообщение")
            return
        target = msg.reply_to_message.from_user
        if target.id == uid or target.is_bot:
            await msg.reply("Нельзя")
            return
        existing = await marriages_col.find_one({
            "$or": [{"user1_id": uid}, {"user2_id": uid},
                    {"user1_id": target.id}, {"user2_id": target.id}],
            "status": "active",
        })
        if existing:
            await msg.reply("💔 Кто-то уже в браке")
            return
        await proposals_col.insert_one({
            "from_id": uid, "to_id": target.id, "chat_id": msg.chat.id, "created_at": now_ts(),
        })
        await msg.reply(
            f"💍 {tg_user_mention(msg.from_user)} → {tg_user_mention(target)}\n"
            f"<code>andrusho принять</code> / <code>andrusho отклонить</code>"
        )
        return
    if action.startswith("принять"):
        p = await proposals_col.find_one({"to_id": uid}, sort=[("created_at", -1)])
        if not p:
            await msg.reply("Нет предложений")
            return
        await marriages_col.insert_one({"user1_id": p["from_id"], "user2_id": uid,
                                        "status": "active", "created_at": now_ts()})
        await proposals_col.delete_one({"_id": p["_id"]})
        await msg.reply("💖 Брак!")
        return
    if action.startswith("отклонить"):
        p = await proposals_col.find_one({"to_id": uid}, sort=[("created_at", -1)])
        if p:
            await proposals_col.delete_one({"_id": p["_id"]})
        await msg.reply("💔 Отклонено")
        return
    if action.startswith("развод"):
        m = await marriages_col.find_one({"$or": [{"user1_id": uid}, {"user2_id": uid}], "status": "active"})
        if not m:
            await msg.reply("Вы не в браке")
            return
        await marriages_col.update_one({"_id": m["_id"]}, {"$set": {"status": "divorced"}})
        await msg.reply("💔 Развод")


        _RP_VARIANTS = {
            # поцеловать
            "поцеловать": "поцеловать", "поцеловал": "поцеловать",
            "поцеловала": "поцеловать", "поцелуй": "поцеловать",
            # обнять
            "обнять": "обнять", "обнял": "обнять", "обняла": "обнять", "обними": "обнять",
            # ударить
            "ударить": "ударить", "ударил": "ударить", "ударила": "ударить", "ударь": "ударить",
            # укусить
            "укусить": "укусить", "укусил": "укусить", "укусила": "укусить", "укуси": "укусить",
            # погладить
            "погладить": "погладить", "погладил": "погладить",
            "погладила": "погладить", "погладь": "погладить",
            # пнуть
            "пнуть": "пнуть", "пнул": "пнуть", "пнула": "пнуть", "пни": "пнуть",
            # лизнуть
            "лизнуть": "лизнуть", "лизнул": "лизнуть", "лизнула": "лизнуть", "лизни": "лизнуть",
            # шлепнуть
            "шлепнуть": "шлепнуть", "шлёпнуть": "шлепнуть",
            "шлепнул": "шлепнуть", "шлёпнул": "шлепнуть",
            "шлепнула": "шлепнуть", "шлёпнула": "шлепнуть",
            "шлепни": "шлепнуть", "шлёпни": "шлепнуть",
            # обнимашки
            "обнимашки": "обнимашки",
            # потанцевать
            "потанцевать": "потанцевать", "танцевать": "потанцевать",
            "потанцевал": "потанцевать", "потанцевала": "потанцевать",
            "танцуй": "потанцевать",
        }

        _BARE_MARRIAGE_WORDS = {"брак", "принять", "отклонить", "развод"}

        def _is_bare_rp_or_marriage(msg: Message) -> bool:
            if not msg.text:
                return False
            t = msg.text.strip().lower()
            if not t or t.startswith("/"):
                return False
            # уже с andrusho-префиксом — пропустим, его ловит твой основной хендлер
            if any(t.startswith(p) for p in COMMAND_PREFIXES):
                return False
            first = t.split()[0]
            if first in _RP_VARIANTS:
                return True
            if first in _BARE_MARRIAGE_WORDS:
                return True
            if t.startswith("создать брак"):
                return True
            return False

        @router.message(StateFilter(None), F.func(_is_bare_rp_or_marriage))
        async def bare_rp_marriage_handler(msg: Message):
            text = msg.text.strip().lower()
            first = text.split()[0]
            log.info("bare_rp_marriage_handler fired: %r", text)  # debug

            # РП — приводим к каноничному ключу, чтобы handle_rp нашёл его в RP_ACTIONS
            if first in _RP_VARIANTS:
                canonical = _RP_VARIANTS[first]
                await handle_rp(msg, canonical)
                return

            # Брак
            if first in _BARE_MARRIAGE_WORDS or text.startswith("создать брак"):
                await handle_marriage(msg, text)
                return


async def handle_quote(msg: Message, kind: str, payload: str):
    text = payload.strip().strip("«»\"'")
    if not text and msg.reply_to_message and msg.reply_to_message.text:
        text = msg.reply_to_message.text
        author = msg.reply_to_message.from_user.first_name if msg.reply_to_message.from_user else "—"
    else:
        author = msg.from_user.first_name
    if not text:
        await msg.reply(f"<code>andrusho {kind} «текст»</code>")
        return
    emoji = "💬" if kind == "цитата" else "🎨"
    await msg.reply(f"{emoji} <blockquote>«{escape(text)}»\n— <i>{escape(author or '')}</i></blockquote>")


# ============= АДМИН ВХОД =============
@router.callback_query(F.data == "take_admin")
async def cb_take_admin(cq: CallbackQuery, state: FSMContext):
    if is_admin(cq.from_user.id):
        await cq.answer("Вы уже админ", show_alert=True)
        return
    if cq.from_user.id in BLOCKED_ADMINS:
        await cq.answer("❌ Ваш доступ заблокирован", show_alert=True)
        return
    await cq.message.reply("🔐 Введите пароль администратора:")
    await state.set_state(AdminLogin.waiting_password)
    await cq.answer()


@router.callback_query(F.data == "open_admin")
async def cb_open_admin(cq: CallbackQuery):
    if not is_admin(cq.from_user.id):
        await cq.answer("❌", show_alert=True)
        return
    await show_admin_panel(cq.message)
    await cq.answer()


@router.message(Command("admin"))
async def cmd_admin(msg: Message, state: FSMContext):
    await state.clear()
    if is_admin(msg.from_user.id):
        await show_admin_panel(msg)
        return
    if msg.from_user.id in BLOCKED_ADMINS:
        await msg.reply("❌ Ваш доступ заблокирован")
        return
    await msg.reply("🔐 Введите пароль администратора:")
    await state.set_state(AdminLogin.waiting_password)


@router.message(AdminLogin.waiting_password)
async def admin_password(msg: Message, state: FSMContext):
    if _is_cmd(msg):
        await state.clear()
        return
    if msg.from_user.id in BLOCKED_ADMINS:
        await state.clear()
        await msg.reply("❌ Ваш доступ заблокирован")
        return
    if msg.text and msg.text.strip() == ADMIN_PASSWORD:
        ADMIN_SESSIONS.add(msg.from_user.id)
        await state.clear()
        await log_action(msg.from_user.id, "admin_login", "OK")
        await admin_log(msg.from_user.id, "admin_login")
        await msg.reply("✅ Доступ разрешён!")
        await show_admin_panel(msg)
    else:
        await state.clear()
        await log_action(msg.from_user.id, "admin_login", "FAIL")
        await msg.reply("❌ Неверный пароль")


@router.message(Command("adminlogout"))
async def cmd_adminlogout(msg: Message, state: FSMContext):
    await state.clear()
    ADMIN_SESSIONS.discard(msg.from_user.id)
    await msg.reply("👋 Вышли")


async def show_admin_panel(msg: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Дать ресурсы", callback_data="res:give")],
        [InlineKeyboardButton(text="💸 Забрать ресурсы", callback_data="res:take")],
        [InlineKeyboardButton(text="💥 Забрать ВСЁ", callback_data="wipe:start")],
        [InlineKeyboardButton(text="🚫 Забанить юзера", callback_data="banuser")],
        [InlineKeyboardButton(text="✅ Разбанить юзера", callback_data="unbanuser")],
        [InlineKeyboardButton(text="👥 Все юзеры", callback_data="adm:users")],
        [InlineKeyboardButton(text="🔎 Инфо о юзере", callback_data="adm:userinfo")],
        [InlineKeyboardButton(text="👤 Список админов", callback_data="adm:list_admins")],
        [InlineKeyboardButton(text="🚫 Блокировать админа", callback_data="adm:block_admin")],
        [InlineKeyboardButton(text="✅ Разблокировать админа", callback_data="adm:unblock_admin")],
        [InlineKeyboardButton(text="📋 Админ-логи", callback_data="adm:admin_logs")],
        [InlineKeyboardButton(text="➕ Добавить карту", callback_data="adm:addcard")],
        [InlineKeyboardButton(text="📜 Все карты (ID)", callback_data="adm:listcards")],
        [InlineKeyboardButton(text="🔄 Синхронизировать карты", callback_data="adm:syncards")],
        [InlineKeyboardButton(text="🏪 Загрузить в маркет", callback_data="adm:loadmarket")],
        [InlineKeyboardButton(text="🗑 Удалить из маркета", callback_data="adm:delmarket")],
        [InlineKeyboardButton(text="📋 Логи юзеров", callback_data="adm:logs")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="adm:stats")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="adm:broadcast")],
    ])
    await msg.reply("👑 <b>Админ-панель</b>", reply_markup=kb)


# ============= БАН ЮЗЕРА В БОТЕ =============
@router.callback_query(F.data == "banuser")
async def cb_banuser(cq: CallbackQuery, state: FSMContext):
    if not is_admin(cq.from_user.id):
        await cq.answer("❌", show_alert=True)
        return
    await state.clear()
    await state.set_state(BanUserFSM.target)
    await cq.message.reply("🚫 Введите <b>@username</b> или <b>user_id</b> для бана в боте (или /cancel):")
    await cq.answer()


@router.callback_query(F.data == "unbanuser")
async def cb_unbanuser(cq: CallbackQuery, state: FSMContext):
    if not is_admin(cq.from_user.id):
        await cq.answer("❌", show_alert=True)
        return
    await state.clear()
    await state.set_state(BanUserFSM.unban_target)
    await cq.message.reply("✅ Введите <b>@username</b> или <b>user_id</b> для разбана (или /cancel):")
    await cq.answer()


@router.message(BanUserFSM.target)
async def fsm_banuser(msg: Message, state: FSMContext):
    if _is_cmd(msg):
        await state.clear()
        return
    if not is_admin(msg.from_user.id):
        await state.clear()
        return
    u = await find_user_by_query(msg.text or "")
    if not u:
        await msg.reply("❌ Юзер не найден. Введите другой или /cancel")
        return
    BANNED_USERS.add(u["user_id"])
    await banned_col.update_one({"user_id": u["user_id"]},
                                {"$set": {"user_id": u["user_id"], "ts": now_ts(), "by": msg.from_user.id}},
                                upsert=True)
    await admin_log(msg.from_user.id, "ban_user", u["user_id"])
    await msg.reply(f"🚫 Юзер {user_mention(u)} (<code>{u['user_id']}</code>) забанен в боте")
    await state.clear()


@router.message(BanUserFSM.unban_target)
async def fsm_unbanuser(msg: Message, state: FSMContext):
    if _is_cmd(msg):
        await state.clear()
        return
    if not is_admin(msg.from_user.id):
        await state.clear()
        return
    u = await find_user_by_query(msg.text or "")
    if not u:
        await msg.reply("❌ Юзер не найден. Введите другой или /cancel")
        return
    BANNED_USERS.discard(u["user_id"])
    await banned_col.delete_one({"user_id": u["user_id"]})
    await admin_log(msg.from_user.id, "unban_user", u["user_id"])
    await msg.reply(f"✅ Юзер {user_mention(u)} разбанен")
    await state.clear()


# ============= ДАТЬ / ЗАБРАТЬ РЕСУРСЫ =============
@router.callback_query(F.data.in_({"res:give", "res:take"}))
async def cb_res_start(cq: CallbackQuery, state: FSMContext):
    if not is_admin(cq.from_user.id):
        await cq.answer("❌", show_alert=True)
        return
    mode = "give" if cq.data == "res:give" else "take"
    await state.clear()
    await state.update_data(mode=mode)
    rows = [[InlineKeyboardButton(text=v["label"], callback_data=f"rsel:{k}")]
            for k, v in RESOURCE_FIELDS.items()]
    rows.append([InlineKeyboardButton(text="🃏 Карту (из индекса)", callback_data="rsel:card")])
    if mode == "take":
        rows.append([InlineKeyboardButton(text="🃏 ВСЕ карты (обнулить)", callback_data="rsel:allcards")])
        rows.append([InlineKeyboardButton(text="📦 ВСЕ сундуки", callback_data="rsel:allchests")])
    title = "🎁 <b>Дать ресурсы</b>" if mode == "give" else "💸 <b>Забрать ресурсы</b>"
    await cq.message.reply(f"{title}\n\nЧто {'выдать' if mode == 'give' else 'забрать'}?",
                           reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await state.set_state(ResourceFSM.resource_type)
    await cq.answer()


@router.callback_query(F.data.startswith("rsel:"), ResourceFSM.resource_type)
async def cb_res_type(cq: CallbackQuery, state: FSMContext):
    rtype = cq.data.split(":", 1)[1]
    await state.update_data(resource_type=rtype)
    data = await state.get_data()
    mode = data.get("mode", "give")

    if rtype == "card":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"{d['emoji']} {d['name']}", callback_data=f"rcrar:{r}")]
            for r, d in RARITIES.items()
        ])
        await cq.message.reply("Выберите редкость карты:", reply_markup=kb)
        await state.set_state(ResourceFSM.card_rarity)
    elif rtype in ("allcards", "allchests"):
        # Скип количества — сразу выбор цели
        await _ask_target(cq.message, state)
    else:
        if rtype not in RESOURCE_FIELDS:
            await cq.answer("❌", show_alert=True)
            return
        label = RESOURCE_FIELDS[rtype]["label"]
        verb = "выдать" if mode == "give" else "забрать"
        await cq.message.reply(f"Выбрано: <b>{label}</b>\n\nВведите <b>количество</b> для {verb} или /cancel:")
        await state.set_state(ResourceFSM.amount)
    await cq.answer()


@router.callback_query(F.data.startswith("rcrar:"), ResourceFSM.card_rarity)
async def cb_res_card_rarity(cq: CallbackQuery, state: FSMContext):
    rarity = cq.data.split(":", 1)[1]
    if rarity not in RARITIES:
        await cq.answer("❌", show_alert=True)
        return
    cards = await cards_col.find({"rarity": rarity}).to_list(length=None)
    if not cards:
        await cq.message.reply("В этой редкости карт нет")
        await cq.answer()
        return
    rows = []
    for c in cards[:50]:
        rows.append([InlineKeyboardButton(
            text=f"{RARITIES[rarity]['emoji']} {c['name'][:40]}",
            callback_data=f"rcpick:{c['_id']}"
        )])
    await cq.message.reply(f"Выберите карту ({RARITIES[rarity]['name']}):",
                           reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await state.set_state(ResourceFSM.card_pick)
    await cq.answer()


@router.callback_query(F.data.startswith("rcpick:"), ResourceFSM.card_pick)
async def cb_res_card_pick(cq: CallbackQuery, state: FSMContext):
    card_id = cq.data.split(":", 1)[1]
    try:
        card = await cards_col.find_one({"_id": ObjectId(card_id)})
    except Exception:
        card = None
    if not card:
        await cq.answer("❌ Карта не найдена", show_alert=True)
        await state.clear()
        return
    await state.update_data(card_id=card_id, card_name=card["name"])
    await _ask_target(cq.message, state)
    await cq.answer()


@router.message(ResourceFSM.amount)
async def fsm_res_amount(msg: Message, state: FSMContext):
    if _is_cmd(msg):
        await state.clear()
        return
    if not is_admin(msg.from_user.id):
        await state.clear()
        return
    try:
        amount = int(msg.text.strip())
        if amount <= 0:
            raise ValueError()
    except Exception:
        await msg.reply("❌ Введите положительное число или /cancel")
        return
    await state.update_data(amount=amount)
    await _ask_target(msg, state)


async def _ask_target(msg: Message, state: FSMContext):
    data = await state.get_data()
    mode = data.get("mode", "give")
    verb = "выдать" if mode == "give" else "забрать"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Конкретному игроку", callback_data="rtgt:one")],
        [InlineKeyboardButton(text="👥 ВСЕМ игрокам", callback_data="rtgt:all")],
    ])
    await msg.reply(f"Кому {verb}?", reply_markup=kb)
    await state.set_state(ResourceFSM.target_choice)


@router.callback_query(F.data.startswith("rtgt:"), ResourceFSM.target_choice)
async def cb_res_target_choice(cq: CallbackQuery, state: FSMContext):
    choice = cq.data.split(":", 1)[1]
    if choice == "one":
        await cq.message.reply("👤 Введите <b>@username</b> или <b>user_id</b> игрока (или /cancel):")
        await state.set_state(ResourceFSM.target_query)
    else:
        await _apply_resource(cq.message, state, target_user=None, admin_id=cq.from_user.id)
    await cq.answer()


@router.message(ResourceFSM.target_query)
async def fsm_res_target_query(msg: Message, state: FSMContext):
    if _is_cmd(msg):
        await state.clear()
        return
    if not is_admin(msg.from_user.id):
        await state.clear()
        return
    target = await find_user_by_query(msg.text or "")
    if not target:
        await msg.reply("❌ Игрок не найден. Введите другой или /cancel:")
        return
    await _apply_resource(msg, state, target_user=target, admin_id=msg.from_user.id)


async def _apply_resource(msg: Message, state: FSMContext, target_user: Optional[dict], admin_id: int):
    data = await state.get_data()
    mode = data.get("mode", "give")
    rtype = data.get("resource_type")
    amount = data.get("amount", 1)
    sign = 1 if mode == "give" else -1

    if target_user is None:
        targets = await users_col.find({}).to_list(length=None)
    else:
        targets = [target_user]

    affected = 0
    failed = 0

    # Обнулить все карты
    if rtype == "allcards":
        if mode != "take":
            await msg.reply("❌ Доступно только в режиме «забрать»")
            await state.clear()
            return
        total_removed = 0
        for u in targets:
            try:
                total_removed += await wipe_all_cards(u["user_id"])
                affected += 1
            except Exception:
                failed += 1
        scope = "у всех" if target_user is None else f"у {user_mention(target_user)}"
        await msg.reply \
            (f"💥 Забраны ВСЕ карты {scope}\nЗатронуто юзеров: <b>{affected}</b>, удалено карт: <b>{total_removed}</b>")
        await admin_log(admin_id, "wipe_cards", target_user["user_id"] if target_user else 0, f"affected={affected}")
        await state.clear()
        return

    # Обнулить все сундуки
    if rtype == "allchests":
        if mode != "take":
            await msg.reply("❌ Доступно только в режиме «забрать»")
            await state.clear()
            return
        for u in targets:
            try:
                await wipe_all_chests(u["user_id"])
                affected += 1
            except Exception:
                failed += 1
        scope = "у всех" if target_user is None else f"у {user_mention(target_user)}"
        await msg.reply(f"💥 Обнулены ВСЕ сундуки {scope}\nЗатронуто: <b>{affected}</b>")
        await admin_log(admin_id, "wipe_chests", target_user["user_id"] if target_user else 0, f"affected={affected}")
        await state.clear()
        return

    # Одна карта
    if rtype == "card":
        card_id = data.get("card_id")
        card_name = data.get("card_name", "?")
        try:
            card_doc = await cards_col.find_one({"_id": ObjectId(card_id)})
        except Exception:
            card_doc = None
        if not card_doc:
            await msg.reply("❌ Карта не найдена")
            await state.clear()
            return
        for u in targets:
            try:
                if mode == "give":
                    await give_card_to_user(u["user_id"], card_doc)
                    affected += 1
                else:
                    ok = await take_card_from_user(u["user_id"], card_id)
                    if ok:
                        affected += 1
                    else:
                        failed += 1
            except Exception:
                failed += 1
        verb = "выдана" if mode == "give" else "забрана"
        scope = "у всех" if target_user is None else f"у {user_mention(target_user)}"
        await msg.reply(
            f"✅ Карта <b>{escape(card_name)}</b> {verb} {scope}\n"
            f"Затронуто: <b>{affected}</b>" + (f" (не было: {failed})" if failed else "")
        )
        await admin_log(admin_id, f"{mode}_card",
                        target_user["user_id"] if target_user else 0,
                        f"{card_name} affected={affected}")
        await state.clear()
        return

    if rtype not in RESOURCE_FIELDS:
        await msg.reply("❌ Неверный тип ресурса")
        await state.clear()
        return

    # Премиум
    if rtype == "premium":
        for u in targets:
            try:
                cur = u.get("premium_until", 0)
                if mode == "give":
                    new_until = max(now_ts(), cur) + amount * 86400
                else:
                    new_until = max(0, cur - amount * 86400)
                await users_col.update_one({"user_id": u["user_id"]}, {"$set": {"premium_until": new_until}})
                affected += 1
            except Exception:
                failed += 1
        verb = "выдан" if mode == "give" else "снят"
        scope = "у всех" if target_user is None else f"у {user_mention(target_user)}"
        await msg.reply(f"✅ Премиум {verb} ({amount} дн.) {scope}\nЗатронуто: <b>{affected}</b>")
        await admin_log(admin_id, f"{mode}_premium",
                        target_user["user_id"] if target_user else 0,
                        f"{amount} days affected={affected}")
        await state.clear()
        return

    # Обычное числовое поле
    delta = sign * amount
    for u in targets:
        try:
            if mode == "take":
                cur = u.get(rtype, 0) or 0
                actual = -min(cur, amount)
                await users_col.update_one({"user_id": u["user_id"]}, {"$inc": {rtype: actual}})
            else:
                await users_col.update_one({"user_id": u["user_id"]}, {"$inc": {rtype: delta}})
            affected += 1
        except Exception:
            failed += 1

    label = RESOURCE_FIELDS[rtype]["label"]
    verb = "выдано" if mode == "give" else "забрано"
    scope = "у всех" if target_user is None else f"у {user_mention(target_user)}"
    await msg.reply(
        f"✅ {label}: <b>{amount}</b> {verb} {scope}\nЗатронуто: <b>{affected}</b>"
        + (f" (ошибок: {failed})" if failed else "")
    )
    await admin_log(admin_id, f"{mode}_{rtype}",
                    target_user["user_id"] if target_user else 0,
                    f"amount={amount} affected={affected}")
    await state.clear()


# ============= ЗАБРАТЬ ВСЁ (отдельный flow) =============
class WipeAllFSM(StatesGroup):
    target_choice = State()
    target_query = State()
    confirm = State()


@router.callback_query(F.data == "wipe:start")
async def cb_wipe_start(cq: CallbackQuery, state: FSMContext):
    if not is_admin(cq.from_user.id):
        await cq.answer("❌", show_alert=True)
        return
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 У конкретного", callback_data="wtgt:one")],
        [InlineKeyboardButton(text="👥 У ВСЕХ", callback_data="wtgt:all")],
    ])
    await cq.message.reply(
        "💥 <b>Забрать ВСЁ</b>\n<blockquote>Снимет: ВСЕ карты, ВСЕ сундуки, монеты, очки, удачу, премиум</blockquote>\n\nУ кого?",
        reply_markup=kb,
    )
    await state.set_state(WipeAllFSM.target_choice)
    await cq.answer()


@router.callback_query(F.data.startswith("wtgt:"), WipeAllFSM.target_choice)
async def cb_wipe_target(cq: CallbackQuery, state: FSMContext):
    choice = cq.data.split(":", 1)[1]
    if choice == "all":
        await state.update_data(scope="all")
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ ДА, обнулить ВСЕХ", callback_data="wconf:yes")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="wconf:no")],
        ])
        await cq.message.reply("⚠️ <b>Подтвердите обнуление ВСЕХ игроков</b>", reply_markup=kb)
        await state.set_state(WipeAllFSM.confirm)
    else:
        await cq.message.reply("👤 Введите <b>@username</b> или <b>user_id</b> (или /cancel):")
        await state.set_state(WipeAllFSM.target_query)
    await cq.answer()


@router.message(WipeAllFSM.target_query)
async def fsm_wipe_target_query(msg: Message, state: FSMContext):
    if _is_cmd(msg):
        await state.clear()
        return
    if not is_admin(msg.from_user.id):
        await state.clear()
        return
    u = await find_user_by_query(msg.text or "")
    if not u:
        await msg.reply("❌ Не найден. /cancel или другой ID/username")
        return
    await state.update_data(scope="one", target_id=u["user_id"], target_name=u.get("nickname", ""))
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ ДА, обнулить {u.get('nickname' ,'')}", callback_data="wconf:yes")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="wconf:no")],
    ])
    await msg.reply(
        f"⚠️ Подтвердите обнуление: {user_mention(u)} (<code>{u['user_id']}</code>)",
        reply_markup=kb,
    )
    await state.set_state(WipeAllFSM.confirm)


@router.callback_query(F.data.startswith("wconf:"), WipeAllFSM.confirm)
async def cb_wipe_confirm(cq: CallbackQuery, state: FSMContext):
    if not is_admin(cq.from_user.id):
        await cq.answer("❌", show_alert=True)
        return
    decision = cq.data.split(":", 1)[1]
    if decision != "yes":
        await state.clear()
        await cq.message.reply("Отменено")
        await cq.answer()
        return
    data = await state.get_data()
    scope = data.get("scope")
    if scope == "all":
        targets = await users_col.find({}).to_list(length=None)
    else:
        targets = [await users_col.find_one({"user_id": data.get("target_id")})]
        targets = [t for t in targets if t]

    wipe_set = {
        "s": 0, "points": 0, "cards_count": 0,
        "luck_charges": 0, "premium_until": 0,
        "favorite_card_id": None,
        **{f: 0 for f in ALL_CHEST_FIELDS_LIST},
    }
    cards_removed = 0
    affected = 0
    for u in targets:
        try:
            res = await inventory_col.delete_many({"user_id": u["user_id"]})
            cards_removed += res.deleted_count
            await users_col.update_one({"user_id": u["user_id"]}, {"$set": wipe_set})
            affected += 1
        except Exception:
            pass
    scope_text = "у ВСЕХ" if scope == "all" else f"у <code>{data.get('target_id')}</code>"
    await cq.message.reply(
        f"💥 <b>Обнулено {scope_text}</b>\n"
        f"Юзеров: <b>{affected}</b>\nКарт удалено: <b>{cards_removed}</b>"
    )
    await admin_log(cq.from_user.id, "wipe_all",
                    data.get("target_id", 0) or 0,
                    f"scope={scope} affected={affected} cards={cards_removed}")
    await state.clear()
    await cq.answer()


@router.message(Command("cancel"))
async def cmd_cancel(msg: Message, state: FSMContext):
    await state.clear()
    await msg.reply("Отменено")


# ============= СПИСОК / БЛОК АДМИНОВ =============
@router.callback_query(F.data == "adm:list_admins")
async def cb_list_admins(cq: CallbackQuery):
    if not is_admin(cq.from_user.id):
        await cq.answer("❌", show_alert=True)
        return
    lines = ["👤 <b>Админы:</b>\n"]
    for aid in ADMINS:
        status = " 🚫 ЗАБЛОКИРОВАН" if aid in BLOCKED_ADMINS else " ✅"
        u = await users_col.find_one({"user_id": aid})
        name = u["nickname"] if u else f"ID:{aid}"
        lines.append(f"• <code>{aid}</code> {escape(name)}{status}")
    for aid in list(ADMIN_SESSIONS):
        if aid not in ADMINS:
            u = await users_col.find_one({"user_id": aid})
            name = u["nickname"] if u else f"ID:{aid}"
            lines.append(f"• <code>{aid}</code> {escape(name)} (сессия)")
    await cq.message.reply("\n".join(lines))
    await cq.answer()


@router.callback_query(F.data == "adm:block_admin")
async def cb_block_admin(cq: CallbackQuery, state: FSMContext):
    if not is_admin(cq.from_user.id):
        await cq.answer("❌", show_alert=True)
        return
    await cq.message.reply("🚫 Введите ID админа для блокировки (или /cancel):")
    await state.update_data(block_action="block")
    await state.set_state(BlockAdminFSM.target_id)
    await cq.answer()


@router.callback_query(F.data == "adm:unblock_admin")
async def cb_unblock_admin(cq: CallbackQuery, state: FSMContext):
    if not is_admin(cq.from_user.id):
        await cq.answer("❌", show_alert=True)
        return
    await cq.message.reply("✅ Введите ID админа для разблокировки (или /cancel):")
    await state.update_data(block_action="unblock")
    await state.set_state(BlockAdminFSM.target_id)
    await cq.answer()


@router.message(BlockAdminFSM.target_id)
async def fsm_block_admin(msg: Message, state: FSMContext):
    if _is_cmd(msg):
        await state.clear()
        return
    if not is_admin(msg.from_user.id):
        await state.clear()
        return
    try:
        uid = int(msg.text.strip())
    except Exception:
        await msg.reply("❌ Введите число или /cancel")
        return
    data = await state.get_data()
    action = data.get("block_action", "block")
    if action == "block":
        BLOCKED_ADMINS.add(uid)
        ADMIN_SESSIONS.discard(uid)
        await admin_log(msg.from_user.id, "block_admin", uid)
        await msg.reply(f"🚫 Админ <code>{uid}</code> заблокирован")
    else:
        BLOCKED_ADMINS.discard(uid)
        await admin_log(msg.from_user.id, "unblock_admin", uid)
        await msg.reply(f"✅ Админ <code>{uid}</code> разблокирован")
    await state.clear()


# ============= АДМИН-ЛОГИ =============
@router.callback_query(F.data == "adm:admin_logs")
async def cb_admin_logs(cq: CallbackQuery):
    if not is_admin(cq.from_user.id):
        await cq.answer("❌", show_alert=True)
        return
    logs = await admin_logs_col.find({}).sort("ts", -1).limit(50).to_list(length=50)
    if not logs:
        await cq.message.reply("📋 Админ-логов нет")
        await cq.answer()
        return
    lines = ["📋 <b>Админ-логи</b> (последние 50):\n"]
    for l in logs:
        t = time.strftime("%d.%m %H:%M", time.localtime(l["ts"]))
        admin_u = await users_col.find_one({"user_id": l["admin_id"]})
        admin_name = admin_u["nickname"] if admin_u else str(l["admin_id"])
        target_u = await users_col.find_one({"user_id": l.get("target_id", 0)}) if l.get("target_id") else None
        target_name = target_u["nickname"] if target_u else str(l.get("target_id", ""))
        details = l.get("details", "")
        lines.append(f"[{t}] <b>{escape(admin_name)}</b> → {escape(target_name)}: {l['action']} {escape(str(details))}")
    text = "\n".join(lines)
    for i in range(0, len(text), 3500):
        await cq.message.reply(text[i: i +3500])
    await cq.answer()


# ============= ОСТАЛЬНЫЕ АДМИН-КНОПКИ =============
@router.callback_query(F.data == "adm:users")
async def cb_adm_users(cq: CallbackQuery):
    if not is_admin(cq.from_user.id):
        await cq.answer("❌", show_alert=True)
        return
    users = await users_col.find({}).sort("created_at", -1).limit(50).to_list(length=50)
    lines = [f"👥 <b>Юзеры ({len(users)}):</b>\n"]
    for u in users:
        prem = " 💎" if is_premium(u) else ""
        banned = " 🚫" if u["user_id"] in BANNED_USERS else ""
        lines.append \
            (f"• <code>{u['user_id']}</code> · {user_mention(u)}{prem}{banned} · 💰{u.get('s' ,0)} ✨{u.get('points' ,0):,} 🃏{u.get('cards_count' ,0)}")
    text = "\n".join(lines)
    for i in range(0, len(text), 3500):
        await cq.message.reply(text[i: i +3500])
    await cq.answer()


@router.callback_query(F.data == "adm:userinfo")
async def cb_adm_userinfo(cq: CallbackQuery):
    if not is_admin(cq.from_user.id):
        await cq.answer("❌", show_alert=True)
        return
    await cq.message.reply("Используйте <code>/userinfo &lt;user_id или @username&gt;</code>")
    await cq.answer()


@router.callback_query(F.data == "adm:addcard")
async def cb_adm_addcard(cq: CallbackQuery, state: FSMContext):
    if not is_admin(cq.from_user.id):
        await cq.answer("❌", show_alert=True)
        return
    await cmd_addcard(cq.message, state)
    await cq.answer()


@router.callback_query(F.data == "adm:listcards")
async def cb_adm_listcards(cq: CallbackQuery):
    if not is_admin(cq.from_user.id):
        await cq.answer("❌", show_alert=True)
        return
    await cmd_listcards(cq.message)
    await cq.answer()


@router.callback_query(F.data == "adm:loadmarket")
async def cb_adm_loadmarket(cq: CallbackQuery):
    if not is_admin(cq.from_user.id):
        await cq.answer("❌", show_alert=True)
        return
    await cq.message.reply(
        "🏪 <b>Добавить карту в маркет</b>\n\n"
        "<code>/addmarket card_id [цена]</code>\n"
        "ID карт — /listcards"
    )
    await cq.answer()


@router.callback_query(F.data == "adm:logs")
async def cb_adm_logs(cq: CallbackQuery):
    if not is_admin(cq.from_user.id):
        await cq.answer("❌", show_alert=True)
        return
    logs = await logs_col.find({}).sort("ts", -1).limit(30).to_list(length=30)
    if not logs:
        await cq.message.reply("📋 Логов нет")
        await cq.answer()
        return
    lines = ["📋 <b>Последние 30:</b>\n"]
    for l in logs:
        t = time.strftime("%d.%m %H:%M", time.localtime(l["ts"]))
        lines.append(f"[{t}] <code>{l['user_id']}</code> · {l['action']} · {escape(str(l.get('details' ,'')))}")
    await cq.message.reply("\n".join(lines))
    await cq.answer()


@router.callback_query(F.data == "adm:stats")
async def cb_adm_stats(cq: CallbackQuery):
    if not is_admin(cq.from_user.id):
        await cq.answer("❌", show_alert=True)
        return
    u = await users_col.count_documents({})
    c = await cards_col.count_documents({})
    inv = await inventory_col.count_documents({})
    mk = await market_col.count_documents({})
    binds = await chest_cards_col.count_documents({})
    bans = await banned_col.count_documents({})
    await cq.message.reply(
        f"📊 <b>Статистика</b>\n<blockquote>"
        f"👥 Юзеров: {u}\n🃏 Карт: {c}\n📦 Инв.: {inv}\n🏪 Маркет: {mk}\n"
        f"🔗 Привязок: {binds}\n🚫 Банов: {bans}</blockquote>"
    )
    await cq.answer()


@router.callback_query(F.data == "adm:broadcast")
async def cb_adm_broadcast(cq: CallbackQuery):
    if not is_admin(cq.from_user.id):
        await cq.answer("❌", show_alert=True)
        return
    await cq.message.reply("📢 <code>/broadcast &lt;текст&gt;</code>")
    await cq.answer()


@router.callback_query(F.data == "adm:syncards")
async def cb_adm_syncards(cq: CallbackQuery):
    if not is_admin(cq.from_user.id):
        await cq.answer("❌", show_alert=True)
        return
    await cmd_syncards(cq.message)
    await cq.answer()


@router.callback_query(F.data == "adm:delmarket")
async def cb_adm_delmarket(cq: CallbackQuery):
    if not is_admin(cq.from_user.id):
        await cq.answer("❌", show_alert=True)
        return
    await cq.message.reply("🗑 <code>/delmarket card_id</code>")
    await cq.answer()


# ============= ТЕКСТОВЫЕ АДМИН-КОМАНДЫ =============
@router.message(Command("userinfo"))
async def cmd_userinfo(msg: Message, state: FSMContext):
    await state.clear()
    if not is_admin(msg.from_user.id):
        return
    parts = msg.text.split(maxsplit=1)
    if len(parts) != 2:
        await msg.reply("Формат: /userinfo &lt;user_id или @username&gt;")
        return
    u = await find_user_by_query(parts[1])
    if not u:
        await msg.reply("❌ Не найден")
        return
    inv = await inventory_col.find({"user_id": u["user_id"]}).to_list(length=None)
    inv_lines = []
    for it in inv[:30]:
        try:
            c = await cards_col.find_one({"_id": ObjectId(it["card_id"])})
            if c:
                rd = RARITIES.get(c["rarity"], {"emoji": "❔"})
                inv_lines.append(f"  {rd['emoji']} {escape(c['name'])} ×{it['count']}")
        except Exception:
            pass
    inv_text = "\n".join(inv_lines) or "  (пусто)"
    banned_mark = " 🚫 БАН" if u["user_id"] in BANNED_USERS else ""
    await msg.reply(
        f"🔎 <b>{escape(u['nickname'])}</b>{banned_mark} ({user_mention(u)})\n<blockquote>"
        f"🆔 <code>{u['user_id']}</code>\n"
        f"✨ {u.get('points' ,0):,}\n💰 {u.get('s' ,0)}\n🃏 {u.get('cards_count' ,0)}\n"
        f"🎁 {u.get('bonus_chests' ,0)} 💜 {u.get('epic_chests' ,0)} 💛 {u.get('legend_chests' ,0)}\n"
        f"🎁 {u.get('common__chests' ,0)} 💚 {u.get('rare__chests' ,0)} ❤️ {u.get('mythic__chests' ,0)}\n"
        f"🍀 {u.get('luck_charges' ,0)}\n"
        f"🚀 {'до ' + time.strftime('%d.%m.%Y', time.localtime(u['premium_until'])) if is_premium(u) else 'нет'}"
        f"</blockquote>\n<b>Карты:</b>\n{inv_text}"
    )


@router.message(Command("logs"))
async def cmd_logs(msg: Message, state: FSMContext):
    await state.clear()
    if not is_admin(msg.from_user.id):
        return
    parts = msg.text.split()
    q = {}
    if len(parts) == 2:
        try:
            q = {"user_id": int(parts[1])}
        except Exception:
            await msg.reply("❌")
            return
    logs = await logs_col.find(q).sort("ts", -1).limit(50).to_list(length=50)
    if not logs:
        await msg.reply("Нет логов")
        return
    lines = []
    for l in logs:
        t = time.strftime("%d.%m %H:%M", time.localtime(l["ts"]))
        lines.append(f"[{t}] <code>{l['user_id']}</code> · {l['action']} · {escape(str(l.get('details' ,'')))}")
    text = "\n".join(lines)
    for i in range(0, len(text), 3500):
        await msg.reply(text[i: i +3500])


@router.message(Command("broadcast"))
async def cmd_broadcast(msg: Message, state: FSMContext):
    await state.clear()
    if not is_admin(msg.from_user.id):
        return
    parts = msg.text.split(maxsplit=1)
    if len(parts) < 2:
        await msg.reply("Формат: /broadcast текст")
        return
    text = parts[1]
    users = await users_col.find({}).to_list(length=None)
    ok = fail = 0
    for u in users:
        try:
            await bot.send_message(u["user_id"], f"📢 <b>Уведомление</b>\n\n{text}")
            ok += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)
    await msg.reply(f"✅ Отправлено: {ok}, ошибок: {fail}")


# ============= /addcard /delcard /listcards =============
@router.message(Command("addcard"))
async def cmd_addcard(msg: Message, state: FSMContext):
    await state.clear()
    if not is_admin(msg.from_user.id):
        await msg.reply("❌")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{d['emoji']} {d['name']}", callback_data=f"addrarity:{r}")]
        for r, d in RARITIES.items()
    ])
    await msg.reply("Выберите редкость новой карты:", reply_markup=kb)
    await state.set_state(AddCardFSM.rarity)


@router.callback_query(F.data.startswith("addrarity:"), AddCardFSM.rarity)
async def cb_add_rar(cq: CallbackQuery, state: FSMContext):
    rarity = cq.data.split(":", 1)[1]
    if rarity not in RARITIES:
        await cq.answer("❌", show_alert=True)
        return
    await state.update_data(rarity=rarity)
    await cq.message.reply(f"Редкость: <b>{RARITIES[rarity]['emoji']} {RARITIES[rarity]['name']}</b>\nНазвание карты:")
    await state.set_state(AddCardFSM.name)
    await cq.answer()


@router.message(AddCardFSM.name)
async def fsm_addname(msg: Message, state: FSMContext):
    if _is_cmd(msg):
        await state.clear()
        return
    if not msg.text:
        await msg.reply("Текстом")
        return
    name = msg.text.strip()[:64]
    existing = await cards_col.find_one({"name": {"$regex": f"^{name}$", "$options": "i"}})
    if existing:
        rd = RARITIES.get(existing["rarity"], {"emoji": "❔"})
        await msg.reply(
            f"❌ Карта <b>«{escape(name)}»</b> уже существует!\n"
            f"{rd['emoji']} — ID: <code>{existing['_id']}</code>\nВведите другое или /cancel"
        )
        return
    await state.update_data(name=name)
    await msg.reply("📸 Отправьте фото:")
    await state.set_state(AddCardFSM.photo)


@router.message(AddCardFSM.photo, F.photo)
async def fsm_addphoto(msg: Message, state: FSMContext):
    data = await state.get_data()
    existing = await cards_col.find_one({"name": {"$regex": f"^{data['name']}$", "$options": "i"}})
    if existing:
        await msg.reply(f"❌ Карта <b>«{escape(data['name'])}»</b> уже существует!")
        await state.clear()
        return
    res = await cards_col.insert_one({
        "name": data["name"], "rarity": data["rarity"],
        "photo_id": msg.photo[-1].file_id,
        "created_at": now_ts(), "created_by": msg.from_user.id,
    })
    card_id = str(res.inserted_id)
    rd = RARITIES[data["rarity"]]
    await log_action(msg.from_user.id, "addcard", data["name"])
    await admin_log(msg.from_user.id, "addcard", 0, data["name"])
    added_chests = await auto_add_card_to_chests(card_id, data["name"], data["rarity"])
    card_doc = {"_id": res.inserted_id, "name": data["name"],
                "rarity": data["rarity"], "photo_id": msg.photo[-1].file_id}
    added_market = await auto_add_card_to_market(card_doc)
    response = f"✅ Добавлена!\n<blockquote>ID: <code>{card_id}</code>\n{rd['emoji']} {data['name']}</blockquote>"
    if added_chests:
        chest_names = [CHEST_LABELS[c] for c in added_chests]
        response += f"\n\n📦 Авто-добавлено в сундуки:\n{chr(10).join(chest_names)}"
    if added_market:
        price = MARKET_PRICES.get(data["rarity"], 0)
        response += f"\n\n🏪 Авто-добавлено в маркет: {price} монет"
    await msg.reply(response)
    await state.clear()


@router.message(AddCardFSM.photo)
async def fsm_addphoto_wrong(msg: Message, state: FSMContext):
    if _is_cmd(msg):
        await state.clear()
        return
    await msg.reply("Нужно фото (или /cancel)")


@router.message(Command("delcard"))
async def cmd_delcard(msg: Message, state: FSMContext):
    await state.clear()
    if not is_admin(msg.from_user.id):
        return
    parts = msg.text.split(maxsplit=1)
    if len(parts) < 2:
        await msg.reply("Формат: /delcard ID")
        return
    try:
        cid = ObjectId(parts[1].strip())
    except Exception:
        await msg.reply("❌ Неверный ID")
        return
    c = await cards_col.find_one({"_id": cid})
    if not c:
        await msg.reply("Не найдена")
        return
    card_id_str = str(cid)
    await cards_col.delete_one({"_id": cid})
    await inventory_col.delete_many({"card_id": card_id_str})
    await chest_cards_col.delete_many({"card_id": card_id_str})
    await market_col.delete_many({"card_id": card_id_str})
    await admin_log(msg.from_user.id, "delcard", 0, c['name'])
    await msg.reply(f"🗑 «{escape(c['name'])}» удалена")


@router.message(Command("listcards"))
async def cmd_listcards(msg: Message, state: FSMContext = None):
    if state is not None:
        await state.clear()
    if not is_admin(msg.from_user.id):
        return
    cards = await cards_col.find({}).sort("rarity", 1).sort("name", 1).to_list(length=None)
    if not cards:
        await msg.reply("Пусто. /addcard")
        return
    lines = [f"Всего карт: {len(cards)}\n"]
    for c in cards:
        rd = RARITIES.get(c["rarity"], {"emoji": "❔"})
        lines.append(f"{rd['emoji']} {c['name']} — <code>{c['_id']}</code>")
    chunk = ""
    for line in lines:
        if len(chunk) + len(line) + 1 > 3500:
            try:
                await msg.reply(chunk)
            except Exception:
                pass
            chunk = ""
            await asyncio.sleep(0.1)
        chunk += line + "\n"
    if chunk:
        try:
            await msg.reply(chunk)
        except Exception:
            pass


@router.message(Command("syncards"))
async def cmd_syncards(msg: Message, state: FSMContext = None):
    if state is not None:
        await state.clear()
    if not is_admin(msg.from_user.id):
        await msg.reply("❌")
        return
    await msg.reply("🔄 Синхронизация...")
    cards = await cards_col.find({}).to_list(length=None)
    added_chests_count = 0
    added_market_count = 0
    for card in cards:
        card_id = str(card["_id"])
        rarity = card["rarity"]
        if rarity in AUTO_CHEST_BINDINGS:
            for chest_type in AUTO_CHEST_BINDINGS[rarity]:
                existing = await chest_cards_col.find_one({"chest_type": chest_type, "card_id": card_id})
                if not existing:
                    await chest_cards_col.insert_one({
                        "chest_type": chest_type, "card_id": card_id,
                        "auto_added": True, "created_at": now_ts(),
                    })
                    added_chests_count += 1
        if rarity in MARKET_PRICES:
            existing = await market_col.find_one({"card_id": card_id})
            if not existing:
                await market_col.insert_one({
                    "card_id": card_id, "name": card["name"],
                    "rarity": rarity, "photo_id": card.get("photo_id"),
                    "price": MARKET_PRICES[rarity],
                    "auto_added": True, "created_at": now_ts(),
                })
                added_market_count += 1
    await admin_log(msg.from_user.id, "syncards", 0, f"chests={added_chests_count} market={added_market_count}")
    await msg.reply(
        f"✅ Синхронизация: карт {len(cards)}, в сундуки +{added_chests_count}, в маркет +{added_market_count}"
    )


@router.message(Command("addmarket"))
async def cmd_addmarket(msg: Message, state: FSMContext):
    await state.clear()
    if not is_admin(msg.from_user.id):
        return
    parts = msg.text.split()
    if len(parts) < 2:
        await msg.reply("Формат: /addmarket card_id [цена]")
        return
    try:
        card_id = parts[1].strip()
        ObjectId(card_id)
    except Exception:
        await msg.reply("❌ Неверный card_id")
        return
    card = await cards_col.find_one({"_id": ObjectId(card_id)})
    if not card:
        await msg.reply("❌ Карта не найдена")
        return
    if len(parts) >= 3:
        try:
            price = int(parts[2])
        except Exception:
            await msg.reply("❌ Цена должна быть числом")
            return
    else:
        rarity = card["rarity"]
        if rarity not in MARKET_PRICES:
            await msg.reply(f"❌ Нет автоцены для '{rarity}'")
            return
        price = MARKET_PRICES[rarity]
    existing = await market_col.find_one({"card_id": card_id})
    if existing:
        await msg.reply(f"⚠️ Уже в маркете за {existing['price']}💰")
        return
    await market_col.insert_one({
        "card_id": card_id, "name": card["name"],
        "rarity": card["rarity"], "photo_id": card.get("photo_id"),
        "price": price, "auto_added": False, "created_at": now_ts(),
    })
    await admin_log(msg.from_user.id, "addmarket", 0, f"{card['name']} {price}")
    rd = RARITIES.get(card["rarity"], {"emoji": "❔"})
    await msg.reply(f"✅ {rd['emoji']} <b>{escape(card['name'])}</b> в маркет за {price}💰")


@router.message(Command("delmarket"))
async def cmd_delmarket(msg: Message, state: FSMContext):
    await state.clear()
    if not is_admin(msg.from_user.id):
        return
    parts = msg.text.split()
    if len(parts) < 2:
        await msg.reply("Формат: /delmarket card_id")
        return
    try:
        card_id = parts[1].strip()
        ObjectId(card_id)
    except Exception:
        await msg.reply("❌ Неверный card_id")
        return
    item = await market_col.find_one({"card_id": card_id})
    if not item:
        await msg.reply("❌ Не найдена в маркете")
        return
    await market_col.delete_one({"card_id": card_id})
    await admin_log(msg.from_user.id, "delmarket", 0, item['name'])
    await msg.reply(f"✅ <b>{escape(item['name'])}</b> удалена из маркета")


# ============= /andrusho и текст =============
@router.message(Command("andrusho"))
async def cmd_andrusho(msg: Message, state: FSMContext):
    await state.clear()
    await try_give_card(msg)


def normalize(s: str) -> str:
    return s.lower().strip()


@router.message(F.text)
async def text_router(msg: Message, state: FSMContext):
    if await state.get_state() is not None:
        return
    if _is_cmd(msg):
        return
    low = normalize(msg.text or "")
    if low in CARD_TRIGGERS:
        await try_give_card(msg)
        return
    for pref in COMMAND_PREFIXES:
        if low.startswith(pref):
            rest = low[len(pref):].strip(" ,.")
            if not rest:
                await try_give_card(msg)
                return
            if rest.startswith(("создать брак", "брак", "принять", "отклонить", "развод")):
                await handle_marriage(msg, rest)
                return
            if rest.startswith("цитата"):
                await handle_quote(msg, "цитата", rest[len("цитата"):])
                return
            if rest.startswith("стикер"):
                await handle_quote(msg, "стикер", rest[len("стикер"):])
                return
            await handle_rp(msg, rest)
            return


# ============= МЕНЮ КОМАНД =============
async def setup_commands():
    public = [
        BotCommand(command="start", description="Запуск"),
        BotCommand(command="profile", description="👤 Профиль"),
        BotCommand(command="andrusho", description="🃏 Карта"),
        BotCommand(command="bonus", description="🎁 Бонус"),
        BotCommand(command="top", description="🏆 Топ"),
        BotCommand(command="shop", description="🛍 Магазин"),
        BotCommand(command="premium", description="🚀 Премиум"),
        BotCommand(command="diceplay", description="🎲 Кости"),
        BotCommand(command="roleplay", description="🎭 РП"),
        BotCommand(command="marriage", description="💍 Брак"),
        BotCommand(command="market", description="🏪 Маркет"),
        BotCommand(command="index", description="📜 Индекс"),
        BotCommand(command="name", description="✨ Ник"),
        BotCommand(command="support", description="📞 Поддержка"),
        BotCommand(command="admin", description="🔑 Админ"),
        BotCommand(command="help", description="❔ Помощь"),
        BotCommand(command="myid", description="🆔 ID"),
    ]
    await bot.set_my_commands(public, scope=BotCommandScopeDefault())
    admin_cmds = public + [
        BotCommand(command="userinfo", description="🔎 Инфо о юзере"),
        BotCommand(command="logs", description="📋 Логи"),
        BotCommand(command="addcard", description="➕ Карта"),
        BotCommand(command="delcard", description="🗑 Удалить карту"),
        BotCommand(command="listcards", description="📜 Список карт"),
        BotCommand(command="syncards", description="🔄 Синхронизировать"),
        BotCommand(command="addmarket", description="🏪 В маркет"),
        BotCommand(command="delmarket", description="🗑 Из маркета"),
        BotCommand(command="broadcast", description="📢 Рассылка"),
        BotCommand(command="replyuser", description="✉️ Ответ юзеру"),
        BotCommand(command="adminlogout", description="🚪 Выйти"),
    ]
    for aid in ADMINS:
        try:
            await bot.set_my_commands(admin_cmds, scope=BotCommandScopeChat(chat_id=aid))
        except Exception as e:
            log.warning("admin menu err %s: %s", aid, e)


async def handle(request):
    return web.Response(text="Andrusho Bot is running!")


async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("BOT_HTTP_PORT", "8080"))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    log.info("HTTP healthcheck on :%d", port)


async def main():
    log.info("Andrusho Bot стартует…")
    await load_banned()
    await setup_commands()
    await bot.delete_webhook(drop_pending_updates=True)
    await start_web_server()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
