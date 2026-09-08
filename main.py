import asyncio
import os
from dotenv import load_dotenv
from FlowErsAI import ai_response
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Track per-user state: {user_id: {"prev_id": str | None, "lang": "en" | "kh"}}
user_state = {}

# Menu buttons by language
MENUS = {
    "en": [
        [KeyboardButton("🍎 Safe Foods"), KeyboardButton("🚫 Foods to Avoid")],
        [KeyboardButton("⚠️ Red Flag Symptoms"), KeyboardButton("💊 Safe Supplements")],
        [KeyboardButton("🔄 Reset Chat"), KeyboardButton("🌐 Change Language")],
    ],
    "kh": [
        [KeyboardButton("🍎 អាហារសុវត្ថិភាព"), KeyboardButton("🚫 អាហារគួរជៀសវាង")],
        [KeyboardButton("⚠️ រោគសញ្ញាគ្រោះថ្នាក់"), KeyboardButton("💊 វីតាមីនជំនួយ")],
        [KeyboardButton("🔄 ចាប់ផ្ដើមថ្មី"), KeyboardButton("🌐 ប្តូរភាសា")],
    ],
}

# Explicit prompts mapped to button presses
PROMPT_MAP = {
    # English mappings
    "🍎 Safe Foods": "What are the most essential and safe foods to eat during pregnancy?",
    "🚫 Foods to Avoid": "What foods and drinks should be strictly avoided during pregnancy and why?",
    "⚠️ Red Flag Symptoms": "What are the urgent red flag pregnancy symptoms requiring emergency care?",
    "💊 Safe Supplements": "What prenatal supplements and vitamins are considered safe and necessary?",
    # Khmer mappings (tells Gemini to answer clearly in Khmer)
    "🍎 អាហារសុវត្ថិភាព": "សូមប្រាប់ពីអាហារដែលមានសុវត្ថិភាព និងល្អបំផុតសម្រាប់ស្ត្រីមានផ្ទៃពោះ (សូមឆ្លើយជាភាសាខ្មែរ)",
    "🚫 អាហារគួរជៀសវាង": "តើអាហារ និងភេសជ្ជៈអ្វីខ្លះដែលស្ត្រីមានផ្ទៃពោះត្រូវជៀសវាងដាច់ខាត? ព្រោះអ្វី? (សូមឆ្លើយជាភាសាខ្មែរ)",
    "⚠️ រោគសញ្ញាគ្រោះថ្នាក់": "តើរោគសញ្ញាគ្រោះថ្នាក់អ្វីខ្លះអំឡុងពេលមានផ្ទៃពោះដែលត្រូវទៅមន្ទីរពេទ្យជាបន្ទាន់? (សូមឆ្លើយជាភាសាខ្មែរ)",
    "💊 វីតាមីនជំនួយ": "តើវីតាមីន និងសារធាតុបំប៉នអ្វីខ្លះដែលស្ត្រីមានផ្ទៃពោះគួរញ៉ាំ? (សូមឆ្លើយជាភាសាខ្មែរ)",
}


def get_permanent_keyboard(lang: str) -> ReplyKeyboardMarkup:
  """Builds a persistent custom keyboard in the selected language."""
  return ReplyKeyboardMarkup(
      MENUS.get(lang, MENUS["en"]),
      resize_keyboard=True,
      is_persistent=True,
      one_time_keyboard=False,
  )


async def send_language_picker(
    target, text: str = "Please choose your language / សូមជ្រើសរើសភាសា៖"
):
  """Displays the inline language selection buttons."""
  keyboard = [
      [
          InlineKeyboardButton("🇬🇧 English", callback_data="set_lang_en"),
          InlineKeyboardButton("🇰🇭 ភាសាខ្មែរ", callback_data="set_lang_kh"),
      ]
  ]
  reply_markup = InlineKeyboardMarkup(keyboard)
  if hasattr(target, "reply_text"):
    await target.reply_text(text, reply_markup=reply_markup)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
  """Resets conversation and triggers language selection."""
  user_id = update.effective_user.id
  user_state[user_id] = {"prev_id": None, "lang": "en"}
  await send_language_picker(update.message)


async def handle_language_choice(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
  """Stores language preference, activates the persistent keyboard, and auto-queries Safe Foods."""
  query = update.callback_query
  await query.answer()

  user_id = update.effective_user.id
  selected_lang = "kh" if query.data == "set_lang_kh" else "en"

  # Initialize or update state
  if user_id not in user_state:
    user_state[user_id] = {"prev_id": None, "lang": selected_lang}
  else:
    user_state[user_id]["lang"] = selected_lang

  await query.message.delete()

  # Set initial prompt based on selected language
  if selected_lang == "kh":
    welcome_text = "👋 សួស្តី! ខ្ញុំជាជំនួយការសុខភាពមាតា និងទារក។\nនេះជាព័ត៌មានអំពីអាហារសុវត្ថិភាពដំបូងសម្រាប់អ្នក៖"
    safe_food_prompt = PROMPT_MAP["🍎 អាហារសុវត្ថិភាព"]
  else:
    welcome_text = "👋 Hello! I am your maternal and pregnancy health assistant.\nHere is your starting guide on safe foods:"
    safe_food_prompt = PROMPT_MAP["🍎 Safe Foods"]

  # Send welcome message and lock the persistent keyboard to the screen
  await context.bot.send_message(
      chat_id=query.message.chat_id,
      text=welcome_text,
      reply_markup=get_permanent_keyboard(selected_lang),
  )

  # Auto-generate the Safe Food response
  await context.bot.send_chat_action(
      chat_id=query.message.chat_id, action="typing"
  )

  try:
    reply_text, new_id = await asyncio.to_thread(ai_response, safe_food_prompt)
    user_state[user_id]["prev_id"] = new_id
    await context.bot.send_message(
        chat_id=query.message.chat_id, text=reply_text
    )
  except Exception as e:
    print(f"Error in initial safe food fetch: {e}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
  """Handles all button presses and regular typed messages."""
  user_id = update.effective_user.id
  user_text = update.message.text.strip()

  # Ensure user has an initialized profile
  if user_id not in user_state:
    user_state[user_id] = {"prev_id": None, "lang": "en"}

  user_lang = user_state[user_id]["lang"]

  # Handle Language Switch button
  if user_text in ["🌐 Change Language", "🌐 ប្តូរភាសា"]:
    await send_language_picker(update.message)
    return

  # Handle Reset Chat button
  if user_text in ["🔄 Reset Chat", "🔄 ចាប់ផ្ដើមថ្មី"]:
    user_state[user_id]["prev_id"] = None
    msg = (
        "🔄 Memory cleared! What would you like to ask?"
        if user_lang == "en"
        else "🔄 ការចងចាំត្រូវបានសម្អាត! តើអ្នកចង់សួរអ្វីបន្តទៀត?"
    )
    await update.message.reply_text(msg)
    return

  # Resolve prompt alias or use raw user text
  actual_prompt = PROMPT_MAP.get(user_text, user_text)

  # Hint language preference to the model if the user is typing free-form Khmer
  if user_lang == "kh" and user_text not in PROMPT_MAP:
    actual_prompt = f"{user_text} (Please reply in Khmer language / សូមឆ្លើយជាភាសាខ្មែរ)"

  await update.message.chat.send_action("typing")
  prev_id = user_state[user_id]["prev_id"]

  try:
    reply_text, new_id = await asyncio.to_thread(
        ai_response, actual_prompt, prev_id
    )
    user_state[user_id]["prev_id"] = new_id

    if len(reply_text) > 4000:
      reply_text = reply_text[:4000] + "\n...[truncated]"

    await update.message.reply_text(reply_text)

  except Exception as e:
    await update.message.reply_text("Sorry, an error occurred while processing.")
    print(f"Error handling message for user {user_id}: {e}")


if __name__ == "__main__":
  app = Application.builder().token(TELEGRAM_TOKEN).build()

  app.add_handler(CommandHandler("start", start_command))
  app.add_handler(
      CallbackQueryHandler(handle_language_choice, pattern="^set_lang_")
  )
  app.add_handler(
      MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
  )

  print("Bot running with language-first onboarding...")
  app.run_polling(poll_interval=1)
  