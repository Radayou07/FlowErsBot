-- ============================================
-- PREGNANCY APP DATABASE SCHEMA
-- ============================================
-- This schema documents the EXISTING database structure
-- shared between the website and Telegram bot.
-- Generated: 2026-10-21
-- ============================================

-- ============================================
-- CORE USER MANAGEMENT
-- ============================================

CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(36) PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255),
    role ENUM('mother', 'doctor', 'hospital_admin', 'family') DEFAULT 'mother',
    subscription_tier ENUM('free', 'basic', 'premium') DEFAULT 'free',
    subscription_status ENUM('active', 'expired', 'pending') DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS profiles (
    user_id VARCHAR(36) PRIMARY KEY,
    data JSON NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_consents (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id VARCHAR(36) NOT NULL,
    consent_version VARCHAR(32) NOT NULL,
    lang ENUM('en', 'kh'),
    accepted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_consents_user (user_id)
);

-- ============================================
-- MOTHER PROFILES
-- ============================================

CREATE TABLE IF NOT EXISTS mother_profiles (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL UNIQUE,
    full_name VARCHAR(255),
    date_of_birth DATE,
    phone VARCHAR(50),
    height_cm DECIMAL(5,2),
    pre_pregnancy_weight_kg DECIMAL(5,2),
    language_pref ENUM('en', 'kh') DEFAULT 'kh',
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pregnancy_profiles (
    id VARCHAR(36) PRIMARY KEY,
    mother_profile_id VARCHAR(36) NOT NULL UNIQUE,
    edd DATE,
    lmp DATE,
    gravida INT DEFAULT 1,
    para INT DEFAULT 0,
    current_week INT DEFAULT 4,
    trimester INT DEFAULT 1,
    FOREIGN KEY (mother_profile_id) REFERENCES mother_profiles(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS mother_medical_info (
    id VARCHAR(36) PRIMARY KEY,
    mother_profile_id VARCHAR(36) NOT NULL UNIQUE,
    blood_type VARCHAR(10),
    allergies TEXT,
    existing_conditions TEXT,
    current_medications TEXT,
    FOREIGN KEY (mother_profile_id) REFERENCES mother_profiles(id) ON DELETE CASCADE
);

-- ============================================
-- FAMILY & EMERGENCY CONTACTS
-- ============================================

CREATE TABLE IF NOT EXISTS family_members (
    id VARCHAR(36) PRIMARY KEY,
    mother_profile_id VARCHAR(36) NOT NULL,
    name VARCHAR(255),
    phone VARCHAR(50),
    relation VARCHAR(50),
    can_edit TINYINT(1) DEFAULT 0,
    FOREIGN KEY (mother_profile_id) REFERENCES mother_profiles(id) ON DELETE CASCADE,
    INDEX idx_family_mother (mother_profile_id)
);

CREATE TABLE IF NOT EXISTS emergency_contacts (
    id VARCHAR(36) PRIMARY KEY,
    mother_profile_id VARCHAR(36) NOT NULL,
    name VARCHAR(255),
    phone VARCHAR(50),
    relation VARCHAR(50),
    is_primary TINYINT(1) DEFAULT 0,
    FOREIGN KEY (mother_profile_id) REFERENCES mother_profiles(id) ON DELETE CASCADE,
    INDEX idx_emergency_mother (mother_profile_id)
);

-- ============================================
-- HEALTHCARE PROVIDERS
-- ============================================

CREATE TABLE IF NOT EXISTS doctor_profiles (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL UNIQUE,
    license_number VARCHAR(100),
    specialty VARCHAR(255),
    facility_name VARCHAR(255),
    phone VARCHAR(50),
    email VARCHAR(255),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS hospital_profiles (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL UNIQUE,
    name VARCHAR(255),
    address TEXT,
    contact_phone VARCHAR(50),
    email VARCHAR(255),
    subscription_tier ENUM('free', 'basic', 'premium') DEFAULT 'free',
    subscription_status ENUM('active', 'expired', 'pending') DEFAULT 'pending',
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- ============================================
-- APPOINTMENTS
-- ============================================

CREATE TABLE IF NOT EXISTS appointments (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    mother_profile_id VARCHAR(36),
    title VARCHAR(255),
    date DATE,
    time TIME,
    hospital VARCHAR(255),
    doctor VARCHAR(255),
    notes TEXT,
    type ENUM('ANC', 'Ultrasound', 'Blood Test', 'Vaccine', 'Specialist', 'Other'),
    reminder ENUM('1_week', '3_days', '1_day', 'same_day', 'custom', 'none') DEFAULT 'none',
    completed TINYINT(1) DEFAULT 0,
    image_attachment LONGTEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (mother_profile_id) REFERENCES mother_profiles(id) ON DELETE CASCADE,
    INDEX idx_appointments_user (user_id),
    INDEX idx_appointments_mother (mother_profile_id)
);

-- ============================================
-- MEDICAL RECORDS
-- ============================================

CREATE TABLE IF NOT EXISTS medical_records (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    mother_profile_id VARCHAR(36),
    title VARCHAR(255) NOT NULL,
    category ENUM('ultrasound', 'lab_test', 'prescription', 'vaccine', 'doctor_note', 'other') NOT NULL,
    date DATE,
    week INT,
    trimester INT,
    facility VARCHAR(255),
    doctor VARCHAR(255),
    notes TEXT,
    image_attachment LONGTEXT,
    status ENUM('Normal', 'Follow-up Needed', 'Completed', 'Pending') DEFAULT 'Normal',
    tags JSON,
    extracted_data JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (mother_profile_id) REFERENCES mother_profiles(id) ON DELETE CASCADE,
    INDEX idx_medical_records_user (user_id),
    INDEX idx_medical_records_mother (mother_profile_id)
);

-- ============================================
-- DAILY NOTES
-- ============================================

CREATE TABLE IF NOT EXISTS daily_notes (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    note_date DATE NOT NULL,
    task VARCHAR(255),
    note TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_daily_notes_user (user_id)
);

-- ============================================
-- SHARING & PERMISSIONS
-- ============================================

CREATE TABLE IF NOT EXISTS sharing_permissions (
    id VARCHAR(36) PRIMARY KEY,
    mother_profile_id VARCHAR(36) NOT NULL,
    doctor_profile_id VARCHAR(36),
    hospital_profile_id VARCHAR(36),
    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    record_types_granted JSON,
    FOREIGN KEY (mother_profile_id) REFERENCES mother_profiles(id) ON DELETE CASCADE,
    FOREIGN KEY (doctor_profile_id) REFERENCES doctor_profiles(id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_profile_id) REFERENCES hospital_profiles(id) ON DELETE CASCADE,
    INDEX idx_sharing_mother (mother_profile_id),
    INDEX idx_sharing_doctor (doctor_profile_id),
    INDEX idx_sharing_hospital (hospital_profile_id)
);

-- ============================================
-- ANALYTICS & FEATURE TRACKING
-- ============================================

CREATE TABLE IF NOT EXISTS feature_usage (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id VARCHAR(36),
    role ENUM('mother', 'doctor', 'hospital_admin', 'family'),
    session_id CHAR(32),
    feature_key VARCHAR(64) NOT NULL,
    action VARCHAR(32) NOT NULL,
    source ENUM('client', 'server') NOT NULL,
    lang ENUM('en', 'kh'),
    metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_feature_usage_user (user_id),
    INDEX idx_feature_usage_session (session_id),
    INDEX idx_feature_usage_feature (feature_key),
    INDEX idx_feature_usage_created (created_at)
);

-- ============================================
-- TELEGRAM BOT TABLES
-- ============================================

CREATE TABLE IF NOT EXISTS telegram_links (
    telegram_user_id BIGINT PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    mother_profile_id VARCHAR(36) NOT NULL UNIQUE,
    user_id VARCHAR(36) NOT NULL,
    linked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (mother_profile_id) REFERENCES mother_profiles(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reminders_sent (
    id INT PRIMARY KEY AUTO_INCREMENT,
    appointment_id VARCHAR(36) NOT NULL,
    kind VARCHAR(20) NOT NULL,
    sent_on DATE NOT NULL,
    UNIQUE KEY unique_reminder (appointment_id, kind, sent_on),
    FOREIGN KEY (appointment_id) REFERENCES appointments(id) ON DELETE CASCADE,
    INDEX idx_reminders_appointment (appointment_id)
);

-- ============================================
-- NOTES
-- ============================================
-- 1. All IDs are VARCHAR(36) UUID4 strings
-- 2. Bot reads from all tables but only WRITES to:
--    - telegram_links (linking users)
--    - medical_records (uploading photos)
--    - reminders_sent (tracking sent reminders)
-- 3. Phone numbers in mother_profiles may be in various formats
--    and need normalization (see phone.py)
-- 4. Language preference is 'kh' (Khmer) or 'en' (English)
-- 5. Medical record images stored as data URIs in image_attachment
-- 6. AI-extracted data stored as JSON in extracted_data column
