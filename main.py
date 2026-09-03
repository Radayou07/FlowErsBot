import asyncio
import os
from dotenv import load_dotenv
from FlowErsAI import ai_response
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Store conversation history per user: {chat_id: previous_interaction_id}
user_last_interaction = {}


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
  user_last_interaction.pop(update.effective_user.id, None)
  await update.message.reply_text(
      "Hello! Ask me anything about health related, or send /reset to start a fresh chat."
  )


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
  user_last_interaction.pop(update.effective_user.id, None)
  await update.message.reply_text("Memory cleared! What's on your mind?")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
  user_id = update.effective_user.id
  user_text = update.message.text

  # Visual feedback in Telegram while the AI thinks/searches
  await update.message.chat.send_action("typing")

  prev_id = user_last_interaction.get(user_id)

  try:
    # Run the blocking Gemini/Tavily calls in a background thread
    reply_text, new_id = await asyncio.to_thread(
        ai_response, user_text, prev_id
    )

    # Save ID so the next message from this user maintains context
    user_last_interaction[user_id] = new_id

    # Telegram message length limit safeguard (4096 chars)
    if len(reply_text) > 4000:
      reply_text = reply_text[:4000] + "\n...[truncated]"

    await update.message.reply_text(reply_text)

  except Exception as e:
    await update.message.reply_text("Sorry, an error occurred while processing.")
    print(f"Error handling user {user_id}: {e}")


async def error(update: Update, context: ContextTypes.DEFAULT_TYPE):
  print(f"Update {update} caused error: {context.error}")


if __name__ == "__main__":
  print("Start running...")
  app = Application.builder().token(TELEGRAM_TOKEN).build()

  # Command Handlers
  app.add_handler(CommandHandler("start", start_command))
  app.add_handler(CommandHandler("reset", reset_command))

  # Message Handler for all non-command text
  app.add_handler(
      MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
  )

  # Error Handler
  app.add_error_handler(error)

  print("Polling...")
  app.run_polling(poll_interval=1)