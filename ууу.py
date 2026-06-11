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
BOT_TOKEN = ""
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
    "common":    {"emoji": "💙", "name": "Обычная",     "chance": 50, "points": 1000,  "coins": 5},
    "rare":      {"emoji": "💚", "name": "Редкая",      "chance": 35, "points": 2000,  "coins": 10},
    "epic":      {"emoji": "💜", "name": "Эпическая",   "chance": 10, "points": 5000,  "coins": 25},
    "mythic":    {"emoji": "❤️", "name": "Мифическая",  "chance": 4,  "points": 10000, "coins": 50},
    "legendary": {"emoji": "💛", "name": "Легендарная", "chance": 1,  "points": 20000, "coins": 100},
}

# ---- КУЛДАУНЫ ----
CARD_COOLDOWN = 60 * 60           # 1 час обычным
PREMIUM_CARD_COOLDOWN = 30 * 60   # 30 минут премиум
BONUS_COOLDOWN = 3 * 60 * 60
DICE_COOLDOWN = 5 * 60
PREMIUM_DICE_COOLDOWN = 3 * 60

# ---- НОВЫЕ СУНДУКИ ЗА МОНЕТЫ ----
# обычный — только common; редкий — rare/epic (маленький шанс эпика);
# мифический — mythic/legendary (маленький шанс леги)
COIN_CHESTS = {
    "common_coin": {
        "name": "Обычный сундук", "emoji": "🎁",
        "price": 15, "field": "common_coin_chests",
        "weights": {"common": 100},
    },
    "rare_coin": {
        "name": "Редкий сундук", "emoji": "💚",
        "price": 30, "field": "rare_coin_chests",
        "weights": {"rare": 85, "epic": 15},
    },
    "mythic_coin": {
        "name": "Мифический сундук", "emoji": "❤️",
        "price": 100, "field": "mythic_coin_chests",
        "weights": {"mythic": 88, "legendary": 12},
    },
}

# Соответствие всех сундуков (star + coin) → поля юзера
CHEST_FIELDS = {
    "bonus": "bonus_chests",
    "epic": "epic_chests",
    "legend": "legend_chests",
    "common_coin": "common_coin_chests",
    "rare_coin": "rare_coin_chests",
    "mythic_coin": "mythic_coin_chests",
}

# Веса для звёздных сундуков (как было)
STAR_CHEST_WEIGHTS = {
    "bonus": {"common": 60, "rare": 30, "epic": 10},
    "epic": {"rare": 40, "epic": 50, "mythic": 10},
    "legend": {"epic": 30, "mythic": 40, "legendary": 30},
}

ALL_CHEST_TYPES = list(CHEST_FIELDS.keys())  # для админки привязки
CHEST_LABELS = {
    "bonus": "🎁 Бонусный (звёзды)",
    "epic": "💜 Эпический (звёзды)",
    "legend": "💛 Легендарный (звёзды)",
    "common_coin": "🎁 Обычный (монеты)",
    "rare_coin": "💚 Редкий (монеты)",
    "mythic_coin": "❤️ Мифический (монеты)",
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
chest_cards_col = db["chest_cards"]  # {chest_type, card_id}

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
    """@username если есть, иначе кликабельная ссылка с ником."""
    uname = u.get("username") or ""
    nick = escape(u.get("nickname") or f"User{u['user_id']}")
    if uname:
        return f"@{uname}"
    return f'<a href="tg://user?id={u["user_id"]}">{nick}</a>'


def tg_user_mention(tg_user) -> str:
    """Из объекта msg.from_user. @username если есть, иначе ссылка."""
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
        "user_id": tg_user.id,
        "username": tg_user.username or "",
        "nickname": tg_user.first_name or f"User{tg_user.id}",
        "points": 0, "coins": 0, "cards_count": 0,
        "favorite_card_id": None,
        "last_card_ts": 0, "last_bonus_ts": 0, "last_dice_ts": 0,
        "bonus_chests": 0, "epic_chests": 0, "legend_chests": 0,
        "common_coin_chests": 0, "rare_coin_chests": 0, "mythic_coin_chests": 0,
        "luck_charges": 0, "premium_until": 0,
        "created_at": now_ts(),
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
    """Выпадает карта из привязанных к сундуку.
       Если привязок нет — fallback на веса редкостей."""
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
    # fallback: по весам редкостей
    weights = COIN_CHESTS[chest_type]["weights"] if chest_type in COIN_CHESTS else STAR_CHEST_WEIGHTS.get(chest_type, {"common": 100})
    rarities = list(weights.keys())
    weights_list = list(weights.values())
    chosen = random.choices(rarities, weights=weights_list)[0]
    return await roll_card(chosen)


async def give_card_to_user(user_id: int, card: dict, premium_bonus: bool = False):
    rd = RARITIES[card["rarity"]]
    points = rd["points"]
    coins = int(rd["coins"] * 1.5) if premium_bonus else rd["coins"]
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
        {"$inc": {"points": points, "coins": coins},
         "$set": {"last_card_ts": now_ts()}},
    )
    u = await users_col.find_one({"user_id": user_id})
    await log_action(user_id, "card_received", f"{card['name']} +{points}/+{coins}")
    return u["points"], u["coins"], points, coins


# ============= СОСТОЯНИЯ =============
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


# ============= /start =============
@router.message(CommandStart())
async def cmd_start(msg: Message):
    await get_or_create_user(msg.from_user)
    await log_action(msg.from_user.id, "start", "")
    text = (
        "👋 <b>Привет!</b> Тут ты собираешь карточки <b>Andrusho</b> и соревнуешься с другими\n\n"
        "<b>Как получить карточки?</b>\n"
        "<blockquote>Отправь <code>andrusho</code> в чат\n"
        "(также: <code>card sir</code>, <code>andryusha</code>, <code>andrysh</code> и др.)</blockquote>\n\n"
        "Все команды — /help"
    )
    rows = [[InlineKeyboardButton(text="📋 Помощь", callback_data="help")]]
    if not is_admin(msg.from_user.id):
        rows.append([InlineKeyboardButton(text="🔑 Взять администратора", callback_data="take_admin")])
    else:
        rows.append([InlineKeyboardButton(text="👑 Админ-панель", callback_data="open_admin")])
    await msg.reply(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data == "help")
async def cb_help(cq: CallbackQuery):
    await cmd_help(cq.message); await cq.answer()


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
        "🆔 /myid — мой ID"
        "</blockquote>\n\n"
        "<b>Триггеры карты</b>\n"
        f"<blockquote>{triggers}</blockquote>\n\n"
        "<b>Действия</b> (ответом на сообщение):\n"
        "<code>andrusho поцеловать</code>, <code>andrusho брак</code>, <code>andrusho цитата</code> и т.д."
    )
    await msg.reply(text)


@router.message(Command("myid"))
async def cmd_myid(msg: Message):
    await msg.reply(f"Ваш ID: <code>{msg.from_user.id}</code>")


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
        f"<b>Профиль «{escape(user['nickname'])}»{prem_mark}</b> ({tg_user_mention(msg.from_user)})\n\n"
        f"<blockquote>"
        f"🔎 ID • <code>{user['user_id']}</code>\n"
        f"🃏 Карт • <b>{user.get('cards_count',0)}</b> из <b>{total_cards}</b>\n"
        f"✨ Очки • <b>{user.get('points',0):,}</b>\n"
        f"💰 Монеты • <b>{user.get('coins',0)}</b>\n"
        f"🏆 Титул • <b>{get_title(user.get('points',0))}</b>\n"
        f"❤️ Любимая карта • <b>{escape(fav_text)}</b>"
        f"{chr(10) + '🚀 PREMIUM до ' + time.strftime('%d.%m.%Y', time.localtime(user['premium_until'])) if is_premium(user) else ''}"
        f"</blockquote>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎒 Инвентарь", callback_data="inventory")],
        [InlineKeyboardButton(text="🃏 Мои карты", callback_data="mycards")],
        [InlineKeyboardButton(text="📦 Мои сундуки", callback_data="open_chests")],
    ])
    if fav_photo:
        try:
            await msg.reply_photo(fav_photo, caption=text, reply_markup=kb); return
        except Exception:
            pass
    await msg.reply(text, reply_markup=kb)


@router.message(Command("name"))
async def cmd_name(msg: Message):
    parts = msg.text.split(maxsplit=1)
    if len(parts) < 2:
        await msg.reply("<b>Использование:</b> /name [ник]"); return
    new_name = parts[1].strip()[:32]
    await get_or_create_user(msg.from_user)
    await users_col.update_one({"user_id": msg.from_user.id}, {"$set": {"nickname": new_name}})
    await msg.reply(f"✅ Никнейм: <b>{escape(new_name)}</b>")


@router.callback_query(F.data == "inventory")
async def cb_inventory(cq: CallbackQuery):
    user = await get_or_create_user(cq.from_user)
    text = (
        f"🎒 <b>Инвентарь</b> ({tg_user_mention(cq.from_user)})\n\n<blockquote>"
        f"💰 Монеты • {user.get('coins',0)}\n"
        f"✨ Очки • {user.get('points',0):,}\n"
        f"🎁 Бонусный сундук • {user.get('bonus_chests',0)}\n"
        f"💜 Эпический сундук • {user.get('epic_chests',0)}\n"
        f"💛 Легендарный сундук • {user.get('legend_chests',0)}\n"
        f"🎁 Обычный (монеты) • {user.get('common_coin_chests',0)}\n"
        f"💚 Редкий (монеты) • {user.get('rare_coin_chests',0)}\n"
        f"❤️ Мифический (монеты) • {user.get('mythic_coin_chests',0)}\n"
        f"🍀 Удача (зарядов) • {user.get('luck_charges',0)}\n"
        f"🚀 Premium • {'до ' + time.strftime('%d.%m.%Y', time.localtime(user['premium_until'])) if is_premium(user) else 'нет'}"
        f"</blockquote>"
    )
    await cq.message.reply(text); await cq.answer()


@router.callback_query(F.data == "mycards")
async def cb_mycards(cq: CallbackQuery):
    items = await inventory_col.find({"user_id": cq.from_user.id}).to_list(length=50)
    if not items:
        await cq.message.reply(f"{tg_user_mention(cq.from_user)}, у тебя пока нет карт. Напиши <code>andrusho</code>"); await cq.answer(); return
    await cq.message.reply(f"🃏 <b>Карты {tg_user_mention(cq.from_user)}</b> ({len(items)})")
    for it in items[:10]:
        try:
            card = await cards_col.find_one({"_id": ObjectId(it["card_id"])})
            if not card: continue
            rd = RARITIES[card["rarity"]]
            cap = f"{rd['emoji']} <b>{escape(card['name'])}</b>\n💎 {rd['name']} ×{it['count']}"
            if card.get("photo_id"):
                await cq.message.reply_photo(card["photo_id"], caption=cap)
            else:
                await cq.message.reply(cap)
        except Exception:
            continue
    await cq.answer()


# ============= ПОЛУЧЕНИЕ КАРТЫ =============
async def try_give_card(msg: Message):
    user = await get_or_create_user(msg.from_user)
    cd = PREMIUM_CARD_COOLDOWN if is_premium(user) else CARD_COOLDOWN
    elapsed = now_ts() - user.get("last_card_ts", 0)
    if elapsed < cd:
        left = cd - elapsed
        await msg.reply(f"Вы посмотрели, но <b>Andrusho</b> не было рядом 🙈\n\n⏳ <b>{fmt_time_left(left)}</b>")
        return
    rarity_override = None
    if user.get("luck_charges", 0) > 0:
        rarity_override = random.choices(["rare", "epic", "mythic", "legendary"], weights=[50, 30, 15, 5])[0]
        await users_col.update_one({"user_id": msg.from_user.id}, {"$inc": {"luck_charges": -1}})
    card = await roll_card(rarity_override)
    if not card:
        await msg.reply("😿 Карт в базе нет"); return
    new_p, new_c, gp, gc = await give_card_to_user(msg.from_user.id, card, premium_bonus=is_premium(user))
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
            log.info("check_subs %s: %s (доверяем)", ch, e)
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
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        ); return
    elapsed = now_ts() - user.get("last_bonus_ts", 0)
    if elapsed < BONUS_COOLDOWN:
        left = BONUS_COOLDOWN - elapsed
        await msg.reply(f"🎁 Следующий бонус через <b>{fmt_time_left(left)}</b>"); return
    amount = 2 if is_premium(user) else 1
    await users_col.update_one(
        {"user_id": msg.from_user.id},
        {"$inc": {"bonus_chests": amount}, "$set": {"last_bonus_ts": now_ts()}},
    )
    await log_action(msg.from_user.id, "bonus", f"+{amount}")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📦 Открыть сундуки", callback_data="open_chests")]])
    await msg.reply(f"🎉 {tg_user_mention(msg.from_user)} получил <b>{amount}</b> бонусный сундук!", reply_markup=kb)


@router.callback_query(F.data == "check_subs")
async def cb_check_subs(cq: CallbackQuery):
    not_subbed = await check_subs(cq.from_user.id)
    if not_subbed:
        await cq.answer("❌ Ты ещё не подписан", show_alert=True); return
    await cq.answer("✅ Подписка ок! Жми /bonus", show_alert=True)


# ============= ТОП =============
@router.message(Command("top"))
async def cmd_top(msg: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✨ По очкам", callback_data="top:points")],
        [InlineKeyboardButton(text="🃏 По картам", callback_data="top:cards_count")],
        [InlineKeyboardButton(text="💰 По монетам", callback_data="top:coins")],
    ])
    await msg.reply("🏆 <b>Топ 10</b>\nВыберите критерий:", reply_markup=kb)


@router.callback_query(F.data.startswith("top:"))
async def cb_top(cq: CallbackQuery):
    field = cq.data.split(":", 1)[1]
    if field not in ("points", "cards_count", "coins"):
        await cq.answer("❌", show_alert=True); return
    try:
        users = await users_col.find({field: {"$gt": 0}}).sort(field, -1).limit(10).to_list(length=10)
    except Exception as e:
        log.exception("top error: %s", e)
        await cq.message.reply("❌ Ошибка получения топа"); await cq.answer(); return
    if not users:
        await cq.message.reply("Топ пуст — никто ещё ничего не набрал"); await cq.answer(); return
    titles = {"points": "по очкам ✨", "cards_count": "по картам 🃏", "coins": "по монетам 💰"}
    lines = [f"🏆 <b>Топ 10 {titles[field]}</b>\n"]
    medals = ["🥇", "🥈", "🥉"] + [f"<b>{i}.</b>" for i in range(4, 11)]
    for i, u in enumerate(users):
        val = u.get(field, 0)
        if field == "points": val = f"{val:,}"
        prem = " 💎" if is_premium(u) else ""
        lines.append(f"{medals[i]} {user_mention(u)}{prem} • {val}")
    await cq.message.reply("\n".join(lines)); await cq.answer()


# ============= МАГАЗИН =============
@router.message(Command("shop"))
async def cmd_shop(msg: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Сундуки (⭐)", callback_data="shop:chests")],
        [InlineKeyboardButton(text="🪙 Сундуки (монеты)", callback_data="shop:coin_chests")],
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
    await cq.message.reply(text, reply_markup=kb); await cq.answer()


@router.callback_query(F.data == "shop:coin_chests")
async def cb_shop_coin_chests(cq: CallbackQuery):
    user = await get_or_create_user(cq.from_user)
    text = (
        "🪙 <b>Сундуки за монеты</b>\n\n<blockquote>"
        f"🎁 Обычный — <b>{COIN_CHESTS['common_coin']['price']}</b> монет (только обычные карты)\n"
        f"💚 Редкий — <b>{COIN_CHESTS['rare_coin']['price']}</b> монет (редкие + маленький шанс эпика)\n"
        f"❤️ Мифический — <b>{COIN_CHESTS['mythic_coin']['price']}</b> монет (мифик + маленький шанс леги)\n\n"
        f"💰 Баланс: <b>{user['coins']}</b>"
        "</blockquote>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🎁 Обычный [{COIN_CHESTS['common_coin']['price']}💰]", callback_data="buy_coin_chest:common_coin")],
        [InlineKeyboardButton(text=f"💚 Редкий [{COIN_CHESTS['rare_coin']['price']}💰]", callback_data="buy_coin_chest:rare_coin")],
        [InlineKeyboardButton(text=f"❤️ Мифический [{COIN_CHESTS['mythic_coin']['price']}💰]", callback_data="buy_coin_chest:mythic_coin")],
    ])
    await cq.message.reply(text, reply_markup=kb); await cq.answer()


@router.callback_query(F.data.startswith("buy_coin_chest:"))
async def cb_buy_coin_chest(cq: CallbackQuery):
    chest_type = cq.data.split(":", 1)[1]
    if chest_type not in COIN_CHESTS:
        await cq.answer("❌", show_alert=True); return
    chest = COIN_CHESTS[chest_type]
    user = await get_or_create_user(cq.from_user)
    if user["coins"] < chest["price"]:
        await cq.answer(f"❌ Нужно {chest['price']} монет", show_alert=True); return
    await users_col.update_one(
        {"user_id": cq.from_user.id},
        {"$inc": {"coins": -chest["price"], chest["field"]: 1}},
    )
    await log_action(cq.from_user.id, "buy_coin_chest", chest_type)
    await cq.answer(f"✅ {chest['name']} куплен!", show_alert=True)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📦 Открыть", callback_data="open_chests")]])
    await cq.message.reply(f"🎉 {tg_user_mention(cq.from_user)} купил <b>{chest['name']}</b>!", reply_markup=kb)


@router.callback_query(F.data == "shop:items")
async def cb_shop_items(cq: CallbackQuery):
    user = await get_or_create_user(cq.from_user)
    text = (
        f"⚡ <b>Бустеры за монеты</b>\n\n<blockquote>"
        f"⏱ Ускоритель — <b>50</b> монет (сброс кулдауна карты)\n"
        f"🍀 Удача — <b>25</b> монет (повышенная редкость)\n\n"
        f"💰 Баланс: <b>{user['coins']}</b></blockquote>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏱ Ускоритель [50💰]", callback_data="buy_item:speed")],
        [InlineKeyboardButton(text="🍀 Удача [25💰]", callback_data="buy_item:luck")],
    ])
    await cq.message.reply(text, reply_markup=kb); await cq.answer()


@router.callback_query(F.data.startswith("buy_item:"))
async def cb_buy_item(cq: CallbackQuery):
    item = cq.data.split(":", 1)[1]
    prices = {"speed": 50, "luck": 25}
    price = prices[item]
    user = await get_or_create_user(cq.from_user)
    if user["coins"] < price:
        await cq.answer(f"❌ Нужно {price} монет", show_alert=True); return
    if item == "speed":
        await users_col.update_one({"user_id": cq.from_user.id},
                                   {"$inc": {"coins": -price}, "$set": {"last_card_ts": 0}})
        await cq.answer("⏱ Кулдаун сброшен!", show_alert=True)
    else:
        await users_col.update_one({"user_id": cq.from_user.id},
                                   {"$inc": {"coins": -price, "luck_charges": 1}})
        await cq.answer("🍀 Удача активирована!", show_alert=True)
    await log_action(cq.from_user.id, "buy_item", item)


@router.callback_query(F.data == "shop:premium")
async def cb_shop_premium(cq: CallbackQuery):
    await cmd_premium(cq.message); await cq.answer()


@router.message(Command("premium"))
async def cmd_premium(msg: Message):
    text = (
        "🚀 <b>Premium — 30 ⭐</b>\n\n<blockquote>"
        "1. ⏳ Карта раз в <b>30 мин</b> (вместо 1ч)\n"
        "2. 🎲 Кости раз в <b>3 минуты</b> (вместо 5мин)\n"
        "3. 💎 Алмаз рядом с ником в топе\n"
        "4. 🎁 Двойной бонус: <b>2 сундука</b> при /bonus\n"
        "5. 🍀 Повышенный шанс легендарок\n"
        "6. 🌟 Отметка <b>PREMIUM</b> в профиле\n"
        "7. 💰 <b>+50%</b> монет за карту\n"
        "8. 🎨 Эксклюзивный эпич-сундук раз в неделю\n\n"
        "Срок: <b>30 дней</b>\n"
        f"💳 Чтобы купить Premium — отправьте <b>30 ⭐</b> на канал {DONATE_CHANNEL}"
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
    rows.append([InlineKeyboardButton(text="🛒 Купить (монеты)", callback_data="shop:coin_chests")])
    rows.append([InlineKeyboardButton(text="🛒 Купить (⭐)", url=DONATE_CHANNEL)])
    await cq.message.reply(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await cq.answer()


@router.callback_query(F.data.startswith("open_chest:"))
async def cb_open_chest(cq: CallbackQuery):
    kind = cq.data.split(":", 1)[1]
    if kind not in CHEST_FIELDS:
        await cq.answer("❌", show_alert=True); return
    field = CHEST_FIELDS[kind]
    user = await get_or_create_user(cq.from_user)
    if user.get(field, 0) < 1:
        await cq.answer("❌ Нет таких сундуков", show_alert=True); return
    card = await roll_chest_card(kind)
    if not card:
        await cq.answer("❌ В сундуке нет карт (админ ещё не настроил)", show_alert=True); return
    await users_col.update_one({"user_id": cq.from_user.id}, {"$inc": {field: -1}})
    await give_card_to_user(cq.from_user.id, card, premium_bonus=is_premium(user))
    rd = RARITIES[card["rarity"]]
    caption = (
        f"📦 <b>Из сундука выпало для {tg_user_mention(cq.from_user)}:</b>\n\n<b>«{escape(card['name'])}»</b>\n<blockquote>"
        f"💎 {rd['emoji']} {rd['name']}\n✨ +{rd['points']:,}\n💰 +{rd['coins']}</blockquote>"
    )
    if card.get("photo_id"):
        await cq.message.reply_photo(card["photo_id"], caption=caption)
    else:
        await cq.message.reply(caption)
    await cq.answer()


# ============= ИНДЕКС =============
@router.message(Command("index"))
async def cmd_index(msg: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{d['emoji']} {d['name']}", callback_data=f"idx:{r}")]
        for r, d in RARITIES.items()
    ] + [[InlineKeyboardButton(text="📜 Все (список)", callback_data="idx:all")]])
    total = await cards_col.count_documents({})
    await msg.reply(f"📜 <b>Индекс карт</b> ({total})\nВыберите редкость:", reply_markup=kb)


@router.callback_query(F.data.startswith("idx:"))
async def cb_index(cq: CallbackQuery):
    key = cq.data.split(":", 1)[1]
    if key == "all":
        cards = await cards_col.find({}).sort("rarity", 1).to_list(length=200)
        if not cards:
            await cq.message.reply(f"{tg_user_mention(cq.from_user)}, карт нет"); await cq.answer(); return
        lines = [f"📜 <b>Все карты ({len(cards)})</b> для {tg_user_mention(cq.from_user)}\n"]
        for c in cards:
            rd = RARITIES.get(c["rarity"], {"emoji": "❔", "name": "?"})
            lines.append(f"{rd['emoji']} <b>{escape(c['name'])}</b>")
        text = "\n".join(lines)
        for i in range(0, len(text), 3500):
            await cq.message.reply(text[i:i+3500])
        await cq.answer(); return
    cards = await cards_col.find({"rarity": key}).to_list(length=100)
    if not cards:
        await cq.message.reply(f"{tg_user_mention(cq.from_user)}, в категории <b>{RARITIES[key]['name']}</b> карт нет"); await cq.answer(); return
    rd = RARITIES[key]
    await cq.message.reply(f"{rd['emoji']} <b>{rd['name']} карты ({len(cards)})</b> для {tg_user_mention(cq.from_user)}")
    for c in cards[:30]:
        cap = f"{rd['emoji']} <b>{escape(c['name'])}</b>\n💎 {rd['name']}"
        if c.get("photo_id"):
            try:
                await cq.message.reply_photo(c["photo_id"], caption=cap)
            except Exception:
                await cq.message.reply(cap)
        else:
            await cq.message.reply(cap)
    await cq.answer()


# ============= МАРКЕТ =============
@router.message(Command("market"))
async def cmd_market(msg: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{d['emoji']} {d['name']}", callback_data=f"mk:{r}")]
        for r, d in RARITIES.items()
    ])
    await msg.reply("🏪 <b>Маркетплейс</b>\nВыберите редкость:", reply_markup=kb)


@router.callback_query(F.data.startswith("mk:"))
async def cb_market(cq: CallbackQuery):
    rarity = cq.data.split(":", 1)[1]
    items = await market_col.find({"rarity": rarity}).to_list(length=20)
    if not items:
        await cq.message.reply(f"{tg_user_mention(cq.from_user)}, в <b>{RARITIES[rarity]['name']}</b> пусто"); await cq.answer(); return
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
        await cq.answer("❌ Лот удалён", show_alert=True); return
    user = await get_or_create_user(cq.from_user)
    if user["coins"] < item["price"]:
        await cq.answer(f"❌ Нужно {item['price']} монет", show_alert=True); return
    card = await cards_col.find_one({"_id": ObjectId(item["card_id"])})
    if not card:
        await cq.answer("❌ Карта не найдена", show_alert=True); return
    await users_col.update_one({"user_id": cq.from_user.id}, {"$inc": {"coins": -item["price"]}})
    await give_card_to_user(cq.from_user.id, card)
    await market_col.delete_one({"_id": item["_id"]})
    await log_action(cq.from_user.id, "market_buy", f"{item['name']} -{item['price']}")
    await cq.message.reply(f"✅ {tg_user_mention(cq.from_user)} купил <b>{escape(card['name'])}</b>!")
    await cq.answer()


# ============= КОСТИ (2 анимированных кубика) =============
@router.message(Command("diceplay"))
async def cmd_diceplay(msg: Message):
    user = await get_or_create_user(msg.from_user)
    cd = PREMIUM_DICE_COOLDOWN if is_premium(user) else DICE_COOLDOWN
    elapsed = now_ts() - user.get("last_dice_ts", 0)
    if elapsed < cd:
        await msg.reply(f"🎲 Доступно через <b>{fmt_time_left(cd - elapsed)}</b>"); return
    if user["coins"] < 1:
        await msg.reply("💸 Нет монет"); return

    # 1) Кубик игрока
    player_msg = await msg.reply_dice(emoji="🎲")
    user_roll = player_msg.dice.value
    await asyncio.sleep(2)
    # 2) Кубик бота — отвечаем на сообщение пользователя
    bot_msg = await msg.reply_dice(emoji="🎲")
    bot_roll = bot_msg.dice.value
    # ждём окончания анимации
    await asyncio.sleep(3.5)

    if user_roll > bot_roll:
        win = random.randint(3, 10)
        await users_col.update_one({"user_id": msg.from_user.id}, {"$inc": {"coins": win}})
        result = f"🎉 {tg_user_mention(msg.from_user)} победил! +<b>{win}</b> монет"
    elif user_roll < bot_roll:
        loss = min(user["coins"], random.randint(1, 5))
        await users_col.update_one({"user_id": msg.from_user.id}, {"$inc": {"coins": -loss}})
        result = f"😿 {tg_user_mention(msg.from_user)} проиграл! -<b>{loss}</b> монет"
    else:
        result = f"🤝 Ничья ({tg_user_mention(msg.from_user)})"
    await users_col.update_one({"user_id": msg.from_user.id}, {"$set": {"last_dice_ts": now_ts()}})
    await msg.reply(f"🎲 Игрок: <b>{user_roll}</b> / Бот: <b>{bot_roll}</b>\n{result}")


# ============= РП / БРАК =============
RP_ACTIONS = {
    "поцеловать": ("💋", "{a} поцеловал(а) {b}"),
    "обнять":     ("🤗", "{a} обнял(а) {b}"),
    "ударить":    ("👊", "{a} ударил(а) {b}"),
    "укусить":    ("😬", "{a} укусил(а) {b}"),
    "погладить":  ("✋", "{a} погладил(а) {b}"),
    "пнуть":      ("🦵", "{a} пнул(а) {b}"),
    "лизнуть":    ("👅", "{a} лизнул(а) {b}"),
    "шлепнуть":   ("✋", "{a} шлёпнул(а) {b}"),
    "обнимашки":  ("🫂", "{a} крепко обнял(а) {b}"),
    "потанцевать":("💃", "{a} танцует с {b}"),
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
        if p: text += f"\n💑 В браке с <b>{escape(p['nickname'])}</b>"
    await msg.reply(text)


async def handle_rp(msg: Message, action: str):
    if not msg.reply_to_message or not msg.reply_to_message.from_user:
        await msg.reply("Ответьте на сообщение игрока"); return
    target = msg.reply_to_message.from_user
    if target.id == msg.from_user.id:
        await msg.reply("Себя нельзя 😉"); return
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
            await msg.reply("Ответьте на сообщение"); return
        target = msg.reply_to_message.from_user
        if target.id == uid or target.is_bot:
            await msg.reply("Нельзя"); return
        existing = await marriages_col.find_one({
            "$or": [{"user1_id": uid}, {"user2_id": uid},
                    {"user1_id": target.id}, {"user2_id": target.id}],
            "status": "active",
        })
        if existing:
            await msg.reply("💔 Кто-то уже в браке"); return
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
        if not p: await msg.reply("Нет предложений"); return
        await marriages_col.insert_one({"user1_id": p["from_id"], "user2_id": uid,
                                        "status": "active", "created_at": now_ts()})
        await proposals_col.delete_one({"_id": p["_id"]})
        await msg.reply("💖 Брак!")
        return
    if action.startswith("отклонить"):
        p = await proposals_col.find_one({"to_id": uid}, sort=[("created_at", -1)])
        if p: await proposals_col.delete_one({"_id": p["_id"]})
        await msg.reply("💔 Отклонено")
        return
    if action.startswith("развод"):
        m = await marriages_col.find_one({"$or": [{"user1_id": uid}, {"user2_id": uid}], "status": "active"})
        if not m: await msg.reply("Вы не в браке"); return
        await marriages_col.update_one({"_id": m["_id"]}, {"$set": {"status": "divorced"}})
        await msg.reply("💔 Развод")


async def handle_quote(msg: Message, kind: str, payload: str):
    text = payload.strip().strip("«»\"'")
    if not text and msg.reply_to_message and msg.reply_to_message.text:
        text = msg.reply_to_message.text
        author = msg.reply_to_message.from_user.first_name if msg.reply_to_message.from_user else "—"
    else:
        author = msg.from_user.first_name
    if not text:
        await msg.reply(f"<code>andrusho {kind} «текст»</code>"); return
    emoji = "💬" if kind == "цитата" else "🎨"
    await msg.reply(f"{emoji} <blockquote>«{escape(text)}»\n— <i>{escape(author or '')}</i></blockquote>")


# ============= АДМИН ВХОД =============
@router.callback_query(F.data == "take_admin")
async def cb_take_admin(cq: CallbackQuery, state: FSMContext):
    if is_admin(cq.from_user.id):
        await cq.answer("Вы уже админ", show_alert=True); return
    await cq.message.reply("🔐 Введите пароль администратора:")
    await state.set_state(AdminLogin.waiting_password)
    await cq.answer()


@router.callback_query(F.data == "open_admin")
async def cb_open_admin(cq: CallbackQuery):
    if not is_admin(cq.from_user.id):
        await cq.answer("❌", show_alert=True); return
    await show_admin_panel(cq.message); await cq.answer()


@router.message(Command("admin"))
async def cmd_admin(msg: Message, state: FSMContext):
    if is_admin(msg.from_user.id):
        await show_admin_panel(msg); return
    await msg.reply("🔐 Введите пароль администратора:")
    await state.set_state(AdminLogin.waiting_password)


@router.message(AdminLogin.waiting_password)
async def admin_password(msg: Message, state: FSMContext):
    if msg.text and msg.text.strip() == ADMIN_PASSWORD:
        ADMIN_SESSIONS.add(msg.from_user.id)
        await state.clear()
        await log_action(msg.from_user.id, "admin_login", "OK")
        await msg.reply("✅ Доступ разрешён!")
        await show_admin_panel(msg)
    else:
        await state.clear()
        await log_action(msg.from_user.id, "admin_login", "FAIL")
        await msg.reply("❌ Неверный пароль")


@router.message(Command("adminlogout"))
async def cmd_adminlogout(msg: Message):
    ADMIN_SESSIONS.discard(msg.from_user.id)
    await msg.reply("👋 Вышли")


async def show_admin_panel(msg: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Все юзеры", callback_data="adm:users")],
        [InlineKeyboardButton(text="🎁 Выдать игроку", callback_data="adm:give_menu")],
        [InlineKeyboardButton(text="🔎 Инфо о юзере", callback_data="adm:userinfo")],
        [InlineKeyboardButton(text="➕ Добавить карту", callback_data="adm:addcard")],
        [InlineKeyboardButton(text="📜 Все карты (ID)", callback_data="adm:listcards")],
        [InlineKeyboardButton(text="🏪 Загрузить в маркет", callback_data="adm:loadmarket")],
        [InlineKeyboardButton(text="🔗 Привязать карту к сундуку", callback_data="adm:chestbind")],
        [InlineKeyboardButton(text="📋 Логи", callback_data="adm:logs")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="adm:stats")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="adm:broadcast")],
    ])
    await msg.reply("👑 <b>Админ-панель</b>", reply_markup=kb)


# ============= АДМИН-ВЫДАЧА (FSM) =============
@router.callback_query(F.data == "adm:give_menu")
async def cb_adm_give_menu(cq: CallbackQuery):
    if not is_admin(cq.from_user.id):
        await cq.answer("❌", show_alert=True); return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Монеты", callback_data="give:coins")],
        [InlineKeyboardButton(text="✨ Очки", callback_data="give:points")],
        [InlineKeyboardButton(text="🎁 Бонусный сундук", callback_data="give:bonus_chests")],
        [InlineKeyboardButton(text="💜 Эпич сундук", callback_data="give:epic_chests")],
        [InlineKeyboardButton(text="💛 Лег сундук", callback_data="give:legend_chests")],
        [InlineKeyboardButton(text="🎁 Обычный (монеты)", callback_data="give:common_coin_chests")],
        [InlineKeyboardButton(text="💚 Редкий (монеты)", callback_data="give:rare_coin_chests")],
        [InlineKeyboardButton(text="❤️ Мифический (монеты)", callback_data="give:mythic_coin_chests")],
        [InlineKeyboardButton(text="🍀 Заряды удачи", callback_data="give:luck_charges")],
        [InlineKeyboardButton(text="🃏 Карту (из индекса)", callback_data="give:card")],
        [InlineKeyboardButton(text="🚀 Премиум (дней)", callback_data="give:premium")],
    ])
    await cq.message.reply("🎁 <b>Что выдать?</b>", reply_markup=kb); await cq.answer()


@router.callback_query(F.data.startswith("give:"))
async def cb_give_choose(cq: CallbackQuery, state: FSMContext):
    if not is_admin(cq.from_user.id):
        await cq.answer("❌", show_alert=True); return
    gtype = cq.data.split(":", 1)[1]
    await state.update_data(give_type=gtype)
    await cq.message.reply("👤 Введите <b>user_id</b> игрока:")
    await state.set_state(AdminGive.target)
    await cq.answer()


@router.message(AdminGive.target)
async def fsm_give_target(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        await state.clear(); return
    try:
        uid = int(msg.text.strip())
    except Exception:
        await msg.reply("❌ Неверный ID. Введите число"); return
    target = await users_col.find_one({"user_id": uid})
    if not target:
        await msg.reply("❌ Юзер не найден (он должен сначала /start). Попробуйте ещё раз или /cancel"); return
    await state.update_data(target_id=uid, target_name=target["nickname"])
    data = await state.get_data()
    gtype = data["give_type"]
    if gtype == "card":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"{d['emoji']} {d['name']}", callback_data=f"givec_rar:{r}")]
            for r, d in RARITIES.items()
        ])
        await msg.reply(f"Юзер: <b>{escape(target['nickname'])}</b>\nВыберите редкость карты:", reply_markup=kb)
        await state.set_state(AdminGive.card_pick)
    elif gtype == "premium":
        await msg.reply(f"Юзер: <b>{escape(target['nickname'])}</b>\nВведите <b>сколько дней</b> премиума:")
        await state.set_state(AdminGive.amount)
    else:
        await msg.reply(f"Юзер: <b>{escape(target['nickname'])}</b>\nВведите <b>количество</b>:")
        await state.set_state(AdminGive.amount)


@router.message(AdminGive.amount)
async def fsm_give_amount(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        await state.clear(); return
    try:
        amount = int(msg.text.strip())
    except Exception:
        await msg.reply("❌ Введите число"); return
    data = await state.get_data()
    uid = data["target_id"]
    gtype = data["give_type"]
    if gtype == "premium":
        cur = await users_col.find_one({"user_id": uid})
        new_until = max(now_ts(), cur.get("premium_until", 0)) + amount * 86400
        await users_col.update_one({"user_id": uid}, {"$set": {"premium_until": new_until}})
        await log_action(msg.from_user.id, "give_premium", f"to={uid} days={amount}")
        await msg.reply(f"✅ Премиум выдан на <b>{amount}</b> дней до {time.strftime('%d.%m.%Y', time.localtime(new_until))}")
    else:
        await users_col.update_one({"user_id": uid}, {"$inc": {gtype: amount}})
        await log_action(msg.from_user.id, f"give_{gtype}", f"to={uid} +{amount}")
        await msg.reply(f"✅ Выдано <b>{amount}</b> [{gtype}] игроку <b>{escape(data['target_name'])}</b>")
    await state.clear()


@router.callback_query(F.data.startswith("givec_rar:"), AdminGive.card_pick)
async def cb_givec_rarity(cq: CallbackQuery, state: FSMContext):
    rarity = cq.data.split(":", 1)[1]
    cards = await cards_col.find({"rarity": rarity}).to_list(length=50)
    if not cards:
        await cq.message.reply("В этой редкости карт нет"); await cq.answer(); return
    kb_rows = []
    for c in cards[:30]:
        kb_rows.append([InlineKeyboardButton(text=f"{RARITIES[rarity]['emoji']} {c['name']}",
                                              callback_data=f"givec_card:{c['_id']}")])
    await cq.message.reply(f"Выберите карту ({RARITIES[rarity]['name']}):",
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))
    await cq.answer()


@router.callback_query(F.data.startswith("givec_card:"), AdminGive.card_pick)
async def cb_givec_card(cq: CallbackQuery, state: FSMContext):
    card_id = cq.data.split(":", 1)[1]
    data = await state.get_data()
    uid = data["target_id"]
    try:
        card = await cards_col.find_one({"_id": ObjectId(card_id)})
    except Exception:
        card = None
    if not card:
        await cq.answer("❌ Карта не найдена", show_alert=True); await state.clear(); return
    await give_card_to_user(uid, card)
    await log_action(cq.from_user.id, "give_card", f"to={uid} card={card['name']}")
    rd = RARITIES[card["rarity"]]
    cap = f"✅ Карта <b>{escape(card['name'])}</b> {rd['emoji']} выдана <b>{escape(data['target_name'])}</b>"
    if card.get("photo_id"):
        try:
            await cq.message.reply_photo(card["photo_id"], caption=cap)
        except Exception:
            await cq.message.reply(cap)
    else:
        await cq.message.reply(cap)
    await state.clear(); await cq.answer()


@router.message(Command("cancel"))
async def cmd_cancel(msg: Message, state: FSMContext):
    await state.clear()
    await msg.reply("Отменено")


# ============= ПРИВЯЗКА КАРТ К СУНДУКАМ =============
@router.callback_query(F.data == "adm:chestbind")
async def cb_adm_chestbind(cq: CallbackQuery, state: FSMContext):
    if not is_admin(cq.from_user.id):
        await cq.answer("❌", show_alert=True); return
    rows = [[InlineKeyboardButton(text=CHEST_LABELS[k], callback_data=f"cbind:{k}")] for k in ALL_CHEST_TYPES]
    rows.append([InlineKeyboardButton(text="📜 Посмотреть привязки", callback_data="cbind_list")])
    await cq.message.reply(
        "🔗 <b>Привязка карт к сундукам</b>\n"
        "<blockquote>Если у сундука есть привязанные карты — выпадают только они.\n"
        "Если привязок нет — выпадает случайная по редкости.</blockquote>\n"
        "Выберите тип сундука:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await cq.answer()


@router.callback_query(F.data.startswith("cbind:"))
async def cb_chest_bind_pick(cq: CallbackQuery, state: FSMContext):
    if not is_admin(cq.from_user.id):
        await cq.answer("❌", show_alert=True); return
    chest_type = cq.data.split(":", 1)[1]
    if chest_type not in CHEST_FIELDS:
        await cq.answer("❌", show_alert=True); return
    await state.update_data(chest_type=chest_type)
    # покажем уже привязанные карты + предложим добавить
    links = await chest_cards_col.find({"chest_type": chest_type}).to_list(length=None)
    lines = [f"🔗 <b>{CHEST_LABELS[chest_type]}</b>\n"]
    if links:
        lines.append("<b>Привязано:</b>")
        for l in links:
            try:
                c = await cards_col.find_one({"_id": ObjectId(l["card_id"])})
                if c:
                    rd = RARITIES.get(c["rarity"], {"emoji": "❔"})
                    lines.append(f"  {rd['emoji']} <b>{escape(c['name'])}</b> — <code>{c['_id']}</code>")
            except Exception:
                pass
    else:
        lines.append("<i>Пока ничего не привязано</i>")
    lines.append("\nОтправьте <b>card_id</b> карты, чтобы привязать (или /cancel).\n"
                 "Чтобы отвязать — отправьте <code>del &lt;card_id&gt;</code>.")
    await cq.message.reply("\n".join(lines))
    await state.set_state(ChestBindFSM.card_id)
    await cq.answer()


@router.callback_query(F.data == "cbind_list")
async def cb_chest_bind_list(cq: CallbackQuery):
    if not is_admin(cq.from_user.id):
        await cq.answer("❌", show_alert=True); return
    lines = ["🔗 <b>Все привязки</b>\n"]
    for k in ALL_CHEST_TYPES:
        links = await chest_cards_col.find({"chest_type": k}).to_list(length=None)
        lines.append(f"\n<b>{CHEST_LABELS[k]}</b> ({len(links)}):")
        for l in links:
            try:
                c = await cards_col.find_one({"_id": ObjectId(l["card_id"])})
                if c:
                    rd = RARITIES.get(c["rarity"], {"emoji": "❔"})
                    lines.append(f"  {rd['emoji']} {escape(c['name'])} — <code>{c['_id']}</code>")
            except Exception:
                pass
        if not links:
            lines.append("  <i>пусто</i>")
    text = "\n".join(lines)
    for i in range(0, len(text), 3500):
        await cq.message.reply(text[i:i+3500])
    await cq.answer()


@router.message(ChestBindFSM.card_id)
async def fsm_chest_bind(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        await state.clear(); return
    data = await state.get_data()
    chest_type = data.get("chest_type")
    txt = (msg.text or "").strip()
    # отвязка
    if txt.lower().startswith("del "):
        try:
            cid = txt.split(maxsplit=1)[1].strip()
            ObjectId(cid)
            res = await chest_cards_col.delete_one({"chest_type": chest_type, "card_id": cid})
            if res.deleted_count:
                await msg.reply("🗑 Карта отвязана")
            else:
                await msg.reply("❌ Привязка не найдена")
        except Exception:
            await msg.reply("❌ Неверный card_id")
        await state.clear()
        return
    # привязка
    try:
        cid = ObjectId(txt)
    except Exception:
        await msg.reply("❌ Неверный card_id. Используйте /listcards"); return
    card = await cards_col.find_one({"_id": cid})
    if not card:
        await msg.reply("❌ Карта не найдена"); return
    # уникальность
    existing = await chest_cards_col.find_one({"chest_type": chest_type, "card_id": str(cid)})
    if existing:
        await msg.reply("⚠️ Уже привязана"); await state.clear(); return
    await chest_cards_col.insert_one({"chest_type": chest_type, "card_id": str(cid), "created_at": now_ts()})
    await log_action(msg.from_user.id, "chest_bind", f"{chest_type} <- {card['name']}")
    rd = RARITIES.get(card["rarity"], {"emoji": "❔"})
    await msg.reply(
        f"✅ Привязано к <b>{CHEST_LABELS[chest_type]}</b>:\n"
        f"{rd['emoji']} <b>{escape(card['name'])}</b>"
    )
    await state.clear()


# ============= АДМИН ОСТАЛЬНОЕ =============
@router.callback_query(F.data == "adm:users")
async def cb_adm_users(cq: CallbackQuery):
    if not is_admin(cq.from_user.id):
        await cq.answer("❌", show_alert=True); return
    users = await users_col.find({}).sort("created_at", -1).limit(50).to_list(length=50)
    lines = [f"👥 <b>Юзеры ({len(users)}):</b>\n"]
    for u in users:
        prem = " 💎" if is_premium(u) else ""
        lines.append(f"• <code>{u['user_id']}</code> · {user_mention(u)}{prem} · 💰{u.get('coins',0)} ✨{u.get('points',0):,} 🃏{u.get('cards_count',0)}")
    text = "\n".join(lines)
    for i in range(0, len(text), 3500):
        await cq.message.reply(text[i:i+3500])
    await cq.answer()


@router.callback_query(F.data == "adm:userinfo")
async def cb_adm_userinfo(cq: CallbackQuery):
    if not is_admin(cq.from_user.id):
        await cq.answer("❌", show_alert=True); return
    await cq.message.reply("Используйте <code>/userinfo &lt;user_id&gt;</code>"); await cq.answer()


@router.callback_query(F.data == "adm:addcard")
async def cb_adm_addcard(cq: CallbackQuery, state: FSMContext):
    if not is_admin(cq.from_user.id):
        await cq.answer("❌", show_alert=True); return
    await cmd_addcard(cq.message, state); await cq.answer()


@router.callback_query(F.data == "adm:listcards")
async def cb_adm_listcards(cq: CallbackQuery):
    if not is_admin(cq.from_user.id):
        await cq.answer("❌", show_alert=True); return
    await cmd_listcards(cq.message); await cq.answer()


@router.callback_query(F.data == "adm:loadmarket")
async def cb_adm_loadmarket(cq: CallbackQuery):
    if not is_admin(cq.from_user.id):
        await cq.answer("❌", show_alert=True); return
    await cq.message.reply("🏪 <code>/loadmarket &lt;card_id&gt; &lt;цена&gt;</code>\nID карт — /listcards"); await cq.answer()


@router.callback_query(F.data == "adm:logs")
async def cb_adm_logs(cq: CallbackQuery):
    if not is_admin(cq.from_user.id):
        await cq.answer("❌", show_alert=True); return
    logs = await logs_col.find({}).sort("ts", -1).limit(30).to_list(length=30)
    if not logs:
        await cq.message.reply("📋 Логов нет"); await cq.answer(); return
    lines = ["📋 <b>Последние 30:</b>\n"]
    for l in logs:
        t = time.strftime("%d.%m %H:%M", time.localtime(l["ts"]))
        lines.append(f"[{t}] <code>{l['user_id']}</code> · {l['action']} · {escape(str(l.get('details','')))}")
    await cq.message.reply("\n".join(lines)); await cq.answer()


@router.callback_query(F.data == "adm:stats")
async def cb_adm_stats(cq: CallbackQuery):
    if not is_admin(cq.from_user.id):
        await cq.answer("❌", show_alert=True); return
    u = await users_col.count_documents({})
    c = await cards_col.count_documents({})
    inv = await inventory_col.count_documents({})
    mk = await market_col.count_documents({})
    binds = await chest_cards_col.count_documents({})
    await cq.message.reply(
        f"📊 <b>Статистика</b>\n<blockquote>"
        f"👥 Юзеров: {u}\n🃏 Карт: {c}\n📦 Инв.: {inv}\n🏪 Маркет: {mk}\n🔗 Привязок: {binds}</blockquote>"
    ); await cq.answer()


@router.callback_query(F.data == "adm:broadcast")
async def cb_adm_broadcast(cq: CallbackQuery):
    if not is_admin(cq.from_user.id):
        await cq.answer("❌", show_alert=True); return
    await cq.message.reply("📢 <code>/broadcast &lt;текст&gt;</code>"); await cq.answer()


# Текстовые админ-команды
@router.message(Command("userinfo"))
async def cmd_userinfo(msg: Message):
    if not is_admin(msg.from_user.id): return
    parts = msg.text.split()
    if len(parts) != 2:
        await msg.reply("Формат: /userinfo &lt;user_id&gt;"); return
    try:
        uid = int(parts[1])
    except:
        await msg.reply("❌"); return
    u = await users_col.find_one({"user_id": uid})
    if not u:
        await msg.reply("❌ Не найден"); return
    inv = await inventory_col.find({"user_id": uid}).to_list(length=None)
    inv_lines = []
    for it in inv[:30]:
        try:
            c = await cards_col.find_one({"_id": ObjectId(it["card_id"])})
            if c:
                rd = RARITIES[c["rarity"]]
                inv_lines.append(f"  {rd['emoji']} {escape(c['name'])} ×{it['count']}")
        except Exception:
            pass
    inv_text = "\n".join(inv_lines) or "  (пусто)"
    await msg.reply(
        f"🔎 <b>{escape(u['nickname'])}</b> ({user_mention(u)})\n<blockquote>"
        f"🆔 <code>{u['user_id']}</code>\n"
        f"✨ {u.get('points',0):,}\n💰 {u.get('coins',0)}\n🃏 {u.get('cards_count',0)}\n"
        f"🎁 {u.get('bonus_chests',0)} 💜 {u.get('epic_chests',0)} 💛 {u.get('legend_chests',0)}\n"
        f"🎁 {u.get('common_coin_chests',0)} 💚 {u.get('rare_coin_chests',0)} ❤️ {u.get('mythic_coin_chests',0)}\n"
        f"🍀 {u.get('luck_charges',0)}\n"
        f"🚀 {'до ' + time.strftime('%d.%m.%Y', time.localtime(u['premium_until'])) if is_premium(u) else 'нет'}"
        f"</blockquote>\n<b>Карты:</b>\n{inv_text}"
    )


@router.message(Command("logs"))
async def cmd_logs(msg: Message):
    if not is_admin(msg.from_user.id): return
    parts = msg.text.split()
    q = {}
    if len(parts) == 2:
        try:
            q = {"user_id": int(parts[1])}
        except:
            await msg.reply("❌"); return
    logs = await logs_col.find(q).sort("ts", -1).limit(50).to_list(length=50)
    if not logs:
        await msg.reply("Нет логов"); return
    lines = []
    for l in logs:
        t = time.strftime("%d.%m %H:%M", time.localtime(l["ts"]))
        lines.append(f"[{t}] <code>{l['user_id']}</code> · {l['action']} · {escape(str(l.get('details','')))}")
    text = "\n".join(lines)
    for i in range(0, len(text), 3500):
        await msg.reply(text[i:i+3500])


@router.message(Command("broadcast"))
async def cmd_broadcast(msg: Message):
    if not is_admin(msg.from_user.id): return
    parts = msg.text.split(maxsplit=1)
    if len(parts) < 2:
        await msg.reply("Формат: /broadcast текст"); return
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


# ============= /addcard /delcard /listcards /loadmarket =============
@router.message(Command("addcard"))
async def cmd_addcard(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        await msg.reply("❌"); return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{d['emoji']} {d['name']}", callback_data=f"addrarity:{r}")]
        for r, d in RARITIES.items()
    ])
    await msg.reply("Выберите редкость новой карты:", reply_markup=kb)
    await state.set_state(AddCardFSM.rarity)


@router.callback_query(F.data.startswith("addrarity:"), AddCardFSM.rarity)
async def cb_add_rar(cq: CallbackQuery, state: FSMContext):
    rarity = cq.data.split(":", 1)[1]
    await state.update_data(rarity=rarity)
    await cq.message.reply(f"Редкость: <b>{RARITIES[rarity]['emoji']} {RARITIES[rarity]['name']}</b>\nНазвание карты:")
    await state.set_state(AddCardFSM.name); await cq.answer()


@router.message(AddCardFSM.name)
async def fsm_addname(msg: Message, state: FSMContext):
    if not msg.text:
        await msg.reply("Текстом"); return
    await state.update_data(name=msg.text.strip()[:64])
    await msg.reply("📸 Отправьте фото:")
    await state.set_state(AddCardFSM.photo)


@router.message(AddCardFSM.photo, F.photo)
async def fsm_addphoto(msg: Message, state: FSMContext):
    data = await state.get_data()
    res = await cards_col.insert_one({
        "name": data["name"], "rarity": data["rarity"],
        "photo_id": msg.photo[-1].file_id,
        "created_at": now_ts(), "created_by": msg.from_user.id,
    })
    rd = RARITIES[data["rarity"]]
    await log_action(msg.from_user.id, "addcard", data["name"])
    await msg.reply(f"✅ Добавлена!\n<blockquote>ID: <code>{res.inserted_id}</code>\n{rd['emoji']} {data['name']}</blockquote>")
    await state.clear()


@router.message(AddCardFSM.photo)
async def fsm_addphoto_wrong(msg: Message):
    await msg.reply("Нужно фото")


@router.message(Command("delcard"))
async def cmd_delcard(msg: Message):
    if not is_admin(msg.from_user.id): return
    parts = msg.text.split(maxsplit=1)
    if len(parts) < 2:
        await msg.reply("Формат: /delcard ID"); return
    try:
        cid = ObjectId(parts[1].strip())
    except:
        await msg.reply("❌"); return
    c = await cards_col.find_one({"_id": cid})
    if not c:
        await msg.reply("Не найдена"); return
    await cards_col.delete_one({"_id": cid})
    await inventory_col.delete_many({"card_id": str(cid)})
    await chest_cards_col.delete_many({"card_id": str(cid)})
    await msg.reply(f"🗑 «{escape(c['name'])}»")


@router.message(Command("listcards"))
async def cmd_listcards(msg: Message):
    if not is_admin(msg.from_user.id): return
    cards = await cards_col.find({}).sort("rarity", 1).to_list(length=500)
    if not cards:
        await msg.reply("Пусто. /addcard"); return
    lines = [f"📜 <b>Всего: {len(cards)}</b>\n"]
    for c in cards:
        rd = RARITIES.get(c["rarity"], {"emoji": "❔"})
        lines.append(f"{rd['emoji']} <b>{escape(c['name'])}</b> — <code>{c['_id']}</code>")
    text = "\n".join(lines)
    for i in range(0, len(text), 3500):
        await msg.reply(text[i:i+3500])


@router.message(Command("loadmarket"))
async def cmd_loadmarket(msg: Message):
    if not is_admin(msg.from_user.id): return
    parts = msg.text.split()
    if len(parts) != 3:
        await msg.reply("Формат: /loadmarket card_id цена"); return
    try:
        cid = ObjectId(parts[1]); price = int(parts[2])
    except:
        await msg.reply("❌"); return
    c = await cards_col.find_one({"_id": cid})
    if not c:
        await msg.reply("Не найдена"); return
    await market_col.insert_one({
        "card_id": str(cid), "name": c["name"], "rarity": c["rarity"],
        "photo_id": c.get("photo_id"), "price": price, "created_at": now_ts(),
    })
    await msg.reply(f"✅ <b>{escape(c['name'])}</b> @ {price}💰")


# ============= /andrusho и текст =============
@router.message(Command("andrusho"))
async def cmd_andrusho(msg: Message):
    await try_give_card(msg)


def normalize(s: str) -> str:
    return s.lower().strip()


@router.message(F.text)
async def text_router(msg: Message, state: FSMContext):
    if await state.get_state() is not None:
        return
    low = normalize(msg.text or "")
    if low in CARD_TRIGGERS:
        await try_give_card(msg); return
    for pref in COMMAND_PREFIXES:
        if low.startswith(pref):
            rest = low[len(pref):].strip(" ,.")
            if not rest:
                await try_give_card(msg); return
            if rest.startswith(("создать брак", "брак", "принять", "отклонить", "развод")):
                await handle_marriage(msg, rest); return
            if rest.startswith("цитата"):
                await handle_quote(msg, "цитата", rest[len("цитата"):]); return
            if rest.startswith("стикер"):
                await handle_quote(msg, "стикер", rest[len("стикер"):]); return
            await handle_rp(msg, rest); return


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
        BotCommand(command="admin", description="🔑 Взять администратора"),
        BotCommand(command="help", description="❔ Помощь"),
        BotCommand(command="myid", description="🆔 ID"),
    ]
    await bot.set_my_commands(public, scope=BotCommandScopeDefault())
    admin_cmds = public + [
        BotCommand(command="userinfo", description="🔎 Инфо о юзере"),
        BotCommand(command="logs", description="📋 Логи"),
        BotCommand(command="addcard", description="➕ Карта"),
        BotCommand(command="delcard", description="🗑 Удалить"),
        BotCommand(command="listcards", description="📜 Список"),
        BotCommand(command="loadmarket", description="🏪 На маркет"),
        BotCommand(command="broadcast", description="📢 Рассылка"),
        BotCommand(command="adminlogout", description="🚪 Выйти"),
    ]
    for aid in ADMINS:
        try:
            await bot.set_my_commands(admin_cmds, scope=BotCommandScopeChat(chat_id=aid))
        except Exception as e:
            log.warning("admin menu err %s: %s", aid, e)


async def main():
    log.info("Andrusho Bot стартует…")
    await setup_commands()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

async def handle(request):
    return web.Response(text="Бот на связи!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()

if __name__ == "__main__":
    asyncio.run(main())
