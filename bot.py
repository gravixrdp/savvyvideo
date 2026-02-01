import os
import logging
import glob
from uuid import uuid4
from telegram import (
    Update, KeyboardButton, ReplyKeyboardMarkup,
    InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ConversationHandler, filters, ContextTypes
)
from telegram.constants import ParseMode
from yt_dlp import YoutubeDL

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Configuration ---
BOT_TOKEN = os.getenv('BOT_TOKEN', '8413258612:AAHmrd9F_9YT6xBIaqlrn4ZN3-R5HhtcKtk')
ADMIN_ID = 5610858626
MAX_FILESIZE = 1950 * 1024 * 1024  # 1.95GB safety limit

# --- Storage ---
initial_welcome_text = "👋 Welcome! Please join our channels to continue."
welcome_text = """🎬 **Welcome to VideoSavvy Bot!**

✨ *Your all-in-one video downloader*  
✨ Supports 1500+ platforms: YouTube, Instagram, TikTok & more  
✨ Choose your preferred quality — 360p to 1080p+  
✨ Instant download with no ads & no signup required

➡️ **How to use:**  
1️⃣ Send any video link  
2️⃣ Select quality  
3️⃣ Receive your video seamlessly!

*Enjoy effortless, premium video downloads!* 🎥🚀"""

welcome_media = None  # (type, file_id)
required_channels = []
user_ids = set()

# Conversation states
(ADMIN_PANEL, EDIT_WELCOME, EDIT_INITIAL_WELCOME, ADD_CHANNEL, REMOVE_CHANNEL, BROADCAST, WELCOME_MEDIA) = range(7)

# --- Keyboards ---
def main_keyboard(user_id):
    keys = [[KeyboardButton("🚀 Start")]]
    if user_id == ADMIN_ID:
        keys[0].append(KeyboardButton("🛠️ Admin Panel"))
    return ReplyKeyboardMarkup(keys, resize_keyboard=True)

def admin_keyboard():
    return ReplyKeyboardMarkup([
        ["✏️ Edit Initial Welcome", "📝 Edit Main Welcome"],
        ["🎨 Edit Welcome Media"],
        ["➕ Add Channel", "➖ Remove Channel"],
        ["📢 Broadcast", "👥 User Count"],
        ["⬅️ Back"]
    ], resize_keyboard=True)

def channel_join_keyboard():
    btns = []
    for chan in required_channels:
        if chan.startswith("http"):
            url = chan
        else:
            clean_chan = chan.lstrip('@')
            url = f"https://t.me/{clean_chan}"
        btns.append([InlineKeyboardButton("✅ Join Channel", url=url)])
    btns.append([InlineKeyboardButton("✔️ I Joined", callback_data="check_joined")])
    return InlineKeyboardMarkup(btns)

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_ids.add(user_id)
    
    # Send short initial welcome message
    await update.message.reply_text(
        initial_welcome_text, 
        reply_markup=main_keyboard(user_id), 
        parse_mode=ParseMode.MARKDOWN
    )

async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not update.message.text:
        return ConversationHandler.END
    text = update.message.text.strip()

    # Admin Panel Access
    if text == "🛠️ Admin Panel" and user_id == ADMIN_ID:
        await update.message.reply_text(
            "🛠️ *Admin Panel*\nSelect an option:", 
            reply_markup=admin_keyboard(), 
            parse_mode=ParseMode.MARKDOWN
        )
        return ADMIN_PANEL

    # Start Bot
    if text == "🚀 Start":
        if required_channels:
            await update.message.reply_text(
                "To use this bot, please join all required channels and click 'I Joined'.",
                reply_markup=channel_join_keyboard()
            )
            return
        await send_welcome(update, user_id)
        return

    # Non-admin users: process video links
    if user_id != ADMIN_ID:
        await process_video_link(update, context)
        return

    # --- Admin Functions ---
    if text == "✏️ Edit Initial Welcome":
        await update.message.reply_text(
            "Send the *new initial welcome message* (short message shown when user first starts):",
            reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True),
            parse_mode=ParseMode.MARKDOWN
        )
        return EDIT_INITIAL_WELCOME

    if text == "📝 Edit Main Welcome":
        await update.message.reply_text(
            "Send the *new main welcome message* (shown after user joins channels, Markdown supported):",
            reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True),
            parse_mode=ParseMode.MARKDOWN
        )
        return EDIT_WELCOME

    if text == "🎨 Edit Welcome Media":
        await update.message.reply_text(
            "Send a photo, GIF, or document to set as welcome media.\nType ❌ Cancel to abort.",
            reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True)
        )
        return WELCOME_MEDIA

    if text == "➕ Add Channel":
        await update.message.reply_text(
            "Send the channel username, link, or ID to add.\n\nExamples:\n• @yourchannel\n• https://t.me/yourchannel\n• -100xxxxxxxxxx",
            reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True),
            parse_mode=ParseMode.MARKDOWN
        )
        return ADD_CHANNEL

    if text == "➖ Remove Channel":
        formatted = "\n".join([f"{i+1}. {c}" for i, c in enumerate(required_channels)]) or "No channels set."
        await update.message.reply_text(
            f"Send the exact username/link/ID to *remove*.\n\nCurrent channels:\n{formatted}",
            reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True),
            parse_mode=ParseMode.MARKDOWN
        )
        return REMOVE_CHANNEL

    if text == "📢 Broadcast":
        await update.message.reply_text(
            "Send the text (or media with caption) to broadcast to all users.\nType ❌ Cancel to abort.",
            reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True)
        )
        return BROADCAST

    if text == "👥 User Count":
        await update.message.reply_text(
            f"👥 Total unique users: *{len(user_ids)}*",
            reply_markup=admin_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )
        return ADMIN_PANEL

    if text == "⬅️ Back" or text == "❌ Cancel":
        await update.message.reply_text("Returning to main menu.", reply_markup=main_keyboard(user_id))
        return ConversationHandler.END

# --- Admin: Save Initial Welcome Text ---
async def save_initial_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global initial_welcome_text
    new_msg = update.message.text
    if not new_msg or new_msg.strip() == "❌ Cancel":
        await update.message.reply_text("Cancelled.", reply_markup=admin_keyboard())
        return ADMIN_PANEL
    initial_welcome_text = new_msg
    await update.message.reply_text("✅ Initial welcome message updated!", reply_markup=admin_keyboard())
    return ADMIN_PANEL

# --- Admin: Save Welcome Text ---
async def save_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global welcome_text
    new_msg = update.message.text
    if not new_msg or new_msg.strip() == "❌ Cancel":
        await update.message.reply_text("Cancelled.", reply_markup=admin_keyboard())
        return ADMIN_PANEL
    welcome_text = new_msg
    await update.message.reply_text("✅ Main welcome message updated!", reply_markup=admin_keyboard())
    return ADMIN_PANEL

# --- Admin: Save Welcome Media ---
async def save_welcome_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global welcome_media
    msg = update.message
    if msg.text and msg.text.strip() == "❌ Cancel":
        await msg.reply_text("Cancelled.", reply_markup=admin_keyboard())
        return ADMIN_PANEL
    
    if msg.photo:
        welcome_media = ("photo", msg.photo[-1].file_id)
        await msg.reply_text("✅ Welcome photo updated!", reply_markup=admin_keyboard())
    elif msg.document:
        welcome_media = ("document", msg.document.file_id)
        await msg.reply_text("✅ Welcome document updated!", reply_markup=admin_keyboard())
    elif msg.animation:
        welcome_media = ("animation", msg.animation.file_id)
        await msg.reply_text("✅ Welcome animation/GIF updated!", reply_markup=admin_keyboard())
    else:
        await msg.reply_text("❌ Please send a photo, document, or GIF.", reply_markup=admin_keyboard())
    return ADMIN_PANEL

# --- Admin: Add Channel ---
async def add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.text:
        await update.message.reply_text("Please send a channel username, link, or ID.", reply_markup=admin_keyboard())
        return ADMIN_PANEL
    entry = update.message.text.strip()
    if entry == "❌ Cancel":
        await update.message.reply_text("Cancelled.", reply_markup=admin_keyboard())
        return ADMIN_PANEL
    if entry not in required_channels:
        required_channels.append(entry)
        await update.message.reply_text(
            f"✅ Channel added!\n\nCurrent channels:\n" + "\n".join(required_channels),
            reply_markup=admin_keyboard()
        )
    else:
        await update.message.reply_text("Channel already exists in the list.", reply_markup=admin_keyboard())
    return ADMIN_PANEL

# --- Admin: Remove Channel ---
async def remove_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.text:
        await update.message.reply_text("Please send a channel username, link, or ID to remove.", reply_markup=admin_keyboard())
        return ADMIN_PANEL
    entry = update.message.text.strip()
    if entry == "❌ Cancel":
        await update.message.reply_text("Cancelled.", reply_markup=admin_keyboard())
        return ADMIN_PANEL
    if entry in required_channels:
        required_channels.remove(entry)
        remaining = "\n".join(required_channels) if required_channels else "No channels remaining."
        await update.message.reply_text(
            f"❌ Channel removed!\n\nCurrent channels:\n{remaining}",
            reply_markup=admin_keyboard()
        )
    else:
        await update.message.reply_text("Channel not found in the list.", reply_markup=admin_keyboard())
    return ADMIN_PANEL

# --- Admin: Broadcast ---
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.text and msg.text.strip() == "❌ Cancel":
        await msg.reply_text("Cancelled.", reply_markup=admin_keyboard())
        return ADMIN_PANEL
    
    delivered = failed = 0
    for uid in list(user_ids):
        try:
            if msg.photo:
                await context.bot.send_photo(uid, msg.photo[-1].file_id, caption=msg.caption)
            elif msg.animation:
                await context.bot.send_animation(uid, msg.animation.file_id, caption=msg.caption)
            elif msg.document:
                await context.bot.send_document(uid, msg.document.file_id, caption=msg.caption)
            else:
                await context.bot.send_message(uid, msg.text or "")
            delivered += 1
        except Exception as e:
            logger.error(f"Broadcast failed for user {uid}: {e}")
            failed += 1
    
    await msg.reply_text(
        f"✅ Broadcast complete!\n\n📤 Delivered: {delivered}\n❌ Failed: {failed}",
        reply_markup=admin_keyboard()
    )
    return ADMIN_PANEL

# --- Send Welcome ---
async def send_welcome(update, user_id):
    if welcome_media:
        mtype, fileid = welcome_media
        try:
            if mtype == "photo":
                await update.message.reply_photo(
                    fileid, 
                    caption=welcome_text, 
                    reply_markup=main_keyboard(user_id), 
                    parse_mode=ParseMode.MARKDOWN
                )
            elif mtype == "animation":
                await update.message.reply_animation(
                    fileid, 
                    caption=welcome_text, 
                    reply_markup=main_keyboard(user_id), 
                    parse_mode=ParseMode.MARKDOWN
                )
            elif mtype == "document":
                await update.message.reply_document(
                    fileid, 
                    caption=welcome_text, 
                    reply_markup=main_keyboard(user_id), 
                    parse_mode=ParseMode.MARKDOWN
                )
        except Exception as e:
            logger.error(f"Error sending welcome: {e}")
            await update.message.reply_text(
                welcome_text, 
                reply_markup=main_keyboard(user_id), 
                parse_mode=ParseMode.MARKDOWN
            )
    else:
        await update.message.reply_text(
            welcome_text, 
            reply_markup=main_keyboard(user_id), 
            parse_mode=ParseMode.MARKDOWN
        )

# --- Check Channel Membership ---
async def join_channels_checker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    not_joined = []
    
    for chan in required_channels:
        try:
            cid = chan
            if cid.startswith("http"):
                cid = "@" + cid.split("/")[-1]
            elif not cid.startswith("@"):
                if not cid.startswith("-"):
                    cid = "@" + cid.lstrip("@")
            member = await context.bot.get_chat_member(cid, user_id)
            if member.status not in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER]:
                not_joined.append(chan)
        except Exception as e:
            logger.error(f"Error checking membership for {chan}: {e}")
            not_joined.append(chan)
    
    if not_joined:
        await query.answer("Please join all required channels first!", show_alert=True)
        await query.edit_message_text(
            "You have not joined all required channels.\nPlease join and then click 'I Joined'.",
            reply_markup=channel_join_keyboard()
        )
    else:
        await query.answer("✅ Verified! Welcome!")
        class DummyUpdate:
            def __init__(self, msg):
                self.message = msg
        await send_welcome(DummyUpdate(query.message), user_id)

# --- Video Link Processing ---
async def process_video_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    user_id = update.effective_user.id
    
    # Quick validation
    if not ("http" in url.lower() and any(platform in url.lower() for platform in [
        'youtu', 'instagram', 'tiktok', 'twitter', 'facebook', 'vimeo', 'reddit', 'dailymotion'
    ])):
        await update.message.reply_text(
            "❌ This doesn't look like a supported video link.\n\nPlease send a valid link from YouTube, Instagram, TikTok, Facebook, Twitter, or other supported platforms.",
            reply_markup=main_keyboard(user_id)
        )
        return
    
    processing_msg = await update.message.reply_text("🔍 Analyzing your link, please wait...")
    
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Filter valid formats - video formats with height
            formats = [
                f for f in info.get('formats', [])
                if f.get('vcodec') != 'none' 
                and f.get('vcodec') is not None
                and f.get('height')
            ]
            
            if not formats:
                await processing_msg.edit_text(
                    "❌ No downloadable video formats found.\n\nThe video may be:\n• Private or restricted\n• Audio-only\n• Not supported",
                    reply_markup=main_keyboard(user_id)
                )
                return
            
            # Extract unique resolutions
            resolutions = sorted(set(f['height'] for f in formats if f.get('height')), reverse=True)
            
            if not resolutions:
                await processing_msg.edit_text(
                    "❌ No video resolutions available for this link.",
                    reply_markup=main_keyboard(user_id)
                )
                return
            
            # Store data in user context - fix: store format_id mapping properly
            context.user_data['video_url'] = url
            context.user_data['video_title'] = info.get('title', 'Video')
            # Create a mapping of resolution to format_id
            format_map = {}
            for f in formats:
                if f.get('height'):
                    res_key = f"{f['height']}p"
                    # Store format_id, preferring formats with both video and audio
                    if f.get('acodec') and f.get('acodec') != 'none':
                        format_map[res_key] = f['format_id']
                    elif res_key not in format_map:
                        format_map[res_key] = f['format_id']
            
            context.user_data['formats'] = format_map
            
            # Create quality selection buttons
            buttons = [[InlineKeyboardButton(f"📥 {res}p", callback_data=f"dl_{res}p")] for res in resolutions[:10]]
            
            duration_min = info.get('duration', 0) // 60
            duration_sec = info.get('duration', 0) % 60
            
            await processing_msg.edit_text(
                f"🎬 *{info.get('title', 'Video')}*\n\n"
                f"⏱ Duration: {duration_min} min {duration_sec} sec\n"
                f"👤 Uploader: {info.get('uploader', 'Unknown')}\n\n"
                f"Choose your preferred quality:",
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode=ParseMode.MARKDOWN
            )
            
    except Exception as e:
        logger.error(f"Video extraction error: {e}")
        await processing_msg.edit_text(
            "❌ Unable to process this link.\n\n*Possible reasons:*\n• Invalid or unsupported URL\n• Private/restricted video\n• Geo-blocked content\n• Platform temporarily unavailable\n\nPlease try another link.",
            reply_markup=main_keyboard(user_id),
            parse_mode=ParseMode.MARKDOWN
        )

# --- Download and Send Video ---
async def download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    quality = query.data.replace("dl_", "")
    
    url = context.user_data.get('video_url')
    title = context.user_data.get('video_title', 'video')
    format_id = context.user_data.get('formats', {}).get(quality)
    
    if not url or not format_id:
        await query.answer("Session expired. Please resend the link.", show_alert=True)
        return
    
    await query.answer("Download started...")
    await query.edit_message_text(f"⬇️ Downloading in {quality}...\nPlease wait, this may take a moment.")
    
    temp_file = f"/tmp/{uuid4()}.mp4"
    
    try:
        ydl_opts = {
            'format': f'{format_id}+bestaudio/best',
            'outtmpl': temp_file.replace('.mp4', ''),
            'merge_output_format': 'mp4',
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
        }
        
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        # Find the actual downloaded file (yt-dlp may add extension)
        downloaded_file = temp_file.replace('.mp4', '') + '.mp4'
        if not os.path.exists(downloaded_file):
            # Try to find any file with similar name
            pattern = temp_file.replace('.mp4', '') + '*'
            files = glob.glob(pattern)
            if files:
                downloaded_file = files[0]
            else:
                raise FileNotFoundError("Downloaded file not found")
        
        file_size = os.path.getsize(downloaded_file)
        
        if file_size > MAX_FILESIZE:
            await query.message.reply_text(
                "❌ File too large (exceeds 2GB limit).\n\nPlease select a lower quality option.",
                reply_markup=main_keyboard(user_id)
            )
            os.remove(downloaded_file)
            return
        
        await query.edit_message_text(f"📤 Uploading {quality} video...\nAlmost done!")
        
        with open(downloaded_file, 'rb') as video_file:
            await query.message.reply_video(
                video_file,
                caption=f"✅ *{title}*\n\n📊 Quality: {quality}\n📦 Size: {file_size / (1024*1024):.1f} MB",
                reply_markup=main_keyboard(user_id),
                parse_mode=ParseMode.MARKDOWN,
                supports_streaming=True
            )
        
        await query.message.reply_text("✅ Video sent successfully! 🎉", reply_markup=main_keyboard(user_id))
        
        os.remove(downloaded_file)
        
    except Exception as e:
        logger.error(f"Download error: {e}")
        await query.message.reply_text(
            "❌ Download failed.\n\n*Possible reasons:*\n• Network connection issues\n• File too large\n• Video restricted or deleted\n• Platform rate limiting\n\nPlease try again or select a different quality.",
            reply_markup=main_keyboard(user_id),
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Clean up any partial files
        pattern = temp_file.replace('.mp4', '') + '*'
        for file in glob.glob(pattern):
            try:
                if os.path.exists(file):
                    os.remove(file)
            except Exception:
                pass

# --- Main Function ---
def main():
    if BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
        logger.error("BOT_TOKEN not set! Please set it as environment variable or in the code.")
        print("❌ ERROR: BOT_TOKEN not set!")
        print("💡 Set it as: export BOT_TOKEN='your_token_here'")
        return
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Admin conversation handler
    admin_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^🛠️ Admin Panel$'), text_router)],
        states={
            ADMIN_PANEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, text_router)],
            EDIT_INITIAL_WELCOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_initial_welcome)],
            EDIT_WELCOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_welcome)],
            WELCOME_MEDIA: [
                MessageHandler(filters.PHOTO | filters.Document.ALL | filters.ANIMATION, save_welcome_media),
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_welcome_media)
            ],
            ADD_CHANNEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_channel)],
            REMOVE_CHANNEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_channel)],
            BROADCAST: [
                MessageHandler(filters.PHOTO | filters.Document.ALL | filters.ANIMATION, broadcast),
                MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast)
            ],
        },
        fallbacks=[MessageHandler(filters.Regex("^⬅️ Back$|^❌ Cancel$"), text_router)],
        allow_reentry=True
    )
    
    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(admin_conv)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))
    application.add_handler(CallbackQueryHandler(join_channels_checker, pattern="check_joined"))
    application.add_handler(CallbackQueryHandler(download_callback, pattern="^dl_"))
    
    logger.info("Bot started successfully!")
    print("✅ Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

