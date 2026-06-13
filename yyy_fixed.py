import asyncio
import logging
import os
import random
import time
from html import escape
from typing import Optional
from aiohttp import web

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
BOT_TOKEN = "8990574965:AAF65OxVb64PFoAjCpVVeUNvi3WgIJjWi9Q"
ADMINS = {6654986539, 8441673923, 869665716}
ADMIN_PASSWORD = "aecandrysha"
ADMIN_SESSIONS: set[int] = set()
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
    "limited":   {"emoji": "🖤", "name": "Лимитированная","chance": 1,  "points": 40000, "s": 200},
}

# Цены для маркета
MARKET_PRICES = {
    "common": 15,
    "rare": 50,
    "epic": 150,
    "mythic": 400,
    "legendary": 1000,
    "limited": 3000,
}

CARD_COOLDOWN = 60 * 60
PREMIUM_CARD_COOLDOWN = 30 * 60
BONUS_COOLDOWN = 3 * 60 * 60
DICE_COOLDOWN = 5 * 60
PREMIUM_DICE_COOLDOWN = 3 * 60

_CHESTS = {
    "common_": {"name": "Обычный сундук", "emoji": "🎁", "price": 15, "field": "common__chests", "weights": {"common": 100}},
    "rare_": {"name": "Редкий сундук", "emoji": "💚", "price": 30, "field": "rare__chests", "weights": {"rare": 85, "epic": 15}},
    "mythic_": {"name": "Мифический сундук", "emoji": "❤️", "price": 100, "field": "mythic__chests", "weights": {"mythic": 80, "legendary": 17, "limited": 3}},
}

CHEST_FIELDS = {
    "bonus": "bonus_chests", "epic": "epic_chests", "legend": "legend_chests",
    "common_": "common__chests", "rare_": "rare__chests", "mythic_": "mythic__chests",
}

STAR_CHEST_WEIGHTS = {
    "bonus": {"common": 60, "rare": 30, "epic": 10},
    "epic": {"rare": 40, "epic": 50, "mythic": 10},
    "legend": {"epic": 25, "mythic": 40, "legendary": 30, "limited": 5},
}

# Автоматическая привязка карт к сундукам (кроме limited)
AUTO_CHEST_BINDINGS = {
    "common": ["common_", "bonus"],
    "rare": ["rare_", "bonus", "epic"],
    "epic": ["epic", "legend"],
    "mythic": ["mythic_", "epic", "legend"],
    "legendary": ["mythic_", "legend"],
}

ALL_CHEST_TYPES = list(CHEST_FIELDS.keys())
CHEST_LABELS = {
    "bonus": "🎁 Бонусный (звёзды)", "epic": "💜 Эпический (звёзды)", "legend": "💛 Легендарный (звёзды)",
    "common_": "🎁 Обычный (монеты)", "rare_": "💚 Редкий (монеты)", "mythic_": "❤️ Мифический (монеты)",
}

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
chest_cards_col = db["chest_cards"]

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

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
    if points >= 500_000:   return "Мастер"
    if points >= 100_000:   return "Эксперт"
    if points >= 50_000:    return "Профи"
    if points >= 10_000:    return "Любитель"
    return "Новичок"

def is_admin(uid: int) -> bool:
    return uid in ADMINS or uid in ADMIN_SESSIONS

def is_premium(user: dict) -> bool:
    return user.get("premium_until", 0) > now_ts()

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
        "user_id": tg_user.id, "username": tg_user.username or "", "nickname": tg_user.first_name or f"User{tg_user.id}",
        "points": 0, "s": 0, "cards_count": 0, "favorite_card_id": None,
        "last_card_ts": 0, "last_bonus_ts": 0, "last_dice_ts": 0,
        "bonus_chests": 0, "epic_chests": 0, "legend_chests": 0,
        "common__chests": 0, "rare__chests": 0, "mythic__chests": 0,
        "luck_charges": 0, "premium_until": 0, "created_at": now_ts(),
    }
    await users_col.insert_one(new_user)
    await log_action(tg_user.id, "register", f"@{tg_user.username or ''}")
    return new_user

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
    weights = _CHESTS[chest_type]["weights"] if chest_type in _CHESTS else STAR_CHEST_WEIGHTS.get(chest_type, {"common": 100})
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
        await inventory_col.insert_one({"user_id": user_id, "card_id": str(card["_id"]), "count": 1, "obtained_at": now_ts()})
        await users_col.update_one({"user_id": user_id}, {"$inc": {"cards_count": 1}})
    await users_col.update_one({"user_id": user_id}, {"$inc": {"points": points, "s": s}, "$set": {"last_card_ts": now_ts()}})
    u = await users_col.find_one({"user_id": user_id})
    await log_action(user_id, "card_received", f"{card['name']} +{points}/+{s}")
    return u["points"], u["s"], points, s

async def auto_add_card_to_chests(card_id: str, rarity: str):
    """Автоматически добавляет карту в сундуки по редкости (кроме limited)"""
    if rarity not in AUTO_CHEST_BINDINGS:
        return []
    added_to = []
    for chest_type in AUTO_CHEST_BINDINGS[rarity]:
        existing = await chest_cards_col.find_one({"chest_type": chest_type, "card_id": card_id})
        if not existing:
            await chest_cards_col.insert_one({"chest_type": chest_type, "card_id": card_id, "auto_added": True, "created_at": now_ts()})
            added_to.append(chest_type)
    return added_to

async def auto_add_card_to_market(card: dict):
    """Автоматически добавляет карту в маркет по редкости"""
    rarity = card["rarity"]
    if rarity not in MARKET_PRICES:
        return False
    price = MARKET_PRICES[rarity]
    existing = await market_col.find_one({"card_id": str(card["_id"])})
    if existing:
        return False
    await market_col.insert_one({
        "card_id": str(card["_id"]), "name": card["name"], "rarity": rarity,
        "photo_id": card.get("photo_id"), "price": price, "auto_added": True, "created_at": now_ts(),
    })
    return True

class AddCardFSM(StatesGroup):
    rarity = State()
    name = State()
    photo = State()

class AdminLogin(StatesGroup):
    waiting_password = State()

class AdminGive(StatesGroup):
    target = State()
    amount = State()
    card_pick = State()

class ChestBindFSM(StatesGroup):
    chest_type = State()
    card_id = State()

def _is_cmd(msg: Message) -> bool:
    return bool(msg.text and msg.text.startswith("/"))

@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    await get_or_create_user(msg.from_user)
    await log_action(msg.from_user.id, "start", "")
    text = ("👋 <b>Привет!</b> Тут ты собираешь карточки <b>Andrusho</b> и соревнуешься с другими\n\n"
            "<b>Как получить карточки?</b>\n<blockquote>Отправь <code>andrusho</code> в чат\n"
            "(также: <code>card sir</code>, <code>andryusha</code>, <code>andrysh</code> и др.)</blockquote>\n\nВсе команды — /help")
    rows = [[InlineKeyboardButton(text="📋 Помощь", callback_data="help")]]
    if not is_admin(msg.from_user.id):
        rows.append([InlineKeyboardButton(text="🔑 Взять администратора", callback_data="take_admin")])
    else:
        rows.append([InlineKeyboardButton(text="👑 Админ-панель", callback_data="open_admin")