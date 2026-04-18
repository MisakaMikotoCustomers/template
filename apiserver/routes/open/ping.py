#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""open 路由：使用 X-Client-Secret 秘钥鉴权"""

from fastapi import APIRouter, Request

router = APIRouter()


@router.get('/ping')
async def ping(request: Request):
    """open 接口样例：返回当前秘钥所属 user_id。"""
    user = request.state.user
    return {
        'code': 200,
        'message': 'ok',
        'data': {'user_id': user.user_id, 'name': user.name},
    }
