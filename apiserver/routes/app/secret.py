#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""前端秘钥管理路由"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from dao.secret_dao import (
    create_user_secret,
    delete_user_secret,
    list_user_secrets,
)

router = APIRouter()


class SecretCreate(BaseModel):
    name: str = ''


def _ok(data=None, message: str = 'ok', code: int = 200) -> dict:
    return {'code': code, 'message': message, 'data': data}


def _err(message: str, code: int) -> JSONResponse:
    return JSONResponse(
        status_code=code,
        content={'code': code, 'message': message, 'data': None},
    )


@router.get('')
async def list_secrets(request: Request):
    user = request.state.user
    secrets = await list_user_secrets(user.user_id)
    return _ok([s.to_dict() for s in secrets])


@router.post('')
async def add_secret(payload: SecretCreate, request: Request):
    name = (payload.name or '').strip()
    if not name:
        return _err('秘钥名称不能为空', 400)
    if len(name) > 64:
        return _err('秘钥名称长度不能超过 64 个字符', 400)
    user = request.state.user
    secret = await create_user_secret(user.user_id, name)
    return _ok(secret.to_dict(), message='秘钥创建成功', code=201)


@router.delete('/{secret_id}')
async def remove_secret(secret_id: int, request: Request):
    user = request.state.user
    ok = await delete_user_secret(secret_id, user.user_id)
    if not ok:
        return _err('秘钥不存在', 404)
    return _ok(None, message='秘钥删除成功')
