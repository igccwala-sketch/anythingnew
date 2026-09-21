import asyncio
import secrets
import string
import random
import uuid
from datetime import datetime
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramBadRequest

from config import config
from database import Database
from proxy_manager import ProxyManager
from gmail_engine import GmailEngine

# Initialize
bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

db = Database(config.DATABASE_PATH)
pm = ProxyManager(db)
engine = GmailEngine(pm)

# Global state for batch control
batch_state = {
    'running': False,
    'paused': False,
    'stopped': False,
    'current_account': 0,
    'total_accounts': 0,
    'success_count': 0,
    'fail_count': 0
}

class BotStates(StatesGroup):
    waiting_for_key = State()
    waiting_for_custom_fname = State()
    waiting_for_custom_lname = State()
    waiting_for_custom_pass = State()
    waiting_for_custom_email = State()
    waiting_for_proxy_input = State()
    owner_key_hours = State()
    owner_key_uses = State()

def main_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 Auto-Generate (1-10)", callback_data="mode_auto")],
        [InlineKeyboardButton(text="🎨 Custom Account", callback_data="mode_custom")],
        [InlineKeyboardButton(text="🌐 Proxy Manager", callback_data="mode_proxy")],
        [InlineKeyboardButton(text="📊 Stats", callback_data="stats")]
    ])

def owner_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 Auto-Generate", callback_data="mode_auto")],
        [InlineKeyboardButton(text="🎨 Custom Account", callback_data="mode_custom")],
        [InlineKeyboardButton(text="🌐 Proxy Manager", callback_data="mode_proxy")],
        [InlineKeyboardButton(text="🔑 Generate Key", callback_data="gen_key")],
        [InlineKeyboardButton(text="📊 Stats", callback_data="stats")]
    ])

def proxy_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Add Proxies", callback_data="proxy_text")],
        [InlineKeyboardButton(text="📁 Upload .txt", callback_data="proxy_file")],
        [InlineKeyboardButton(text="🔍 Validate All", callback_data="proxy_validate")],
        [InlineKeyboardButton(text="📊 Proxy Stats", callback_data="proxy_stats")],
        [InlineKeyboardButton(text="◀️ Back", callback_data="main_menu")]
    ])

def batch_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1", callback_data="batch_1"),
            InlineKeyboardButton(text="2", callback_data="batch_2"),
            InlineKeyboardButton(text="3", callback_data="batch_3")
        ],
        [
            InlineKeyboardButton(text="5", callback_data="batch_5"),
            InlineKeyboardButton(text="10", callback_data="batch_10"),
            InlineKeyboardButton(text="◀️ Back", callback_data="main_menu")
        ]
    ])

def control_keyboard():
    """Keyboard for batch control"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⏸️ Pause", callback_data="batch_pause"),
            InlineKeyboardButton(text="▶️ Resume", callback_data="batch_resume")
        ],
        [
            InlineKeyboardButton(text="⏹️ Stop", callback_data="batch_stop"),
            InlineKeyboardButton(text="📊 Status", callback_data="batch_status")
        ]
    ])

@router.error()
async def error_handler(event, exception):
    if isinstance(exception, TelegramBadRequest) and "message is not modified" in str(exception):
        return True
    print(f"Error: {exception}")
    return True

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()

    if message.from_user.id == config.OWNER_ID:
        await message.answer(
            "👑 Sheikh Gmail Maker\n\nChoose mode:",
            reply_markup=owner_keyboard()
        )
    else:
        user_data = await state.get_data()
        if user_data.get('access_key'):
            await message.answer("Choose mode:", reply_markup=main_menu_keyboard())
        else:
            await message.answer("🔐 Enter access key:")
            await state.set_state(BotStates.waiting_for_key)

@router.message(BotStates.waiting_for_key)
async def process_key(message: Message, state: FSMContext):
    key = message.text.strip()
    check = await db.validate_key(key)

    if check and check['valid']:
        await state.update_data(access_key=key)
        await db.increment_key_usage(key)
        await message.answer("✅ Access granted!", reply_markup=main_menu_keyboard())
    else:
        reason = check.get('reason', 'invalid') if check else 'not found'
        await message.answer(f"❌ Key rejected: {reason}")

@router.callback_query(F.data == "mode_auto")
async def mode_auto(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🤖 Auto-Generate Mode\n\nHow many accounts?",
        reply_markup=batch_keyboard()
    )

@router.callback_query(F.data.startswith("batch_"))
async def process_batch(callback: CallbackQuery, state: FSMContext):
    # Check if batch already running
    if batch_state['running']:
        # Check if it's actually running or just stuck state
        await callback.answer(
            "⚠️ Batch state shows running.\n\n"
            "If no batch is actually running, use /reset command or tap Reset button.",
            show_alert=True
        )
        return

    count = int(callback.data.split("_")[1])

    # Reset batch state
    batch_state.update({
        'running': True,
        'paused': False,
        'stopped': False,
        'current_account': 0,
        'total_accounts': count,
        'success_count': 0,
        'fail_count': 0
    })

    msg = await callback.message.edit_text(
        "🚀 Starting Batch\n\nAccounts: " + str(count) + "\nStatus: Initializing...\n\nUse controls below:",
        reply_markup=control_keyboard()
    )

    user_data = await state.get_data()
    access_key = user_data.get('access_key', 'owner')

    start_time = datetime.now()

    for i in range(count):
        # Check if stopped
        if batch_state['stopped']:
            await msg.edit_text(
                f"⏹️ Batch Stopped\n\n"
                f"Completed: {batch_state['current_account']}/{count}\n"
                f"✅ Success: {batch_state['success_count']}\n"
                f"❌ Failed: {batch_state['fail_count']}",
                reply_markup=owner_keyboard() if callback.from_user.id == config.OWNER_ID else main_menu_keyboard()
            )
            batch_state['running'] = False
            return

        # Check if paused
        while batch_state['paused']:
            await asyncio.sleep(1)
            # Update status while paused
            try:
                await msg.edit_text(
                    f"⏸️ Batch Paused\n\n"
                    f"Progress: {batch_state['current_account']}/{count}\n"
                    f"✅ Success: {batch_state['success_count']}\n"
                    f"❌ Failed: {batch_state['fail_count']}\n\n"
                    f"Use controls below:",
                    reply_markup=control_keyboard()
                )
            except:
                pass

        # Check again if stopped while paused
        if batch_state['stopped']:
            break

        batch_state['current_account'] = i + 1

        identity = engine.get_random_identity()
        fname, lname = identity['first'], identity['last']

        async def update_status(text):
            nonlocal msg, i, count
            elapsed = (datetime.now() - start_time).total_seconds()
            try:
                await msg.edit_text(
                    f"🚀 Creating Account {i+1}/{count}\n\n"
                    f"👤 Name: {fname} {lname}\n"
                    f"📊 Progress: ✅{batch_state['success_count']} ❌{batch_state['fail_count']}\n"
                    f"⏱️ Elapsed: {elapsed:.0f}s\n\n"
                    f"📝 Status: {text}\n\n"
                    f"Use controls below:",
                    reply_markup=control_keyboard()
                )
            except:
                pass

        await update_status("Starting browser...")

        result = await engine.create_account(
            fname, lname,
            password=None,
            custom_email=None,
            status_callback=update_status,
            account_num=i+1,
            total=count
        )

        if result['success']:
            batch_state['success_count'] += 1
            await db.log_account(
                result['email'], result['password'],
                fname, lname, access_key, result['proxy_used']
            )

            await callback.message.answer(
                f"✅ Account {i+1} Created\n\n"
                f"📧 Email: `{result['email']}`\n"
                f"🔑 Pass: `{result['password']}`\n"
                f"🌐 Proxy: {result['proxy_used'][:30]}",
                parse_mode="Markdown"
            )
        else:
            batch_state['fail_count'] += 1
            await callback.message.answer(
                f"❌ Account {i+1} Failed\n\n"
                f"Error: `{result.get('error', 'Unknown')[:200]}`\n"
                f"Attempted: `{result.get('email_attempted', 'N/A')}`",
                parse_mode="Markdown"
            )

        if i < count - 1 and not batch_state['stopped']:
            await asyncio.sleep(2)

    # Batch complete
    batch_state['running'] = False
    total_time = (datetime.now() - start_time).total_seconds()

    await msg.edit_text(
        f"🏁 Batch Complete\n\n"
        f"✅ Success: {batch_state['success_count']}\n"
        f"❌ Failed: {batch_state['fail_count']}\n"
        f"⏱️ Total time: {total_time:.0f}s",
        reply_markup=owner_keyboard() if callback.from_user.id == config.OWNER_ID else main_menu_keyboard()
    )

# Batch Control Handlers
@router.callback_query(F.data == "batch_pause")
async def batch_pause(callback: CallbackQuery):
    if not batch_state['running']:
        await callback.answer("⚠️ No batch running! Start a new batch.", show_alert=True)
        return

    batch_state['paused'] = True
    await callback.answer("⏸️ Batch paused")

    try:
        await callback.message.edit_text(
            f"⏸️ Batch Paused\n\n"
            f"Progress: {batch_state['current_account']}/{batch_state['total_accounts']}\n"
            f"✅ Success: {batch_state['success_count']}\n"
            f"❌ Failed: {batch_state['fail_count']}\n\n"
            f"Use controls below:",
            reply_markup=control_keyboard()
        )
    except:
        pass

@router.callback_query(F.data == "batch_resume")
async def batch_resume(callback: CallbackQuery):
    if not batch_state['running']:
        await callback.answer("⚠️ No batch running!", show_alert=True)
        return

    if not batch_state['paused']:
        await callback.answer("⚠️ Batch is not paused!", show_alert=True)
        return

    batch_state['paused'] = False
    await callback.answer("▶️ Batch resumed")

@router.callback_query(F.data == "batch_stop")
async def batch_stop(callback: CallbackQuery):
    if not batch_state['running']:
        await callback.answer("⚠️ No batch running!", show_alert=True)
        return

    batch_state['stopped'] = True
    batch_state['paused'] = False
    await callback.answer("⏹️ Batch stopping...")

    # Reset state after stopping
    import asyncio
    async def reset_after_stop():
        await asyncio.sleep(3)
        batch_state.update({
            'running': False,
            'paused': False,
            'stopped': False,
            'current_account': 0,
            'total_accounts': 0,
            'success_count': 0,
            'fail_count': 0
        })

    asyncio.create_task(reset_after_stop())

@router.callback_query(F.data == "batch_status")
async def batch_status(callback: CallbackQuery):
    if not batch_state['running']:
        await callback.answer(
            "📊 No batch running\n\n"
            "Start a new batch with Auto-Generate",
            show_alert=True
        )
        return

    status_text = "🟢 Running" if not batch_state['paused'] else "🟡 Paused"

    await callback.answer(
        f"📊 Batch Status\n\n"
        f"Status: {status_text}\n"
        f"Progress: {batch_state['current_account']}/{batch_state['total_accounts']}\n"
        f"✅ Success: {batch_state['success_count']}\n"
        f"❌ Failed: {batch_state['fail_count']}",
        show_alert=True
    )

@router.callback_query(F.data == "batch_reset")
async def batch_reset(callback: CallbackQuery):
    """Force reset batch state"""
    batch_state.update({
        'running': False,
        'paused': False,
        'stopped': False,
        'current_account': 0,
        'total_accounts': 0,
        'success_count': 0,
        'fail_count': 0
    })
    await callback.answer("🔄 Batch state reset! You can start new batch now.")

    try:
        await callback.message.edit_text(
            "🔄 Batch Reset\n\n"
            "State cleared. Start a new batch:",
            reply_markup=owner_keyboard() if callback.from_user.id == config.OWNER_ID else main_menu_keyboard()
        )
    except:
        pass

@router.callback_query(F.data == "mode_custom")
async def mode_custom(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🎨 Custom Account Creator\n\nEnter first name:")
    await state.set_state(BotStates.waiting_for_custom_fname)

@router.message(BotStates.waiting_for_custom_fname)
async def custom_fname(message: Message, state: FSMContext):
    await state.update_data(custom_fname=message.text)
    await message.answer("✅ First name saved\n\nEnter last name:")
    await state.set_state(BotStates.waiting_for_custom_lname)

@router.message(BotStates.waiting_for_custom_lname)
async def custom_lname(message: Message, state: FSMContext):
    await state.update_data(custom_lname=message.text)
    await message.answer("✅ Last name saved\n\n🔐 Enter custom password:\n(Min 8 chars, 1 uppercase, 1 number)")
    await state.set_state(BotStates.waiting_for_custom_pass)

@router.message(BotStates.waiting_for_custom_pass)
async def custom_pass(message: Message, state: FSMContext):
    pwd = message.text.strip()

    # Validate password strength
    if len(pwd) < 8:
        await message.answer("❌ Password too short! Need at least 8 characters.\n\nTry again:")
        return

    if not any(c.isupper() for c in pwd):
        await message.answer("❌ Password needs at least 1 uppercase letter!\n\nTry again:")
        return

    if not any(c.isdigit() for c in pwd):
        await message.answer("❌ Password needs at least 1 number!\n\nTry again:")
        return

    await state.update_data(custom_pass=pwd)
    await message.answer(f"✅ Password saved\n\n📧 Enter desired Gmail username:\n(Without @gmail.com, or type 'auto' for random)")
    await state.set_state(BotStates.waiting_for_custom_email)

@router.message(BotStates.waiting_for_custom_email)
async def custom_email(message: Message, state: FSMContext):
    email = message.text
    if email.lower() == 'auto':
        email = None

    data = await state.get_data()
    msg = await message.answer("🚀 Creating account...")

    async def update_status(text):
        try:
            await msg.edit_text(f"🚀 Creating...\n\n📝 {text}")
        except:
            pass

    result = await engine.create_account(
        data['custom_fname'],
        data['custom_lname'],
        data['custom_pass'],
        email,
        update_status
    )

    if result['success']:
        user_data = await state.get_data()
        await db.log_account(
            result['email'], result['password'],
            data['custom_fname'], data['custom_lname'],
            user_data.get('access_key', 'owner'),
            result['proxy_used']
        )
        await message.answer(
            f"✅ Account Created\n\n"
            f"📧 `{result['email']}`\n"
            f"🔑 `{result['password']}`",
            parse_mode="Markdown",
            reply_markup=owner_keyboard() if message.from_user.id == config.OWNER_ID else main_menu_keyboard()
        )
    else:
        await message.answer(
            f"❌ Failed\n\n"
            f"Error: `{result.get('error', 'Unknown')[:300]}`",
            parse_mode="Markdown",
            reply_markup=owner_keyboard() if message.from_user.id == config.OWNER_ID else main_menu_keyboard()
        )

    await state.clear()

@router.callback_query(F.data == "mode_proxy")
async def mode_proxy(callback: CallbackQuery, state: FSMContext):
    stats = await get_proxy_stats()
    await callback.message.edit_text(
        f"🌐 Proxy Manager\n\n"
        f"Total: {stats['total']}\n"
        f"✅ Live: {stats['live']}\n"
        f"❌ Dead: {stats['dead']}",
        reply_markup=proxy_keyboard()
    )

async def get_proxy_stats():
    import aiosqlite
    async with aiosqlite.connect(config.DATABASE_PATH) as db_conn:
        cursor = await db_conn.execute("SELECT COUNT(*) FROM proxies")
        total = (await cursor.fetchone())[0]
        cursor = await db_conn.execute("SELECT COUNT(*) FROM proxies WHERE status='live'")
        live = (await cursor.fetchone())[0]
        cursor = await db_conn.execute("SELECT COUNT(*) FROM proxies WHERE status='dead'")
        dead = (await cursor.fetchone())[0]
        return {"total": total, "live": live, "dead": dead}

@router.callback_query(F.data == "proxy_text")
async def proxy_text(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📥 Send proxies (any format):\n"
        "`ip:port` or `user:pass@ip:port`",
        parse_mode="Markdown"
    )
    await state.set_state(BotStates.waiting_for_proxy_input)

@router.message(BotStates.waiting_for_proxy_input)
async def process_proxy_text(message: Message, state: FSMContext):
    # Show validating message
    status_msg = await message.answer("🔍 Validating proxies... Please wait.")

    # Parse and validate each proxy
    lines = message.text.strip().split('\n')
    live_proxies = []
    dead_proxies = []

    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue

        # Validate this proxy
        is_live, latency, auth_type = await pm.check_proxy(line)

        if is_live:
            live_proxies.append((line, latency, auth_type))
            await pm.db.add_proxy(line, 'http')
            await pm.db.update_proxy_status(line, 'live', latency)
        else:
            dead_proxies.append(line)

    # Build result message
    result_text = f"📊 Validation Complete\n\n"
    result_text += f"✅ Live: {len(live_proxies)}\n"
    result_text += f"❌ Dead: {len(dead_proxies)}\n\n"

    if live_proxies:
        result_text += f"✅ Live Proxies Added:\n"
        for proxy, latency, auth in live_proxies[:5]:  # Show first 5
            result_text += f"  • {proxy[:40]}... ({latency:.2f}s)\n"
        if len(live_proxies) > 5:
            result_text += f"  ... and {len(live_proxies) - 5} more\n"
        result_text += "\n"

    if dead_proxies:
        result_text += f"❌ Dead Proxies (Not Added):\n"
        for proxy in dead_proxies[:3]:  # Show first 3
            result_text += f"  • {proxy[:40]}...\n"
        if len(dead_proxies) > 3:
            result_text += f"  ... and {len(dead_proxies) - 3} more\n"

    if not live_proxies:
        result_text += "\n⚠️ No live proxies found!\n"
        result_text += "Check your proxy format or contact provider."

    await status_msg.edit_text(
        result_text,
        reply_markup=proxy_keyboard()
    )
    await state.clear()

@router.message(F.document)
async def handle_file(message: Message, state: FSMContext):
    if not message.document.file_name.endswith('.txt'):
        return

    status_msg = await message.answer("🔍 Validating proxies from file... Please wait.")

    file = await bot.get_file(message.document.file_id)
    downloaded = await bot.download_file(file.file_path)
    content = downloaded.read().decode('utf-8')

    # Parse and validate each proxy
    lines = content.strip().split('\n')
    live_proxies = []
    dead_proxies = []

    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue

        is_live, latency, auth_type = await pm.check_proxy(line)

        if is_live:
            live_proxies.append((line, latency, auth_type))
            await pm.db.add_proxy(line, 'http')
            await pm.db.update_proxy_status(line, 'live', latency)
        else:
            dead_proxies.append(line)

    # Build result
    result_text = f"📊 File Validation Complete\n\n"
    result_text += f"✅ Live: {len(live_proxies)}\n"
    result_text += f"❌ Dead: {len(dead_proxies)}\n\n"

    if live_proxies:
        result_text += f"✅ {len(live_proxies)} live proxies added!\n"
    else:
        result_text += f"⚠️ No live proxies found in file!"

    await status_msg.edit_text(
        result_text,
        reply_markup=proxy_keyboard()
    )

@router.callback_query(F.data == "proxy_validate")
async def proxy_validate(callback: CallbackQuery):
    msg = await callback.message.edit_text("🔍 Validating...")

    async def update(text):
        try:
            await msg.edit_text(f"🔍 Validating...\n\n{text[:200]}")
        except:
            pass

    live = await pm.validate_all_proxies(update)
    await msg.edit_text(
        f"✅ Validation complete\n\nLive: {live}",
        reply_markup=proxy_keyboard()
    )

@router.callback_query(F.data == "stats")
async def show_stats(callback: CallbackQuery, state: FSMContext):
    import aiosqlite
    user_data = await state.get_data()
    key = user_data.get('access_key', 'owner')

    async with aiosqlite.connect(config.DATABASE_PATH) as db_conn:
        cursor = await db_conn.execute(
            "SELECT COUNT(*) FROM created_accounts WHERE created_by_key = ?", (key,)
        )
        count = (await cursor.fetchone())[0]

    await callback.message.edit_text(
        f"📊 Stats\n\nAccounts created: {count}",
        reply_markup=owner_keyboard() if callback.from_user.id == config.OWNER_ID else main_menu_keyboard()
    )

@router.callback_query(F.data == "gen_key")
async def gen_key(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != config.OWNER_ID:
        return
    await callback.message.edit_text("Key duration (hours):")
    await state.set_state(BotStates.owner_key_hours)

@router.message(BotStates.owner_key_hours)
async def key_hours(message: Message, state: FSMContext):
    try:
        hours = int(message.text)
        await state.update_data(key_hours=hours)
        await message.answer("Max uses:")
        await state.set_state(BotStates.owner_key_uses)
    except:
        await message.answer("Enter number.")

@router.message(BotStates.owner_key_uses)
async def key_uses(message: Message, state: FSMContext):
    try:
        uses = int(message.text)
        data = await state.get_data()
        key = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(16))
        await db.create_key(key, message.from_user.id, data['key_hours'], uses)
        await message.answer(
            f"🔑 Key: `{key}`\nHours: {data['key_hours']}\nUses: {uses}",
            parse_mode="Markdown",
            reply_markup=owner_keyboard()
        )
        await state.clear()
    except:
        await message.answer("Enter number.")

@router.callback_query(F.data == "main_menu")
async def back(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id == config.OWNER_ID:
        await callback.message.edit_text("👑 Owner Menu:", reply_markup=owner_keyboard())
    else:
        await callback.message.edit_text("Main Menu:", reply_markup=main_menu_keyboard())

async def main():
    await db.init()
    print("✅ Sheikh Gmail Maker Started with Batch Controls")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
