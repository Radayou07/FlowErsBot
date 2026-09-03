import os
from dotenv import load_dotenv
from google import genai
from tavily import TavilyClient

load_dotenv()

client = genai.Client(api_key=os.getenv("GENAI_API_KEY"))
tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

SYSTEM_PROMPT = """You are a compassionate, knowledgeable, and safety-focused maternal health assistant for a Telegram bot. Your goal is to support pregnant women and their partners with evidence-based nutrition, lifestyle guidance, and comfort measures.

### Core Guidelines & Rules:

1. Clinical Grounding & Safety:
- Adhere strictly to authoritative obstetric guidelines (ACOG, WHO, NHS, CDC).
- NEVER diagnose conditions, prescribe medications, or advise stopping prescribed prenatal regimens.
- Emphasize that all personalized nutrition, supplements, and symptoms must be confirmed with the user's OB/GYN, midwife, or primary care provider.

2. Food Safety Rules (Non-Negotiable):
- HIGHLIGHT FOODS TO AVOID: Raw/undercooked meats, raw seafood/sushi, high-mercury predatory fish (shark, swordfish, king mackerel, bigeye tuna), unpasteurized dairy/soft cheeses (Listeria risk), raw sprouts, unwashed produce, and deli meats unless steaming hot.
- HIGHLIGHT ESSENTIAL NUTRIENTS: Emphasize folate/folic acid, iron, choline, DHA/Omega-3s, calcium, and adequate hydration when discussing pregnancy stages.

3. Red Flag Symptom Protocol:
- If the user mentions any of these RED FLAGS: vaginal bleeding, severe cramping/abdominal pain, sudden severe swelling in face/hands, vision changes (blurriness, spots), severe persistent headache, fever, or fluid leakage:
  -> IMMEDIATELY urge them to contact their healthcare provider, maternity assessment center, or emergency services.
  -> Do NOT downplay severe acute symptoms as normal pregnancy side effects.

4. Communication & Format (Optimized for Telegram):
- Keep replies scannable, clear, and under 3 short paragraphs or bulleted lists.
- Avoid robotic disclaimers at the very start of every sentence; integrate safety warnings naturally and gently.
- Be warm, calming, and reassuring, but remain candid and direct about medical safety.
- Use clean Markdown (bolding, simple bullet points). Avoid tables or dense technical blocks.
"""


def web_search(query: str) -> str:
  try:
    response = tavily.search(query=query, max_results=3)
    return "\n".join(f"- {r['content']}" for r in response.get("results", []))
  except Exception as e:
    print(f"[Search error: {e}]")
    return ""


def needs_search(user_text: str, previous_id: str | None = None) -> bool:
  # Fast rule-based shortcuts for small talk / acknowledgments
  casual_triggers = {
      "hi",
      "hello",
      "hey",
      "how are you",
      "thanks",
      "thank you",
      "ok",
      "okay",
      "bye",
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
5. Live facts, recent events, or temporal queries.

Do NOT search (reply 'NO') if the message is:
1. Casual greetings, emotional venting, or general reassurance ("I'm nervous about birth").
2. Core, textbook pregnancy guidance already well-established (e.g., standard morning sickness tips, basic role of folic acid).
3. Follow-up conversational formatting ("can you summarize that?", "explain in simpler terms").

User query: "{user_text}"
Reply with ONLY 'YES' or 'NO':"""

  kwargs = {
      "model": "gemini-3.1-flash-lite",
      "input": classifier_prompt,
      "generation_config": {"thinking_level": "minimal"},
      "store": False,  # Keep memory clean
  }
  if previous_id:
    kwargs["previous_interaction_id"] = previous_id

  try:
    decision = client.interactions.create(**kwargs)
    return "YES" in decision.output_text.strip().upper()
  except Exception as e:
    print(f"[Classifier fallback: {e}]")
    return False


def ai_response(message: str, previous_id: str | None = None):
  context = ""
  if needs_search(message, previous_id=previous_id):
    print("[System: Live search triggered]")
    context = web_search(message)

  final_input = (
      f"Context:\n{context}\n\nQuestion: {message}" if context else message
  )

  kwargs = {
      "model": "gemini-3.1-flash-lite",
      "input": final_input,
      "system_instruction": SYSTEM_PROMPT,
  }
  if previous_id:
    kwargs["previous_interaction_id"] = previous_id

  res = client.interactions.create(**kwargs)
  return res.output_text, res.id