import asyncio
import json
import pytest
from pathlib import Path

from maktab_downloader.db.database import Database
from maktab_downloader.db.repository import Repository
from maktab_downloader.utils.helpers import sanitize_filename, format_bytes, format_duration


SAMPLE_COURSE = {
    "id": 18067,
    "slug": "آموزش-کتابخانه-beautifulsoup۴-وب-اسکرپینگ",
    "title": "آموزش جامع و پیشرفته کتابخانه Beautiful Soup 4 در پایتون",
    "slug_id": 18067,
    "prices": {
        "real": 599000,
        "discounted": 599000
    },
    "discount": 0.0,
    "image_url": "https://media1.maktabkhooneh.org/courses/poster.webp",
    "units_count": 0,
    "required_hours": "0:00",
    "no_of_students": 0,
    "organization": {
        "slug": "مکتبخونه",
        "name": "مکتب‌خونه",
        "image_url": "https://media1.maktabkhooneh.org/logoo.png",
        "id": 2,
        "obj_type": "organization"
    },
    "teachers": [
        {
            "slug": "احسان-شهبازی-18602",
            "full_name": "احسان شهبازی",
            "teacher_id": 18602,
            "landing_view": False,
            "id": 18602,
            "obj_type": "teacher"
        }
    ],
    "specifics": {
        "type": "PLUS",
        "avg_rating": 0.0,
        "content_grouping": {
            "index": "contentGroup1",
            "name": "Plus Courses"
        },
        "content_rate_count": 0,
        "certification": True,
        "carousel_discount": "",
        "has_subtitle": False,
        "is_last_version": True,
        "labels": {
            "main": None,
            "business": None
        },
        "course_progress": {
            "progress_id": 9404795,
            "score": 0.0,
            "access_level": "CONTENT",
            "progress": 0.0,
            "access_level_text": "دسترسی به محتوا",
            "full_access_expiry_date": None
        },
        "can_rate": True,
        "has_rate": False
    },
    "obj_type": "course"
}

SAMPLE_OUTLINE = {
    "slug_id": 15822,
    "title": "آموزش مقدماتی پلتفرم بله",
    "student_effort_seconds": 360000,
    "teachers": [
        {
            "id": 25498,
            "slug": "رهام-شاکر",
            "display_name": "ثنا شریفیان"
        }
    ],
    "chapters_count": 1,
    "chapters": [
        {
            "id": 43054,
            "slug": "آموزش-مقدماتی-پلتفرم-بله",
            "slug_id": 43054,
            "title": "آموزش مقدماتی پلتفرم بله",
            "order": 1,
            "worth": "0.00",
            "units": [
                {
                    "id": 216341,
                    "title": "شروع کن حتی به غلط!",
                    "slug": "شروع-کن-حتی-غلط",
                    "type": 1,
                    "type_display": "Video Lecture",
                    "order": 1,
                    "student_effort_seconds": 168,
                    "view_access": 0
                },
                {
                    "id": 216352,
                    "title": "چطور در مجله دیده بشیم؟",
                    "slug": "چطور-مجله-دیده-بشیم",
                    "type": 1,
                    "type_display": "Video Lecture",
                    "order": 5,
                    "student_effort_seconds": 127,
                    "view_access": 2
                }
            ],
            "units_count": 2,
            "student_effort_seconds": 1833
        }
    ]
}

SAMPLE_UNIT = {
    "id": 216352,
    "title": "چطور در مجله دیده بشیم؟",
    "slug": "چطور-مجله-دیده-بشیم",
    "type": 1,
    "type_display": "Video Lecture",
    "chapter_title": "آموزش مقدماتی پلتفرم بله",
    "course_title": "آموزش مقدماتی پلتفرم بله",
    "course_slug_id": 15822,
    "course_id": 15822,
    "chapter_id": 43054,
    "order": 5,
    "description": "توضیحات ویدیوی پنجم",
    "student_effort_seconds": 127,
    "file_id": "62142694516302221781959154",
    "duration": 127,
    "has_caption": False,
    "caption_file": "https://maktabkhooneh.org/caption/?file=",
    "poster": "https://cdn.maktabkhooneh.org/images/poster.jpg",
    "worth": None,
    "threshold": None,
    "is_required": False,
    "has_submit_access": True,
    "project": None,
    "quiz": None,
    "media": {
        "point": 3.0
    },
    "resources": [
        {
            "id": 17763408,
            "type": 1,
            "type_display": "Video (Low Quality)",
            "quality": "1080p",
            "quality_display": "Full HD (1080p)",
            "title": "video 1080p",
            "display_title": "دانلود ویدیو Full HD (1080p)",
            "download_url": "https://cdn.maktabkhooneh.org/videos/1080p.mp4",
            "size_mb": 45.2,
            "resolution_height": 1080,
            "is_downloadable": False,
            "file_extension": None,
            "bitrate_kbps": None,
            "codec": "",
            "order": 0
        },
        {
            "id": 17763407,
            "type": 1,
            "type_display": "Video (Low Quality)",
            "quality": "720p",
            "quality_display": "HD (720p)",
            "title": "video 720p",
            "display_title": "دانلود ویدیو HD (720p)",
            "download_url": "https://cdn.maktabkhooneh.org/videos/720p.mp4",
            "size_mb": 22.1,
            "resolution_height": 720,
            "is_downloadable": False,
            "file_extension": None,
            "bitrate_kbps": None,
            "codec": "",
            "order": 1
        }
    ],
    "navigation": {
        "previous": {
            "id": 216351,
            "title": "نحوه آپلود محتوا در کانال بله",
            "type": 1,
            "type_display": "Video Lecture"
        },
        "next": {
            "id": 216354,
            "title": "200 ممبر اولیه رایگان",
            "type": 1,
            "type_display": "Video Lecture"
        }
    },
    "is_completed": False,
    "engagement": {
        "likes": 9,
        "dislikes": 0,
        "user_rating": 0
    },
    "view_access": 2,
    "submit_access": 1,
    "teacher_ids": [
        25498
    ],
    "courseflow_access_level": 45
}

SAMPLE_CATALOG_COURSE = {
    "id": 11217,
    "slug": "آموزش-ساخت-rest-api",
    "title": "آموزش جامع ساخت REST API حرفهای با پایتون، فلاسک (Flask) و داکر(Docker)",
    "slug_id": 11217,
    "prices": {
        "real": 599000,
        "discounted": 239600
    },
    "discount": 60.0,
    "image_url": "https://media1.maktabkhooneh.org/courses/restapi.webp",
    "units_count": 115,
    "required_hours": 12,
    "no_of_students": 33,
    "organization": {
        "slug": "udemy",
        "name": "Udemy",
        "image_url": "https://media1.maktabkhooneh.org/org.png",
        "id": 133,
        "obj_type": "organization"
    },
    "teachers": [
        {
            "slug": "jose-salvatierra",
            "full_name": "Jose Salvatierra",
            "teacher_id": 27508,
            "landing_view": True,
            "id": 27508,
            "obj_type": "teacher"
        }
    ],
    "specifics": {
        "type": "PLUS",
        "avg_rating": 0.0,
        "content_grouping": {
            "index": "contentGroup1",
            "name": "Plus Courses"
        },
        "content_rate_count": 0,
        "certification": True,
        "carousel_discount": "",
        "has_subtitle": True,
        "is_last_version": True
    },
    "obj_type": "course"
}

SAMPLE_LANDING = {
    "id": 11217,
    "slug": "آموزش-ساخت-rest-api",
    "title": "آموزش جامع ساخت REST API حرفهای با پایتون، فلاسک (Flask) و داکر(Docker)",
    "level": "مقدماتی تا پیشرفته",
    "version_number": 1,
    "course_effort_time": "12 ساعت",
    "required_hours": 12,
    "content_hours": 12,
    "description": "<p>آموزش حرفه‌ای ساخت REST API</p>",
    "prerequisite_description": "<p>پیش‌نیاز ساده پایتون</p>",
    "learning_goals": ["ساخت REST APIهای امن", "کار با Docker"],
    "topics": [{"id": 20, "title": "آموزش برنامهنویسی بک اند", "slug": "backend-programming"}],
    "publisher": {"organization_id": 133, "name": "Udemy", "slug": "udemy"},
    "video_url": {
        "lq": "https://cdn.maktabkhooneh.org/videos/480p.mp4",
        "hq": "https://cdn.maktabkhooneh.org/videos/720p.mp4",
        "caption": "/api/v1/general/download/caption.vtt"
    }
}

SAMPLE_REVIEW = {
    "id": 2725530,
    "user": {
        "id": 4559828,
        "first_name": "Armin",
        "last_name": "Inanloo",
        "full_name": "Armin Inanloo",
        "image_url": "https://media.org/avatar.jpg"
    },
    "rate": 5,
    "review_description": "بسیار عالی و خوب مطالب را توضیح میدادند",
    "review_reply": "ممنون از نظر شما",
    "created_date": "2026-08-31T17:09:06.328471",
    "modified_date": "2026-08-31T17:09:32.134589"
}


def test_sanitize_filename():
    assert sanitize_filename("آموزش جامع: پایتون / بخش ۱*?") == "آموزش جامع_ پایتون _ بخش ۱"
    assert sanitize_filename("Hello / World : Test * < > | ?") == "Hello _ World _ Test"


def test_helpers_formatters():
    assert format_bytes(1024 * 1024 * 50) == "50.00 MB"
    assert format_duration(127) == "02:07"
    assert format_duration(3665) == "01:01:05"


@pytest.mark.asyncio
async def test_database_and_repository_pipeline(tmp_path):
    test_db_path = tmp_path / "test_maktab.db"
    db = Database(test_db_path)
    await db.init_db()
    repo = Repository(db)

    # 1. Upsert course
    async with db.connection() as conn:
        cid = await repo.upsert_course(conn, SAMPLE_COURSE, is_enrolled=True)
        await conn.commit()
    assert cid == 18067

    # 2. Upsert outline for another course (15822)
    async with db.connection() as conn:
        await repo.upsert_course(conn, {
            "id": 15822,
            "title": "آموزش مقدماتی پلتفرم بله",
            "slug": "آموزش-مقدماتی-پلتفرم-بله",
        }, is_enrolled=True)
        await repo.upsert_outline(conn, 15822, SAMPLE_OUTLINE)
        await conn.commit()

    # 3. Upsert unit details
    async with db.connection() as conn:
        await repo.upsert_unit_detail(conn, SAMPLE_UNIT)
        await conn.commit()

    # 4. Upsert public catalog course (11217)
    async with db.connection() as conn:
        await repo.upsert_course(conn, SAMPLE_CATALOG_COURSE, is_enrolled=False)
        await repo.upsert_course_landing(conn, 11217, SAMPLE_LANDING)
        await repo.update_course_actions(conn, 11217, {
            "actions": {"call_to_action": "BusinessEnroll", "call_to_action_text": "ثبتنام"},
            "enrollment": {"access_level": 0}
        })
        await repo.upsert_review(conn, 11217, SAMPLE_REVIEW)
        await conn.commit()

    # 5. Verify data integrity
    courses = await repo.get_all_courses()
    assert len(courses) == 3

    enrolled = await repo.get_all_courses(enrolled_only=True)
    assert len(enrolled) == 2

    # Check landing details
    c11217 = await repo.get_course_by_id(11217)
    assert c11217["publisher_name"] == "Udemy"
    assert c11217["level"] == "مقدماتی تا پیشرفته"
    assert "ساخت REST APIهای امن" in c11217["learning_goals_json"]

    # Check reviews
    reviews = await repo.get_reviews_for_course(11217)
    assert len(reviews) == 1
    assert reviews[0]["rate"] == 5
    assert reviews[0]["user_full_name"] == "Armin Inanloo"

    # 6. Test Enrollment
    await repo.mark_course_enrolled(11217, True)
    enrolled_after = await repo.get_all_courses(enrolled_only=True)
    assert len(enrolled_after) == 3

    # 7. Test get_downloadable_resources quality resolution
    res_1080p = await repo.get_downloadable_resources(course_id=15822, preferred_quality="1080p")
    assert len(res_1080p) == 1
    assert res_1080p[0]["quality"] == "1080p"
    assert res_1080p[0]["unit_id"] == 216352

    # 8. Test size calculation and updates
    await repo.update_resource_size(17763408, 47432819)
    course_sizes = await repo.get_course_size_stats(course_id=15822, preferred_quality="1080p")
    assert course_sizes["total_items"] == 1
    assert course_sizes["total_bytes"] == 47432819
    assert course_sizes["size_mb"] == 45.24

    stats = await repo.get_db_stats()
    assert stats["courses"] == 3
    assert stats["courses_enrolled"] == 3
    assert stats["reviews_total"] == 1
    assert stats["units_total"] == 2


def test_telegram_cleanup_and_instantiation(tmp_path):
    from maktab_downloader.telegram.uploader import CourseTelegramUploader
    from maktab_downloader.telegram.client import TelegramManager

    tg_mgr = TelegramManager(api_id=12345, api_hash="fakehash")
    uploader = CourseTelegramUploader(
        telegram_manager=tg_mgr,
        temp_dir=tmp_path / "temp_tg",
        max_storage_mb=1024.0,
    )

    test_file = tmp_path / "temp_tg" / "test_video.mp4"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("dummy video data")
    assert test_file.exists()

    uploader._cleanup_file(test_file)
    assert not test_file.exists()

