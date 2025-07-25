import logging
import json
from pathlib import Path
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, ChatMemberHandler
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
            # Load the list and convert it to a set for efficient adds/removes
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        # If the file doesn't exist or is empty/corrupt, start with an empty set
        return set()

def save_channels(channel_ids: set) -> None:
    """Saves the set of channel IDs to the JSON file."""
    with open(CHANNELS_FILE, "w") as f:
        # Convert the set to a list to make it JSON serializable
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
        "I automatically learn which channels to broadcast to when you add me as an admin.\n\n"
        "<b>Authorized Command:</b> /broadcast <i>your message</i>"
    )

async def update_channel_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles the bot being added to or removed from a channel.
    This is how the bot "learns" where it can post.
    """
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
    """Broadcasts a message to all learned channels."""
    user_id = update.message.from_user.id

    # --- NEW: Check if the user is in the authorized list ---
    if user_id not in AUTHORIZED_USERS:
        await update.message.reply_text("Sorry, you are not authorized to use this command.")
        logger.warning(f"Unauthorized broadcast attempt by user ID: {user_id}")
        return

    message_to_broadcast = " ".join(context.args)
    if not message_to_broadcast:
        await update.message.reply_text("Please provide a message. Ex: /broadcast Hello channels!")
        return

    logger.info(f"Broadcast initiated by authorized user {user_id}. Message: '{message_to_broadcast}'")
    
    channels_to_broadcast = load_channels()

    if not channels_to_broadcast:
        await update.message.reply_text("I don't know about any channels yet. Add me to a channel as an admin first.")
        return

    successful_sends = 0
    failed_sends = 0

    for channel_id in channels_to_broadcast:
        try:
            await context.bot.send_message(
                chat_id=channel_id, text=message_to_broadcast, parse_mode='HTML'
            )
            logger.info(f"Successfully sent message to channel {channel_id}")
            successful_sends += 1
        except TelegramError as e:
            logger.error(f"Failed to send to channel {channel_id}: {e}. It might be removed.")
            failed_sends += 1
            
    await update.message.reply_text(
        f"📢 <b>Broadcast Complete!</b>\n\n"
        f"✅ Sent to <b>{successful_sends}</b> channel(s).\n"
        f"❌ Failed for <b>{failed_sends}</b> channel(s).",
        parse_mode='HTML'
    )

def main() -> None:
    """Start the bot."""
    if not AUTHORIZED_USERS or 0 in AUTHORIZED_USERS:
        logger.error("FATAL: AUTHORIZED_USERS list is not set up correctly. Please edit the script and add at least one real Telegram User ID.")
        return
        
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(ChatMemberHandler(update_channel_list, ChatMemberHandler.MY_CHAT_MEMBER))

    logger.info("Smart Bot is starting...")
    application.run_polling()

if __name__ == "__main__":
    main()
