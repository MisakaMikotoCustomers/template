#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
支付宝服务 - 封装 RSA2 签名/验签 和支付链接生成
支持 alipay.trade.page.pay（PC端）和 alipay.trade.wap.pay（移动端）
"""

import base64
import hashlib
import json
import logging
import time
import urllib.parse
from typing import Dict

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey

from config_model import AlipayConfig
from dao.models import Order, Product

logger = logging.getLogger(__name__)

# 支付宝沙箱网关
_SANDBOX_GATEWAY = 'https://openapi-sandbox.dl.alipaydev.com/gateway.do'


def _load_private_key(pem_content: str) -> RSAPrivateKey:
    """加载 RSA 私钥（支持带/不带 PEM 头尾）"""
    pem_content = pem_content.strip()
    if not pem_content.startswith('-----'):
        pem_content = (
            '-----BEGIN PRIVATE KEY-----\n'
            + '\n'.join(pem_content[i:i+64] for i in range(0, len(pem_content), 64))
            + '\n-----END PRIVATE KEY-----'
        )
    return serialization.load_pem_private_key(
        pem_content.encode('utf-8'), password=None, backend=default_backend()
    )


def _load_public_key(pem_content: str) -> RSAPublicKey:
    """加载 RSA 公钥（支付宝公钥，支持带/不带 PEM 头尾）"""
    pem_content = pem_content.strip()
    if not pem_content.startswith('-----'):
        pem_content = (
            '-----BEGIN PUBLIC KEY-----\n'
            + '\n'.join(pem_content[i:i+64] for i in range(0, len(pem_content), 64))
            + '\n-----END PUBLIC KEY-----'
        )
    return serialization.load_pem_public_key(pem_content.encode('utf-8'), backend=default_backend())


def _build_sign_string(params: Dict) -> str:
    """构建签名原串：按 key 字母排序，过滤 sign/sign_type/空值，拼接 k=v&k=v"""
    items = sorted(
        ((k, v) for k, v in params.items() if k not in ('sign', 'sign_type') and v is not None and v != ''),
        key=lambda x: x[0]
    )
    return '&'.join(f'{k}={v}' for k, v in items)


def _rsa2_sign(sign_string: str, private_key: RSAPrivateKey) -> str:
    """RSA2（SHA256withRSA）签名，返回 base64 字符串"""
    signature = private_key.sign(
        sign_string.encode('utf-8'),
        padding.PKCS1v15(),
        hashes.SHA256()
    )
    return base64.b64encode(signature).decode('utf-8')


def _rsa2_verify(sign_string: str, signature_b64: str, public_key: RSAPublicKey) -> bool:
    """RSA2 验签"""
    try:
        signature = base64.b64decode(signature_b64)
        public_key.verify(
            signature,
            sign_string.encode('utf-8'),
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        return True
    except Exception as e:
        logger.warning("RSA2 verify failed: %s", e)
        return False


def build_pay_url(config: AlipayConfig, product: Product, order: Order, device: str) -> str:
    """
    生成支付宝支付 URL
    - device='pc': alipay.trade.page.pay（电脑网站支付）
    - device='mobile': alipay.trade.wap.pay（手机网站支付）
    返回可直接在浏览器打开的 URL
    """
    if device == 'mobile':
        method = 'alipay.trade.wap.pay'
        biz_content = {
            'out_trade_no': order.out_trade_no,
            'subject': product.title,
            'total_amount': f'{float(order.amount):.2f}',
            'product_code': 'QUICK_WAP_WAY',
        }
    else:
        method = 'alipay.trade.page.pay'
        biz_content = {
            'out_trade_no': order.out_trade_no,
            'subject': product.title,
            'total_amount': f'{float(order.amount):.2f}',
            'product_code': 'FAST_INSTANT_TRADE_PAY',
        }

    gateway = _SANDBOX_GATEWAY if config.sandbox else config.gateway

    params = {
        'app_id': config.app_id,
        'method': method,
        'format': 'JSON',
        'charset': 'utf-8',
        'sign_type': 'RSA2',
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'version': '1.0',
        'biz_content': json.dumps(biz_content, ensure_ascii=False),
        'notify_url': config.notify_url,
    }
    if config.return_url:
        params['return_url'] = config.return_url

    private_key = _load_private_key(config.app_private_key)
    sign_string = _build_sign_string(params)
    params['sign'] = _rsa2_sign(sign_string, private_key)

    return f"{gateway}?{urllib.parse.urlencode(params)}"


def verify_notify(config: AlipayConfig, post_data: Dict) -> bool:
    """
    验证支付宝异步通知签名
    post_data 为支付宝 POST 过来的所有参数
    """
    sign = post_data.get('sign', '')
    if not sign:
        return False

    # 构建待验证字符串（排除 sign 和 sign_type）
    sign_string = _build_sign_string(post_data)

    try:
        public_key = _load_public_key(config.alipay_public_key)
        return _rsa2_verify(sign_string, sign, public_key)
    except Exception as e:
        logger.exception("支付宝验签异常: %s", e)
        return False
