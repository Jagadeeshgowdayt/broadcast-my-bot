import logging
import json
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
    """Sends a welcome message explaining the new features."""
    await update.message.reply_html(
        "👋 <b>Welcome to the Advanced Broadcast Bot!</b>\n\n"
        "I can now send complex posts to all your channels.\n\n"
        "<b>Two Ways to Broadcast:</b>\n\n"
        "1️⃣ <b>Copy Existing Message:</b>\n"
        "Simply reply to <i>any</i> message (text, photo, poll, etc.) with the command <code>/broadcast</code>. I will send an exact copy of that message to all channels.\n\n"
        "2️⃣ <b>Create a New Post with Buttons:</b>\n"
        "Use this format to create a message with inline URL buttons:\n"
        "<code>/broadcast Your message text here. || Button 1 Text | https://link1.com || Button 2 Text | https://link2.com</code>\n\n"
        "Use <code>||</code> to separate the message from the buttons, and to separate each button. Use <code>|</code> to separate a button's text from its URL."
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
    """Broadcasts a message by copying or creating a new one with buttons."""
    user_id = update.message.from_user.id
    if user_id not in AUTHORIZED_USERS:
        await update.message.reply_text("Sorry, you are not authorized to use this command.")
        return

    channels_to_broadcast = load_channels()
    if not channels_to_broadcast:
        await update.message.reply_text("I don't know about any channels yet. Add me to a channel as an admin first.")
        return

    successful_sends = 0
    failed_sends = 0
    
    # --- METHOD 1: Reply to a message to copy it ---
    if update.message.reply_to_message:
        logger.info(f"Broadcast initiated by {user_id} by replying to a message.")
        message_to_copy = update.message.reply_to_message
        for channel_id in channels_to_broadcast:
            try:
                await context.bot.copy_message(
                    chat_id=channel_id,
                    from_chat_id=message_to_copy.chat_id,
                    message_id=message_to_copy.message_id
                )
                successful_sends += 1
            except TelegramError as e:
                logger.error(f"Failed to copy message to channel {channel_id}: {e}")
                failed_sends += 1
    
    # --- METHOD 2: Create a new message from command arguments ---
    else:
        full_command_text = " ".join(context.args)
        if not full_command_text:
            await update.message.reply_text("Please provide a message or reply to one.\nSee /start for instructions.")
            return

        logger.info(f"Broadcast initiated by {user_id} with new message.")
        
        parts = full_command_text.split('||')
        message_text = parts[0].strip()
        button_definitions = parts[1:]
        
        keyboard = []
        for definition in button_definitions:
            try:
                btn_text, btn_url = [item.strip() for item in definition.split('|', 1)]
                if btn_text and btn_url:
                    keyboard.append([InlineKeyboardButton(text=btn_text, url=btn_url)])
            except ValueError:
                logger.warning(f"Could not parse button definition: '{definition}'")
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

        for channel_id in channels_to_broadcast:
            try:
                await context.bot.send_message(
                    chat_id=channel_id,
                    text=message_text,
                    parse_mode='HTML',
                    reply_markup=reply_markup,
                    disable_web_page_preview=True
                )
                successful_sends += 1
            except TelegramError as e:
                logger.error(f"Failed to send message to channel {channel_id}: {e}")
                failed_sends += 1

    # --- Send final report ---
    await update.message.reply_html(
        f"📢 <b>Broadcast Complete!</b>\n\n"
        f"✅ Sent to <b>{successful_sends}</b> channel(s).\n"
        f"❌ Failed for <b>{failed_sends}</b> channel(s)."
    )

def main() -> None:
    """Start the bot."""
    if not AUTHORIZED_USERS or 0 in AUTHORIZED_USERS:
        logger.error("FATAL: AUTHORIZED_USERS list is not set up correctly. Please edit it.")
        return
        
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(ChatMemberHandler(update_channel_list, ChatMemberHandler.MY_CHAT_MEMBER))

    logger.info("Advanced Bot is starting...")
    application.run_polling()

if __name__ == "__main__":
    main()
