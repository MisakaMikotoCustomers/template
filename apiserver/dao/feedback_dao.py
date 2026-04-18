#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""反馈与反馈消息的异步 DAO

注意：MySQL 不支持 `ORDER BY ... NULLS LAST`（那是 PostgreSQL/Oracle 语法），
不要用 SQLAlchemy 的 `.nulls_last()` / `.nulls_first()`，否则会直接 1064 语法错。
需要"NULL 排后面"的等价效果时，用 `col.is_(None)` 作为首个排序 key（ASC 时
非 NULL 行 = 0 在前、NULL 行 = 1 在后）。
"""

from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy import func, select, update

from utils.id_utils import random_feedback_key

from .connection import get_db_session
from .models import Feedback, FeedbackMessage, User


_TITLE_MAX = 60


def _make_title(first_content: str) -> str:
    text = (first_content or '').strip().splitlines()[0] if first_content else ''
    if len(text) > _TITLE_MAX:
        return text[: _TITLE_MAX - 1] + '…'
    return text or '未命名反馈'


async def _allocate_unique_feedback_key(session, user_id: int) -> str:
    for _ in range(300):
        key = random_feedback_key()
        exists = await session.scalar(
            select(Feedback.id).where(
                Feedback.user_id == user_id,
                Feedback.feedback_key == key,
            ).limit(1)
        )
        if not exists:
            return key
    raise RuntimeError('无法生成唯一反馈 key，请稍后重试')


# ===================== 会话创建 & 消息追加 =====================

async def create_feedback_session(
    user_id: int, sender_name: Optional[str], initial_content: str
) -> Feedback:
    """创建反馈会话，同时写入第一条用户消息。"""
    now = datetime.now(timezone.utc)
    async with get_db_session() as session:
        key = await _allocate_unique_feedback_key(session, user_id)
        fb = Feedback(
            user_id=user_id,
            feedback_key=key,
            title=_make_title(initial_content),
            status=Feedback.STATUS_OPEN,
            last_message_at=now,
        )
        session.add(fb)
        await session.flush()

        first_msg = FeedbackMessage(
            user_id=user_id,
            feedback_key=key,
            sender_type=FeedbackMessage.SENDER_USER,
            sender_name=sender_name,
            content=initial_content,
        )
        session.add(first_msg)
        await session.flush()
        await session.refresh(fb)
        return fb


async def append_feedback_message(
    user_id: int,
    feedback_key: str,
    sender_type: str,
    sender_name: Optional[str],
    content: str,
) -> Optional[FeedbackMessage]:
    """向已有会话追加一条消息；若会话不存在返回 None。"""
    now = datetime.now(timezone.utc)
    async with get_db_session() as session:
        fb = await session.scalar(
            select(Feedback).where(
                Feedback.user_id == user_id,
                Feedback.feedback_key == feedback_key,
            )
        )
        if not fb:
            return None

        msg = FeedbackMessage(
            user_id=user_id,
            feedback_key=feedback_key,
            sender_type=sender_type,
            sender_name=sender_name,
            content=content,
        )
        session.add(msg)

        # 用户补充消息时，若会话已是 resolved/closed 则自动拉回 processing
        update_fields = {Feedback.last_message_at: now}
        if sender_type == FeedbackMessage.SENDER_USER and fb.status in (
            Feedback.STATUS_RESOLVED, Feedback.STATUS_CLOSED
        ):
            update_fields[Feedback.status] = Feedback.STATUS_PROCESSING
        if sender_type == FeedbackMessage.SENDER_ADMIN and fb.status == Feedback.STATUS_OPEN:
            update_fields[Feedback.status] = Feedback.STATUS_PROCESSING

        await session.execute(
            update(Feedback)
            .where(Feedback.id == fb.id)
            .values(update_fields)
        )
        await session.flush()
        await session.refresh(msg)
        return msg


# ===================== 查询 =====================

async def get_feedback_session(user_id: int, feedback_key: str) -> Optional[Feedback]:
    async with get_db_session() as session:
        return await session.scalar(
            select(Feedback).where(
                Feedback.user_id == user_id,
                Feedback.feedback_key == feedback_key,
            )
        )


async def list_feedback_messages(
    user_id: int, feedback_key: str
) -> List[FeedbackMessage]:
    async with get_db_session() as session:
        result = await session.execute(
            select(FeedbackMessage)
            .where(
                FeedbackMessage.user_id == user_id,
                FeedbackMessage.feedback_key == feedback_key,
            )
            .order_by(FeedbackMessage.id.asc())
        )
        return list(result.scalars().all())


async def _attach_last_messages(
    session, feedbacks: List[Feedback]
) -> List[Tuple[Feedback, Optional[str]]]:
    """为每个反馈会话抓取"最后一条消息"的正文（列表摘要用）。"""
    if not feedbacks:
        return []
    ids = [fb.id for fb in feedbacks]
    # 每个 (user_id, feedback_key) 最新 id
    sub = (
        select(
            FeedbackMessage.user_id,
            FeedbackMessage.feedback_key,
            func.max(FeedbackMessage.id).label('max_id'),
        )
        .where(
            FeedbackMessage.user_id.in_([fb.user_id for fb in feedbacks]),
            FeedbackMessage.feedback_key.in_([fb.feedback_key for fb in feedbacks]),
        )
        .group_by(FeedbackMessage.user_id, FeedbackMessage.feedback_key)
        .subquery()
    )
    result = await session.execute(
        select(
            FeedbackMessage.user_id,
            FeedbackMessage.feedback_key,
            FeedbackMessage.content,
        ).join(
            sub,
            (FeedbackMessage.user_id == sub.c.user_id)
            & (FeedbackMessage.feedback_key == sub.c.feedback_key)
            & (FeedbackMessage.id == sub.c.max_id),
        )
    )
    last_map = {(uid, key): content for uid, key, content in result.all()}
    return [(fb, last_map.get((fb.user_id, fb.feedback_key))) for fb in feedbacks]


async def list_feedbacks_by_user(
    user_id: int, page: int, page_size: int
) -> Tuple[List[Tuple[Feedback, Optional[str]]], int]:
    """普通用户：分页查询自己的反馈列表，附带每个会话最后一条消息摘要。"""
    async with get_db_session() as session:
        total = await session.scalar(
            select(func.count(Feedback.id)).where(Feedback.user_id == user_id)
        )
        offset = max(0, (page - 1) * page_size)
        result = await session.execute(
            select(Feedback)
            .where(Feedback.user_id == user_id)
            .order_by(
                Feedback.last_message_at.is_(None),
                Feedback.last_message_at.desc(),
                Feedback.created_at.desc(),
            )
            .offset(offset)
            .limit(page_size)
        )
        items = list(result.scalars().all())
        attached = await _attach_last_messages(session, items)
        return attached, int(total or 0)


async def list_all_feedbacks(
    page: int, page_size: int, status: Optional[str] = None
) -> Tuple[List[Tuple[Feedback, Optional[str], Optional[str]]], int]:
    """管理员：分页查询全量反馈，附带最后消息与用户名。

    返回 [(Feedback, last_message_text, user_name), ...]
    """
    async with get_db_session() as session:
        total_stmt = select(func.count(Feedback.id))
        list_stmt = select(Feedback)
        if status:
            total_stmt = total_stmt.where(Feedback.status == status)
            list_stmt = list_stmt.where(Feedback.status == status)

        total = await session.scalar(total_stmt)
        offset = max(0, (page - 1) * page_size)
        result = await session.execute(
            list_stmt
            .order_by(
                Feedback.last_message_at.is_(None),
                Feedback.last_message_at.desc(),
                Feedback.created_at.desc(),
            )
            .offset(offset)
            .limit(page_size)
        )
        items = list(result.scalars().all())
        if not items:
            return [], int(total or 0)

        attached = await _attach_last_messages(session, items)

        # 附加用户名
        user_ids = list({fb.user_id for fb in items})
        user_rows = await session.execute(
            select(User.user_id, User.name).where(User.user_id.in_(user_ids))
        )
        name_map = {uid: name for uid, name in user_rows.all()}

        enriched = [(fb, msg, name_map.get(fb.user_id)) for fb, msg in attached]
        return enriched, int(total or 0)


async def update_feedback_status(
    user_id: int, feedback_key: str, status: str
) -> bool:
    if status not in Feedback.ALLOWED_STATUS:
        raise ValueError(f'非法状态: {status}')
    async with get_db_session() as session:
        result = await session.execute(
            update(Feedback)
            .where(
                Feedback.user_id == user_id,
                Feedback.feedback_key == feedback_key,
            )
            .values(status=status)
        )
        return result.rowcount > 0
