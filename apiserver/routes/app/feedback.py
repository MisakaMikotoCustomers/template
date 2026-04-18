#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
前端反馈路由

一个反馈 = 一个会话；会话内有多条消息（用户/平台方）。
- GET  /api/app/feedback               分页查询当前用户的反馈会话列表
- POST /api/app/feedback               新增反馈（附带首条消息）
- GET  /api/app/feedback/{key}         查看反馈会话详情（含全部消息）
- POST /api/app/feedback/{key}/messages 在已有会话中追加一条用户消息
"""

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from service.feedback_service import (
    create_feedback,
    get_user_feedback_detail,
    list_user_feedbacks,
    reply_as_user,
)
from service.user_service import UserServiceError

router = APIRouter()


class FeedbackCreate(BaseModel):
    content: str = ''


class MessageCreate(BaseModel):
    content: str = ''


def _ok(data=None, message: str = 'ok', code: int = 200) -> dict:
    return {'code': code, 'message': message, 'data': data}


def _err(message: str, code: int) -> JSONResponse:
    return JSONResponse(
        status_code=code,
        content={'code': code, 'message': message, 'data': None},
    )


@router.get('')
async def list_feedbacks(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """分页查询当前用户的反馈会话列表。"""
    user = request.state.user
    items, total = await list_user_feedbacks(user.user_id, page, page_size)
    return _ok({
        'total': total,
        'page': page,
        'page_size': page_size,
        'items': [fb.to_dict(last_message=last_msg) for fb, last_msg in items],
    })


@router.post('')
async def create_new_feedback(payload: FeedbackCreate, request: Request):
    """新增反馈会话（附首条用户消息）。"""
    user = request.state.user
    try:
        fb = await create_feedback(user.user_id, user.name, payload.content)
    except UserServiceError as e:
        return _err(e.message, e.code)
    return _ok(fb.to_dict(last_message=payload.content), message='反馈已提交', code=201)


@router.get('/{feedback_key}')
async def get_feedback_detail(feedback_key: str, request: Request):
    """查看反馈会话详情（含全部消息）。"""
    user = request.state.user
    try:
        fb, messages = await get_user_feedback_detail(user.user_id, feedback_key)
    except UserServiceError as e:
        return _err(e.message, e.code)
    return _ok({
        'feedback': fb.to_dict(),
        'messages': [m.to_dict() for m in messages],
    })


@router.post('/{feedback_key}/messages')
async def post_feedback_message(
    feedback_key: str, payload: MessageCreate, request: Request
):
    """在已有会话中追加一条用户消息。"""
    user = request.state.user
    try:
        msg = await reply_as_user(
            user.user_id, feedback_key, user.name, payload.content
        )
    except UserServiceError as e:
        return _err(e.message, e.code)
    return _ok(msg.to_dict(), message='已发送', code=201)
