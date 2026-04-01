# 投资助手 — Investment Assistant

个人投资决策支持系统，本地部署版本。

## 功能（Phase 1 — 股票数据同步）

- **多账户持仓同步**：富途 OpenAPI（港股+美股）、盈透 TWS（美股）、同花顺 CSV（A股）
- **统一持仓看板**：市值、盈亏、PE/PB、52周高低、今日涨跌
- **仓位分类**：抄底 / 防守 / 配置 / 波动 / 投机五种类型标注
- **实时行情刷新**：AKShare（免费）
- **关注列表**：新增、备注、目标价、止损价
- **移动端适配**：底部导航，手机浏览器可直接访问

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+ (前端)
- 富途 OpenD（如需同步富途数据）
- IB TWS 或 IB Gateway（如需同步盈透数据）

### 启动

```bash
git clone <repo>
cd investment-assistant
./start.sh
```

首次启动会自动：
1. 创建 Python 虚拟环境并安装依赖
2. 生成 `backend/.env` 配置文件
3. 安装前端 npm 依赖
4. 启动后端（port 8000）和前端（port 3000）

打开浏览器访问：**http://localhost:3000**

### 配置

编辑 `backend/.env`：

```env
# 富途 OpenD 配置
FUTU_HOST=127.0.0.1
FUTU_PORT=11111

# 盈透 TWS 配置
IB_HOST=127.0.0.1
IB_PORT=7497   # TWS 模拟盘: 7497 | 实盘: 7496

# 自动刷新行情间隔（秒），0 关闭
SYNC_INTERVAL=300

# 测试用：使用模拟数据，无需连接券商
USE_MOCK_DATA=false
```

### 富途 OpenD 设置

1. 打开 **富途牛牛 App**
2. 设置 → OpenAPI → 开启 OpenD
3. 默认端口 11111，确保防火墙未阻止
4. 启动脚本前先打开 OpenD

### 盈透 TWS 设置

1. 打开 **TWS** 或 **IB Gateway**
2. 全局配置 → API → 设置：勾选「Enable ActiveX and Socket Clients」
3. Socket 端口：模拟盘 7497 / 实盘 7496
4. 可信任 IP 加入 127.0.0.1

### A股（同花顺 CSV 导入）

1. 打开同花顺 → 交易 → 持股
2. 右键 → 导出数据 → 保存为 CSV
3. 在「同步」页面上传 CSV 文件

## 项目结构

```
investment-assistant/
├── backend/                  # Python FastAPI 后端
│   ├── main.py               # 应用入口
│   ├── config.py             # 配置管理
│   ├── database.py           # SQLite 数据库
│   ├── models/               # 数据模型
│   ├── schemas/              # Pydantic 数据结构
│   ├── brokers/              # 券商对接
│   │   ├── futu_broker.py    # 富途 OpenAPI
│   │   ├── ib_broker.py      # 盈透 TWS
│   │   ├── csv_importer.py   # 同花顺 CSV
│   │   └── mock_broker.py    # 模拟数据
│   ├── services/             # 业务逻辑
│   │   ├── market_data.py    # AKShare 行情
│   │   └── sync_service.py   # 同步协调
│   └── routers/              # API 路由
│       ├── accounts.py
│       ├── portfolio.py
│       ├── sync.py
│       └── watchlist.py
├── frontend/                 # Next.js 前端
│   └── src/
│       ├── app/              # 页面
│       ├── components/       # UI 组件
│       └── lib/              # API 客户端 & 类型
├── start.sh                  # 一键启动脚本
└── README.md
```

## API 文档

后端启动后访问：http://localhost:8000/docs

## Roadmap

- **Phase 2** — 交易策略引擎（仓位规则 + 合规检查 + 操作提醒）
- **Phase 3** — 资讯采集 + Claude AI 分析
- **Phase 4** — 策略回测系统
- **Phase 5** — 推送通知（微信/邮件）
