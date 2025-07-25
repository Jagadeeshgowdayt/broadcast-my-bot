import logging
import json
import asyncio
from pathlib import Path
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, ChatMemberHandler, AIORateLimiter
from telegram.error import TelegramError

# --- CONFIGURATION ---
# Your bot's token.
BOT_TOKEN = "7707396854:AAHYPvTe_rv7pxmkzQ04w1QN0_FEeEGYRiY"

# A list of personal Telegram User IDs of everyone who can use the broadcast command.
# Get user IDs by messaging @userinfobot
AUTHORIZED_USERS = [
    1946827941,  # This is the authorized user ID you provided.
    # 12345678, # You can add your friend's user ID here
    # 87654321, # And another friend's user ID here
]

# The file where the bot will store the channel IDs it learns.
CHANNELS_FILE = "broadcast_channels.json"
# --- END CONFIGURATION ---

# --- DATA PERSISTENCE ---
def load_channels() -> set:
    """Loads the set of channel IDs from the JSON file."""
    try:
        with open(CHANNELS_FILE, "r") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def save_channels(channel_ids: set) -> None:
    """Saves the set of channel IDs to the JSON file."""
    with open(CHANNELS_FILE, "w") as f:
        json.dump(list(channel_ids), f, indent=4)

# --- BOT LOGIC ---
# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message."""
    await update.message.reply_html(
        "👋 <b>Welcome to the Smart Broadcast Bot!</b>\n\n"
        "<b>--- Single Message ---</b>\n"
        "Use <code>/broadcast &lt;your message&gt;</code> to send a one-time message.\n\n"
        "<b>--- Continuous Broadcast (Spam) ---</b>\n"
        "Use <code>/start_spam &lt;your message&gt;</code> to send a message continuously at high speed.\n\n"
        "Use <code>/stop_spam</code> to halt the continuous broadcast."
    )

async def update_channel_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the bot being added to or removed from a channel."""
    chat_member_update = update.my_chat_member
    if chat_member_update.chat.type != 'channel':
        return
    chat_id = chat_member_update.chat.id
    new_status = chat_member_update.new_chat_member.status
    current_channels = load_channels()
    if new_status in ['administrator', 'member']:
        if chat_id not in current_channels:
            logger.info(f"Bot was added to new channel: {chat_id}. Adding to list.")
            current_channels.add(chat_id)
            save_channels(current_channels)
    elif new_status in ['left', 'kicked']:
        if chat_id in current_channels:
            logger.info(f"Bot was removed from channel: {chat_id}. Removing from list.")
            current_channels.remove(chat_id)
            save_channels(current_channels)

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Broadcasts a single message to all learned channels."""
    user_id = update.message.from_user.id
    if user_id not in AUTHORIZED_USERS:
        await update.message.reply_text("Sorry, you are not authorized to use this command.")
        return
    message_to_broadcast = " ".join(context.args)
    if not message_to_broadcast:
        await update.message.reply_text("Please provide a message. Ex: /broadcast Hello channels!")
        return
    logger.info(f"Broadcast initiated by {user_id}. Message: '{message_to_broadcast}'")
    channels_to_broadcast = load_channels()
    if not channels_to_broadcast:
        await update.message.reply_text("I don't know any channels yet. Add me to a channel as an admin first.")
        return
    successful_sends, failed_sends = 0, 0
    for channel_id in channels_to_broadcast:
        try:
            await context.bot.send_message(chat_id=channel_id, text=message_to_broadcast, parse_mode='HTML')
            successful_sends += 1
        except TelegramError as e:
            logger.error(f"Failed to send to channel {channel_id}: {e}")
            failed_sends += 1
    await update.message.reply_text(
        f"📢 <b>Broadcast Complete!</b>\n\n"
        f"✅ Sent to <b>{successful_sends}</b> channel(s).\n"
        f"❌ Failed for <b>{failed_sends}</b> channel(s).",
        parse_mode='HTML'
    )

# --- Spam Feature Functions ---

async def spam_task(context: ContextTypes.DEFAULT_TYPE):
    """The background task that sends messages continuously."""
    task_id = context.job.data['task_id']
    message = context.job.data['message']
    
    while context.bot_data.get(task_id, False):
        channels = load_channels()
        if not channels:
            logger.warning("Spam task running but no channels found. Sleeping for 60s.")
            await asyncio.sleep(60)
            continue
        
        for channel_id in channels:
            # Check if the loop should stop before sending each message
            if not context.bot_data.get(task_id, False):
                logger.info(f"Spam task {task_id} stopped during channel loop.")
                return
            try:
                await context.bot.send_message(chat_id=channel_id, text=message, parse_mode='HTML')
            except TelegramError as e:
                # The rate limiter handles FloodWait, this catches other errors.
                logger.error(f"Error sending spam message to {channel_id}: {e}")
                await asyncio.sleep(1) # Wait a bit after other errors
        await asyncio.sleep(1) # Wait 1 second after completing a full loop

async def start_spam(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Starts the continuous broadcast loop."""
    user_id = update.message.from_user.id
    if user_id not in AUTHORIZED_USERS:
        await update.message.reply_text("Sorry, you are not authorized to use this command.")
        return

    if context.bot_data.get('spam_active', False):
        await update.message.reply_text("A spam broadcast is already active. Use /stop_spam first.")
        return

    message_to_spam = " ".join(context.args)
    if not message_to_spam:
        await update.message.reply_text("Please provide a message to spam. Ex: /start_spam Hello")
        return

    task_id = f"spam_task_{user_id}"
    context.bot_data[task_id] = True
    context.bot_data['spam_active'] = task_id

    # Using job_queue to run an async task. This is a common pattern.
    context.job_queue.run_once(
        spam_task, 
        when=0, 
        data={'task_id': task_id, 'message': message_to_spam}, 
        name=task_id
    )
    
    await update.message.reply_html(f"✅ <b>Continuous broadcast started!</b>\nSending message: '<i>{message_to_spam}</i>'")
    logger.info(f"Spam started by {user_id} with task ID {task_id}")

async def stop_spam(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Stops the continuous broadcast loop."""
    user_id = update.message.from_user.id
    if user_id not in AUTHORIZED_USERS:
        await update.message.reply_text("Sorry, you are not authorized to use this command.")
        return

    task_id = context.bot_data.pop('spam_active', None)
    if task_id:
        context.bot_data[task_id] = False  # Set the flag to false to stop the while loop
        current_jobs = context.job_queue.get_jobs_by_name(task_id)
        for job in current_jobs:
            job.schedule_removal()
        await update.message.reply_text("✅ Continuous broadcast has been stopped.")
        logger.info(f"Spam task {task_id} stopped by {user_id}.")
    else:
        await update.message.reply_text("There is no active spam broadcast to stop.")

def main() -> None:
    """Start the bot."""
    if not AUTHORIZED_USERS or 0 in AUTHORIZED_USERS:
        logger.error("FATAL: AUTHORIZED_USERS list is not set up correctly. Please edit it.")
        return
        
    # Build the application with the automatic rate limiter
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .rate_limiter(AIORateLimiter())
        .build()
    )

    # Add all command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(CommandHandler("start_spam", start_spam))
    application.add_handler(CommandHandler("stop_spam", stop_spam))
    application.add_handler(ChatMemberHandler(update_channel_list, ChatMemberHandler.MY_CHAT_MEMBER))

    logger.info("Smart Bot is starting...")
    application.run_polling()

if __name__ == "__main__":
    main()
