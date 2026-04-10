# OpenAI-Compatible Local Aggregation Proxy / OpenAI 兼容本地聚合代理

This project runs a local `FastAPI` proxy in front of multiple OpenAI-compatible upstream relays.  
本项目在多个 OpenAI 兼容上游前面运行一个本地 `FastAPI` 代理。

Your client points at one local endpoint, and the proxy selects an upstream based on model support, priority, and temporary health state.  
你的客户端只需要指向一个本地入口，代理会根据模型支持、优先级和临时健康状态选择合适的上游。

The admin UI now supports both English and Chinese. It follows browser language by default and also supports manual switching in the top bar.  
管理界面现在同时支持英文和中文。默认会跟随浏览器语言，也可以在顶部栏手动切换。

## Features / 功能

- `POST /v1/chat/completions`
- `POST /v1/responses`
- `GET /v1/models`
- `GET /healthz`
- Streaming failover before the first chunk / 首包前的流式故障转移
- Non-streaming failover on timeout, connection errors, `429`, and `5xx`
- Priority-based routing with a simple circuit breaker / 基于优先级的路由与简单熔断
- Built-in admin UI at `/admin` / 内置 `/admin` 管理界面
- Persistent provider management with config writes and hot reload / Provider 配置写回与热重载
- In-memory recent request history and usage stats / 内存中的近期请求记录与用量统计
- Hourly metrics persisted to `./data/metrics/admin_hourly.json` for charts / 图表小时级指标会持久化到 `./data/metrics/admin_hourly.json`

## Quick Start / 快速开始

1. Install dependencies. / 安装依赖。  
2. Copy `config.example.yaml` to `config.yaml`. / 复制 `config.example.yaml` 为 `config.yaml`。  
3. Replace upstream URLs and configure your keys. / 替换上游地址并配置密钥。  
4. Start the proxy. / 启动代理。  

```powershell
uv sync --extra dev
Copy-Item config.example.yaml config.yaml
$env:RELAY_A_API_KEY="your-key-a"
$env:RELAY_B_API_KEY="your-key-b"
uv run vibecoding-board --config config.yaml
```

Default listen address / 默认监听地址:

- `http://127.0.0.1:9000`

Proxy endpoint / 代理入口:

- `http://127.0.0.1:9000/v1`

Admin UI / 管理界面:

- `http://127.0.0.1:9000/admin/`

## Admin UI / 管理界面

The admin UI supports:  
管理界面支持：

- overview, provider management, and traffic inspection / 总览、Provider 管理与流量查看
- adding, editing, deleting, enabling, and disabling providers / 新增、编辑、删除、启用与停用 Provider
- hot-updating provider priority / 热更新 Provider 优先级
- promoting a provider to global primary / 一键提升为主路由
- per-provider manual health checks / 单个 Provider 的手动健康检查
- English and Chinese UI switching / 中英文界面切换

Behavior notes / 行为说明:

- management changes write back to `config.yaml` / 管理操作会写回 `config.yaml`
- successful saves hot-reload the running proxy / 保存成功后会热重载正在运行的代理
- request history is memory only / 请求历史仅保存在内存中
- existing API keys are never sent back to the browser / 现有 API Key 不会回传到浏览器
- manual health checks can be configured to use standard or streaming mode globally / 手动健康检查支持全局切换为普通或流式模式

## Config / 配置

See [config.example.yaml](/D:/Codes/vibecoding-board/config.example.yaml).  
配置示例见 [config.example.yaml](/D:/Codes/vibecoding-board/config.example.yaml)。

Important notes / 重要说明:

- `base_url` should point at the upstream API root, usually ending in `/v1`  
  `base_url` 应指向上游 API 根路径，通常以 `/v1` 结尾
- lower `priority` values are tried first  
  `priority` 数字越小，越先参与路由
- `models: ["*"]` allows routing any model to that provider  
  `models: ["*"]` 表示该 Provider 可以接收任意模型名
- wildcard providers should set `healthcheck_model`  
  通配模型 Provider 建议设置 `healthcheck_model`
- `healthcheck.stream: true` makes manual admin health checks verify streaming startup before marking success  
  `healthcheck.stream: true` 会让管理界面的手动健康检查在确认流式输出启动后才判定成功

## Frontend Development / 前端开发

The built admin app is served from `vibecoding_board/static/admin`.  
构建后的管理前端会由 `vibecoding_board/static/admin` 提供。

If you want to iterate on frontend source:  
如果你要开发前端源码：

```powershell
cd web
npm install --cache .npm-cache
npm run dev
```

Build the production admin bundle:  
构建生产静态资源：

```powershell
cd web
npm run build
```

## Tests / 测试

Backend:

```powershell
$env:UV_CACHE_DIR="D:\Codes\vibecoding-board\.uv-cache"
uv run pytest
```

Frontend:

```powershell
cd web
npm run lint
npm run build
```

## Design Docs / 设计文档

- [2026-04-07-openai-aggregator-proxy-design.md](/D:/Codes/vibecoding-board/docs/superpowers/specs/2026-04-07-openai-aggregator-proxy-design.md)
- [2026-04-07-provider-management-hot-update-design.md](/D:/Codes/vibecoding-board/docs/superpowers/specs/2026-04-07-provider-management-hot-update-design.md)
- [2026-04-08-admin-shell-refactor-design.md](/D:/Codes/vibecoding-board/docs/superpowers/specs/2026-04-08-admin-shell-refactor-design.md)
