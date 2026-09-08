-- ============================================================================
-- FLOWER — Digital Maternal Health Passport & Clinical Doctor Portal
-- Complete MySQL Database Schema (10 Core Tables + Sharing & Security)
-- Optimized for Khmer Unicode (utf8mb4) and Clinical Workflows
-- ============================================================================

CREATE DATABASE IF NOT EXISTS flowers_db
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE flowers_db;

-- ----------------------------------------------------------------------------
-- 1. USERS TABLE
-- Authentication and identity for all platform roles
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(36) PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('mother', 'doctor', 'hospital_admin', 'family') NOT NULL DEFAULT 'mother',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_users_email (email),
    INDEX idx_users_role (role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- 2. MOTHER PROFILES TABLE
-- Personal demographic info for pregnant mothers
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mother_profiles (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL UNIQUE,
    full_name VARCHAR(255) NOT NULL,
    date_of_birth DATE NULL,
    phone VARCHAR(50) NULL,
    height_cm DECIMAL(5,2) NULL,
    pre_pregnancy_weight_kg DECIMAL(5,2) NULL,
    language_pref ENUM('en', 'kh') DEFAULT 'kh',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_mother_profiles_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- 3. PREGNANCY PROFILES TABLE
-- Gestational tracking: EDD, LMP, Gravida, Para, current week, and trimester
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pregnancy_profiles (
    id VARCHAR(36) PRIMARY KEY,
    mother_profile_id VARCHAR(36) NOT NULL UNIQUE,
    edd DATE NOT NULL,
    lmp DATE NULL,
    gravida INT DEFAULT 1,
    para INT DEFAULT 0,
    current_week INT DEFAULT 4,
    trimester INT DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (mother_profile_id) REFERENCES mother_profiles(id) ON DELETE CASCADE,
    INDEX idx_pregnancy_mother (mother_profile_id),
    INDEX idx_pregnancy_trimester (trimester)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- 4. MOTHER MEDICAL INFO TABLE
-- Blood type, allergies, pre-existing conditions, and ongoing medications
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mother_medical_info (
    id VARCHAR(36) PRIMARY KEY,
    mother_profile_id VARCHAR(36) NOT NULL UNIQUE,
    blood_type VARCHAR(10) NULL,
    allergies TEXT NULL,
    existing_conditions TEXT NULL,
    current_medications TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (mother_profile_id) REFERENCES mother_profiles(id) ON DELETE CASCADE,
    INDEX idx_medical_info_mother (mother_profile_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- 5. EMERGENCY CONTACTS TABLE
-- Emergency next-of-kin contacts with quick-dial support
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS emergency_contacts (
    id VARCHAR(36) PRIMARY KEY,
    mother_profile_id VARCHAR(36) NOT NULL,
    name VARCHAR(255) NOT NULL,
    phone VARCHAR(50) NOT NULL,
    relation VARCHAR(50) NULL,
    is_primary BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (mother_profile_id) REFERENCES mother_profiles(id) ON DELETE CASCADE,
    INDEX idx_emergency_mother (mother_profile_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- 6. MEDICAL RECORDS TABLE (Digital Document Vault)
-- Scanned ultrasound images, lab tests, prescriptions, vaccines, and doctor notes
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS medical_records (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    mother_profile_id VARCHAR(36) NULL,
    title VARCHAR(255) NOT NULL,
    category ENUM('ultrasound', 'lab_test', 'prescription', 'vaccine', 'doctor_note', 'other') NOT NULL,
    date DATE NULL,
    week INT NULL,
    trimester INT NULL,
    facility VARCHAR(255) NULL,
    doctor VARCHAR(255) NULL,
    notes TEXT NULL,
    image_attachment LONGTEXT NULL,
    status ENUM('Normal', 'Follow-up Needed', 'Completed', 'Pending') DEFAULT 'Normal',
    tags JSON NULL,
    extracted_data JSON NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (mother_profile_id) REFERENCES mother_profiles(id) ON DELETE SET NULL,
    INDEX idx_records_user (user_id),
    INDEX idx_records_mother (mother_profile_id),
    INDEX idx_records_category (category),
    INDEX idx_records_trimester (trimester),
    INDEX idx_records_date (date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- 7. APPOINTMENTS TABLE
-- Antenatal care (ANC) visits, ultrasound appointments, and reminders
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS appointments (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    mother_profile_id VARCHAR(36) NULL,
    title VARCHAR(255) NULL,
    date DATE NOT NULL,
    time TIME NULL,
    hospital VARCHAR(255) NOT NULL,
    doctor VARCHAR(255) NULL,
    notes TEXT NULL,
    type ENUM('ANC', 'Ultrasound', 'Blood Test', 'Vaccine', 'Specialist', 'Other') DEFAULT 'ANC',
    reminder ENUM('1_week', '3_days', '1_day', 'same_day', 'custom', 'none') DEFAULT 'none',
    completed BOOLEAN DEFAULT FALSE,
    image_attachment LONGTEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (mother_profile_id) REFERENCES mother_profiles(id) ON DELETE SET NULL,
    INDEX idx_appts_user (user_id),
    INDEX idx_appts_mother (mother_profile_id),
    INDEX idx_appts_date (date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- 8. DOCTOR PROFILES TABLE
-- Healthcare provider profile with specialty, facility, and medical license
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS doctor_profiles (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL UNIQUE,
    license_number VARCHAR(100) NOT NULL,
    specialty VARCHAR(255) NOT NULL,
    facility_name VARCHAR(255) NOT NULL,
    phone VARCHAR(50) NULL,
    email VARCHAR(255) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_doctor_license (license_number)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- 9. HOSPITAL PROFILES TABLE
-- Hospital/Clinic administration and SaaS subscription management
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hospital_profiles (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    address TEXT NULL,
    contact_phone VARCHAR(50) NULL,
    email VARCHAR(255) NULL,
    subscription_tier ENUM('free', 'basic', 'premium') DEFAULT 'free',
    subscription_status ENUM('active', 'expired', 'pending') DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- 10. SHARING PERMISSIONS TABLE
-- Granular record access control granted by Mother to Doctor / Clinic
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sharing_permissions (
    id VARCHAR(36) PRIMARY KEY,
    mother_profile_id VARCHAR(36) NOT NULL,
    doctor_profile_id VARCHAR(36) NULL,
    hospital_profile_id VARCHAR(36) NULL,
    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NULL,
    record_types_granted JSON NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (mother_profile_id) REFERENCES mother_profiles(id) ON DELETE CASCADE,
    FOREIGN KEY (doctor_profile_id) REFERENCES doctor_profiles(id) ON DELETE SET NULL,
    FOREIGN KEY (hospital_profile_id) REFERENCES hospital_profiles(id) ON DELETE SET NULL,
    INDEX idx_share_mother (mother_profile_id),
    INDEX idx_share_doctor (doctor_profile_id),
    CONSTRAINT chk_target_exists CHECK (doctor_profile_id IS NOT NULL OR hospital_profile_id IS NOT NULL)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- 11. QR SHARE TOKENS (Track 1 Planned Feature)
-- Temporary QR / access codes generated by mother for quick scan-to-share
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS qr_share_tokens (
    id VARCHAR(36) PRIMARY KEY,
    mother_profile_id VARCHAR(36) NOT NULL,
    token_code VARCHAR(64) UNIQUE NOT NULL,
    record_categories JSON NULL,
    expires_at TIMESTAMP NOT NULL,
    used_at TIMESTAMP NULL,
    used_by_doctor_id VARCHAR(36) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (mother_profile_id) REFERENCES mother_profiles(id) ON DELETE CASCADE,
    FOREIGN KEY (used_by_doctor_id) REFERENCES doctor_profiles(id) ON DELETE SET NULL,
    INDEX idx_qr_tokens_code (token_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- 12. FAMILY MEMBERS TABLE (Track 2 Planned Feature)
-- Companion access for partner / family members
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS family_members (
    id VARCHAR(36) PRIMARY KEY,
    mother_profile_id VARCHAR(36) NOT NULL,
    user_id VARCHAR(36) NULL,
    name VARCHAR(255) NOT NULL,
    phone VARCHAR(50) NULL,
    relation VARCHAR(50) NULL,
    can_edit BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (mother_profile_id) REFERENCES mother_profiles(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
    INDEX idx_family_mother (mother_profile_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- DEMO SEED DATA (Ready-to-use for Testing & Demonstrations)
-- ============================================================================

-- Password for all demo accounts: 1234 ($2a$10$7vN1K6e3k4v1a/kY4I... pre-hashed)
INSERT IGNORE INTO users (id, email, password_hash, role) VALUES
('usr-mother-001', 'sophy@example.com', '$2a$10$7R0Zq8tXN04e937dY7B08uF/eP6j1gCsl0eYv2Z5v6F7l1R5n0e5W', 'mother'),
('usr-doctor-001', 'dr.sophy@hospital.com', '$2a$10$7R0Zq8tXN04e937dY7B08uF/eP6j1gCsl0eYv2Z5v6F7l1R5n0e5W', 'doctor'),
('usr-admin-001', 'admin@calmette.gov.kh', '$2a$10$7R0Zq8tXN04e937dY7B08uF/eP6j1gCsl0eYv2Z5v6F7l1R5n0e5W', 'hospital_admin');

-- Mother Profile
INSERT IGNORE INTO mother_profiles (id, user_id, full_name, date_of_birth, phone, height_cm, pre_pregnancy_weight_kg, language_pref) VALUES
('moth-001', 'usr-mother-001', 'Sophy Cheat', '1998-05-15', '+855-97-123-4567', 158.00, 52.00, 'kh');

-- Pregnancy Profile (Week 26, Trimester 2)
INSERT IGNORE INTO pregnancy_profiles (id, mother_profile_id, edd, lmp, gravida, para, current_week, trimester) VALUES
('preg-001', 'moth-001', '2026-11-20', '2026-02-13', 1, 0, 26, 2);

-- Mother Medical Info
INSERT IGNORE INTO mother_medical_info (id, mother_profile_id, blood_type, allergies, existing_conditions, current_medications) VALUES
('medinfo-001', 'moth-001', 'O+', 'None / គ្មាន', 'None / គ្មាន', 'Prenatal Multivitamin, Iron Supplement');

-- Emergency Contact
INSERT IGNORE INTO emergency_contacts (id, mother_profile_id, name, phone, relation, is_primary) VALUES
('emg-001', 'moth-001', 'Vannak Cheat', '+855-12-987-6543', 'Husband / ស្វាមី', TRUE);

-- Doctor Profile
INSERT IGNORE INTO doctor_profiles (id, user_id, license_number, specialty, facility_name, phone, email) VALUES
('doc-001', 'usr-doctor-001', 'DOC-KH-2024-8891', 'Obstetrics & Gynecology', 'Calmette Hospital, Phnom Penh', '+855-23-426-948', 'dr.sophy@hospital.com');

-- Hospital Profile
INSERT IGNORE INTO hospital_profiles (id, user_id, name, address, contact_phone, email, subscription_tier, subscription_status) VALUES
('hosp-001', 'usr-admin-001', 'Calmette Hospital', 'No. 3, Monivong Blvd, Phnom Penh, Cambodia', '+855-23-426-948', 'admin@calmette.gov.kh', 'premium', 'active');

-- Sharing Permission (Mother shares all 5 categories with Dr. Sophy)
INSERT IGNORE INTO sharing_permissions (id, mother_profile_id, doctor_profile_id, record_types_granted) VALUES
('perm-001', 'moth-001', 'doc-001', '["ultrasound", "lab_test", "prescription", "vaccine", "doctor_note"]');
