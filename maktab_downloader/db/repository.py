import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import aiosqlite
from maktab_downloader.db.database import Database, db_instance


class Repository:
    """High-performance repository for SQLite persistence with idempotent upserts."""

    def __init__(self, db: Optional[Database] = None):
        self.db = db or db_instance

    # -------------------------------------------------------------
    # 1. Course Upserts & Queries (My Courses & Catalog Search)
    # -------------------------------------------------------------
    async def upsert_course(self, conn: aiosqlite.Connection, item: Dict[str, Any], is_enrolled: bool = True) -> int:
        """Upsert a single course from my_courses or catalog search endpoint."""
        course_id = item.get("id") or item.get("slug_id")
        prices = item.get("prices") or {}
        org = item.get("organization") or {}
        specs = item.get("specifics") or {}
        progress = specs.get("course_progress") or {}
        grouping = specs.get("content_grouping") or {}

        query = """
        INSERT INTO courses (
            id, slug, title, slug_id, real_price, discounted_price, discount,
            image_url, units_count, required_hours, no_of_students,
            organization_id, organization_slug, organization_name, organization_image_url, organization_obj_type,
            specifics_type, avg_rating, content_grouping_name, content_rate_count,
            certification, carousel_discount, has_subtitle, is_last_version, is_enrolled,
            progress_id, score, access_level, progress, access_level_text, full_access_expiry_date,
            can_rate, has_rate, obj_type, raw_json, updated_at
        ) VALUES (
            :id, :slug, :title, :slug_id, :real_price, :discounted_price, :discount,
            :image_url, :units_count, :required_hours, :no_of_students,
            :organization_id, :organization_slug, :organization_name, :organization_image_url, :organization_obj_type,
            :specifics_type, :avg_rating, :content_grouping_name, :content_rate_count,
            :certification, :carousel_discount, :has_subtitle, :is_last_version, :is_enrolled,
            :progress_id, :score, :access_level, :progress, :access_level_text, :full_access_expiry_date,
            :can_rate, :has_rate, :obj_type, :raw_json, CURRENT_TIMESTAMP
        )
        ON CONFLICT(id) DO UPDATE SET
            slug = excluded.slug,
            title = excluded.title,
            slug_id = excluded.slug_id,
            real_price = excluded.real_price,
            discounted_price = excluded.discounted_price,
            discount = excluded.discount,
            image_url = excluded.image_url,
            units_count = excluded.units_count,
            required_hours = excluded.required_hours,
            no_of_students = excluded.no_of_students,
            organization_id = excluded.organization_id,
            organization_slug = excluded.organization_slug,
            organization_name = excluded.organization_name,
            organization_image_url = excluded.organization_image_url,
            organization_obj_type = excluded.organization_obj_type,
            specifics_type = excluded.specifics_type,
            avg_rating = excluded.avg_rating,
            content_grouping_name = excluded.content_grouping_name,
            content_rate_count = excluded.content_rate_count,
            certification = excluded.certification,
            carousel_discount = excluded.carousel_discount,
            has_subtitle = excluded.has_subtitle,
            is_last_version = excluded.is_last_version,
            is_enrolled = CASE WHEN :is_enrolled = 1 THEN 1 ELSE courses.is_enrolled END,
            progress_id = COALESCE(excluded.progress_id, courses.progress_id),
            score = COALESCE(excluded.score, courses.score),
            access_level = COALESCE(excluded.access_level, courses.access_level),
            progress = COALESCE(excluded.progress, courses.progress),
            access_level_text = COALESCE(excluded.access_level_text, courses.access_level_text),
            full_access_expiry_date = COALESCE(excluded.full_access_expiry_date, courses.full_access_expiry_date),
            can_rate = excluded.can_rate,
            has_rate = excluded.has_rate,
            obj_type = excluded.obj_type,
            raw_json = excluded.raw_json,
            updated_at = CURRENT_TIMESTAMP;
        """

        params = {
            "id": course_id,
            "slug": item.get("slug"),
            "title": item.get("title", "Untitled Course"),
            "slug_id": item.get("slug_id"),
            "real_price": prices.get("real"),
            "discounted_price": prices.get("discounted"),
            "discount": item.get("discount", 0.0),
            "image_url": item.get("image_url") or item.get("image"),
            "units_count": item.get("units_count") or item.get("unit_count", 0),
            "required_hours": str(item.get("required_hours", "0")),
            "no_of_students": item.get("no_of_students") or item.get("student_count", 0),
            "organization_id": org.get("id"),
            "organization_slug": org.get("slug"),
            "organization_name": org.get("name"),
            "organization_image_url": org.get("image_url"),
            "organization_obj_type": org.get("obj_type"),
            "specifics_type": specs.get("type"),
            "avg_rating": specs.get("avg_rating", 0.0),
            "content_grouping_name": grouping.get("name"),
            "content_rate_count": specs.get("content_rate_count", 0),
            "certification": 1 if specs.get("certification") else 0,
            "carousel_discount": str(specs.get("carousel_discount", "")),
            "has_subtitle": 1 if specs.get("has_subtitle") else 0,
            "is_last_version": 1 if specs.get("is_last_version", True) else 0,
            "is_enrolled": 1 if is_enrolled else 0,
            "progress_id": progress.get("progress_id"),
            "score": progress.get("score", 0.0),
            "access_level": progress.get("access_level"),
            "progress": progress.get("progress", 0.0),
            "access_level_text": progress.get("access_level_text"),
            "full_access_expiry_date": progress.get("full_access_expiry_date"),
            "can_rate": 1 if specs.get("can_rate") else 0,
            "has_rate": 1 if specs.get("has_rate") else 0,
            "obj_type": item.get("obj_type", "course"),
            "raw_json": json.dumps(item, ensure_ascii=False),
        }

        await conn.execute(query, params)

        # Upsert teachers
        teachers = item.get("teachers") or []
        for t in teachers:
            t_id = t.get("id") or t.get("teacher_id")
            if not t_id:
                continue
            await conn.execute(
                """
                INSERT INTO teachers (id, slug, full_name, display_name, landing_view, obj_type, raw_json)
                VALUES (:id, :slug, :full_name, :display_name, :landing_view, :obj_type, :raw_json)
                ON CONFLICT(id) DO UPDATE SET
                    slug = excluded.slug,
                    full_name = COALESCE(excluded.full_name, teachers.full_name),
                    display_name = COALESCE(excluded.display_name, teachers.display_name),
                    landing_view = excluded.landing_view,
                    obj_type = excluded.obj_type,
                    raw_json = excluded.raw_json;
                """,
                {
                    "id": t_id,
                    "slug": t.get("slug"),
                    "full_name": t.get("full_name"),
                    "display_name": t.get("display_name") or t.get("full_name"),
                    "landing_view": 1 if t.get("landing_view") else 0,
                    "obj_type": t.get("obj_type", "teacher"),
                    "raw_json": json.dumps(t, ensure_ascii=False),
                },
            )
            await conn.execute(
                """
                INSERT OR IGNORE INTO course_teachers (course_id, teacher_id)
                VALUES (?, ?);
                """,
                (course_id, t_id),
            )

        return course_id

    # -------------------------------------------------------------
    # 2. Public Course Landing Page Metadata Upsert
    # -------------------------------------------------------------
    async def upsert_course_landing(self, conn: aiosqlite.Connection, course_id: int, data: Dict[str, Any]):
        """Upsert full public landing page details for a course."""
        publisher = data.get("publisher") or {}
        certif_org = data.get("certif_organization") or {}
        video_url = data.get("video_url") or {}
        prices = data.get("price") or {}
        discounted = data.get("discounted_price") or {}

        query = """
        INSERT INTO courses (
            id, slug, title, slug_id, real_price, discounted_price,
            image_url, units_count, required_hours, no_of_students,
            organization_id, organization_slug, organization_name, organization_image_url,
            publisher_id, publisher_slug, publisher_name, publisher_image_url,
            level, version_number, course_effort_time, content_hours,
            description_html, prerequisite_description, learning_goals_json, topics_json,
            categories_json, preview_video_hq, preview_video_lq, preview_caption,
            published_date, latest_update_date, landing_synced, raw_json, updated_at
        ) VALUES (
            :id, :slug, :title, :slug_id, :real_price, :discounted_price,
            :image_url, :units_count, :required_hours, :no_of_students,
            :organization_id, :organization_slug, :organization_name, :organization_image_url,
            :publisher_id, :publisher_slug, :publisher_name, :publisher_image_url,
            :level, :version_number, :course_effort_time, :content_hours,
            :description_html, :prerequisite_description, :learning_goals_json, :topics_json,
            :categories_json, :preview_video_hq, :preview_video_lq, :preview_caption,
            :published_date, :latest_update_date, 1, :raw_json, CURRENT_TIMESTAMP
        )
        ON CONFLICT(id) DO UPDATE SET
            slug = COALESCE(excluded.slug, courses.slug),
            title = excluded.title,
            slug_id = excluded.slug_id,
            real_price = COALESCE(excluded.real_price, courses.real_price),
            discounted_price = COALESCE(excluded.discounted_price, courses.discounted_price),
            image_url = COALESCE(excluded.image_url, courses.image_url),
            units_count = COALESCE(excluded.units_count, courses.units_count),
            required_hours = COALESCE(excluded.required_hours, courses.required_hours),
            no_of_students = COALESCE(excluded.no_of_students, courses.no_of_students),
            organization_id = COALESCE(excluded.organization_id, courses.organization_id),
            organization_slug = COALESCE(excluded.organization_slug, courses.organization_slug),
            organization_name = COALESCE(excluded.organization_name, courses.organization_name),
            organization_image_url = COALESCE(excluded.organization_image_url, courses.organization_image_url),
            publisher_id = excluded.publisher_id,
            publisher_slug = excluded.publisher_slug,
            publisher_name = excluded.publisher_name,
            publisher_image_url = excluded.publisher_image_url,
            level = excluded.level,
            version_number = excluded.version_number,
            course_effort_time = excluded.course_effort_time,
            content_hours = excluded.content_hours,
            description_html = excluded.description_html,
            prerequisite_description = excluded.prerequisite_description,
            learning_goals_json = excluded.learning_goals_json,
            topics_json = excluded.topics_json,
            categories_json = excluded.categories_json,
            preview_video_hq = excluded.preview_video_hq,
            preview_video_lq = excluded.preview_video_lq,
            preview_caption = excluded.preview_caption,
            published_date = excluded.published_date,
            latest_update_date = excluded.latest_update_date,
            landing_synced = 1,
            raw_json = excluded.raw_json,
            updated_at = CURRENT_TIMESTAMP;
        """

        params = {
            "id": course_id,
            "slug": data.get("slug"),
            "title": data.get("title", ""),
            "slug_id": data.get("slug_id", course_id),
            "real_price": prices.get("CONTENT") or prices.get("FULL") or 0,
            "discounted_price": discounted.get("CONTENT") or discounted.get("FULL") or 0,
            "image_url": data.get("image") or data.get("image_thumbnail_url") or data.get("poster"),
            "units_count": data.get("unit_count", 0),
            "required_hours": str(data.get("required_hours", 0)),
            "no_of_students": data.get("student_count", 0),
            "organization_id": certif_org.get("organization_id"),
            "organization_slug": certif_org.get("slug"),
            "organization_name": certif_org.get("name"),
            "organization_image_url": certif_org.get("image_url"),
            "publisher_id": publisher.get("organization_id"),
            "publisher_slug": publisher.get("slug"),
            "publisher_name": publisher.get("name"),
            "publisher_image_url": publisher.get("image_url"),
            "level": data.get("level"),
            "version_number": data.get("version_number", 1),
            "course_effort_time": data.get("course_effort_time"),
            "content_hours": data.get("content_hours", 0),
            "description_html": data.get("description"),
            "prerequisite_description": data.get("prerequisite_description"),
            "learning_goals_json": json.dumps(data.get("learning_goals", []), ensure_ascii=False),
            "topics_json": json.dumps(data.get("topics", []), ensure_ascii=False),
            "categories_json": json.dumps(data.get("categories", {}), ensure_ascii=False),
            "preview_video_hq": video_url.get("hq"),
            "preview_video_lq": video_url.get("lq"),
            "preview_caption": video_url.get("caption"),
            "published_date": data.get("published_date"),
            "latest_update_date": data.get("latest_update_date"),
            "raw_json": json.dumps(data, ensure_ascii=False),
        }

        await conn.execute(query, params)

        # Teachers from landing page
        for t in data.get("teachers", []):
            t_id = t.get("id") or t.get("teacher_id")
            if not t_id:
                continue
            await conn.execute(
                """
                INSERT INTO teachers (
                    id, slug, full_name, display_name, headline, image_url, description,
                    course_count, student_count, landing_view, raw_json
                ) VALUES (
                    :id, :slug, :full_name, :display_name, :headline, :image_url, :description,
                    :course_count, :student_count, :landing_view, :raw_json
                )
                ON CONFLICT(id) DO UPDATE SET
                    slug = excluded.slug,
                    full_name = COALESCE(excluded.full_name, teachers.full_name),
                    display_name = COALESCE(excluded.display_name, teachers.display_name),
                    headline = excluded.headline,
                    image_url = excluded.image_url,
                    description = excluded.description,
                    course_count = excluded.course_count,
                    student_count = excluded.student_count,
                    raw_json = excluded.raw_json;
                """,
                {
                    "id": t_id,
                    "slug": t.get("slug"),
                    "full_name": t.get("full_name"),
                    "display_name": t.get("full_name"),
                    "headline": t.get("headline", ""),
                    "image_url": t.get("image_url"),
                    "description": t.get("description", ""),
                    "course_count": t.get("course_count", 0),
                    "student_count": t.get("student_count", 0),
                    "landing_view": 1 if t.get("landing_view") else 0,
                    "raw_json": json.dumps(t, ensure_ascii=False),
                },
            )
            await conn.execute(
                "INSERT OR IGNORE INTO course_teachers (course_id, teacher_id) VALUES (?, ?);",
                (course_id, t_id),
            )

    # -------------------------------------------------------------
    # 3. Actions & Enrollment Status
    # -------------------------------------------------------------
    async def update_course_actions(self, conn: aiosqlite.Connection, course_id: int, actions_data: Dict[str, Any]):
        """Update actions and call to action status for a course."""
        actions = actions_data.get("actions") or {}
        enrollment = actions_data.get("enrollment") or {}
        access_level = enrollment.get("access_level")
        is_enrolled = 1 if access_level and access_level > 0 else 0

        await conn.execute(
            """
            UPDATE courses SET
                call_to_action = :cta,
                call_to_action_text = :cta_text,
                is_enrolled = CASE WHEN :is_enrolled = 1 THEN 1 ELSE is_enrolled END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :course_id;
            """,
            {
                "cta": actions.get("call_to_action"),
                "cta_text": actions.get("call_to_action_text"),
                "is_enrolled": is_enrolled,
                "course_id": course_id,
            },
        )

    async def mark_course_enrolled(self, course_id: int, is_enrolled: bool = True, conn: Optional[aiosqlite.Connection] = None):
        """Mark a course as enrolled in database."""
        if conn:
            await conn.execute(
                "UPDATE courses SET is_enrolled = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?;",
                (1 if is_enrolled else 0, course_id),
            )
        else:
            async with self.db.connection() as c:
                await c.execute(
                    "UPDATE courses SET is_enrolled = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?;",
                    (1 if is_enrolled else 0, course_id),
                )
                await c.commit()

    # -------------------------------------------------------------
    # 4. Student Reviews Upsert & Queries
    # -------------------------------------------------------------
    async def upsert_review(self, conn: aiosqlite.Connection, course_id: int, review_item: Dict[str, Any]):
        """Upsert a student review and reviewer user info."""
        rev_id = review_item.get("id")
        if not rev_id:
            return

        user = review_item.get("user") or {}
        query = """
        INSERT INTO reviews (
            id, course_id, user_id, user_first_name, user_last_name, user_full_name,
            user_image_url, rate, review_description, review_reply, created_date, modified_date, raw_json
        ) VALUES (
            :id, :course_id, :user_id, :user_first_name, :user_last_name, :user_full_name,
            :user_image_url, :rate, :review_description, :review_reply, :created_date, :modified_date, :raw_json
        )
        ON CONFLICT(id) DO UPDATE SET
            course_id = excluded.course_id,
            user_id = excluded.user_id,
            user_first_name = excluded.user_first_name,
            user_last_name = excluded.user_last_name,
            user_full_name = excluded.user_full_name,
            user_image_url = excluded.user_image_url,
            rate = excluded.rate,
            review_description = excluded.review_description,
            review_reply = excluded.review_reply,
            created_date = excluded.created_date,
            modified_date = excluded.modified_date,
            raw_json = excluded.raw_json;
        """

        params = {
            "id": rev_id,
            "course_id": course_id,
            "user_id": user.get("id"),
            "user_first_name": user.get("first_name", ""),
            "user_last_name": user.get("last_name", ""),
            "user_full_name": user.get("full_name") or f"{user.get('first_name', '')} {user.get('last_name', '')}".strip(),
            "user_image_url": user.get("image_url", ""),
            "rate": review_item.get("rate", 5),
            "review_description": review_item.get("review_description", ""),
            "review_reply": review_item.get("review_reply", ""),
            "created_date": review_item.get("created_date"),
            "modified_date": review_item.get("modified_date"),
            "raw_json": json.dumps(review_item, ensure_ascii=False),
        }

        await conn.execute(query, params)

    async def get_reviews_for_course(self, course_id: int) -> List[aiosqlite.Row]:
        """Fetch all reviews for a course."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM reviews WHERE course_id = ? ORDER BY created_date DESC, id DESC;",
                (course_id,),
            )
            return await cursor.fetchall()

    # -------------------------------------------------------------
    # 5. Course Outline Upserts
    # -------------------------------------------------------------
    async def upsert_outline(self, conn: aiosqlite.Connection, course_id: int, outline_data: Dict[str, Any]):
        """Upsert chapters and initial unit items from course outline."""
        student_effort = outline_data.get("student_effort_seconds", 0)
        chapters_count = outline_data.get("chapters_count", 0)
        title = outline_data.get("title")

        # Update course outline summary
        await conn.execute(
            """
            UPDATE courses SET
                student_effort_seconds = :effort,
                chapters_count = :ch_count,
                outline_synced = 1,
                title = COALESCE(title, :title),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :course_id;
            """,
            {"effort": student_effort, "ch_count": chapters_count, "title": title, "course_id": course_id},
        )

        # Teachers from outline
        for t in outline_data.get("teachers", []):
            t_id = t.get("id")
            if t_id:
                await conn.execute(
                    """
                    INSERT INTO teachers (id, slug, display_name, raw_json)
                    VALUES (:id, :slug, :display_name, :raw_json)
                    ON CONFLICT(id) DO UPDATE SET
                        slug = excluded.slug,
                        display_name = COALESCE(excluded.display_name, teachers.display_name);
                    """,
                    {
                        "id": t_id,
                        "slug": t.get("slug"),
                        "display_name": t.get("display_name"),
                        "raw_json": json.dumps(t, ensure_ascii=False),
                    },
                )
                await conn.execute(
                    "INSERT OR IGNORE INTO course_teachers (course_id, teacher_id) VALUES (?, ?);",
                    (course_id, t_id),
                )

        # Chapters
        chapters = outline_data.get("chapters", [])
        for ch in chapters:
            ch_id = ch.get("id") or ch.get("slug_id")
            if not ch_id:
                continue

            await conn.execute(
                """
                INSERT INTO chapters (
                    id, course_id, slug, slug_id, title, order_num, worth, units_count,
                    student_effort_seconds, raw_json, updated_at
                ) VALUES (
                    :id, :course_id, :slug, :slug_id, :title, :order_num, :worth, :units_count,
                    :student_effort_seconds, :raw_json, CURRENT_TIMESTAMP
                )
                ON CONFLICT(id) DO UPDATE SET
                    course_id = excluded.course_id,
                    slug = excluded.slug,
                    slug_id = excluded.slug_id,
                    title = excluded.title,
                    order_num = excluded.order_num,
                    worth = excluded.worth,
                    units_count = excluded.units_count,
                    student_effort_seconds = excluded.student_effort_seconds,
                    raw_json = excluded.raw_json,
                    updated_at = CURRENT_TIMESTAMP;
                """,
                {
                    "id": ch_id,
                    "course_id": course_id,
                    "slug": ch.get("slug"),
                    "slug_id": ch.get("slug_id"),
                    "title": ch.get("title", f"Chapter {ch.get('order', 1)}"),
                    "order_num": ch.get("order", 0),
                    "worth": str(ch.get("worth", "0.00")),
                    "units_count": ch.get("units_count", 0),
                    "student_effort_seconds": ch.get("student_effort_seconds", 0),
                    "raw_json": json.dumps(ch, ensure_ascii=False),
                },
            )

            # Units in chapter
            for u in ch.get("units", []):
                u_id = u.get("id")
                if not u_id:
                    continue

                await conn.execute(
                    """
                    INSERT INTO units (
                        id, course_id, chapter_id, title, slug, type, type_display,
                        order_num, student_effort_seconds, view_access, sync_status, updated_at
                    ) VALUES (
                        :id, :course_id, :chapter_id, :title, :slug, :type, :type_display,
                        :order_num, :student_effort_seconds, :view_access, 'pending', CURRENT_TIMESTAMP
                    )
                    ON CONFLICT(id) DO UPDATE SET
                        course_id = excluded.course_id,
                        chapter_id = excluded.chapter_id,
                        title = excluded.title,
                        slug = excluded.slug,
                        type = excluded.type,
                        type_display = excluded.type_display,
                        order_num = excluded.order_num,
                        student_effort_seconds = excluded.student_effort_seconds,
                        view_access = excluded.view_access,
                        updated_at = CURRENT_TIMESTAMP;
                    """,
                    {
                        "id": u_id,
                        "course_id": course_id,
                        "chapter_id": ch_id,
                        "title": u.get("title", f"Unit {u.get('order', 1)}"),
                        "slug": u.get("slug"),
                        "type": u.get("type", 1),
                        "type_display": u.get("type_display"),
                        "order_num": u.get("order", 0),
                        "student_effort_seconds": u.get("student_effort_seconds", 0),
                        "view_access": u.get("view_access", 0),
                    },
                )

    # -------------------------------------------------------------
    # 6. Detailed Unit & Resources Upserts
    # -------------------------------------------------------------
    async def upsert_unit_detail(self, conn: aiosqlite.Connection, unit_data: Dict[str, Any]):
        """Upsert full detailed unit metadata along with all downloadable video resources."""
        unit_id = unit_data.get("id")
        if not unit_id:
            return

        course_id = unit_data.get("course_id") or unit_data.get("course_slug_id")
        chapter_id = unit_data.get("chapter_id")
        media = unit_data.get("media") or {}
        engagement = unit_data.get("engagement") or {}

        query = """
        INSERT INTO units (
            id, course_id, chapter_id, title, slug, type, type_display,
            chapter_title, course_title, order_num, description, student_effort_seconds,
            file_id, duration, has_caption, caption_file, poster, worth, threshold,
            is_required, has_submit_access, project_json, quiz_json, media_point,
            is_completed, likes, dislikes, user_rating, view_access, submit_access,
            courseflow_access_level, sync_status, error_message, raw_json, updated_at
        ) VALUES (
            :id, :course_id, :chapter_id, :title, :slug, :type, :type_display,
            :chapter_title, :course_title, :order_num, :description, :student_effort_seconds,
            :file_id, :duration, :has_caption, :caption_file, :poster, :worth, :threshold,
            :is_required, :has_submit_access, :project_json, :quiz_json, :media_point,
            :is_completed, :likes, :dislikes, :user_rating, :view_access, :submit_access,
            :courseflow_access_level, 'synced', NULL, :raw_json, CURRENT_TIMESTAMP
        )
        ON CONFLICT(id) DO UPDATE SET
            course_id = COALESCE(excluded.course_id, units.course_id),
            chapter_id = COALESCE(excluded.chapter_id, units.chapter_id),
            title = excluded.title,
            slug = excluded.slug,
            type = excluded.type,
            type_display = excluded.type_display,
            chapter_title = excluded.chapter_title,
            course_title = excluded.course_title,
            order_num = excluded.order_num,
            description = excluded.description,
            student_effort_seconds = excluded.student_effort_seconds,
            file_id = excluded.file_id,
            duration = excluded.duration,
            has_caption = excluded.has_caption,
            caption_file = excluded.caption_file,
            poster = excluded.poster,
            worth = excluded.worth,
            threshold = excluded.threshold,
            is_required = excluded.is_required,
            has_submit_access = excluded.has_submit_access,
            project_json = excluded.project_json,
            quiz_json = excluded.quiz_json,
            media_point = excluded.media_point,
            is_completed = excluded.is_completed,
            likes = excluded.likes,
            dislikes = excluded.dislikes,
            user_rating = excluded.user_rating,
            view_access = excluded.view_access,
            submit_access = excluded.submit_access,
            courseflow_access_level = excluded.courseflow_access_level,
            sync_status = 'synced',
            error_message = NULL,
            raw_json = excluded.raw_json,
            updated_at = CURRENT_TIMESTAMP;
        """

        params = {
            "id": unit_id,
            "course_id": course_id,
            "chapter_id": chapter_id,
            "title": unit_data.get("title", ""),
            "slug": unit_data.get("slug"),
            "type": unit_data.get("type", 1),
            "type_display": unit_data.get("type_display"),
            "chapter_title": unit_data.get("chapter_title"),
            "course_title": unit_data.get("course_title"),
            "order_num": unit_data.get("order", 0),
            "description": unit_data.get("description", ""),
            "student_effort_seconds": unit_data.get("student_effort_seconds", 0),
            "file_id": unit_data.get("file_id"),
            "duration": unit_data.get("duration", 0),
            "has_caption": 1 if unit_data.get("has_caption") else 0,
            "caption_file": unit_data.get("caption_file"),
            "poster": unit_data.get("poster"),
            "worth": str(unit_data.get("worth")) if unit_data.get("worth") is not None else None,
            "threshold": str(unit_data.get("threshold")) if unit_data.get("threshold") is not None else None,
            "is_required": 1 if unit_data.get("is_required") else 0,
            "has_submit_access": 1 if unit_data.get("has_submit_access") else 0,
            "project_json": json.dumps(unit_data.get("project"), ensure_ascii=False) if unit_data.get("project") else None,
            "quiz_json": json.dumps(unit_data.get("quiz"), ensure_ascii=False) if unit_data.get("quiz") else None,
            "media_point": media.get("point", 0.0),
            "is_completed": 1 if unit_data.get("is_completed") else 0,
            "likes": engagement.get("likes", 0),
            "dislikes": engagement.get("dislikes", 0),
            "user_rating": engagement.get("user_rating", 0.0),
            "view_access": unit_data.get("view_access", 0),
            "submit_access": unit_data.get("submit_access", 0),
            "courseflow_access_level": unit_data.get("courseflow_access_level", 0),
            "raw_json": json.dumps(unit_data, ensure_ascii=False),
        }

        await conn.execute(query, params)

        # Teachers
        for t_id in unit_data.get("teacher_ids", []):
            await conn.execute(
                "INSERT OR IGNORE INTO unit_teachers (unit_id, teacher_id) VALUES (?, ?);",
                (unit_id, t_id),
            )

        # Resources (Videos / Files)
        resources = unit_data.get("resources", [])
        for res in resources:
            res_id = res.get("id")
            if not res_id:
                continue

            await conn.execute(
                """
                INSERT INTO resources (
                    id, unit_id, course_id, chapter_id, type, type_display, quality,
                    quality_display, title, display_title, download_url, size_mb,
                    resolution_height, is_downloadable, file_extension, bitrate_kbps,
                    codec, order_num, raw_json, updated_at
                ) VALUES (
                    :id, :unit_id, :course_id, :chapter_id, :type, :type_display, :quality,
                    :quality_display, :title, :display_title, :download_url, :size_mb,
                    :resolution_height, :is_downloadable, :file_extension, :bitrate_kbps,
                    :codec, :order_num, :raw_json, CURRENT_TIMESTAMP
                )
                ON CONFLICT(id) DO UPDATE SET
                    unit_id = excluded.unit_id,
                    course_id = excluded.course_id,
                    chapter_id = excluded.chapter_id,
                    type = excluded.type,
                    type_display = excluded.type_display,
                    quality = excluded.quality,
                    quality_display = excluded.quality_display,
                    title = excluded.title,
                    display_title = excluded.display_title,
                    download_url = excluded.download_url,
                    size_mb = excluded.size_mb,
                    resolution_height = excluded.resolution_height,
                    is_downloadable = excluded.is_downloadable,
                    file_extension = excluded.file_extension,
                    bitrate_kbps = excluded.bitrate_kbps,
                    codec = excluded.codec,
                    order_num = excluded.order_num,
                    raw_json = excluded.raw_json,
                    updated_at = CURRENT_TIMESTAMP;
                """,
                {
                    "id": res_id,
                    "unit_id": unit_id,
                    "course_id": course_id,
                    "chapter_id": chapter_id,
                    "type": res.get("type", 1),
                    "type_display": res.get("type_display"),
                    "quality": res.get("quality", "default"),
                    "quality_display": res.get("quality_display"),
                    "title": res.get("title"),
                    "display_title": res.get("display_title"),
                    "download_url": res.get("download_url", ""),
                    "size_mb": res.get("size_mb"),
                    "resolution_height": res.get("resolution_height"),
                    "is_downloadable": 1 if res.get("is_downloadable") else 0,
                    "file_extension": res.get("file_extension"),
                    "bitrate_kbps": res.get("bitrate_kbps"),
                    "codec": res.get("codec", ""),
                    "order_num": res.get("order", 0),
                    "raw_json": json.dumps(res, ensure_ascii=False),
                },
            )

    async def mark_unit_error(self, conn: aiosqlite.Connection, unit_id: int, error_msg: str):
        """Mark unit sync as error."""
        await conn.execute(
            """
            UPDATE units SET
                sync_status = 'error',
                error_message = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """,
            (error_msg, unit_id),
        )

    # -------------------------------------------------------------
    # 7. Status, Queries & Analytics
    # -------------------------------------------------------------
    async def get_all_courses(self, enrolled_only: bool = False) -> List[aiosqlite.Row]:
        async with self.db.connection() as conn:
            where_clause = "WHERE c.is_enrolled = 1" if enrolled_only else ""
            cursor = await conn.execute(
                f"""
                SELECT c.*, 
                       COUNT(DISTINCT ch.id) AS actual_chapters_count,
                       COUNT(DISTINCT u.id) AS actual_units_count,
                       COUNT(DISTINCT r.id) AS total_resources_count,
                       COUNT(DISTINCT rev.id) AS actual_reviews_count,
                       SUM(CASE WHEN r.download_status = 'completed' THEN 1 ELSE 0 END) AS downloaded_resources_count
                FROM courses c
                LEFT JOIN chapters ch ON ch.course_id = c.id
                LEFT JOIN units u ON u.course_id = c.id
                LEFT JOIN resources r ON r.unit_id = u.id
                LEFT JOIN reviews rev ON rev.course_id = c.id
                {where_clause}
                GROUP BY c.id
                ORDER BY c.id DESC;
                """
            )
            return await cursor.fetchall()

    async def get_course_by_id(self, course_id: int) -> Optional[aiosqlite.Row]:
        async with self.db.connection() as conn:
            cursor = await conn.execute("SELECT * FROM courses WHERE id = ?;", (course_id,))
            return await cursor.fetchone()

    async def get_pending_units(self, course_id: Optional[int] = None) -> List[aiosqlite.Row]:
        """Fetch units that need metadata syncing."""
        async with self.db.connection() as conn:
            if course_id:
                cursor = await conn.execute(
                    "SELECT id, course_id, chapter_id, title FROM units WHERE course_id = ? AND sync_status != 'synced' ORDER BY id ASC;",
                    (course_id,),
                )
            else:
                cursor = await conn.execute(
                    "SELECT id, course_id, chapter_id, title FROM units WHERE sync_status != 'synced' ORDER BY id ASC;"
                )
            return await cursor.fetchall()

    async def get_all_units(self, course_id: Optional[int] = None) -> List[aiosqlite.Row]:
        """Fetch all units for crawling."""
        async with self.db.connection() as conn:
            if course_id:
                cursor = await conn.execute(
                    "SELECT id, course_id, chapter_id, title FROM units WHERE course_id = ? ORDER BY id ASC;",
                    (course_id,),
                )
            else:
                cursor = await conn.execute(
                    "SELECT id, course_id, chapter_id, title FROM units ORDER BY id ASC;"
                )
            return await cursor.fetchall()

    async def get_chapters_for_course(self, course_id: int) -> List[aiosqlite.Row]:
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM chapters WHERE course_id = ? ORDER BY order_num ASC, id ASC;",
                (course_id,),
            )
            return await cursor.fetchall()

    async def get_units_for_chapter(self, chapter_id: int) -> List[aiosqlite.Row]:
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM units WHERE chapter_id = ? ORDER BY order_num ASC, id ASC;",
                (chapter_id,),
            )
            return await cursor.fetchall()

    async def get_resources_for_unit(self, unit_id: int) -> List[aiosqlite.Row]:
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM resources WHERE unit_id = ? ORDER BY resolution_height DESC, order_num ASC;",
                (unit_id,),
            )
            return await cursor.fetchall()

    async def get_downloadable_resources(
        self,
        course_id: Optional[int] = None,
        preferred_quality: str = "1080p",
        include_completed: bool = False,
    ) -> List[aiosqlite.Row]:
        """
        Query downloadable resources per unit matching the preferred quality.
        If the preferred quality (e.g. 1080p) is not available for a unit,
        it automatically falls back to highest available quality.
        """
        async with self.db.connection() as conn:
            params = []
            where_clauses = ["u.sync_status = 'synced'"]
            if course_id:
                where_clauses.append("u.course_id = ?")
                params.append(course_id)
            if not include_completed:
                where_clauses.append("r.download_status != 'completed'")

            where_str = " AND ".join(where_clauses)

            # Query all resources with course and chapter metadata
            query = f"""
            SELECT 
                r.id AS resource_id,
                r.unit_id,
                r.quality,
                r.quality_display,
                r.download_url,
                r.size_mb,
                r.total_bytes,
                r.downloaded_bytes,
                r.resolution_height,
                r.download_status,
                r.local_file_path,
                u.title AS unit_title,
                u.order_num AS unit_order,
                u.has_caption,
                u.caption_file,
                u.poster,
                ch.id AS chapter_id,
                ch.title AS chapter_title,
                ch.order_num AS chapter_order,
                c.id AS course_id,
                c.title AS course_title
            FROM resources r
            JOIN units u ON u.id = r.unit_id
            JOIN chapters ch ON ch.id = u.chapter_id
            JOIN courses c ON c.id = u.course_id
            WHERE {where_str}
            ORDER BY u.course_id, ch.order_num, u.order_num, r.resolution_height DESC;
            """

            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()

            # Group by unit_id to select the best match for preferred_quality
            unit_map: Dict[int, List[aiosqlite.Row]] = {}
            for r in rows:
                u_id = r["unit_id"]
                if u_id not in unit_map:
                    unit_map[u_id] = []
                unit_map[u_id].append(r)

            selected_resources = []
            for u_id, res_list in unit_map.items():
                if preferred_quality in ["all"]:
                    selected_resources.extend(res_list)
                    continue

                # Match exact quality (e.g. 1080p, 720p, 480p)
                match = next((r for r in res_list if r["quality"] == preferred_quality), None)
                if match:
                    selected_resources.append(match)
                elif preferred_quality == "worst":
                    selected_resources.append(res_list[-1])
                else:
                    # Fallback to highest available resolution
                    selected_resources.append(res_list[0])

            return selected_resources

    async def update_resource_download_status(
        self,
        resource_id: int,
        status: str,
        local_path: Optional[str] = None,
        downloaded_bytes: int = 0,
        total_bytes: int = 0,
        error_msg: Optional[str] = None,
    ):
        """Update download status and local file path."""
        async with self.db.connection() as conn:
            await conn.execute(
                """
                UPDATE resources SET
                    download_status = :status,
                    local_file_path = COALESCE(:local_path, local_file_path),
                    downloaded_bytes = :downloaded,
                    total_bytes = :total,
                    downloaded_at = CASE WHEN :status = 'completed' THEN CURRENT_TIMESTAMP ELSE downloaded_at END,
                    error_message = :error_msg,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id;
                """,
                {
                    "status": status,
                    "local_path": local_path,
                    "downloaded": downloaded_bytes,
                    "total": total_bytes,
                    "error_msg": error_msg,
                    "id": resource_id,
                },
            )
            await conn.commit()

    async def update_resource_size(self, resource_id: int, total_bytes: int):
        """Update discovered size in bytes and MB for a resource."""
        size_mb = round(total_bytes / (1024 * 1024), 2)
        async with self.db.connection() as conn:
            await conn.execute(
                """
                UPDATE resources SET
                    size_mb = :size_mb,
                    total_bytes = :total_bytes,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id;
                """,
                {"size_mb": size_mb, "total_bytes": total_bytes, "id": resource_id},
            )
            await conn.commit()

    async def get_course_size_stats(self, course_id: Optional[int] = None, preferred_quality: str = "1080p") -> Dict[str, Any]:
        """Calculate total estimated download size and counted video resources."""
        resources = await self.get_downloadable_resources(course_id=course_id, preferred_quality=preferred_quality, include_completed=True)
        total_bytes = sum(r["total_bytes"] or (int(r["size_mb"] * 1024 * 1024) if r["size_mb"] else 0) for r in resources)
        known_count = sum(1 for r in resources if (r["total_bytes"] or r["size_mb"]))
        return {
            "total_items": len(resources),
            "known_size_items": known_count,
            "total_bytes": total_bytes,
            "size_mb": round(total_bytes / (1024 * 1024), 2),
            "size_gb": round(total_bytes / (1024 * 1024 * 1024), 2),
        }

    async def get_db_stats(self) -> Dict[str, int]:
        """Get aggregate counts for courses, chapters, units, resources, and reviews."""
        async with self.db.connection() as conn:
            c1 = await (await conn.execute("SELECT COUNT(*) FROM courses;")).fetchone()
            c1_enrolled = await (await conn.execute("SELECT COUNT(*) FROM courses WHERE is_enrolled = 1;")).fetchone()
            c2 = await (await conn.execute("SELECT COUNT(*) FROM chapters;")).fetchone()
            c3 = await (await conn.execute("SELECT COUNT(*) FROM units;")).fetchone()
            c4 = await (await conn.execute("SELECT COUNT(*) FROM units WHERE sync_status = 'synced';")).fetchone()
            c5 = await (await conn.execute("SELECT COUNT(*) FROM resources;")).fetchone()
            c6 = await (await conn.execute("SELECT COUNT(*) FROM resources WHERE download_status = 'completed';")).fetchone()
            c7 = await (await conn.execute("SELECT COUNT(*) FROM reviews;")).fetchone()

            return {
                "courses": c1[0] if c1 else 0,
                "courses_enrolled": c1_enrolled[0] if c1_enrolled else 0,
                "chapters": c2[0] if c2 else 0,
                "units_total": c3[0] if c3 else 0,
                "units_synced": c4[0] if c4 else 0,
                "resources_total": c5[0] if c5 else 0,
                "resources_downloaded": c6[0] if c6 else 0,
                "reviews_total": c7[0] if c7 else 0,
            }


repo_instance = Repository()
