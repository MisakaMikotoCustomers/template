# template

模板项目 - 当前所有新应用创建，默认使用这个模板

---

# 商品支付模板

基于 Python（Flask + Gunicorn + gevent）+ Vite 前端的商品购买与支付宝支付完整解决方案模板，支持生产环境高并发。

## 目录结构

```
template/
├── apiserver/          # 后端 API 服务
│   ├── main.py         # 启动入口（兼容 Gunicorn）
│   ├── config_model.py # 配置 dataclass
│   ├── config_example.toml  # 配置示例
│   ├── Dockerfile      # Python 3.11 + Gunicorn + gevent
│   ├── dao/            # 数据库访问层（纯 DB 操作）
│   │   ├── connection.py   # SQLAlchemy 连接池
│   │   ├── models.py       # ORM 模型（User / Product / Order）
│   │   ├── init_db.py      # 数据库初始化建表
│   │   ├── product_dao.py  # 商品 CRUD
│   │   ├── order_dao.py    # 订单 CRUD
│   │   └── user_dao.py     # 用户操作
│   ├── routes/         # HTTP 路由层
│   │   ├── auth_plugin.py  # 统一鉴权中间件
│   │   ├── commercial.py   # 商业化路由
│   │   ├── admin.py        # 管理后台路由
│   │   └── user.py         # 用户登录/注册
│   └── service/        # 业务逻辑层
│       ├── product_service.py
│       ├── order_service.py
│       ├── alipay_service.py  # 支付宝签名/验签（RSA2）
│       └── oss_service.py     # 腾讯云 COS 图片上传
└── web/                # 前端项目（Vite）
    ├── main.py         # Flask 静态文件服务
    ├── config_model.py
    ├── config_example.toml  # 含 business 开关
    ├── Dockerfile      # 多阶段：Node 构建 + Python 服务
    ├── build.sh        # 前端打包脚本（传入 tag 防缓存）
    ├── package.json    # Vite 项目
    ├── vite.config.js
    ├── index.html
    └── src/
        ├── main.js     # 主入口（商品列表 + 认证）
        ├── admin.js    # 管理后台逻辑
        ├── api.js      # API 客户端
        └── style.css
```

## 快速开始

### 一、ApiServer

#### 1. 配置文件

```bash
cp apiserver/config_example.toml apiserver/config.toml
# 编辑 config.toml，填写 MySQL、支付宝、OSS 等配置
```

#### 2. 本地运行（开发）

```bash
cd apiserver
pip install flask flask-cors werkzeug pymysql sqlalchemy tomli cryptography cos-python-sdk-v5 gunicorn gevent
python main.py --config config.toml
```

#### 3. 生产部署（Docker）

```bash
cd apiserver
docker build -t shop-apiserver .
docker run -d \
  -p 8080:8080 \
  -v $(pwd)/config.toml:/app/config.toml \
  -e API_CONFIG=/app/config.toml \
  shop-apiserver
```

### 二、Web 前端

#### 1. 配置文件

```bash
cp web/config_example.toml web/config.toml
# 编辑 config.toml，填写 apiserver 地址，按需开关 business
```

#### 2. 本地开发

```bash
cd web
npm install
npm run dev
```

#### 3. 构建（带版本标识防缓存）

```bash
cd web
./build.sh v1.2.3
# 构建产物输出到 dist/，资源文件名包含内容 hash
```

#### 4. 生产部署（Docker）

```bash
cd web
docker build --build-arg BUILD_TAG=v1.2.3 -t shop-web .
docker run -d \
  -p 8081:8081 \
  -v $(pwd)/config.toml:/app/config.toml \
  -e WEB_CONFIG=/app/config.toml \
  shop-web
```

## API 接口说明

### 商业化接口

| 方法 | 路径 | 描述 | 认证 |
|------|------|------|------|
| GET  | `/api/commercial/products` | 商品列表 | 无 |
| POST | `/api/commercial/buy` | 生成支付宝支付链接 | Bearer Token |
| POST | `/api/commercial/alipay/notify` | 支付宝异步回调 | 签名验证 |

### 管理接口

| 方法 | 路径 | 描述 | 认证 |
|------|------|------|------|
| POST | `/api/admin/product` | 新增商品 | Bearer Token（admin） |
| GET  | `/api/admin/orders` | 查询购买记录 | Bearer Token（admin） |
| POST | `/api/admin/upload/icon` | 上传商品封面图 | Bearer Token（admin） |

### 用户接口

| 方法 | 路径 | 描述 | 认证 |
|------|------|------|------|
| POST | `/api/user/register` | 注册 | 无 |
| POST | `/api/user/login` | 登录 | 无 |
| GET  | `/api/user/me` | 当前用户 | Bearer Token |

## 商品字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| key | string | 是 | 商品唯一标识 |
| title | string | 是 | 商品名称 |
| desc | string | 否 | 商品描述（支持富文本 HTML） |
| price | float | 是 | 价格（元），精度 0.01 |
| expire_time | int | 否 | 购买后有效时长（秒），null=永久 |
| support_continue | bool | 否 | 是否支持续费，默认 false |
| icon | string | 否 | 商品封面图 URL |

## 支付宝配置说明

1. 登录支付宝开放平台，创建应用
2. 开通「电脑网站支付」和「手机网站支付」功能
3. 配置应用 RSA2 公私钥
4. 将 `notify_url` 设置为公网可访问的回调地址
5. 沙箱测试：将 `sandbox = true` 并使用沙箱 appid

## 高并发设计

- **Gunicorn + gevent**：`--worker-class gevent --workers 4 --worker-connections 1000`，单节点支持数千并发
- **连接池**：SQLAlchemy `pool_size=20, max_overflow=40`
- **幂等回调**：支付宝通知仅更新 `status='pending'` 的订单，防重复处理
- **唯一约束**：`out_trade_no` 数据库唯一索引，防并发重复创建

## 前端缓存策略

- Vite 构建时自动为 JS/CSS 文件名加内容 hash（如 `main-a1b2c3d4.js`）
- `./build.sh <tag>` 中的 `tag` 参数通过环境变量 `VITE_BUILD_TAG` 注入前端代码，可用于日志追踪版本

## business 开关

`web/config.toml` 中设置 `business = false` 时，前端不渲染任何商品购买相关页面和入口，适用于非商业化部署场景。
