#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
订单 Service - 业务逻辑
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from dao import order_dao
from dao.models import Order, Product

logger = logging.getLogger(__name__)


def _generate_out_trade_no() -> str:
    """生成唯一商户订单号：时间戳 + UUID"""
    ts = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
    uid = uuid.uuid4().hex[:12].upper()
    return f'{ts}{uid}'


def create_order(user_id: int, product: Product, order_type: str) -> Order:
    """
    创建订单
    - 计算到期时间（如果商品有 expire_time）
    - 生成唯一 out_trade_no
    """
    out_trade_no = _generate_out_trade_no()

    expire_at: Optional[datetime] = None
    if product.expire_time:
        expire_at = datetime.now(timezone.utc) + timedelta(seconds=product.expire_time)

    order = order_dao.create_order(
        user_id=user_id,
        product_id=product.id,
        product_key=product.key,
        out_trade_no=out_trade_no,
        amount=float(product.price),
        order_type=order_type,
        expire_at=expire_at,
    )
    logger.info("订单创建: user_id=%s, product_key=%s, out_trade_no=%s",
                user_id, product.key, out_trade_no)
    return order


def confirm_paid(out_trade_no: str, trade_no: str):
    """
    确认订单支付成功（幂等）
    仅更新 pending 状态的订单，已 paid 的忽略
    """
    updated = order_dao.mark_order_paid(out_trade_no, trade_no)
    if updated:
        logger.info("订单支付确认: out_trade_no=%s, trade_no=%s", out_trade_no, trade_no)
    else:
        logger.info("订单已处理或不存在（幂等）: out_trade_no=%s", out_trade_no)
