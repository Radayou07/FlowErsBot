from telegram import Update
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Store conversation history per user: {chat_id: previous_interaction_id}
user_last_interaction = {}

# Start
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
  user_last_interaction.pop(update.effective_user.id, None)
  await update.message.reply_text(
      "Hello! Ask me anything about health related, or send /reset to start a fresh chat."
  )

# Reset
async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
  user_last_interaction.pop(update.effective_user.id, None)
  await update.message.reply_text("Memory cleared! What's on your mind?")
