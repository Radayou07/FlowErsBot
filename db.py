import json
import os
import uuid
from datetime import datetime, date
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
import pymysql
import pymysql.cursors

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "flowers_db")

USER_LINKS_FILE = os.path.join(os.path.dirname(__file__), "user_links.json")  # legacy, no longer used

# In-memory demo store used if MySQL connection cannot be established
FALLBACK_DATA = {
    "users": {
        "usr-mother-001": {
            "id": "usr-mother-001",
            "email": "sophy@example.com",
            "role": "mother"
        }
    },
    "mother_profiles": {
        "moth-001": {
            "id": "moth-001",
            "user_id": "usr-mother-001",
            "full_name": "Sophy Cheat",
            "date_of_birth": "1998-05-15",
            "phone": "+855971234567",
            "height_cm": 158.00,
            "pre_pregnancy_weight_kg": 52.00,
            "language_pref": "kh"
        }
    },
    "pregnancy_profiles": {
        "preg-001": {
            "id": "preg-001",
            "mother_profile_id": "moth-001",
            "edd": "2026-11-20",
            "lmp": "2026-02-13",
            "gravida": 1,
            "para": 0,
            "current_week": 26,
            "trimester": 2
        }
    },
    "mother_medical_info": {
        "medinfo-001": {
            "id": "medinfo-001",
            "mother_profile_id": "moth-001",
            "blood_type": "O+",
            "allergies": "None / គ្មាន",
            "existing_conditions": "None / គ្មាន",
            "current_medications": "Prenatal Multivitamin, Iron Supplement"
        }
    },
    "emergency_contacts": [
        {
            "id": "emg-001",
            "mother_profile_id": "moth-001",
            "name": "Vannak Cheat",
            "phone": "+855129876543",
            "relation": "Husband / ស្វាមី",
            "is_primary": True
        }
    ],
    "appointments": [
        {
            "id": "apt-001",
            "user_id": "usr-mother-001",
            "mother_profile_id": "moth-001",
            "title": "Routine 2nd Trimester ANC Visit",
            "date": "2026-09-18",
            "time": "09:00:00",
            "hospital": "Calmette Hospital, Phnom Penh",
            "doctor": "Dr. Sophy (OB/GYN)",
            "type": "ANC",
            "notes": "Fetal growth check & Glucose screening test",
            "completed": False
        }
    ],
    "medical_records": [
        {
            "id": "rec-demo-001",
            "user_id": "usr-mother-001",
            "mother_profile_id": "moth-001",
            "title": "20-Week Anomaly Ultrasound",
            "category": "ultrasound",
            "date": "2026-07-28",
            "week": 20,
            "trimester": 2,
            "facility": "Calmette Hospital",
            "doctor": "Dr. Sophy",
            "notes": "Normal fetal anatomy and amniotic fluid volume. Fetal heart rate 142 bpm.",
            "status": "Normal",
            "extracted_data": {"fetal_weight_est_g": 350, "fhr_bpm": 142, "placenta": "Anterior normal"}
        }
    ]
}


def get_db_connection():
    """Attempts to connect to MySQL. Returns connection or None if unavailable."""
    try:
        conn = pymysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=3
        )
        return conn
    except Exception as e:
        # Fallback to local offline mode
        return None


# ---------------------------------------------------------------------------
# Telegram <-> Mother Profile Linking (telegram_links table, auto-created)
# ---------------------------------------------------------------------------

def _ensure_telegram_links_table():
    """Creates the telegram_links table if it doesn't exist yet."""
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS telegram_links (
                        telegram_id BIGINT PRIMARY KEY,
                        mother_profile_id VARCHAR(36) NOT NULL,
                        linked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_telegram_mother (mother_profile_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """)
                conn.commit()
        finally:
            conn.close()


# Auto-create on module load
_ensure_telegram_links_table()


def link_telegram_user(telegram_id: int | str, mother_profile_id: str):
    """Links a Telegram user ID to a mother profile in the database."""
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO telegram_links (telegram_id, mother_profile_id)
                       VALUES (%s, %s)
                       ON DUPLICATE KEY UPDATE mother_profile_id = VALUES(mother_profile_id), linked_at = CURRENT_TIMESTAMP""",
                    (int(telegram_id), mother_profile_id)
                )
                conn.commit()
        finally:
            conn.close()

# Aliases for convenience
link_telegram_to_mother = link_telegram_user


def get_linked_mother_id(telegram_id: int | str) -> Optional[str]:
    """Looks up the mother_profile_id linked to a Telegram user."""
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT mother_profile_id FROM telegram_links WHERE telegram_id = %s",
                    (int(telegram_id),)
                )
                row = cur.fetchone()
                if row:
                    return row["mother_profile_id"]
        finally:
            conn.close()
    return None

# Aliases for convenience
get_mother_id_by_telegram = get_linked_mother_id


def unlink_telegram_user(telegram_id: int | str):
    """Removes the Telegram-to-mother link from the database."""
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM telegram_links WHERE telegram_id = %s",
                    (int(telegram_id),)
                )
                conn.commit()
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Mother & Pregnancy Queries
# ---------------------------------------------------------------------------

def get_default_mother_id() -> str:
    """Returns the first real mother_profile_id from MySQL, or fallback 'moth-001'."""
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM mother_profiles LIMIT 1")
                row = cur.fetchone()
                if row:
                    return row["id"]
        finally:
            conn.close()
    return "moth-001"


def get_all_mother_profiles() -> List[Dict[str, Any]]:
    """Returns a list of available mother profiles for demo/selection."""
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                sql = """
                SELECT m.id, m.full_name, m.phone, m.language_pref,
                       p.current_week, p.trimester, p.edd
                FROM mother_profiles m
                LEFT JOIN pregnancy_profiles p ON m.id = p.mother_profile_id
                ORDER BY m.id DESC
                """
                cur.execute(sql)
                return cur.fetchall()
        finally:
            conn.close()

    # Fallback to demo profile
    res = []
    for m_id, m in FALLBACK_DATA["mother_profiles"].items():
        preg = list(FALLBACK_DATA["pregnancy_profiles"].values())[0]
        res.append({
            "id": m["id"],
            "full_name": m["full_name"],
            "phone": m["phone"],
            "language_pref": m["language_pref"],
            "current_week": preg["current_week"],
            "trimester": preg["trimester"],
            "edd": preg["edd"],
        })
    return res


def normalize_phone(p: str) -> str:
    """Normalizes phone number to base national digits for robust comparison."""
    if not p:
        return ""
    digits = "".join(filter(str.isdigit, p))
    # Remove international Cambodia prefix 855 if present
    if digits.startswith("855"):
        digits = digits[3:]
    # Remove leading 0 if present
    if digits.startswith("0"):
        digits = digits[1:]
    return digits


def find_mother_by_phone(phone_input: str) -> Optional[str]:
    """Matches raw phone number to mother_profile_id strictly from database."""
    norm_input = normalize_phone(phone_input)
    if not norm_input or len(norm_input) < 6:
        return None

    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id, phone FROM mother_profiles")
                for row in cur.fetchall():
                    raw_db_phone = row.get("phone", "") or ""
                    norm_db = normalize_phone(raw_db_phone)
                    if not norm_db:
                        continue
                    if norm_input == norm_db:
                        return row["id"]
                    if len(norm_input) >= 7 and len(norm_db) >= 7 and (norm_input.endswith(norm_db) or norm_db.endswith(norm_input)):
                        return row["id"]
                return None
        finally:
            conn.close()

    # In case MySQL is down, check fallback demo data only
    for m_id, m in FALLBACK_DATA["mother_profiles"].items():
        raw_db_phone = m.get("phone", "") or ""
        norm_db = normalize_phone(raw_db_phone)
        if norm_db and (norm_input == norm_db or (len(norm_input) >= 7 and len(norm_db) >= 7 and (norm_input.endswith(norm_db) or norm_db.endswith(norm_input)))):
            return m_id

    return None


def get_mother_full_profile(mother_profile_id: str) -> Optional[Dict[str, Any]]:
    """Fetches complete clinical snapshot for a mother."""
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                # 1. Mother + Pregnancy + Medical
                sql = """
                SELECT
                    m.id AS mother_id, m.user_id, m.full_name, m.phone, m.height_cm,
                    m.pre_pregnancy_weight_kg, m.language_pref, m.date_of_birth,
                    p.id AS pregnancy_id, p.edd, p.lmp, p.gravida, p.para, p.current_week, p.trimester,
                    med.blood_type, med.allergies, med.existing_conditions, med.current_medications
                FROM mother_profiles m
                LEFT JOIN pregnancy_profiles p ON m.id = p.mother_profile_id
                LEFT JOIN mother_medical_info med ON m.id = med.mother_profile_id
                WHERE m.id = %s
                """
                cur.execute(sql, (mother_profile_id,))
                profile = cur.fetchone()
                if not profile:
                    return None

                # 2. Primary Emergency Contact
                cur.execute(
                    "SELECT name, phone, relation FROM emergency_contacts WHERE mother_profile_id = %s ORDER BY is_primary DESC LIMIT 1",
                    (mother_profile_id,)
                )
                profile["emergency_contact"] = cur.fetchone()

                # 3. Next Upcoming Appointment (match by mother_profile_id OR user_id)
                today = date.today()
                cur.execute(
                    """
                    SELECT id, title, date, time, hospital, doctor, type, notes
                    FROM appointments
                    WHERE (mother_profile_id = %s OR user_id = %s) AND date >= %s AND completed = FALSE
                    ORDER BY date ASC, time ASC LIMIT 1
                    """,
                    (mother_profile_id, profile.get("user_id"), today)
                )
                profile["next_appointment"] = cur.fetchone()
                profile["name"] = profile.get("full_name") or "Mother"

                return profile
        finally:
            conn.close()

    # Fallback demo
    m = FALLBACK_DATA["mother_profiles"].get(mother_profile_id)
    if not m:
        return None
    preg = FALLBACK_DATA["pregnancy_profiles"].get("preg-001", {})
    med = FALLBACK_DATA["mother_medical_info"].get("medinfo-001", {})
    emg = FALLBACK_DATA["emergency_contacts"][0]
    apt = FALLBACK_DATA["appointments"][0]

    name_val = m.get("full_name") or m.get("name") or "Mother"
    return {
        "mother_id": m["id"],
        "user_id": m["user_id"],
        "full_name": name_val,
        "name": name_val,
        "phone": m["phone"],
        "height_cm": m["height_cm"],
        "pre_pregnancy_weight_kg": m["pre_pregnancy_weight_kg"],
        "language_pref": m["language_pref"],
        "date_of_birth": m["date_of_birth"],
        "pregnancy_id": preg.get("id"),
        "edd": preg.get("edd"),
        "lmp": preg.get("lmp"),
        "gravida": preg.get("gravida", 1),
        "para": preg.get("para", 0),
        "current_week": preg.get("current_week", 26),
        "trimester": preg.get("trimester", 2),
        "blood_type": med.get("blood_type", "O+"),
        "allergies": med.get("allergies", "None"),
        "existing_conditions": med.get("existing_conditions", "None"),
        "current_medications": med.get("current_medications", "Prenatal Vitamins"),
        "emergency_contact": emg,
        "next_appointment": apt
    }


def get_mother_appointments(mother_profile_id: str) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    if conn:
        try:
            # Resolve user_id so we also catch appointments created from the website
            # where mother_profile_id may be NULL but user_id is set
            profile = get_mother_full_profile(mother_profile_id)
            user_id = profile["user_id"] if profile else None

            with conn.cursor() as cur:
                if user_id:
                    cur.execute(
                        """
                        SELECT id, title, date, time, hospital, doctor, type, notes, completed
                        FROM appointments
                        WHERE mother_profile_id = %s OR user_id = %s
                        ORDER BY date ASC, time ASC
                        """,
                        (mother_profile_id, user_id)
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, title, date, time, hospital, doctor, type, notes, completed
                        FROM appointments
                        WHERE mother_profile_id = %s
                        ORDER BY date ASC, time ASC
                        """,
                        (mother_profile_id,)
                    )
                return cur.fetchall()
        finally:
            conn.close()

    return [a for a in FALLBACK_DATA["appointments"] if a["mother_profile_id"] == mother_profile_id]


def get_mother_medical_records(mother_profile_id: str) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, title, category, date, week, trimester, facility, doctor, notes, status, extracted_data, created_at
                    FROM medical_records
                    WHERE mother_profile_id = %s
                    ORDER BY date DESC, created_at DESC
                    LIMIT 10
                    """,
                    (mother_profile_id,)
                )
                return cur.fetchall()
        finally:
            conn.close()

    return [r for r in FALLBACK_DATA["medical_records"] if r.get("mother_profile_id") == mother_profile_id]


# ---------------------------------------------------------------------------
# Write / Insert Operations (Writing to website database)
# ---------------------------------------------------------------------------

def save_medical_record(
    mother_profile_id: str,
    title: str,
    category: str = "other",
    notes: Optional[str] = None,
    facility: Optional[str] = None,
    doctor: Optional[str] = None,
    date_str: Optional[str] = None,
    record_date: Optional[str] = None,
    week: Optional[int] = None,
    trimester: Optional[int] = None,
    status: str = "normal",
    extracted_data: Optional[dict] = None,
    image_attachment: Optional[str] = None
) -> bool:
    """Inserts a new record into medical_records table."""
    rec_id = f"rec-{uuid.uuid4().hex[:12]}"
    effective_date = date_str or record_date or datetime.now().strftime("%Y-%m-%d")
    effective_notes = notes or ""

    # Normalize status to match MySQL ENUM('Normal','Follow-up Needed','Completed','Pending')
    status_map = {
        "normal": "Normal",
        "abnormal": "Follow-up Needed",
        "review_required": "Follow-up Needed",
        "follow-up needed": "Follow-up Needed",
        "completed": "Completed",
        "pending": "Pending",
    }
    status = status_map.get(status.lower().strip(), "Normal") if status else "Normal"

    profile = get_mother_full_profile(mother_profile_id)
    user_id = profile["user_id"] if profile else None
    if not user_id:
        # Cannot insert without a valid user_id (FK constraint)
        print(f"[DB Error: No user_id found for mother_profile_id={mother_profile_id}]")
        return False
    if week is None and profile:
        week = profile.get("current_week", 26)
    if trimester is None and profile:
        trimester = profile.get("trimester", 2)

    extracted_json = json.dumps(extracted_data or {}, ensure_ascii=False)

    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                sql = """
                INSERT INTO medical_records (
                    id, user_id, mother_profile_id, title, category, date, week, trimester,
                    facility, doctor, notes, image_attachment, status, extracted_data
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                )
                """
                cur.execute(sql, (
                    rec_id, user_id, mother_profile_id, title, category, effective_date, week, trimester,
                    facility, doctor, effective_notes, image_attachment, status, extracted_json
                ))
            conn.commit()
            return True
        except Exception as e:
            print(f"[DB Error inserting medical record: {e}]")
            return False
        finally:
            conn.close()

    # Fallback save to memory
    FALLBACK_DATA["medical_records"].insert(0, {
        "id": rec_id,
        "user_id": user_id,
        "mother_profile_id": mother_profile_id,
        "title": title,
        "category": category,
        "date": effective_date,
        "week": week,
        "trimester": trimester,
        "facility": facility,
        "doctor": doctor,
        "notes": effective_notes,
        "status": status,
        "extracted_data": extracted_data or {},
        "image_attachment": image_attachment,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    return True


def update_mother_weight(mother_profile_id: str, weight_kg: float) -> bool:
    """Updates mother's pre_pregnancy_weight_kg and adds a log entry in medical_records."""
    profile = get_mother_full_profile(mother_profile_id)
    week = profile.get("current_week", 26) if profile else 26
    trimester = profile.get("trimester", 2) if profile else 2

    # 1. Update mother_profiles
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE mother_profiles SET pre_pregnancy_weight_kg = %s WHERE id = %s",
                    (weight_kg, mother_profile_id)
                )
            conn.commit()
        except Exception as e:
            print(f"[DB Error updating weight: {e}]")
        finally:
            conn.close()

    if mother_profile_id in FALLBACK_DATA["mother_profiles"]:
        FALLBACK_DATA["mother_profiles"][mother_profile_id]["pre_pregnancy_weight_kg"] = weight_kg

    # 2. Add medical record log
    return save_medical_record(
        mother_profile_id=mother_profile_id,
        title=f"Weight Check ({weight_kg} kg)",
        category="other",
        notes=f"Mother logged current weight: {weight_kg} kg during Week {week}.",
        week=week,
        trimester=trimester,
        status="Normal",
        extracted_data={"weight_kg": weight_kg, "logged_via": "telegram_bot"}
    )


# ---------------------------------------------------------------------------
# Gestational Milestones & Baby Growth Guide
# ---------------------------------------------------------------------------

BABY_MILESTONES = {
    "en": {
        4: ("Poppy Seed 🌰", "Embryo implantation in the uterus."),
        8: ("Raspberry 🍓", "Baby's heart is beating, tiny webbed fingers are forming."),
        12: ("Plum 🍑", "Trimester 1 finishes! Baby has vocal cords and tiny fingernails."),
        16: ("Avocado 🥑", "Baby can make facial expressions and perceive light."),
        20: ("Banana 🍌", "Halfway mark! You can feel baby's first kicks and movements."),
        24: ("Corn 🌽", "Baby's inner ear is fully formed; they can hear your voice and heartbeat!"),
        26: ("Eggplant 🍆 (~35cm, 760g)", "Baby's eyes are beginning to open and retina is developing. Lungs are practicing breathing movements."),
        28: ("Butternut Squash 🎃 (~1kg)", "Trimester 3 begins! Baby is actively blinking and gaining fat stores."),
        32: ("Pineapple 🍍 (~1.7kg)", "Baby is practicing sucking and swallowing. Bones are fully hardened except the skull."),
        36: ("Papaya 🍈 (~2.6kg)", "Lungs are almost fully mature. Baby is dropping lower into pelvis."),
        40: ("Watermelon 🍉 (~3.5kg)", "Full term! Your baby is ready to meet you! Happy birthing journey! 🎉")
    },
    "kh": {
        4: ("គ្រាប់អាភៀន 🌰", "អំប្រ៊ីយ៉ុងចាប់ផ្តើមតោងជាប់នឹងជញ្ជាំងស្បូន។"),
        8: ("ផ្លែប៊្លូបឺរី 🍓", "បេះដូងទារកចាប់ផ្តើមលោត ហើយម្រាមដៃតូចៗចាប់ផ្តើមលេចចេញ។"),
        12: ("ផ្លែព្រូន 🍑", "ចប់ត្រីមាសទី១! ទារកមានក្រចកដៃ និងប្រអប់សំឡេងរួចរាល់។"),
        16: ("ផ្លែបឺរ 🥑", "ទារកអាចបញ្ចេញទឹកមុខ និងចាប់ផ្តើមដឹងពន្លឺ។"),
        20: ("ផ្លែចេក 🍌", "ពាក់កណ្តាលផ្លូវហើយ! អ្នកម្តាយអាចចាប់ផ្តើមដឹងពីចលនាកូនធាក់។"),
        24: ("ផ្លែពោត 🌽", "ត្រចៀកកូនលូតលាស់ពេញលេញ អាចស្តាប់ឮសំឡេងបេះដូង និងសំឡេងអ្នកម្តាយ។"),
        26: ("ផ្លែត្រប់វែង 🍆 (ប្រវែង ~35cm, ទម្ងន់ ~760g)", "ភ្នែកទារកចាប់ផ្តើមបើក និងសួតចាប់ផ្តើមហាត់ប្រាណដកដង្ហើម។"),
        28: ("ផ្លែល្ពៅវែង 🎃 (~1kg)", "ឈានចូលត្រីមាសទី៣! ទារកអាចព្រិចភ្នែក និងចាប់ផ្តើមស្តុកជាតិខ្លាញ់ក្រោមស្បែក។"),
        32: ("ផ្លែម្នាស់ 🍍 (~1.7kg)", "ទារកហាត់ប្រាណជញ្ជក់ និងលេបទឹកភ្លោះ។ ឆ្អឹងរឹងមាំល្អ។"),
        36: ("ផ្លែល្ហុង 🍈 (~2.6kg)", "សួតលូតលាស់ជិតពេញលេញ ហើយកូនចាប់ផ្តើមបែរក្បាលចុះក្រោម។"),
        40: ("ផ្លែឪឡឹក 🍉 (~3.5kg)", "គ្រប់ខែហើយ! ទារកត្រៀមខ្លួនជួបមុខអ្នកម្តាយហើយ! 🎉")
    }
}


def get_baby_milestone(week: int, lang: str = "en") -> tuple[str, str]:
    """Returns (fruit_size, milestone_description) for a given week."""
    milestones = BABY_MILESTONES.get(lang, BABY_MILESTONES["en"])
    closest_week = min(milestones.keys(), key=lambda w: abs(w - week))
    return milestones[closest_week]
