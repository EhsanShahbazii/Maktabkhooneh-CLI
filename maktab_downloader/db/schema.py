"""SQLite Database Schema Definitions for Maktabkhooneh Data."""

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

-- Courses Table (Supports both enrolled courses and public catalog courses)
CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY,
    slug TEXT,
    title TEXT NOT NULL,
    slug_id INTEGER,
    real_price INTEGER,
    discounted_price INTEGER,
    discount REAL DEFAULT 0.0,
    image_url TEXT,
    units_count INTEGER DEFAULT 0,
    required_hours TEXT,
    no_of_students INTEGER DEFAULT 0,
    
    -- Organization info
    organization_id INTEGER,
    organization_slug TEXT,
    organization_name TEXT,
    organization_image_url TEXT,
    organization_obj_type TEXT,
    
    -- Publisher info
    publisher_id INTEGER,
    publisher_slug TEXT,
    publisher_name TEXT,
    publisher_image_url TEXT,
    
    -- Specifics / Progress / Enrollment Status
    specifics_type TEXT,
    avg_rating REAL DEFAULT 0.0,
    content_grouping_name TEXT,
    content_rate_count INTEGER DEFAULT 0,
    certification BOOLEAN DEFAULT 0,
    carousel_discount TEXT,
    has_subtitle BOOLEAN DEFAULT 0,
    is_last_version BOOLEAN DEFAULT 1,
    is_enrolled BOOLEAN DEFAULT 0,
    call_to_action TEXT,
    call_to_action_text TEXT,
    
    progress_id INTEGER,
    score REAL DEFAULT 0.0,
    access_level TEXT,
    progress REAL DEFAULT 0.0,
    access_level_text TEXT,
    full_access_expiry_date TEXT,
    can_rate BOOLEAN DEFAULT 0,
    has_rate BOOLEAN DEFAULT 0,
    obj_type TEXT DEFAULT 'course',
    
    -- Outline summary fields
    student_effort_seconds INTEGER DEFAULT 0,
    chapters_count INTEGER DEFAULT 0,
    outline_synced BOOLEAN DEFAULT 0,
    
    -- Public Landing Page Rich Metadata
    level TEXT,
    version_number INTEGER DEFAULT 1,
    course_effort_time TEXT,
    content_hours REAL DEFAULT 0,
    description_html TEXT,
    prerequisite_description TEXT,
    learning_goals_json TEXT,
    topics_json TEXT,
    categories_json TEXT,
    preview_video_hq TEXT,
    preview_video_lq TEXT,
    preview_caption TEXT,
    published_date TEXT,
    latest_update_date TEXT,
    landing_synced BOOLEAN DEFAULT 0,
    
    -- Telegram Upload Tracking
    telegram_message_id INTEGER,
    telegram_uploaded BOOLEAN DEFAULT 0,
    telegram_uploaded_at TIMESTAMP,

    -- Full Raw Payload Archive
    raw_json TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Teachers Table
CREATE TABLE IF NOT EXISTS teachers (
    id INTEGER PRIMARY KEY,
    slug TEXT,
    full_name TEXT,
    display_name TEXT,
    headline TEXT,
    image_url TEXT,
    description TEXT,
    course_count INTEGER DEFAULT 0,
    student_count INTEGER DEFAULT 0,
    landing_view BOOLEAN DEFAULT 0,
    obj_type TEXT DEFAULT 'teacher',
    raw_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Course Teachers (Many-to-Many)
CREATE TABLE IF NOT EXISTS course_teachers (
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
    PRIMARY KEY (course_id, teacher_id)
);

-- Chapters Table
CREATE TABLE IF NOT EXISTS chapters (
    id INTEGER PRIMARY KEY,
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    slug TEXT,
    slug_id INTEGER,
    title TEXT NOT NULL,
    order_num INTEGER DEFAULT 0,
    worth TEXT,
    units_count INTEGER DEFAULT 0,
    student_effort_seconds INTEGER DEFAULT 0,
    raw_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Units Table
CREATE TABLE IF NOT EXISTS units (
    id INTEGER PRIMARY KEY,
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    chapter_id INTEGER REFERENCES chapters(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    slug TEXT,
    type INTEGER DEFAULT 1,
    type_display TEXT,
    chapter_title TEXT,
    course_title TEXT,
    order_num INTEGER DEFAULT 0,
    description TEXT,
    student_effort_seconds INTEGER DEFAULT 0,
    file_id TEXT,
    duration INTEGER DEFAULT 0,
    has_caption BOOLEAN DEFAULT 0,
    caption_file TEXT,
    poster TEXT,
    worth TEXT,
    threshold TEXT,
    is_required BOOLEAN DEFAULT 0,
    has_submit_access BOOLEAN DEFAULT 0,
    project_json TEXT,
    quiz_json TEXT,
    media_point REAL DEFAULT 0.0,
    is_completed BOOLEAN DEFAULT 0,
    likes INTEGER DEFAULT 0,
    dislikes INTEGER DEFAULT 0,
    user_rating REAL DEFAULT 0.0,
    view_access INTEGER DEFAULT 0,
    submit_access INTEGER DEFAULT 0,
    courseflow_access_level INTEGER DEFAULT 0,
    
    -- Sync Status Tracking
    sync_status TEXT DEFAULT 'pending', -- 'pending', 'synced', 'error'
    error_message TEXT,
    raw_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Resources / Videos Table
CREATE TABLE IF NOT EXISTS resources (
    id INTEGER PRIMARY KEY,
    unit_id INTEGER NOT NULL REFERENCES units(id) ON DELETE CASCADE,
    course_id INTEGER,
    chapter_id INTEGER,
    type INTEGER DEFAULT 1,
    type_display TEXT,
    quality TEXT NOT NULL, -- e.g. '1080p', '720p', '480p'
    quality_display TEXT,
    title TEXT,
    display_title TEXT,
    download_url TEXT NOT NULL,
    size_mb REAL,
    total_bytes INTEGER DEFAULT 0,
    resolution_height INTEGER,
    is_downloadable BOOLEAN DEFAULT 0,
    file_extension TEXT,
    bitrate_kbps INTEGER,
    codec TEXT,
    order_num INTEGER DEFAULT 0,
    
    -- Download tracking
    download_status TEXT DEFAULT 'not_downloaded', -- 'not_downloaded', 'downloading', 'completed', 'failed'
    local_file_path TEXT,
    downloaded_bytes INTEGER DEFAULT 0,
    downloaded_at TIMESTAMP,
    error_message TEXT,
    raw_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Reviews Table
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY,
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    user_id INTEGER,
    user_first_name TEXT,
    user_last_name TEXT,
    user_full_name TEXT,
    user_image_url TEXT,
    rate INTEGER DEFAULT 5,
    review_description TEXT,
    review_reply TEXT,
    created_date TIMESTAMP,
    modified_date TIMESTAMP,
    raw_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Unit Teachers (Many-to-Many)
CREATE TABLE IF NOT EXISTS unit_teachers (
    unit_id INTEGER NOT NULL REFERENCES units(id) ON DELETE CASCADE,
    teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
    PRIMARY KEY (unit_id, teacher_id)
);

-- Performance Indexes
CREATE INDEX IF NOT EXISTS idx_courses_is_enrolled ON courses(is_enrolled);
CREATE INDEX IF NOT EXISTS idx_chapters_course_id ON chapters(course_id);
CREATE INDEX IF NOT EXISTS idx_units_course_id ON units(course_id);
CREATE INDEX IF NOT EXISTS idx_units_chapter_id ON units(chapter_id);
CREATE INDEX IF NOT EXISTS idx_units_sync_status ON units(sync_status);
CREATE INDEX IF NOT EXISTS idx_resources_unit_id ON resources(unit_id);
CREATE INDEX IF NOT EXISTS idx_resources_quality ON resources(quality);
CREATE INDEX IF NOT EXISTS idx_resources_download_status ON resources(download_status);
CREATE INDEX IF NOT EXISTS idx_course_teachers_course ON course_teachers(course_id);
CREATE INDEX IF NOT EXISTS idx_reviews_course_id ON reviews(course_id);
CREATE INDEX IF NOT EXISTS idx_reviews_user_id ON reviews(user_id);
CREATE INDEX IF NOT EXISTS idx_reviews_rate ON reviews(rate);
"""
