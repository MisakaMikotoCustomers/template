#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
admin 路由（仅 name=='admin' 的用户可访问）

反馈处理：
- GET   /api/admin/feedback                                 分页列出全部用户反馈
- GET   /api/admin/feedback/{user_id}/{feedback_key}        查看会话详情（含全部消息）
- POST  /api/admin/feedback/{user_id}/{feedback_key}/messages   以 admin 身份回复
- PATCH /api/admin/feedback/{user_id}/{feedback_key}/status 改变会话状态
"""

from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from dao.user_dao import get_user_by_user_id
from service.feedback_service import (
    change_feedback_status,
    get_feedback_detail_for_admin,
    list_all_feedbacks,
    reply_as_admin,
)
from service.user_service import UserServiceError

router = APIRouter()


class MessagePayload(BaseModel):
    content: str = ''


class StatusPayload(BaseModel):
    status: str = ''


def _ok(data=None, message: str = 'ok', code: int = 200) -> dict:
    return {'code': code, 'message': message, 'data': data}


def _err(message: str, code: int) -> JSONResponse:
    return JSONResponse(
        status_code=code,
        content={'code': code, 'message': message, 'data': None},
    )


@router.get('/ping')
async def ping(request: Request):
    return _ok({'admin': request.state.user.name})


@router.get('/feedback')
async def list_feedback(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, description='按状态筛选：open/processing/resolved/closed'),
):
    """管理员查看所有用户反馈（分页，可按状态筛选）。"""
    try:
        items, total = await list_all_feedbacks(page, page_size, status)
    except UserServiceError as e:
        return _err(e.message, e.code)

    rows = []
    for fb, last_msg, user_name in items:
        d = fb.to_dict(last_message=last_msg)
        d['user_name'] = user_name
        rows.append(d)

    return _ok({
        'total': total,
        'page': page,
        'page_size': page_size,
        'items': rows,
    })


@router.get('/feedback/{user_id}/{feedback_key}')
async def get_feedback_detail(user_id: int, feedback_key: str, request: Request):
    try:
        fb, messages = await get_feedback_detail_for_admin(user_id, feedback_key)
    except UserServiceError as e:
        return _err(e.message, e.code)

    # 附上用户名，便于页面展示
    user = await get_user_by_user_id(user_id)
    return _ok({
        'feedback': fb.to_dict(),
        'user': {'user_id': user_id, 'name': user.name if user else None},
        'messages': [m.to_dict() for m in messages],
    })


@router.post('/feedback/{user_id}/{feedback_key}/messages')
async def post_admin_reply(
    user_id: int, feedback_key: str, payload: MessagePayload, request: Request
):
    admin_user = request.state.user
    try:
        msg = await reply_as_admin(user_id, feedback_key, admin_user.name, payload.content)
    except UserServiceError as e:
        return _err(e.message, e.code)
    return _ok(msg.to_dict(), message='回复已发送', code=201)


@router.patch('/feedback/{user_id}/{feedback_key}/status')
async def patch_feedback_status(
    user_id: int, feedback_key: str, payload: StatusPayload, request: Request
):
    try:
        await change_feedback_status(user_id, feedback_key, payload.status)
    except UserServiceError as e:
        return _err(e.message, e.code)
    return _ok({'status': payload.status}, message='状态已更新')
