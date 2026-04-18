#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""反馈业务层：会话 + 对话消息 + 状态流转"""

from typing import List, Optional, Tuple

from dao import feedback_dao
from dao.models import Feedback, FeedbackMessage
from service.user_service import UserServiceError


MAX_MESSAGE_LENGTH = 5000


def _ensure_content(content: str) -> str:
    content = (content or '').strip()
    if not content:
        raise UserServiceError('内容不能为空')
    if len(content) > MAX_MESSAGE_LENGTH:
        raise UserServiceError(f'内容不能超过 {MAX_MESSAGE_LENGTH} 个字符')
    return content


# ===================== 用户侧 =====================

async def create_feedback(user_id: int, sender_name: str, content: str) -> Feedback:
    content = _ensure_content(content)
    return await feedback_dao.create_feedback_session(user_id, sender_name, content)


async def reply_as_user(
    user_id: int, feedback_key: str, sender_name: str, content: str
) -> FeedbackMessage:
    content = _ensure_content(content)
    msg = await feedback_dao.append_feedback_message(
        user_id=user_id,
        feedback_key=feedback_key,
        sender_type=FeedbackMessage.SENDER_USER,
        sender_name=sender_name,
        content=content,
    )
    if not msg:
        raise UserServiceError('反馈会话不存在', code=404)
    return msg


async def list_user_feedbacks(
    user_id: int, page: int, page_size: int
) -> Tuple[List[Tuple[Feedback, Optional[str]]], int]:
    page = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or 20), 100))
    return await feedback_dao.list_feedbacks_by_user(user_id, page, page_size)


async def get_user_feedback_detail(
    user_id: int, feedback_key: str
) -> Tuple[Feedback, List[FeedbackMessage]]:
    fb = await feedback_dao.get_feedback_session(user_id, feedback_key)
    if not fb:
        raise UserServiceError('反馈不存在', code=404)
    messages = await feedback_dao.list_feedback_messages(user_id, feedback_key)
    return fb, messages


# ===================== 管理员侧 =====================

async def list_all_feedbacks(
    page: int, page_size: int, status: Optional[str] = None
):
    page = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or 20), 100))
    if status and status not in Feedback.ALLOWED_STATUS:
        raise UserServiceError('非法的状态筛选', code=400)
    return await feedback_dao.list_all_feedbacks(page, page_size, status)


async def get_feedback_detail_for_admin(
    user_id: int, feedback_key: str
) -> Tuple[Feedback, List[FeedbackMessage]]:
    fb = await feedback_dao.get_feedback_session(user_id, feedback_key)
    if not fb:
        raise UserServiceError('反馈不存在', code=404)
    messages = await feedback_dao.list_feedback_messages(user_id, feedback_key)
    return fb, messages


async def reply_as_admin(
    user_id: int, feedback_key: str, admin_name: str, content: str
) -> FeedbackMessage:
    content = _ensure_content(content)
    msg = await feedback_dao.append_feedback_message(
        user_id=user_id,
        feedback_key=feedback_key,
        sender_type=FeedbackMessage.SENDER_ADMIN,
        sender_name=admin_name,
        content=content,
    )
    if not msg:
        raise UserServiceError('反馈会话不存在', code=404)
    return msg


async def change_feedback_status(
    user_id: int, feedback_key: str, status: str
) -> None:
    if status not in Feedback.ALLOWED_STATUS:
        raise UserServiceError('非法的状态值', code=400)
    ok = await feedback_dao.update_feedback_status(user_id, feedback_key, status)
    if not ok:
        raise UserServiceError('反馈不存在', code=404)
