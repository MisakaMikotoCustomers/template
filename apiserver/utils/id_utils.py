#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""ID / Key 生成工具"""

import secrets
import string

_FEEDBACK_KEY_ALPHABET = string.ascii_letters + string.digits  # 62 字符


def random_feedback_key(length: int = 8) -> str:
    """生成随机 feedback_key。

    使用大小写字母+数字，默认 8 位。与 user_id 组合保证唯一。
    """
    return ''.join(secrets.choice(_FEEDBACK_KEY_ALPHABET) for _ in range(length))
