import base64
import json
import os
import re
from typing import Any, Dict, Optional, Tuple
from dotenv import load_dotenv
from google import genai
from tavily import TavilyClient

load_dotenv()

client = genai.Client(api_key=os.getenv("GENAI_API_KEY"))
tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

SYSTEM_PROMPT = """You are a compassionate, knowledgeable, and safety-focused maternal health assistant for a Telegram bot called FLOWER (Maternal & Pregnancy Companion). Your goal is to support pregnant women and their families with evidence-based nutrition, lifestyle guidance, and comfort measures.

### Core Guidelines & Rules:

1. Clinical Grounding & Safety:
- Adhere strictly to authoritative obstetric guidelines (ACOG, WHO, NHS, CDC, National Maternal Health Cambodia).
- NEVER diagnose medical conditions or advise stopping prescribed prenatal regimens.
- Emphasize that all personalized nutrition, supplements, and symptoms should be confirmed with the user's OB/GYN or midwife.

2. Food Safety Rules (Non-Negotiable):
- HIGHLIGHT FOODS TO AVOID: Raw/undercooked meats, raw seafood/sushi, high-mercury fish (shark, swordfish, king mackerel), unpasteurized dairy/soft cheeses (Listeria risk), raw sprouts, unwashed produce, and alcohol.
- HIGHLIGHT ESSENTIAL NUTRIENTS: Folate/folic acid, iron, choline, DHA/Omega-3s, calcium, and adequate hydration.

3. Red Flag Symptom Protocol:
- If the user mentions any RED FLAGS: vaginal bleeding, severe cramping/abdominal pain, sudden severe swelling in face/hands, vision changes (blurriness, spots), severe persistent headache, fever, or fluid leakage:
  -> IMMEDIATELY urge them to contact their healthcare provider or emergency hospital.
  -> Do NOT downplay severe acute symptoms as normal pregnancy side effects.

4. Communication & Format (Telegram Friendly):
- Keep replies scannable, clear, and under 3 short paragraphs or bulleted lists.
- Avoid robotic disclaimers on every line; integrate safety warnings naturally and gently.
- Be warm, encouraging, and reassuring.
- Use clean Telegram Markdown formatting (bolding with single *asterisks*, simple bullet points with •).

5. Khmer Language & Typography Rules (Crucial for Font Size Consistency):
- When responding in Khmer, NEVER use italic underscores (_text_) or monospace code backticks (`text` or ```). In Telegram, italics and monospace cause Khmer font to shrink into a tiny, unreadable, or broken size.
- Use ONLY clean regular text, bullet points (•), and standard bold (*text*) for headings or key terms.
- Keep all Khmer text uniform in size and natural to read.
"""


def clean_khmer_formatting(text: str) -> str:
    """
    Sanitizes markdown tags (backticks, italic underscores, heading hashes)
    that cause Khmer characters to render in distorted or tiny font sizes in Telegram.
    """
    if not text:
        return ""
    # Remove triple/single backticks (`...` and ```...```)
    text = re.sub(r"`{1,3}(.*?)`{1,3}", r"\1", text, flags=re.DOTALL)
    text = text.replace("`", "")
    # Convert Markdown headers #, ##, ### into bold *Header*
    text = re.sub(r"^#{1,6}\s*(.+)$", r"*\1*", text, flags=re.MULTILINE)
    # Remove italic underscores (_text_) which shrink Khmer font
    text = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"\1", text)
    # Normalize double asterisks **bold** to single *bold* for Telegram Markdown
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
    return text


def web_search(query: str) -> str:
    """Performs live Tavily web search for updated health facts, food safety, or recalls."""
    try:
        response = tavily.search(query=query, max_results=3)
        return "\n".join(f"- {r['content']}" for r in response.get("results", []))
    except Exception as e:
        print(f"[Search error: {e}]")
        return ""


def needs_search(user_text: str, previous_id: Optional[str] = None) -> bool:
    """Classifies if user query requires live web search."""
    casual_triggers = {
        "hi", "hello", "hey", "how are you", "thanks", "thank you", "ok", "okay", "bye",
        "សួស្តី", "អរគុណ", "បាទ", "ចាស"
    }
    if user_text.lower().strip() in casual_triggers:
        return False

    classifier_prompt = f"""You are an intent routing classifier for a maternal and pregnancy health Telegram assistant.
Determine whether answering the user query requires an external web search.

Trigger SEARCH (reply 'YES') if the message involves:
1. Specific medications, herbs, teas, supplements, or cosmetics (checking pregnancy/lactation safety).
2. Niche, regional, or unverified foods/dishes (checking food safety, Listeria, mercury, or toxoplasmosis risks).
3. Recent health advisories, FDA/CDC warnings, or infant formula / baby food recalls.
4. Specific scientific, medical, or diagnostic questions requiring verified, up-to-date obstetric literature.

Do NOT search (reply 'NO') if the message is:
1. Casual greetings, emotional venting, or general reassurance.
2. Core, textbook pregnancy guidance already well-established (e.g., standard morning sickness tips, basic role of folic acid).
3. Follow-up conversational formatting ("can you summarize that?", "explain in simpler terms").

User query: "{user_text}"
Reply with ONLY 'YES' or 'NO':"""

    kwargs = {
        "model": "gemini-3.1-flash-lite",
        "input": classifier_prompt,
        "store": False,
    }
    if previous_id:
        kwargs["previous_interaction_id"] = previous_id

    try:
        decision = client.interactions.create(**kwargs)
        return "YES" in decision.output_text.strip().upper()
    except Exception as e:
        print(f"[Classifier fallback: {e}]")
        return False


def ai_response(
    message: str,
    previous_id: Optional[str] = None,
    patient_context: Optional[Dict[str, Any]] = None,
    lang: str = "en"
) -> Tuple[str, str]:
    """
    Generates personalized maternal health AI response with patient context and web search.
    """
    context_sections = []

    # 1. Clinical patient context injection
    if patient_context:
        week_str = f"Week {patient_context['current_week']}" if patient_context.get("current_week") else "Unknown week"
        tri_str = f"Trimester {patient_context['trimester']}" if patient_context.get("trimester") else "Unknown trimester"
        ctx_lines = [
            f"- Patient: {patient_context.get('name', 'Mother')}",
            f"- Gestational Age: {week_str} ({tri_str})",
            f"- Blood Type: {patient_context.get('blood_type', 'Unknown')}",
            f"- Known Allergies: {patient_context.get('allergies', 'None recorded')}",
            f"- Pre-existing Conditions: {patient_context.get('pre_existing_conditions', 'None')}",
        ]
        context_sections.append("Patient Health Profile:\n" + "\n".join(ctx_lines))

    # 2. Live search if needed
    if needs_search(message, previous_id=previous_id):
        print(f"[System: Live search triggered for: '{message[:40]}...']")
        search_res = web_search(message)
        if search_res:
            context_sections.append(f"Recent Medical Literature / Search Results:\n{search_res}")

    # 3. Build prompt
    prompt_parts = []
    if context_sections:
        prompt_parts.append("\n\n".join(context_sections))

    if lang == "kh":
        prompt_parts.append(f"Question (Please answer warmly and clearly in Khmer language / សូមឆ្លើយជាភាសាខ្មែរ): {message}")
    else:
        prompt_parts.append(f"Question: {message}")

    final_input = "\n\n---\n\n".join(prompt_parts)

    kwargs = {
        "model": "gemini-3.1-flash-lite",
        "input": final_input,
        "system_instruction": SYSTEM_PROMPT,
    }
    if previous_id:
        kwargs["previous_interaction_id"] = previous_id

    res = client.interactions.create(**kwargs)
    output = res.output_text
    if lang == "kh" or re.search(r"[ក-៿]", output):
        output = clean_khmer_formatting(output)
    return output, res.id


def analyze_medical_photo(
    image_bytes: bytes,
    lang: str = "en",
    patient_context: Optional[Dict[str, Any]] = None,
    mime_type: str = "image/jpeg"
) -> Dict[str, Any]:
    """
    Analyzes an uploaded medical photo (ultrasound, lab test, prescription, vaccine card, doctor note)
    using Gemini 3.1 Flash-Lite multimodal vision.
    Extracts structured JSON metadata ready for database insertion + bilingual plain summaries.
    """
    b64_image = base64.b64encode(image_bytes).decode("utf-8")

    patient_hint = ""
    if patient_context:
        w = patient_context.get("current_week")
        t = patient_context.get("trimester")
        w_text = f", current week: {w}" if w else ""
        t_text = f", trimester: {t}" if t else ""
        patient_hint = f"Patient Context: {patient_context.get('name', 'Patient')}{w_text}{t_text}."

    extraction_prompt = f"""You are an expert obstetric medical document analyzer for the FLOWER maternal health platform.
Analyze this medical document or photo (e.g. Ultrasound Scan, Blood/Urine Lab Test, Doctor Prescription, Vaccination Card, or Clinical Note).
{patient_hint}

Extract the clinical information and return ONLY a valid JSON object adhering strictly to this schema:
{{
  "category": "ultrasound" | "lab_test" | "prescription" | "vaccine" | "doctor_note" | "other",
  "title": "Clear descriptive title (e.g. 'Ultrasound 26 Weeks Scan', 'CBC Blood Test', 'Iron Supplement Prescription')",
  "facility": "Hospital, Clinic, or Laboratory name (or null if not found)",
  "doctor": "Doctor name with title (or null if not found)",
  "date": "Date of document in YYYY-MM-DD format (or today's date if not visible)",
  "week": integer_gestational_week_or_null,
  "trimester": 1_or_2_or_3_or_null,
  "status": "normal" | "abnormal" | "review_required" | "pending",
  "extracted_data": {{
    "parameter_name": "value with unit"
  }},
  "summary_en": "A clear, reassuring 2-3 sentence summary in plain English explaining what this document shows to the pregnant mother.",
  "summary_kh": "សេចក្តីសង្ខេបយ៉ាងច្បាស់ និងផ្តល់ទំនុកចិត្តជាភាសាខ្មែរ ២-៣ ប្រយោគ សម្រាប់ស្ត្រីមានផ្ទៃពោះយល់ដឹងពីលទ្ធផលនេះ។"
}}

Rules:
1. Ensure the JSON is 100% syntactically valid.
2. If any field is unclear, make your best clinical inference or provide null.
3. For 'status', mark 'normal' if results are within standard reference ranges, or 'review_required'/'abnormal' if there are critical values that require doctor attention.
4. Return ONLY the JSON object, no Markdown ticks or conversational text.
"""

    try:
        res = client.interactions.create(
            model="gemini-3.1-flash-lite",
            input=[
                {"type": "text", "text": extraction_prompt},
                {"type": "image", "data": b64_image, "mime_type": mime_type}
            ]
        )

        raw_output = res.output_text.strip()
        # Strip markdown ```json ... ``` wrapper if present
        cleaned_json = re.sub(r"^```json\s*", "", raw_output)
        cleaned_json = re.sub(r"^```\s*", "", cleaned_json)
        cleaned_json = re.sub(r"\s*```$", "", cleaned_json).strip()

        data = json.loads(cleaned_json)
        if "summary_kh" in data and isinstance(data["summary_kh"], str):
            data["summary_kh"] = clean_khmer_formatting(data["summary_kh"])
        return data

    except Exception as e:
        print(f"[Medical photo analysis error: {e}]")
        # Graceful fallback structure
        return {
            "category": "other",
            "title": "Scanned Medical Document",
            "facility": None,
            "doctor": None,
            "date": None,
            "week": patient_context.get("current_week") if patient_context else None,
            "trimester": patient_context.get("trimester") if patient_context else None,
            "status": "review_required",
            "extracted_data": {"note": "Automated scan captured image."},
            "summary_en": "Medical document photo captured and stored. Please consult your doctor to review detailed findings.",
            "summary_kh": "ឯកសារវេជ្ជសាស្ត្រត្រូវបានស្កេន និងរក្សាទុក។ សូមពិគ្រោះជាមួយវេជ្ជបណ្ឌិតរបស់អ្នកដើម្បីពិនិត្យលម្អិតបន្ថែម។"
        }
