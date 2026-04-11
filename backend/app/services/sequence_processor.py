"""Sequence processor — sends drip sequence emails on schedule.

Runs periodically (every 60s). For each active enrollment with next_send_at <= now:
1. Check business hours (send_window_start/end in sequence timezone)
2. Check rate limits (max_per_hour, max_per_day)
3. Compose email from step template + row data (using render_prompt)
4. Send via SMTP (using EmailSender, non-blocking)
5. Log EmailEvent with message_id
6. Calculate next_send_at (delay_days ± jitter)
7. On bounce: mark enrollment bounced, downgrade email confidence
"""
import asyncio
import logging
import random
import smtplib
import uuid
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.database import async_session
from app.models.sequence import (
    Sequence, SequenceStatus, SequenceStep,
    SequenceEnrollment, EnrollmentStatus,
    EmailEvent, EmailEventType,
)
from app.models.row import Row
from app.models.column import Column
from app.workers.scrape_worker import render_prompt

logger = logging.getLogger(__name__)


async def process_pending_sends() -> dict:
    """Process all pending sequence sends. Returns stats."""
    stats = {"checked": 0, "sent": 0, "skipped": 0, "errors": 0, "bounced": 0}

    async with async_session() as db:
        now = datetime.now(timezone.utc)

        # Find active enrollments ready to send
        result = await db.execute(
            select(SequenceEnrollment)
            .where(
                SequenceEnrollment.status == EnrollmentStatus.ACTIVE,
                SequenceEnrollment.next_send_at <= now,
            )
            .options(
                selectinload(SequenceEnrollment.sequence).selectinload(Sequence.steps),
            )
            .limit(50)  # Process max 50 per cycle
        )
        enrollments = result.scalars().all()
        stats["checked"] = len(enrollments)

        for enrollment in enrollments:
            sequence = enrollment.sequence

            # Skip non-active sequences
            if sequence.status != SequenceStatus.ACTIVE:
                stats["skipped"] += 1
                continue

            # Check business hours in sequence's local timezone
            try:
                import zoneinfo
                tz = zoneinfo.ZoneInfo(sequence.timezone)
            except Exception:
                tz = timezone.utc
            local_now = now.astimezone(tz)
            if not (sequence.send_window_start <= local_now.hour < sequence.send_window_end):
                stats["skipped"] += 1
                continue

            # Check rate limits — count SENT events in the last hour
            hour_ago = now - timedelta(hours=1)
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

            enrollment_subq = (
                select(SequenceEnrollment.id)
                .where(SequenceEnrollment.sequence_id == sequence.id)
                .scalar_subquery()
            )

            sent_this_hour = await db.scalar(
                select(func.count(EmailEvent.id)).where(
                    EmailEvent.enrollment_id.in_(enrollment_subq),
                    EmailEvent.event_type == EmailEventType.SENT,
                    EmailEvent.created_at >= hour_ago,
                )
            ) or 0

            if sent_this_hour >= sequence.max_per_hour:
                stats["skipped"] += 1
                continue

            sent_today = await db.scalar(
                select(func.count(EmailEvent.id)).where(
                    EmailEvent.enrollment_id.in_(enrollment_subq),
                    EmailEvent.event_type == EmailEventType.SENT,
                    EmailEvent.created_at >= day_start,
                )
            ) or 0

            if sent_today >= sequence.max_per_day:
                stats["skipped"] += 1
                continue

            # Get the step we're on
            step = next(
                (s for s in sequence.steps if s.step_number == enrollment.current_step),
                None,
            )
            if not step:
                # No matching step — mark completed
                enrollment.status = EnrollmentStatus.COMPLETED
                enrollment.next_send_at = None
                await db.commit()
                stats["skipped"] += 1
                continue

            # Build row data dict for template rendering
            row_data = await _build_row_data(db, enrollment.row_id)

            # Render subject and body from templates
            subject = render_prompt(step.subject_template, row_data)
            body = render_prompt(step.body_template, row_data)

            # Send email
            try:
                send_result = await _send_sequence_email(
                    to=enrollment.email,
                    subject=subject,
                    body=body,
                )

                if send_result.get("success"):
                    # Log sent event
                    event = EmailEvent(
                        enrollment_id=enrollment.id,
                        step_number=enrollment.current_step,
                        event_type=EmailEventType.SENT,
                        message_id=send_result.get("message_id", ""),
                        smtp_response=send_result.get("response", ""),
                    )
                    db.add(event)

                    enrollment.last_sent_at = now

                    # Advance to next step, or mark completed
                    next_step = next(
                        (s for s in sequence.steps if s.step_number == enrollment.current_step + 1),
                        None,
                    )
                    if next_step:
                        jitter_hours = random.randint(
                            -next_step.delay_jitter_hours,
                            next_step.delay_jitter_hours,
                        )
                        enrollment.next_send_at = now + timedelta(
                            days=next_step.delay_days,
                            hours=jitter_hours,
                        )
                        enrollment.current_step += 1
                    else:
                        enrollment.status = EnrollmentStatus.COMPLETED
                        enrollment.next_send_at = None

                    await db.commit()
                    stats["sent"] += 1
                    logger.info(f"Sent step {step.step_number} to {enrollment.email}")

                elif send_result.get("is_bounce"):
                    enrollment.status = EnrollmentStatus.BOUNCED
                    enrollment.bounce_reason = send_result.get("error", "")
                    enrollment.next_send_at = None

                    event = EmailEvent(
                        enrollment_id=enrollment.id,
                        step_number=enrollment.current_step,
                        event_type=EmailEventType.BOUNCED,
                        smtp_response=send_result.get("error", ""),
                    )
                    db.add(event)
                    await db.commit()

                    # Downgrade confidence so future enrichments skip this email
                    await _downgrade_email_confidence(db, enrollment.email)
                    stats["bounced"] += 1
                    logger.warning(f"Bounce for {enrollment.email}: {send_result.get('error')}")

                else:
                    stats["errors"] += 1
                    logger.warning(f"Send failed for {enrollment.email}: {send_result.get('error')}")

            except Exception as exc:
                logger.error(f"Exception sending to {enrollment.email}: {exc}", exc_info=True)
                stats["errors"] += 1

    if stats["sent"] > 0 or stats["bounced"] > 0:
        logger.info(f"Sequence processor: {stats}")
    return stats


async def _build_row_data(db, row_id: uuid.UUID) -> dict:
    """Build {column_name: value} dict from a row's cells."""
    result = await db.execute(
        select(Row).where(Row.id == row_id).options(selectinload(Row.cells))
    )
    row = result.scalar_one_or_none()
    if not row:
        return {}

    row_data: dict[str, str] = {}
    for cell in row.cells:
        if cell.value:
            col = await db.get(Column, cell.column_id)
            if col:
                row_data[col.name] = cell.value
    return row_data


async def _send_sequence_email(to: str, subject: str, body: str) -> dict:
    """Send a sequence email via SMTP (non-blocking) and return result dict."""
    from app.config import settings

    if not all([settings.smtp_host, settings.smtp_user, settings.smtp_pass]):
        return {"success": False, "is_bounce": False, "error": "SMTP not configured"}

    message_id = f"<scrpr-seq-{uuid.uuid4()}@scrpr.dev>"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_user
    msg["To"] = to
    msg["Message-ID"] = message_id
    msg.attach(MIMEText(body, "html"))

    def _smtp_send():
        with smtplib.SMTP(settings.smtp_host, int(settings.smtp_port)) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_pass)
            server.sendmail(settings.smtp_user, to, msg.as_string())

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _smtp_send)
        return {"success": True, "message_id": message_id, "response": "250 OK"}

    except smtplib.SMTPRecipientsRefused as exc:
        return {"success": False, "is_bounce": True, "error": str(exc)}
    except smtplib.SMTPException as exc:
        error_str = str(exc)
        is_bounce = any(code in error_str for code in ["550", "551", "552", "553", "554"])
        return {"success": False, "is_bounce": is_bounce, "error": error_str}
    except Exception as exc:
        return {"success": False, "is_bounce": False, "error": str(exc)}


async def _downgrade_email_confidence(db, email_address: str) -> None:
    """Set confidence to 0 for a bounced email in the cache."""
    try:
        from app.services.email_cache import EmailCacheService
        cache = EmailCacheService()
        entry = await cache.lookup_by_email(email_address)
        if entry:
            entry.confidence = 0.0
            entry.verified = False
            await db.commit()
            logger.info(f"Downgraded confidence for bounced email: {email_address}")
    except Exception as exc:
        logger.debug(f"Could not downgrade email confidence for {email_address}: {exc}")
