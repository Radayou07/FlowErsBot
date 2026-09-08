import asyncio
import os
import re
from typing import Any, Dict, Optional
from dotenv import load_dotenv
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

import db
from FlowErsAI import ai_response, analyze_medical_photo

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# In-memory user state:
# {
#   user_id: {
#     "lang": "en" | "kh",
#     "mother_id": str | None,
#     "prev_id": str | None,
#     "pending_scan": dict | None,
#     "awaiting_input": "weight" | "symptom" | None,
#   }
# }
user_state: Dict[int, Dict[str, Any]] = {}

# Ensure uploads directory exists
os.makedirs("uploads", exist_ok=True)

# -------------------------------------------------------------
# Permanent Reply Keyboards
# -------------------------------------------------------------
MENUS = {
    "en": [
        [KeyboardButton("📊 My Progress"), KeyboardButton("📸 Scan Medical Photo")],
        [KeyboardButton("❓ Pregnancy FAQ"), KeyboardButton("📝 Log Symptoms & Weight")],
        [KeyboardButton("📅 Appointments"), KeyboardButton("🚨 Emergency SOS")],
        [KeyboardButton("🍎 Pregnancy Guide (AI)"), KeyboardButton("🌐 Change Language")],
    ],
    "kh": [
        [KeyboardButton("📊 ការវិវត្តរបស់គភ៌"), KeyboardButton("📸 ស្កេនរូបភាពវេជ្ជសាស្ត្រ")],
        [KeyboardButton("❓ សំណួរញឹកញាប់ (FAQ)"), KeyboardButton("📝 កត់ត្រារោគសញ្ញា/ទម្ងន់")],
        [KeyboardButton("📅 ការណាត់ជួប"), KeyboardButton("🚨 សង្គ្រោះបន្ទាន់ (SOS)")],
        [KeyboardButton("🍎 មគ្គុទ្ទេសក៍សុខភាព"), KeyboardButton("🌐 ប្តូរភាសា")],
    ],
}


def get_permanent_keyboard(lang: str) -> ReplyKeyboardMarkup:
    """Builds a persistent custom keyboard in the selected language."""
    return ReplyKeyboardMarkup(
        MENUS.get(lang, MENUS["en"]),
        resize_keyboard=True,
        is_persistent=True,
        one_time_keyboard=False,
    )


def get_user_session(user_id: int) -> Dict[str, Any]:
    """Helper to retrieve or initialize a user session, checking DB links."""
    if user_id not in user_state:
        linked_mother_id = db.get_mother_id_by_telegram(user_id)
        user_state[user_id] = {
            "lang": "en",
            "mother_id": linked_mother_id,
            "prev_id": None,
            "pending_scan": None,
            "awaiting_input": None,
        }
    return user_state[user_id]


def is_phone_number_text(text: str) -> bool:
    """Detects whether a user's text message is an entered phone number."""
    cleaned = text.strip()
    if re.search(r"[a-zA-Zក-៿]", cleaned):
        return False
    digits = "".join(filter(str.isdigit, cleaned))
    if 8 <= len(digits) <= 15:
        valid_chars = set("0123456789+ -().")
        if all(c in valid_chars for c in cleaned):
            return True
    return False


# -------------------------------------------------------------
# Language & Onboarding Handlers
# -------------------------------------------------------------
async def send_language_picker(target, text: str = "Please choose your language / សូមជ្រើសរើសភាសា៖"):
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


async def send_connect_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE, feature_name_kh: str, feature_name_en: str):
    """Prompts unlinked users to connect their account before accessing personal clinical features."""
    user_id = update.effective_user.id
    session = get_user_session(user_id)
    lang = session["lang"]

    if lang == "kh":
        msg = (
            f"🔒 *សូមភ្ជាប់គណនីដើម្បីប្រើមុខងារ {feature_name_kh}*\n\n"
            f"លោកអ្នកមិនទាន់បានភ្ជាប់គណនីជាមួយប្រព័ន្ធគេហទំព័រនៅឡើយទេ។ "
            f"សូមភ្ជាប់គណនីតាមរយៈលេខទូរស័ព្ទរបស់អ្នក ឬភ្ជាប់គណនីគំរូដើម្បីសាកល្បងមុខងារនេះ។"
        )
        keyboard = [
            [InlineKeyboardButton("📱 ផ្ញើលេខទូរស័ព្ទដើម្បីភ្ជាប់", callback_data="req_phone_link")],
            [InlineKeyboardButton("👩 ភ្ជាប់គណនីគំរូ (Demo)", callback_data="link_demo_profile")],
        ]
    else:
        msg = (
            f"🔒 *Please Connect Your Account for {feature_name_en}*\n\n"
            f"You are not connected to a website health profile yet. "
            f"Please link your registered phone number or connect the Demo profile to use this feature."
        )
        keyboard = [
            [InlineKeyboardButton("📱 Link Phone Number", callback_data="req_phone_link")],
            [InlineKeyboardButton("👩 Connect Demo Profile", callback_data="link_demo_profile")],
        ]

    markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(msg, parse_mode="Markdown", reply_markup=markup)
    else:
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=markup)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for /start command or new bot interactions."""
    user_id = update.effective_user.id
    # Always clear existing link so the user can re-enter their phone number
    db.unlink_telegram_user(user_id)
    user_state[user_id] = {
        "lang": "en",
        "mother_id": None,
        "prev_id": None,
        "pending_scan": None,
        "awaiting_input": None,
    }
    await send_language_picker(update.message)


async def handle_language_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stores language preference and checks profile connection status."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    selected_lang = "kh" if query.data == "set_lang_kh" else "en"
    session = get_user_session(user_id)
    session["lang"] = selected_lang

    try:
        await query.message.delete()
    except Exception:
        pass

    # Check if linked to a valid mother profile in the database
    mother_id = session.get("mother_id") or db.get_linked_mother_id(user_id)
    profile = db.get_mother_full_profile(mother_id) if mother_id else None

    if profile:
        session["mother_id"] = mother_id
        mother_name = profile.get("name", "Mother")
        week = profile.get("current_week", 1)

        if selected_lang == "kh":
            welcome = f"👋 សួស្តីអ្នកម្តាយ *{mother_name}*! (សប្តាហ៍ទី {week})\nតើខ្ញុំអាចជួយអ្វីដល់អ្នកថ្ងៃនេះ?"
        else:
            welcome = f"👋 Welcome back, *{mother_name}*! (Week {week})\nHow can I support your pregnancy today?"

        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=welcome,
            parse_mode="Markdown",
            reply_markup=get_permanent_keyboard(selected_lang),
        )
    else:
        # If the stored link was invalid or not found, clear it
        if mother_id:
            db.unlink_telegram_user(user_id)
            session["mother_id"] = None

        # Ask for phone number immediately after language selection
        if selected_lang == "kh":
            phone_btn_text = "📱 ចុចទីនេះដើម្បីផ្ញើលេខទូរស័ព្ទ"
            prompt_text = (
                "🌸 *សូមភ្ជាប់គណនីសុខភាពមាតារបស់អ្នក*\n\n"
                "សូមចុចប៊ូតុងខាងក្រោមដើម្បីផ្ញើលេខទូរស័ព្ទ ឬវាយបញ្ចូលលេខទូរស័ព្ទរបស់អ្នកដោយផ្ទាល់ក្នុងឆាតនេះ៖"
            )
        else:
            phone_btn_text = "📱 Tap to Share Phone Number"
            prompt_text = (
                "🌸 *Connect Your Health Profile*\n\n"
                "Please tap the button below to share your phone number, or simply type your phone number in this chat:"
            )

        contact_keyboard = ReplyKeyboardMarkup(
            [[KeyboardButton(phone_btn_text, request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=prompt_text,
            parse_mode="Markdown",
            reply_markup=contact_keyboard,
        )

        # Also provide inline options for demo profile or guest mode
        inline_kb = [
            [InlineKeyboardButton("👩 ភ្ជាប់គណនីគំរូ (Demo Profile)" if selected_lang == "kh" else "👩 Connect Demo Profile", callback_data="link_demo_profile")],
            [InlineKeyboardButton("⏩ បន្តជាភ្ញៀវ (Guest)" if selected_lang == "kh" else "⏩ Continue as Guest", callback_data="skip_link_profile")],
        ]
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="💡 " + ("ឬជ្រើសរើសជម្រើសខាងក្រោម៖" if selected_lang == "kh" else "Or select an option below:"),
            reply_markup=InlineKeyboardMarkup(inline_kb),
        )


async def handle_profile_linking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles linking via demo profile, phone sharing, or skipping."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    session = get_user_session(user_id)
    lang = session["lang"]
    data = query.data

    if data == "link_demo_profile":
        # Link explicitly to the demo profile from the live database
        demo_id = db.get_default_mother_id()
        db.link_telegram_to_mother(user_id, demo_id)
        session["mother_id"] = demo_id
        profile = db.get_mother_full_profile(demo_id)
        name = profile.get("name", profile.get("full_name", "Mother")) if profile else "Mother"
        week = profile.get("current_week", "?") if profile else "?"

        if lang == "kh":
            text = f"✅ បានភ្ជាប់គណនីគំរូជោគជ័យ! សួស្តីអ្នកម្តាយ *{name}* (សប្តាហ៍ទី {week})។\nលោកអ្នកអាចប្រើប្រាស់មុខងារទាំងអស់ខាងក្រោមនេះបាន៖"
        else:
            text = f"✅ Successfully connected to Demo Profile: *{name}* (Week {week})!\nYou can now access all maternal tools below:"

        try:
            await query.message.delete()
        except Exception:
            pass

        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=text,
            parse_mode="Markdown",
            reply_markup=get_permanent_keyboard(lang),
        )

    elif data == "req_phone_link":
        # Prompt for phone number via contact button or typed input
        if lang == "kh":
            phone_btn_text = "📱 ចុចទីនេះដើម្បីផ្ញើលេខទូរស័ព្ទ"
            prompt_text = (
                "📱 *សូមផ្ញើលេខទូរស័ព្ទរបស់អ្នក*\n\n"
                "សូមចុចប៊ូតុងខាងក្រោមដើម្បីផ្ញើលេខទូរស័ព្ទ ឬវាយបញ្ចូលលេខទូរស័ព្ទរបស់អ្នកដោយផ្ទាល់ (ឧ. 012 345 678)៖"
            )
        else:
            phone_btn_text = "📱 Tap to Share Phone Number"
            prompt_text = (
                "📱 *Share Your Phone Number*\n\n"
                "Please tap the button below to share your registered phone number, or type it directly in chat (e.g. 012 345 678):"
            )

        contact_keyboard = ReplyKeyboardMarkup(
            [[KeyboardButton(phone_btn_text, request_contact=True)], [KeyboardButton("🔙 Back / ត្រឡប់ក្រោយ")]],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
        try:
            await query.message.delete()
        except Exception:
            pass

        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=prompt_text,
            parse_mode="Markdown",
            reply_markup=contact_keyboard,
        )

    elif data == "skip_link_profile":
        if lang == "kh":
            text = "👋 សួស្តី! ខ្ញុំជាជំនួយការសុខភាពមាតា FLOWER។ តើអ្នកចង់ដឹងអ្វីខ្លះថ្ងៃនេះ?"
        else:
            text = "👋 Hello! I am your FLOWER maternal health assistant. How can I help you today?"

        try:
            await query.message.delete()
        except Exception:
            pass

        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=text,
            reply_markup=get_permanent_keyboard(lang),
        )


async def process_phone_linking(user_id: int, phone: str, lang: str, reply_target):
    """Matches phone against mother_profiles in database and sets user session."""
    session = get_user_session(user_id)
    mother_id = db.find_mother_by_phone(phone)
    if mother_id:
        db.link_telegram_to_mother(user_id, mother_id)
        session["mother_id"] = mother_id
        profile = db.get_mother_full_profile(mother_id)
        name = profile.get("name", "Mother") if profile else "Mother"
        week = profile.get("current_week", "?") if profile else "?"
        msg = (
            f"🎉 *រកឃើញគណនីក្នុងប្រព័ន្ធ!*\n\n"
            f"សួស្តីអ្នកម្តាយ *{name}* (សប្តាហ៍ទី {week})។\n"
            f"គណនី Telegram របស់អ្នកត្រូវបានភ្ជាប់ជាមួយគេហទំព័រដោយជោគជ័យ! ✨"
            if lang == "kh"
            else (
                f"🎉 *Account Connected Successfully!*\n\n"
                f"Welcome *{name}* (Week {week})!\n"
                f"Your Telegram is now securely linked to your website health profile! ✨"
            )
        )
        await reply_target.reply_text(
            msg,
            parse_mode="Markdown",
            reply_markup=get_permanent_keyboard(lang),
        )
    else:
        session["mother_id"] = None
        db.unlink_telegram_user(user_id)
        msg = (
            f"❌ *រកមិនឃើញគណនី*\n\n"
            f"យើងរកមិនឃើញគណនីដែលបានចុះឈ្មោះជាមួយលេខទូរស័ព្ទ *{phone}* នៅក្នុងប្រព័ន្ធគេហទំព័រទេ។\n\n"
            f"សូមពិនិត្យមើលលេខទូរស័ព្ទដែលបានចុះឈ្មោះនៅលើ Website ឬភ្ជាប់គណនីគំរូ (Demo) ដើម្បីសាកល្បងមុខងារ។"
            if lang == "kh"
            else (
                f"❌ *Account Not Found*\n\n"
                f"No registered profile was found with phone number *{phone}* on the website.\n\n"
                f"Please check your registered phone number or connect the Demo profile to explore features."
            )
        )
        keyboard = [
            [InlineKeyboardButton("📱 ផ្ញើលេខទូរស័ព្ទម្តងទៀត" if lang == "kh" else "📱 Retry Phone Number", callback_data="req_phone_link")],
            [InlineKeyboardButton("👩 ភ្ជាប់គណនីគំរូ (Demo)" if lang == "kh" else "👩 Connect Demo Profile", callback_data="link_demo_profile")],
            [InlineKeyboardButton("⏩ បន្តជាភ្ញៀវ" if lang == "kh" else "⏩ Continue as Guest", callback_data="skip_link_profile")],
        ]
        await reply_target.reply_text(
            msg,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


async def handle_contact_share(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles shared phone number to match with mother_profiles.phone."""
    user_id = update.effective_user.id
    session = get_user_session(user_id)
    lang = session["lang"]
    contact = update.message.contact
    phone = contact.phone_number.strip()
    await process_phone_linking(user_id, phone, lang, update.message)


# -------------------------------------------------------------
# Feature 1: 📊 My Progress
# -------------------------------------------------------------
async def handle_my_progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Renders maternal pregnancy progress, baby size milestone, and clinical summary."""
    user_id = update.effective_user.id
    session = get_user_session(user_id)
    lang = session["lang"]
    mother_id = session.get("mother_id") or db.get_linked_mother_id(user_id)

    if not mother_id:
        await send_connect_prompt(update, context, "ព័ត៌មានការវិវត្តរបស់គភ៌", "Pregnancy Progress")
        return

    session["mother_id"] = mother_id
    profile = db.get_mother_full_profile(mother_id)
    if not profile:
        session["mother_id"] = None
        db.unlink_telegram_user(user_id)
        await send_connect_prompt(update, context, "ព័ត៌មានការវិវត្តរបស់គភ៌", "Pregnancy Progress")
        return

    name = profile.get("name", "Mother")
    week = profile.get("current_week", 1)
    trimester = profile.get("trimester", 1)
    edd = profile.get("edd", "N/A")
    blood_type = profile.get("blood_type", "N/A")
    weight = profile.get("pre_pregnancy_weight_kg", profile.get("weight_kg", "N/A"))
    allergies = profile.get("allergies", "None")

    size_name, milestone_text = db.get_baby_milestone(week, lang)

    if lang == "kh":
        progress_card = (
            f"🌸 *ព័ត៌មានការវិវត្តរបស់គភ៌* 🌸\n\n"
            f"👤 *អ្នកម្តាយ:* {name}\n"
            f"📅 *អាយុគភ៌:* *សប្តាហ៍ទី {week}* (ត្រីមាសទី {trimester})\n"
            f"⏳ *ថ្ងៃសម្រាលរំពឹងទុក (EDD):* {edd}\n\n"
            f"👶 *ទំហំ និងការលូតលាស់របស់កូន:*\n"
            f"• ទំហំប៉ុន៖ *{size_name}*\n"
            f"• ការលូតលាស់៖ {milestone_text}\n\n"
            f"🩺 *ទិន្នន័យសុខភាព:*\n"
            f"• ប្រភេទឈាម៖ *{blood_type}* | ទម្ងន់បច្ចុប្បន្ន៖ *{weight} kg*\n"
            f"• ប្រវត្តិប្រតិកម្មថ្នាំ៖ *{allergies}*\n"
        )
        quick_btns = [
            [
                InlineKeyboardButton("📸 ស្កេនរូបភាពវេជ្ជសាស្ត្រ", callback_data="prompt_scan_photo"),
                InlineKeyboardButton("📝 កត់ត្រាទម្ងន់/រោគសញ្ញា", callback_data="prompt_log_menu"),
            ],
            [
                InlineKeyboardButton("📅 មើលការណាត់ជួប", callback_data="view_appointments_inline"),
            ]
        ]
    else:
        progress_card = (
            f"🌸 *Pregnancy Progress & Milestones* 🌸\n\n"
            f"👤 *Mother:* {name}\n"
            f"📅 *Gestational Age:* *Week {week}* (Trimester {trimester})\n"
            f"⏳ *Estimated Due Date (EDD):* {edd}\n\n"
            f"👶 *Baby Size & Development:*\n"
            f"• Baby Size: *{size_name}*\n"
            f"• Milestone: {milestone_text}\n\n"
            f"🩺 *Clinical Summary:*\n"
            f"• Blood Type: *{blood_type}* | Current Weight: *{weight} kg*\n"
            f"• Allergies: *{allergies}*\n"
        )
        quick_btns = [
            [
                InlineKeyboardButton("📸 Scan Medical Photo", callback_data="prompt_scan_photo"),
                InlineKeyboardButton("📝 Log Weight / Symptom", callback_data="prompt_log_menu"),
            ],
            [
                InlineKeyboardButton("📅 View Appointments", callback_data="view_appointments_inline"),
            ]
        ]

    await update.message.reply_text(
        progress_card,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(quick_btns),
    )


# -------------------------------------------------------------
# Feature 2: 📸 Scan Medical Photo & Website Sync
# -------------------------------------------------------------
async def handle_photo_upload_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Instructs the user on how to upload a medical document photo."""
    user_id = update.effective_user.id
    session = get_user_session(user_id)
    lang = session["lang"]

    if lang == "kh":
        msg = (
            "📸 *ស្កេនរូបភាពវេជ្ជសាស្ត្រ & ផ្ញើទៅកាន់គេហទំព័រ*\n\n"
            "សូមផ្ញើរូបថតច្បាស់មួយនៃ៖\n"
            "• 🩺 លទ្ធផលពិនិត្យអេកូ (Ultrasound Scan)\n"
            "• 🧪 លទ្ធផលពិនិត្យឈាម/ទឹកនោម (Lab Test Results)\n"
            "• 💊 វេជ្ជបញ្ជា ឬកាតចាក់វ៉ាក់សាំង (Prescription/Vaccine)\n\n"
            "👉 គ្រាន់តែចុចរូបកាមេរ៉ា ឬ Upload រូបថតចូលក្នុងឆាតនេះផ្ទាល់!"
        )
    else:
        msg = (
            "📸 *Scan Medical Document & Sync to Website*\n\n"
            "Please send a clear photo of your:\n"
            "• 🩺 Ultrasound scan report\n"
            "• 🧪 Blood/Urine lab test result\n"
            "• 💊 Doctor's prescription or vaccine card\n\n"
            "👉 Simply tap the attachment/camera button and send your photo directly to this chat!"
        )

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(msg, parse_mode="Markdown")
    else:
        await update.message.reply_text(msg, parse_mode="Markdown")


async def handle_photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes medical photo uploads with Gemini Vision, shows preview, and offers save button."""
    user_id = update.effective_user.id
    session = get_user_session(user_id)
    lang = session["lang"]
    mother_id = session.get("mother_id") or db.get_linked_mother_id(user_id)

    if mother_id:
        session["mother_id"] = mother_id
        patient_ctx = db.get_mother_full_profile(mother_id)
    else:
        patient_ctx = None

    # Send analyzing status
    status_msg = await update.message.reply_text(
        "🔍 កំពុងវិភាគរូបភាពវេជ្ជសាស្ត្រជាមួយ Gemini AI..." if lang == "kh" else "🔍 Analyzing medical document with Gemini AI..."
    )
    await update.message.chat.send_action("typing")

    try:
        # Get highest resolution photo
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()

        # Call Gemini Multimodal extraction
        extracted_doc = await asyncio.to_thread(
            analyze_medical_photo,
            bytes(photo_bytes),
            lang=lang,
            patient_context=patient_ctx,
            mime_type="image/jpeg",
        )

        # Save to session pending state
        session["pending_scan"] = {
            "mother_profile_id": mother_id,
            "title": extracted_doc.get("title", "Scanned Medical Document"),
            "category": extracted_doc.get("category", "other"),
            "facility": extracted_doc.get("facility"),
            "doctor": extracted_doc.get("doctor"),
            "date": extracted_doc.get("date"),
            "week": extracted_doc.get("week") or (patient_ctx.get("current_week") if patient_ctx else None),
            "trimester": extracted_doc.get("trimester") or (patient_ctx.get("trimester") if patient_ctx else None),
            "status": extracted_doc.get("status", "normal"),
            "notes": extracted_doc.get("summary_kh" if lang == "kh" else "summary_en", ""),
            "extracted_data": extracted_doc.get("extracted_data", {}),
            "image_attachment": f"photo_{user_id}_{update.message.message_id}.jpg",
        }

        # Build preview card
        title = session["pending_scan"]["title"]
        category = session["pending_scan"]["category"].capitalize()
        facility = session["pending_scan"]["facility"] or ("មន្ទីរពេទ្យ/គ្លីនិក" if lang == "kh" else "Not specified")
        doctor = session["pending_scan"]["doctor"] or ("វេជ្ជបណ្ឌិត" if lang == "kh" else "Not specified")
        date_str = session["pending_scan"]["date"] or "Today"
        status_badge = "✅ Normal" if session["pending_scan"]["status"] == "normal" else "⚠️ Review Needed"
        summary = session["pending_scan"]["notes"]

        # Format findings list
        findings_lines = []
        if isinstance(session["pending_scan"]["extracted_data"], dict):
            for k, v in list(session["pending_scan"]["extracted_data"].items())[:4]:
                findings_lines.append(f"• {k.replace('_', ' ').title()}: *{v}*")
        findings_text = "\n".join(findings_lines) if findings_lines else "• Extracted clinical parameters"

        if lang == "kh":
            preview_card = (
                f"📋 *លទ្ធផលនៃការវិភាគឯកសារវេជ្ជសាស្ត្រ*\n\n"
                f"🏷️ *ចំណងជើង:* {title}\n"
                f"🩺 *ប្រភេទ:* {category}\n"
                f"🏥 *មន្ទីរពេទ្យ:* {facility}\n"
                f"👨‍⚕️ *វេជ្ជបណ្ឌិត:* {doctor}\n"
                f"📅 *កាលបរិច្ឆេទ:* {date_str} | ស្ថានភាព: *{status_badge}*\n\n"
                f"🔬 *ទិន្នន័យសំខាន់ៗ:*\n{findings_text}\n\n"
                f"📝 *សេចក្តីសង្ខេប AI សម្រាប់អ្នកម្តាយ:*\n{summary}\n\n"
                f"❓ *តើអ្នកចង់រក្សាទុកឯកសារនេះទៅកាន់គណនីគេហទំព័រដែរឬទេ?*"
            )
            confirm_keyboard = [
                [
                    InlineKeyboardButton("✅ បញ្ជាក់ & រក្សាទុកក្នុងគេហទំព័រ", callback_data="save_scan_confirm"),
                ],
                [
                    InlineKeyboardButton("❌ បោះបង់ / មិនរក្សាទុក", callback_data="save_scan_cancel"),
                ],
            ]
        else:
            preview_card = (
                f"📋 *Medical Document Analysis Preview*\n\n"
                f"🏷️ *Title:* {title}\n"
                f"🩺 *Category:* {category}\n"
                f"🏥 *Facility:* {facility}\n"
                f"👨‍⚕️ *Doctor:* {doctor}\n"
                f"📅 *Date:* {date_str} | Status: *{status_badge}*\n\n"
                f"🔬 *Key Extracted Measurements:*\n{findings_text}\n\n"
                f"📝 *AI Summary for Mother:*\n{summary}\n\n"
                f"❓ *Would you like to save this record directly to your website health profile?*"
            )
            confirm_keyboard = [
                [
                    InlineKeyboardButton("✅ Confirm & Save to Website", callback_data="save_scan_confirm"),
                ],
                [
                    InlineKeyboardButton("❌ Discard / Cancel", callback_data="save_scan_cancel"),
                ],
            ]

        await status_msg.delete()
        await update.message.reply_text(
            preview_card,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(confirm_keyboard),
        )

    except Exception as e:
        print(f"Error analyzing photo: {e}")
        await status_msg.edit_text(
            "❌ មានបញ្ហាក្នុងការវិភាគរូបភាព។ សូមព្យាយាមម្តងទៀតជាមួយរូបភាពច្បាស់ជាងនេះ។"
            if lang == "kh"
            else "❌ Failed to analyze the photo. Please try again with a clearer image."
        )


async def handle_save_scan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the user clicking [Confirm & Save to Website] or [Discard]."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    session = get_user_session(user_id)
    lang = session["lang"]
    data = query.data

    if data == "save_scan_confirm":
        pending = session.get("pending_scan")
        if pending:
            target_mother_id = pending.get("mother_profile_id") or session.get("mother_id") or db.get_linked_mother_id(user_id)
            if not target_mother_id:
                if lang == "kh":
                    msg = "🔒 *សូមភ្ជាប់គណនីជាមុនសិន*\n\nដើម្បីរក្សាទុកកំណត់ត្រាវេជ្ជសាស្ត្រនេះទៅកាន់គេហទំព័រ សូមភ្ជាប់គណនីរបស់អ្នក៖"
                else:
                    msg = "🔒 *Please Connect Your Account First*\n\nTo save this medical record to the website, please connect your profile:"
                keyboard = [
                    [InlineKeyboardButton("📱 ផ្ញើលេខទូរស័ព្ទដើម្បីភ្ជាប់" if lang == "kh" else "📱 Link Phone Number", callback_data="req_phone_link")],
                    [InlineKeyboardButton("👩 ភ្ជាប់គណនីគំរូ (Demo)" if lang == "kh" else "👩 Connect Demo Profile", callback_data="link_demo_profile")],
                ]
                await query.message.reply_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
                return

            # Save to Database
            success = db.save_medical_record(
                mother_profile_id=target_mother_id,
                title=pending["title"],
                category=pending["category"],
                facility=pending["facility"],
                doctor=pending["doctor"],
                date_str=pending["date"],
                week=pending["week"],
                trimester=pending["trimester"],
                notes=pending["notes"],
                extracted_data=pending["extracted_data"],
                status=pending["status"],
                image_attachment=pending["image_attachment"],
            )

            session["pending_scan"] = None
            try:
                await query.message.delete()
            except Exception:
                pass

            if success:
                msg = (
                    "🎉 *បានរក្សាទុកដោយជោគជ័យ!*\n\n"
                    "កំណត់ត្រាវេជ្ជសាស្ត្ររបស់អ្នកត្រូវបានបញ្ចូលទៅកាន់គេហទំព័ររួចរាល់ហើយ។ "
                    "លោកអ្នក និងវេជ្ជបណ្ឌិតអាចមើលឃើញទិន្នន័យនេះនៅលើ Portal គេហទំព័របានភ្លាមៗ។ 🌸"
                    if lang == "kh"
                    else (
                        "🎉 *Successfully Saved to Website!*\n\n"
                        "Your medical record has been stored in your official health file. "
                        "Both you and your doctor can now view these results on the website clinical portal. 🌸"
                    )
                )
            else:
                msg = "❌ Error saving record. Please try again."

            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=msg,
                parse_mode="Markdown",
                reply_markup=get_permanent_keyboard(lang),
            )
        else:
            await query.message.reply_text("No pending scan found / មិនមានឯកសារដែលត្រូវរក្សាទុកទេ។")

    elif data == "save_scan_cancel":
        session["pending_scan"] = None
        try:
            await query.message.delete()
        except Exception:
            pass

        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="🗑️ បានបោះបង់ឯកសារ។" if lang == "kh" else "🗑️ Document discarded.",
            reply_markup=get_permanent_keyboard(lang),
        )


# -------------------------------------------------------------
# Feature 3: ❓ Interactive Pregnancy FAQ
# -------------------------------------------------------------
FAQ_DATA = {
    "en": {
        "faq_nausea": {
            "title": "🤢 Morning Sickness & Nausea",
            "body": (
                "💡 *Morning Sickness Relief:*\n"
                "• Eat small, frequent meals every 2-3 hours instead of large ones.\n"
                "• Keep plain crackers by your bed to eat before getting up.\n"
                "• Sip ginger tea or lemon water to soothe your stomach.\n"
                "• Avoid spicy, greasy, or strong-smelling foods.\n"
                "⚠️ *Contact your doctor if you cannot keep liquids down for 24 hours.*"
            ),
        },
        "faq_sleep": {
            "title": "🛌 Safe Sleeping Positions",
            "body": (
                "💡 *Sleeping Advice:*\n"
                "• *Left-Side Sleeping* is the best position from Week 20 onward because it maximizes blood flow and nutrients to the placenta and baby.\n"
                "• Place a pregnancy pillow between your knees and under your belly.\n"
                "• Avoid sleeping flat on your back after 20 weeks, as your uterus can press on the vena cava vein."
            ),
        },
        "faq_kicks": {
            "title": "👶 Baby Kick Counting",
            "body": (
                "💡 *How to Count Kicks (Starting ~Week 28):*\n"
                "• Choose a quiet time when baby is usually active (often after a meal or in the evening).\n"
                "• Count kicks, rolls, flutters, or jabs.\n"
                "• Target: You should feel *at least 10 distinct movements within 2 hours*.\n"
                "🚨 *If baby's movement slows noticeably, contact your clinic immediately.*"
            ),
        },
        "faq_swelling": {
            "title": "🦶 Swelling & Leg Cramps",
            "body": (
                "💡 *Managing Swelling & Cramps:*\n"
                "• Elevate your feet whenever sitting or resting.\n"
                "• Stay well hydrated (drink 8-10 glasses of clean water daily).\n"
                "• Stretch your calf muscles before sleeping to prevent cramps.\n"
                "⚠️ *Red Flag:* Sudden swelling in your face or hands accompanied by headaches can indicate preeclampsia—seek urgent care."
            ),
        },
        "faq_travel": {
            "title": "✈️ Travel & Work Safety",
            "body": (
                "💡 *Travel Guidelines:*\n"
                "• The safest time to travel is during the *2nd Trimester (Weeks 14-28)*.\n"
                "• Always wear your seatbelt under your belly and across your hip bones.\n"
                "• On long trips, stand up and walk every 1-2 hours to prevent blood clots.\n"
                "• Always carry a copy of your prenatal health records."
            ),
        },
        "faq_vitamins": {
            "title": "💊 Essential Supplements",
            "body": (
                "💡 *Core Prenatal Supplements:*\n"
                "• *Folic Acid (400-800 mcg):* Crucial for baby's brain and spinal cord development.\n"
                "• *Iron (27-30 mg):* Prevents maternal anemia and supports blood volume growth.\n"
                "• *Calcium & Vitamin D:* Supports baby's bones and teeth.\n"
                "• *DHA (Omega-3):* Essential for fetal brain and eye development."
            ),
        },
    },
    "kh": {
        "faq_nausea": {
            "title": "🤢 ចង្អោរ និងក្អួត (Morning Sickness)",
            "body": (
                "💡 *វិធីកាត់បន្ថយការចង្អោរ និងក្អួត:*\n"
                "• ញ៉ាំអាហារតិចៗតែញឹកញាប់ (រៀងរាល់ ២-៣ ម៉ោងម្តង) កុំទុកឱ្យក្រពះទទេ\n"
                "• ញ៉ាំនំបុ័ងក្រៀម ឬនំស្រួយបន្តិចមុនពេលក្រោកពីគេង\n"
                "• ផឹកទឹកខ្ញីក្តៅឧណ្ហៗ ឬទឹកក្រូចឆ្មារដើម្បីសម្រួលក្រពះ\n"
                "• ជៀសវាងអាហារហឹរ ខ្លាញ់ច្រើន ឬមានក្លិនឆួល\n"
                "⚠️ *ត្រូវជួបគ្រូពេទ្យប្រសិនបើក្អួតខ្លាំងរហូតញ៉ាំទឹកមិនបានពេញមួយថ្ងៃ។*"
            ),
        },
        "faq_sleep": {
            "title": "🛌 របៀបគេងឱ្យមានសុវត្ថិភាព",
            "body": (
                "💡 *ការគេងត្រឹមត្រូវសម្រាប់ស្ត្រីមានផ្ទៃពោះ:*\n"
                "• *ការគេងផ្អៀងទៅខាងឆ្វេង* គឺជាកាយវិការល្អបំផុត (ចាប់ពីសប្តាហ៍ទី ២០ ឡើង) ព្រោះជួយឱ្យឈាម និងសារធាតុចិញ្ចឹមរត់ទៅកាន់សុក និងទារកបានល្អបំផុត\n"
                "• ប្រើខ្នើយកល់នៅចន្លោះជង្គង់ និងក្រោមក្បាលពោះ\n"
                "• ជៀសវាងការគេងផ្ងារត្រង់យូរ ព្រោះស្បូនសង្កត់លើសរសៃឈាមធំ។"
            ),
        },
        "faq_kicks": {
            "title": "👶 ការរាប់ចលនាកូនកន្ត្រាក់ (Kick Count)",
            "body": (
                "💡 *របៀបរាប់កូនកន្ត្រាក់ (ចាប់ពីសប្តាហ៍ទី ២៨):*\n"
                "• ជ្រើសរើសពេលសម្រាកស្ងប់ស្ងាត់ (ជាពិសេសក្រោយបាយ ឬពេលល្ងាច)\n"
                "• រាប់ចលនាធាក់ បង្វិល ឬកន្ត្រាក់របស់កូន\n"
                "• គោលដៅ៖ គួរមានចលនា *យ៉ាងហោចណាស់ ១០ ដងក្នុងរយៈពេល ២ ម៉ោង*\n"
                "🚨 *ប្រសិនបើកូនស្ងាត់ខុសពីធម្មតា សូមទៅមន្ទីរពេទ្យពិនិត្យជាបន្ទាន់។*"
            ),
        },
        "faq_swelling": {
            "title": "🦶 ហើមជើង និងរមួលក្រពើ",
            "body": (
                "💡 *វិធីកាត់បន្ថយការហើម និងរមួលក្រពើ:*\n"
                "• កល់ជើងឱ្យខ្ពស់បន្តិចនៅពេលអង្គុយ ឬគេងសម្រាក\n"
                "• ផឹកទឹកស្អាតឱ្យបានគ្រប់គ្រាន់ (៨-១០ កែវក្នុងមួយថ្ងៃ)\n"
                "• ពត់ជើង ឬធ្វើលំហាត់ប្រាណបាតជើងស្រាលៗមុនគេង\n"
                "⚠️ *រោគសញ្ញាគ្រោះថ្នាក់:* ប្រសិនបើហើមមុខ ហើមដៃភ្លាមៗ និងឈឺក្បាលខ្លាំង អាចជាសញ្ញាបម្រុងក្រឡាភ្លើង ត្រូវទៅជួបគ្រូពេទ្យជាបន្ទាន់។"
            ),
        },
        "faq_travel": {
            "title": "✈️ សុវត្ថិភាពពេលធ្វើដំណើរ និងការងារ",
            "body": (
                "💡 *ការណែនាំអំពីការធ្វើដំណើរ:*\n"
                "• ពេលវេលាសុវត្ថិភាពបំផុតក្នុងការធ្វើដំណើរគឺ *ត្រីមាសទី ២ (សប្តាហ៍ទី ១៤-២៨)*\n"
                "• ពាក់ខ្សែក្រវាត់សុវត្ថិភាពឱ្យនៅក្រោមក្បាលពោះជាប់នឹងត្រគាកជានិច្ច\n"
                "• ពេលជិះឡានផ្លូវឆ្ងាយ គួរឈប់សម្រាកដើររៀងរាល់ ១-២ ម៉ោងម្តង\n"
                "• ត្រូវយកសៀវភៅតាមដានសុខភាពមាតាជាប់ខ្លួនជានិច្ច។"
            ),
        },
        "faq_vitamins": {
            "title": "💊 វីតាមីន និងសារធាតុបំប៉នចាំបាច់",
            "body": (
                "💡 *វីតាមីនចាំបាច់ក្នុងការពពោះ:*\n"
                "• *អាស៊ីតហ្វូលិក (Folic Acid):* ការពារភាពមិនប្រក្រតីនៃខួរក្បាល និងឆ្អឹងខ្នងកូន\n"
                "• *ជាតិដែក (Iron):* ការពារជំងឺស្លេកស្លាំង និងជួយបង្កើនបរិមាណឈាម\n"
                "• *កាល់ស្យូម & វីតាមីន D:* ជួយបង្កើតឆ្អឹង និងធ្មេញរឹងមាំដល់ទារក\n"
                "• *DHA (Omega-3):* ជំនួយការលូតលាស់ខួរក្បាល និងភ្នែករបស់កូន។"
            ),
        },
    },
}


async def handle_faq_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the interactive Pregnancy FAQ menu buttons."""
    user_id = update.effective_user.id
    session = get_user_session(user_id)
    lang = session["lang"]

    if lang == "kh":
        header_text = "❓ *សំណួរញឹកញាប់អំពីសុខភាពស្ត្រីមានផ្ទៃពោះ (FAQ)*\nសូមជ្រើសរើសប្រធានបទខាងក្រោម៖"
        keyboard = [
            [
                InlineKeyboardButton("🤢 ចង្អោរ & ក្អួត", callback_data="faq_nausea"),
                InlineKeyboardButton("🛌 របៀបគេងត្រឹមត្រូវ", callback_data="faq_sleep"),
            ],
            [
                InlineKeyboardButton("👶 ការរាប់កូនកន្ត្រាក់", callback_data="faq_kicks"),
                InlineKeyboardButton("🦶 ហើមជើង & រមួលក្រពើ", callback_data="faq_swelling"),
            ],
            [
                InlineKeyboardButton("✈️ ការធ្វើដំណើរ", callback_data="faq_travel"),
                InlineKeyboardButton("💊 វីតាមីនជំនួយ", callback_data="faq_vitamins"),
            ],
        ]
    else:
        header_text = "❓ *Frequently Asked Pregnancy Questions (FAQ)*\nPlease select a topic below for instant guidance:"
        keyboard = [
            [
                InlineKeyboardButton("🤢 Morning Sickness", callback_data="faq_nausea"),
                InlineKeyboardButton("🛌 Safe Sleep Positions", callback_data="faq_sleep"),
            ],
            [
                InlineKeyboardButton("👶 Baby Kick Counts", callback_data="faq_kicks"),
                InlineKeyboardButton("🦶 Swelling & Cramps", callback_data="faq_swelling"),
            ],
            [
                InlineKeyboardButton("✈️ Travel & Work", callback_data="faq_travel"),
                InlineKeyboardButton("💊 Vitamins & Nutrition", callback_data="faq_vitamins"),
            ],
        ]

    await update.message.reply_text(
        header_text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def handle_faq_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Renders the selected FAQ answer and offers an AI follow-up option."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    session = get_user_session(user_id)
    lang = session["lang"]
    faq_key = query.data

    faq_dict = FAQ_DATA.get(lang, FAQ_DATA["en"])
    item = faq_dict.get(faq_key)

    if item:
        if lang == "kh":
            back_btn = [
                [InlineKeyboardButton("🔙 មើលសំណួរ FAQ ផ្សេងទៀត", callback_data="reopen_faq_menu")],
            ]
        else:
            back_btn = [
                [InlineKeyboardButton("🔙 Browse More FAQ Topics", callback_data="reopen_faq_menu")],
            ]

        await query.message.reply_text(
            f"*{item['title']}*\n\n{item['body']}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(back_btn),
        )


async def handle_reopen_faq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reopens the FAQ selection list."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    session = get_user_session(user_id)
    lang = session["lang"]

    if lang == "kh":
        header_text = "❓ *សំណួរញឹកញាប់អំពីសុខភាពស្ត្រីមានផ្ទៃពោះ (FAQ)*"
        keyboard = [
            [
                InlineKeyboardButton("🤢 ចង្អោរ & ក្អួត", callback_data="faq_nausea"),
                InlineKeyboardButton("🛌 របៀបគេងត្រឹមត្រូវ", callback_data="faq_sleep"),
            ],
            [
                InlineKeyboardButton("👶 ការរាប់កូនកន្ត្រាក់", callback_data="faq_kicks"),
                InlineKeyboardButton("🦶 ហើមជើង & រមួលក្រពើ", callback_data="faq_swelling"),
            ],
            [
                InlineKeyboardButton("✈️ ការធ្វើដំណើរ", callback_data="faq_travel"),
                InlineKeyboardButton("💊 វីតាមីនជំនួយ", callback_data="faq_vitamins"),
            ],
        ]
    else:
        header_text = "❓ *Frequently Asked Pregnancy Questions (FAQ)*"
        keyboard = [
            [
                InlineKeyboardButton("🤢 Morning Sickness", callback_data="faq_nausea"),
                InlineKeyboardButton("🛌 Safe Sleep Positions", callback_data="faq_sleep"),
            ],
            [
                InlineKeyboardButton("👶 Baby Kick Counts", callback_data="faq_kicks"),
                InlineKeyboardButton("🦶 Swelling & Cramps", callback_data="faq_swelling"),
            ],
            [
                InlineKeyboardButton("✈️ Travel & Work", callback_data="faq_travel"),
                InlineKeyboardButton("💊 Vitamins & Nutrition", callback_data="faq_vitamins"),
            ],
        ]

    await query.message.edit_text(
        header_text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# -------------------------------------------------------------
# Feature 4: 📝 Log Daily Symptoms & Weight
# -------------------------------------------------------------
async def handle_log_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the logging choices (Weight vs Symptom)."""
    user_id = update.effective_user.id
    session = get_user_session(user_id)
    lang = session["lang"]
    mother_id = session.get("mother_id") or db.get_linked_mother_id(user_id)

    if not mother_id:
        await send_connect_prompt(update, context, "កត់ត្រាទម្ងន់/រោគសញ្ញា", "Log Symptoms & Weight")
        return

    session["mother_id"] = mother_id

    if lang == "kh":
        msg = "📝 *កត់ត្រាសុខភាពប្រចាំថ្ងៃទៅកាន់គេហទំព័រ*\nតើអ្នកចង់កត់ត្រាអ្វីថ្ងៃនេះ?"
        keyboard = [
            [
                InlineKeyboardButton("⚖️ កត់ត្រាទម្ងន់ (kg)", callback_data="log_prompt_weight"),
                InlineKeyboardButton("🩺 កត់ត្រារោគសញ្ញា/អារម្មណ៍", callback_data="log_prompt_symptom"),
            ]
        ]
    else:
        msg = "📝 *Log Daily Health to Website*\nWhat would you like to record today?"
        keyboard = [
            [
                InlineKeyboardButton("⚖️ Update Weight (kg)", callback_data="log_prompt_weight"),
                InlineKeyboardButton("🩺 Log Symptoms / Notes", callback_data="log_prompt_symptom"),
            ]
        ]

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


async def handle_log_prompts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sets awaiting_input mode for weight or symptom."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    session = get_user_session(user_id)
    lang = session["lang"]
    mother_id = session.get("mother_id") or db.get_linked_mother_id(user_id)

    if not mother_id:
        await send_connect_prompt(update, context, "កត់ត្រាទម្ងន់/រោគសញ្ញា", "Log Symptoms & Weight")
        return

    session["mother_id"] = mother_id
    data = query.data

    if data == "log_prompt_weight":
        session["awaiting_input"] = "weight"
        if lang == "kh":
            text = "⚖️ សូមវាយបញ្ចូលទម្ងន់បច្ចុប្បន្នរបស់អ្នកជាគីឡូក្រាម (ឧទាហរណ៍៖ *54.5*):"
        else:
            text = "⚖️ Please type your current weight in kg (e.g. *54.5*):"
        await query.message.reply_text(text, parse_mode="Markdown")

    elif data == "log_prompt_symptom":
        session["awaiting_input"] = "symptom"
        if lang == "kh":
            text = "🩺 សូមរៀបរាប់ពីរោគសញ្ញា ឬអារម្មណ៍របស់អ្នកថ្ងៃនេះ (ឧទាហរណ៍៖ *ឈឺខ្នងបន្តិចបន្តួច អស់កម្លាំង*):"
        else:
            text = "🩺 Please describe how you are feeling or any symptoms today (e.g. *mild lower back ache, feeling tired*):"
        await query.message.reply_text(text, parse_mode="Markdown")


# -------------------------------------------------------------
# Feature 5: 📅 Appointments
# -------------------------------------------------------------
async def handle_appointments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays upcoming and recent clinical appointments."""
    user_id = update.effective_user.id
    session = get_user_session(user_id)
    lang = session["lang"]
    mother_id = session.get("mother_id") or db.get_linked_mother_id(user_id)

    if not mother_id:
        await send_connect_prompt(update, context, "កាលវិភាគណាត់ជួប", "Appointments")
        return

    session["mother_id"] = mother_id
    appts = db.get_mother_appointments(mother_id)

    if lang == "kh":
        if not appts:
            msg = "📅 មិនទាន់មានកាលវិភាគណាត់ជួបនៅឡើយទេ។"
        else:
            lines = ["📅 *កាលវិភាគពិនិត្យផ្ទៃពោះ & ការណាត់ជួប*\n"]
            for a in appts:
                status_icon = "🟢" if not a.get("completed") else "⚪"
                lines.append(
                    f"{status_icon} *{a.get('title', 'ពិនិត្យសុខភាព')}*\n"
                    f"• 📅 កាលបរិច្ឆេទ: *{a.get('date')}* ម៉ោង *{a.get('time', 'ព្រឹក')}*\n"
                    f"• 🏥 មន្ទីរពេទ្យ: {a.get('hospital', 'Calmette Hospital')}\n"
                    f"• 👨‍⚕️ វេជ្ជបណ្ឌិត: {a.get('doctor', 'Dr. Sophy Chan')}\n"
                    f"• ស្ថានភាព: *{'រួចរាល់' if a.get('completed') else 'គ្រោងទុក'}*\n"
                )
            msg = "\n".join(lines)
    else:
        if not appts:
            msg = "📅 No scheduled appointments found."
        else:
            lines = ["📅 *Your Prenatal & Clinical Appointments*\n"]
            for a in appts:
                status_icon = "🟢" if not a.get("completed") else "⚪"
                lines.append(
                    f"{status_icon} *{a.get('title', 'Prenatal Visit')}*\n"
                    f"• 📅 Date: *{a.get('date')}* at *{a.get('time', 'Morning')}*\n"
                    f"• 🏥 Facility: {a.get('hospital', 'Calmette Hospital')}\n"
                    f"• 👨‍⚕️ Doctor: {a.get('doctor', 'Dr. Sophy Chan')}\n"
                    f"• Status: *{'Completed' if a.get('completed') else 'Scheduled'}*\n"
                )
            msg = "\n".join(lines)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(msg, parse_mode="Markdown")
    else:
        await update.message.reply_text(msg, parse_mode="Markdown")


# -------------------------------------------------------------
# Feature 6: 🚨 Emergency SOS
# -------------------------------------------------------------
async def handle_emergency_sos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays urgent red flag symptom warnings and emergency telephone numbers."""
    user_id = update.effective_user.id
    session = get_user_session(user_id)
    lang = session["lang"]
    mother_id = session.get("mother_id") or db.get_linked_mother_id(user_id)

    profile = db.get_mother_full_profile(mother_id) if mother_id else None
    emergency_contact = profile.get("emergency_contact", {}) if profile else {}
    contact_name = emergency_contact.get("name") if emergency_contact else None
    contact_phone = emergency_contact.get("phone") if emergency_contact else None

    if lang == "kh":
        contact_line = (
            f"• 👤 អ្នកជិតស្និទ្ធ: *{contact_name}* (*{contact_phone}*)\n"
            if contact_name and contact_phone
            else ""
        )
        sos_msg = (
            "🚨 *សង្គ្រោះបន្ទាន់ផ្នែកសម្ភព (Emergency SOS)* 🚨\n\n"
            "⚠️ *រោគសញ្ញាគ្រោះថ្នាក់ដែលត្រូវទៅមន្ទីរពេទ្យភ្លាមៗ:*\n"
            "• ធ្លាក់ឈាមតាមទ្វារមាស\n"
            "• ឈឺពោះ ឬកន្ត្រាក់ស្បូនខ្លាំង\n"
            "• ហើមមុខ ឬដៃភ្លាមៗ និងឈឺក្បាលខ្លាំង\n"
            "• ស្រវាំងភ្នែក ឬឃើញពន្លឺភ្លឹបភ្លែត\n"
            "• បែកទឹកភ្លោះ ឬធ្លាយទឹករម្អិល\n"
            "• ក្តៅខ្លួនខ្លាំងលើសពី 38°C\n"
            "• កូនស្ងាត់លែងកន្ត្រាក់លើសពី ២ ម៉ោង\n\n"
            "📞 *លេខទំនាក់ទំនងបន្ទាន់:*\n"
            f"{contact_line}"
            "• 🚑 រថយន្តសង្គ្រោះជាតិកម្ពុជា: *119*\n"
            "• 🏥 មន្ទីរពេទ្យកាល់ម៉ែត (Calmette): *+855 23 426 948*\n"
        )
    else:
        contact_line = (
            f"• 👤 Primary Contact: *{contact_name}* (*{contact_phone}*)\n"
            if contact_name and contact_phone
            else ""
        )
        sos_msg = (
            "🚨 *Maternal Emergency & Red Flags (SOS)* 🚨\n\n"
            "⚠️ *Urgent Red Flag Symptoms Requiring Emergency Care:*\n"
            "• Vaginal bleeding or spotting\n"
            "• Severe abdominal cramping or pain\n"
            "• Sudden swelling in face/hands with persistent headache\n"
            "• Vision disturbances (blurriness, flashing lights)\n"
            "• Fluid leakage (ruptured membranes)\n"
            "• High fever above 38°C (100.4°F)\n"
            "• Significant decrease or absence of baby movements\n\n"
            "📞 *Emergency Contact Numbers:*\n"
            f"{contact_line}"
            "• 🚑 National Ambulance (Cambodia): *119*\n"
            "• 🏥 Calmette Hospital Emergency: *+855 23 426 948*\n"
        )

    await update.message.reply_text(sos_msg, parse_mode="Markdown")


# -------------------------------------------------------------
# Feature 7: 🍎 Pregnancy Guide (AI Prompts)
# -------------------------------------------------------------
async def handle_pregnancy_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays AI health guide quick topics."""
    user_id = update.effective_user.id
    session = get_user_session(user_id)
    lang = session["lang"]

    if lang == "kh":
        msg = "🍎 *មគ្គុទ្ទេសក៍សុខភាព & អាហារូបត្ថម្ភ (AI Guide)*\nសូមជ្រើសរើសប្រធានបទដើម្បីសួរ AI៖"
        keyboard = [
            [
                InlineKeyboardButton("🍎 អាហារសុវត្ថិភាព", callback_data="ai_prompt_safe_foods"),
                InlineKeyboardButton("🚫 អាហារគួរជៀសវាង", callback_data="ai_prompt_avoid_foods"),
            ],
            [
                InlineKeyboardButton("💊 វីតាមីនជំនួយ", callback_data="ai_prompt_supplements"),
                InlineKeyboardButton("⚠️ រោគសញ្ញាប្រុងប្រយ័ត្ន", callback_data="ai_prompt_symptoms"),
            ]
        ]
    else:
        msg = "🍎 *Pregnancy Nutrition & Health Guide (AI)*\nSelect a topic for instant clinical advice:"
        keyboard = [
            [
                InlineKeyboardButton("🍎 Safe Essential Foods", callback_data="ai_prompt_safe_foods"),
                InlineKeyboardButton("🚫 Foods to Avoid", callback_data="ai_prompt_avoid_foods"),
            ],
            [
                InlineKeyboardButton("💊 Safe Prenatal Vitamins", callback_data="ai_prompt_supplements"),
                InlineKeyboardButton("⚠️ Red Flag Symptoms", callback_data="ai_prompt_symptoms"),
            ]
        ]

    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


async def handle_ai_guide_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the user tapping an AI guide pill."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    session = get_user_session(user_id)
    lang = session["lang"]
    mother_id = session.get("mother_id") or db.get_linked_mother_id(user_id)
    patient_ctx = db.get_mother_full_profile(mother_id) if mother_id else None
    data = query.data

    prompts = {
        "ai_prompt_safe_foods": (
            "What are the most essential and safe foods to eat during my current pregnancy stage?"
            if lang == "en"
            else "សូមប្រាប់ពីអាហារដែលមានសុវត្ថិភាព និងល្អបំផុតសម្រាប់ស្ត្រីមានផ្ទៃពោះ"
        ),
        "ai_prompt_avoid_foods": (
            "What foods and drinks should be strictly avoided during pregnancy and why?"
            if lang == "en"
            else "តើអាហារ និងភេសជ្ជៈអ្វីខ្លះដែលស្ត្រីមានផ្ទៃពោះត្រូវជៀសវាងដាច់ខាត? ព្រោះអ្វី?"
        ),
        "ai_prompt_supplements": (
            "What prenatal vitamins and supplements are recommended and safe?"
            if lang == "en"
            else "តើវីតាមីន និងសារធាតុបំប៉នអ្វីខ្លះដែលស្ត្រីមានផ្ទៃពោះគួរញ៉ាំ?"
        ),
        "ai_prompt_symptoms": (
            "What are the urgent pregnancy warning signs requiring medical care?"
            if lang == "en"
            else "តើរោគសញ្ញាគ្រោះថ្នាក់អ្វីខ្លះអំឡុងពេលមានផ្ទៃពោះដែលត្រូវទៅមន្ទីរពេទ្យ?"
        ),
    }

    selected_prompt = prompts.get(data, "Please provide maternal health advice.")

    await query.message.reply_text(
        f"🤔 *Question:* {selected_prompt}\n\n_Thinking with Gemini AI..._",
        parse_mode="Markdown",
    )
    await context.bot.send_chat_action(chat_id=query.message.chat_id, action="typing")

    try:
        reply_text, new_id = await asyncio.to_thread(
            ai_response,
            selected_prompt,
            previous_id=session.get("prev_id"),
            patient_context=patient_ctx,
            lang=lang,
        )
        session["prev_id"] = new_id
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=reply_text,
        )
    except Exception as e:
        print(f"AI response error: {e}")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Sorry, an error occurred while querying AI.",
        )


# -------------------------------------------------------------
# Main Message Router (Buttons + Free-form text + Phone Linking)
# -------------------------------------------------------------
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dispatches text messages to button handlers, input collectors, phone linking, or Gemini AI."""
    user_id = update.effective_user.id
    session = get_user_session(user_id)
    lang = session["lang"]
    mother_id = session.get("mother_id") or db.get_linked_mother_id(user_id)
    user_text = update.message.text.strip()

    # 1. Back button
    if user_text in ["🔙 Back", "🔙 ត្រឡប់ក្រោយ", "🔙 Back / ត្រឡប់ក្រោយ"]:
        session["awaiting_input"] = None
        await update.message.reply_text(
            "🏠 ត្រឡប់ទៅម៉ឺនុយដើម" if lang == "kh" else "🏠 Back to Main Menu",
            reply_markup=get_permanent_keyboard(lang),
        )
        return

    # 2. Main Menu Button Dispatches
    if user_text in ["📊 My Progress", "📊 ការវិវត្តរបស់គភ៌"]:
        await handle_my_progress(update, context)
        return

    if user_text in ["📸 Scan Medical Photo", "📸 ស្កេនរូបភាពវេជ្ជសាស្ត្រ"]:
        await handle_photo_upload_prompt(update, context)
        return

    if user_text in ["❓ Pregnancy FAQ", "❓ សំណួរញឹកញាប់ (FAQ)"]:
        await handle_faq_menu(update, context)
        return

    if user_text in ["📝 Log Symptoms & Weight", "📝 កត់ត្រារោគសញ្ញា/ទម្ងន់"]:
        await handle_log_menu(update, context)
        return

    if user_text in ["📅 Appointments", "📅 ការណាត់ជួប"]:
        await handle_appointments(update, context)
        return

    if user_text in ["🚨 Emergency SOS", "🚨 សង្គ្រោះបន្ទាន់ (SOS)"]:
        await handle_emergency_sos(update, context)
        return

    if user_text in ["🍎 Pregnancy Guide (AI)", "🍎 មគ្គុទ្ទេសក៍សុខភាព"]:
        await handle_pregnancy_guide(update, context)
        return

    if user_text in ["🌐 Change Language", "🌐 ប្តូរភាសា"]:
        await send_language_picker(update.message)
        return

    # 3. Handle Awaiting Inputs (Weight or Symptom logging)
    if session.get("awaiting_input") == "weight":
        if not mother_id:
            await send_connect_prompt(update, context, "កត់ត្រាទម្ងន់", "Log Weight")
            return
        match = re.search(r"(\d+(\.\d+)?)", user_text)
        if match:
            new_weight = float(match.group(1))
            db.update_mother_weight(mother_id, new_weight)
            session["awaiting_input"] = None
            msg = (
                f"✅ បានកត់ត្រាទម្ងន់ *{new_weight} kg* ទៅកាន់គេហទំព័រដោយជោគជ័យ! ⚖️"
                if lang == "kh"
                else f"✅ Successfully updated your weight to *{new_weight} kg* on the website! ⚖️"
            )
            await update.message.reply_text(
                msg,
                parse_mode="Markdown",
                reply_markup=get_permanent_keyboard(lang),
            )
        else:
            err = "⚠️ សូមវាយបញ្ចូលលេខទម្ងន់ត្រឹមត្រូវ (ឧ. 54.5)៖" if lang == "kh" else "⚠️ Please enter a valid number (e.g. 54.5):"
            await update.message.reply_text(err)
        return

    if session.get("awaiting_input") == "symptom":
        if not mother_id:
            await send_connect_prompt(update, context, "កត់ត្រារោគសញ្ញា", "Log Symptom")
            return
        patient_ctx = db.get_mother_full_profile(mother_id)
        current_week = patient_ctx.get("current_week") if patient_ctx else None
        trimester = patient_ctx.get("trimester") if patient_ctx else None

        db.save_medical_record(
            mother_profile_id=mother_id,
            title="Daily Symptom Log" if lang == "en" else "កំណត់ត្រារោគសញ្ញាប្រចាំថ្ងៃ",
            category="doctor_note",
            notes=user_text,
            week=current_week,
            trimester=trimester,
            status="normal",
            extracted_data={"patient_reported_symptom": user_text},
        )
        session["awaiting_input"] = None
        msg = (
            "✅ បានកត់ត្រារោគសញ្ញារបស់អ្នកទៅកាន់ប្រព័ន្ធគេហទំព័រជោគជ័យ! វេជ្ជបណ្ឌិតអាចពិនិត្យតាមដានបាន។ 🩺"
            if lang == "kh"
            else "✅ Your symptom note has been logged to your website health records for your doctor to review! 🩺"
        )
        await update.message.reply_text(
            msg,
            parse_mode="Markdown",
            reply_markup=get_permanent_keyboard(lang),
        )
        return

    # 4. Direct typed phone number linking
    if is_phone_number_text(user_text):
        await process_phone_linking(user_id, user_text, lang, update.message)
        return

    # 5. Free-form AI query
    await update.message.chat.send_action("typing")
    patient_ctx = db.get_mother_full_profile(mother_id) if mother_id else None
    prev_id = session.get("prev_id")

    try:
        reply_text, new_id = await asyncio.to_thread(
            ai_response,
            user_text,
            previous_id=prev_id,
            patient_context=patient_ctx,
            lang=lang,
        )
        session["prev_id"] = new_id

        if len(reply_text) > 4000:
            reply_text = reply_text[:4000] + "\n...[truncated]"

        await update.message.reply_text(reply_text)

    except Exception as e:
        print(f"Error handling message for user {user_id}: {e}")
        await update.message.reply_text(
            "សូមអភ័យទោស មានបញ្ហាក្នុងការឆ្លើយតប។"
            if lang == "kh"
            else "Sorry, an error occurred while processing your request."
        )


# -------------------------------------------------------------
# Main Entry Point
# -------------------------------------------------------------
def build_application() -> Application:
    """Builds and configures the Telegram Bot application."""
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start_command))

    # Callback Query Handlers
    app.add_handler(CallbackQueryHandler(handle_language_choice, pattern="^set_lang_"))
    app.add_handler(CallbackQueryHandler(handle_profile_linking, pattern="^(link_demo_profile|req_phone_link|skip_link_profile)$"))
    app.add_handler(CallbackQueryHandler(handle_photo_upload_prompt, pattern="^prompt_scan_photo$"))
    app.add_handler(CallbackQueryHandler(handle_save_scan_callback, pattern="^save_scan_(confirm|cancel)$"))
    app.add_handler(CallbackQueryHandler(handle_faq_callback, pattern="^faq_"))
    app.add_handler(CallbackQueryHandler(handle_reopen_faq, pattern="^reopen_faq_menu$"))
    app.add_handler(CallbackQueryHandler(handle_log_menu, pattern="^prompt_log_menu$"))
    app.add_handler(CallbackQueryHandler(handle_log_prompts, pattern="^log_prompt_"))
    app.add_handler(CallbackQueryHandler(handle_appointments, pattern="^view_appointments_inline$"))
    app.add_handler(CallbackQueryHandler(handle_ai_guide_callback, pattern="^ai_prompt_"))

    # Message Handlers
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_message))
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact_share))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    return app


if __name__ == "__main__":
    print("🚀 FLOWER Maternal Companion Telegram Bot is starting...")
    app = build_application()
    print("🤖 Bot is live and listening for messages (Zero-schema & Button-driven)...")
    app.run_polling(drop_pending_updates=True, poll_interval=1)
