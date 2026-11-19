# 账单查询分析系统（Bill Query）

一个可本地运行的 **微信支付 / 支付宝账单 / 银行流水** 导入与分析项目。支持多文件合并、ZIP 直传、智能分类、多维统计分析、消费洞察、预算管理、自然语言查询、交易标注、跨账单检索、年度报告与商户画像，并可导出多 Sheet Excel 报告、打印友好报告页与整库备份。

> 目录：`skills/物料停启用Agent/大小群迭代/1105`

---

## 功能特性

### 账单解析
- **格式自适应**：自动扫描前 40 行定位真正表头，兼容微信账单（含标题行、说明行、汇总行）、支付宝账单与银行流水
- **列名模糊匹配**：`交易时间/交易日期/交易创建时间`、`金额(元)/发生额/交易金额` 等常见别名自动映射
- **渠道自动识别**：微信支付 / 支付宝 / 银行 / 多来源合并 / 通用
- **多文件合并**：一次上传多个账单（或多选 CSV/XLSX），自动合并为一个数据集
- **ZIP 直传**：支持微信/支付宝导出的加密压缩包，填写 6 位解压密码即可自动解压导入
- **跨文件去重**：优先按交易号去重，缺失交易号时按「时间+金额+方向+对方」组合键去重
- **收支方向推断**：优先读取 `收/支`、`借贷标志`，识别失败时回退到金额正负与关键词
- **编码兼容**：UTF-8 / UTF-8-BOM / GBK / GB18030 / UTF-16 依次尝试
- **容错解析**：单行解析失败自动跳过并记录，不影响整体导入
- **转账标记**：自动识别转账、红包、提现、充值、还款、退款、零钱通、余额宝、内部划转、群收款，可在筛选时一键剔除

### 智能分类
- **规则引擎**：基于配置化的关键词表（`config.yaml` → `billing.categories`）做最长关键词优先匹配
- **11 大类预置**：餐饮美食、交通出行、日用百货、服饰鞋包、住房物业、医疗健康、文教娱乐、通讯数码、投资理财、转账红包、其他
- **可扩展**：新增分类只需改 yaml，无需改代码
- **原始分类优先**：账单自带分类时直接沿用

### 统计分析
| 维度 | 说明 |
|---|---|
| 总览 | 收入/支出/净收支、日均支出、笔均支出、最大/最小/中位数、储蓄率、本月预测支出、转账笔数 |
| 趋势 | 按日 / 周 / 月 / 年聚合的收支趋势，点击月份可下钻 |
| 分类占比 | 支出与收入分类金额、笔数、占比，点击分类可直接筛选 |
| 交易对方 | TOP N 排行，点击对方可联动关键词筛选 |
| 星期分布 | 一周七天消费金额与笔数，点击星期可筛选 |
| 时段分布 | 0-23 点消费分布，用于发现消费高峰 |
| 7×24 热力图 | 星期 × 小时双维度消费金额热力矩阵，快速定位消费习惯 |
| 月度环比 | 最近两个自然月金额、笔数、各分类差额与变化百分比 |
| 消费洞察 | 大额消费、高频商户、深夜消费、疑似订阅、环比异动、储蓄率六类规则洞察 |
| 预算执行 | 月预算进度环 + 分类预算进度条，超支高亮 |
| 大额明细 | TOP N 单笔支出 |
| 年度概览 | 年份切换、8 项年度 KPI、12 个月收支矩阵（点击月份下钻） |
| 分类月度趋势 | 支出分类逐月堆叠面积/柱状图，观察结构变化 |
| 累计支出曲线 | 按日累计支出，观察消费进度与月度节奏 |
| 商户画像 | 单笔数/累计/笔均/最大额/活跃月数/平均消费间隔 + 按月/时段/分类/商品四维拆解 |

### 标注与检索
- **交易标注**：给任意交易打标签、写备注、标记「忽略」，明细表内直接操作
- **忽略过滤**：勾选「排除已忽略的交易」后，卡片/图表/日历/明细/导出口径同步排除
- **全局搜索**：顶栏搜索框跨账单检索交易对方、商品、分类、交易号、时间
- **SQLite 索引**：交易写入本地索引库（`data/bills.db`），支持毫秒级跨账单检索与一键重建
- **数据管理面板**：查看索引统计、重建索引

### 报告与运维
- **打印友好报告页**：`/report/<bill_id>` 单页汇总 KPI、年度矩阵、分类条、商户表、洞察与环比，支持浏览器直接打印/存 PDF
- **API 文档页**：`/apidocs` 自动遍历路由生成接口清单
- **整库备份/恢复**：`/api/backup` 打包 pkl + 索引 + 预算 + 标注为 ZIP，`/api/restore` 上传还原

### 查询与导出
- 多维筛选：日期区间、收/支、分类、关键词（对方/商品/单号/备注）、金额区间、星期、剔除转账、排除已忽略
- **快捷日期**：今天 / 本周 / 本月 / 上月 / 今年 / 近 180 天
- **自然语言查询**：如「本月支出大于100」「上个月餐饮」「美团一共花了多少」「今年收入」
- **图表下钻**：趋势、分类、对方、星期图表点击即联动筛选；点击对方名称打开商户画像抽屉
- 分页 + 字段排序；日历热力图点击某天可筛选该日
- 导出 **Excel 多 Sheet 报告**（汇总 / 明细 / 月度趋势 / 分类 / 收入分类 / TOP / 星期 / 时段 / 大额 / 消费洞察 / 7x24 热力 / 环比对比）
- 导出 **CSV 明细**（UTF-8-BOM，Excel 直接打开不乱码）
- 页面内置 **数据口径说明**，明确分类占比、星期分布、对方累计、筛选一致性等计算规则

---

## 快速开始

```bash
cd "skills/物料停启用Agent/大小群迭代/1105"

pip install -r requirements.txt

# 生成示例账单（可选）
python tests/make_sample.py

# 启动服务
python app.py
# 浏览器访问 http://127.0.0.1:5105
```

### 命令行参数

```bash
python app.py --port 8080 --host 127.0.0.1 --debug
```

### Docker 运行

```bash
docker compose up -d --build
# 访问 http://127.0.0.1:5105
```

`docker-compose.yml` 会把宿主机 `./data` 挂载到容器内，账单数据与预算配置持久化保存。

---

## 目录结构

```
1105/
├── app.py                     # 启动入口
├── config.yaml                # 全局配置（端口/分类关键词/收入关键词）
├── requirements.txt
├── Dockerfile                 # 容器镜像
├── docker-compose.yml         # 一键编排
├── bill_query/                # 核心业务包
│   ├── __init__.py
│   ├── settings.py            # 配置加载与日志
│   ├── normalizer.py          # 账单解析归一化（微信/支付宝/银行）
│   ├── classifier.py          # 分类引擎 + 转账标记
│   ├── repository.py          # 数据集仓库、多文件合并、去重、ZIP 解压、查询过滤
│   ├── store.py               # SQLite 索引层（跨账单检索）
│   ├── annotations.py         # 交易标注（标签/备注/忽略）
│   ├── analytics.py           # 统计分析、热力图、环比、洞察、预算、自然语言查询
│   ├── exporter.py            # CSV/Excel 导出
│   ├── api.py                 # Flask 路由
│   └── cli.py                 # 命令行入口
├── templates/
│   ├── index.html             # 单页界面
│   ├── report.html            # 打印友好报告页
│   └── apidocs.html           # API 文档页
├── static/
│   ├── style.css
│   └── app.js                 # 前端逻辑 + Chart.js 图表 + 下钻联动
├── tests/
│   ├── make_sample.py         # 生成微信/银行示例账单
│   ├── test_bill.py           # 基础单元测试（11 个用例）
│   ├── test_features.py       # 扩展功能测试（41 个用例）
│   ├── demo_fake_bill.py      # 生成 630 笔 180 天演示账单
│   ├── verify_filters.py      # 筛选口径一致性校验
│   ├── _smoke_new.py          # 第一轮接口冒烟
│   ├── _smoke_extra.py        # 第二轮接口冒烟（索引/标注/年度/画像/报告/备份）
│   ├── _ui_check.py           # Playwright 页面渲染冒烟
│   └── smoke_api.py           # 服务冒烟测试
└── data/
    ├── upload/                # 上传原始文件
    ├── bills/                 # 解析后的数据集（pkl）
    ├── export/                # 导出文件
    ├── logs/                  # 运行日志
    ├── bills.db               # SQLite 检索索引（可重建）
    ├── budgets.json           # 预算配置
    ├── annotations.json       # 交易标注
    └── sample/                # 示例账单
```

---

## 配置说明（config.yaml）

```yaml
app:
  port: 5105                  # 服务端口
  max_upload_mb: 50           # 上传大小限制

billing:
  currency: CNY
  income_keywords:            # 收支方向识别辅助关键词
    - 收入
    - 收钱码收款
    - 转账-来自
  ignore_types:               # 可忽略的交易类型
    - 零钱提现
    - 充值
  categories:                 # 分类规则：分类名 -> 关键词列表
    餐饮美食: [美团, 饿了么, 餐厅, 咖啡, ...]
    交通出行: [滴滴, 地铁, 公交, 12306, ...]
```

新增一个分类：

```yaml
billing:
  categories:
    宠物用品: [宠物, 猫粮, 狗粮, 宠物医院]
```

---

## API 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/bills/upload` | 上传并解析账单，返回 `bill_id` 与汇总 |
| POST | `/api/bills/preview` | 仅预览解析结果（不落库） |
| GET | `/api/bills` | 历史账单列表 |
| GET | `/api/bills/<bill_id>` | 账单基本信息 |
| DELETE | `/api/bills/<bill_id>` | 删除账单 |
| GET | `/api/bills/<bill_id>/transactions` | 分页查询明细（支持全部筛选参数） |
| GET | `/api/bills/<bill_id>/overview` | 汇总统计 |
| GET | `/api/bills/<bill_id>/trend?freq=month` | 趋势（day/week/month/year） |
| GET | `/api/bills/<bill_id>/categories` | 分类统计 |
| GET | `/api/bills/<bill_id>/counterparties?top=20` | 交易对方排行 |
| GET | `/api/bills/<bill_id>/weekday` | 星期分布 |
| GET | `/api/bills/<bill_id>/hours` | 时段分布 |
| GET | `/api/bills/<bill_id>/top?top=20` | 大额明细 |
| GET | `/api/bills/<bill_id>/monthly-comparison` | 月度对比 |
| GET | `/api/bills/<bill_id>/heatmap?direction=支出` | 7×24 消费热力矩阵 |
| GET | `/api/bills/<bill_id>/comparison?direction=支出` | 最近两个自然月环比 |
| GET | `/api/bills/<bill_id>/insights` | 规则型消费洞察 |
| GET | `/api/bills/<bill_id>/budget` | 预算执行情况 |
| POST | `/api/bills/<bill_id>/budget` | 保存预算（`{monthly, categories}`） |
| GET | `/api/bills/<bill_id>/nl-query?q=...` | 自然语言查询 |
| GET | `/api/bills/<bill_id>/report` | 完整分析报告（一次性返回全部维度） |
| GET | `/api/bills/<bill_id>/year-report?year=2026` | 年度报告（12 月矩阵 + 分类/商户/支付方式 TOP） |
| GET | `/api/bills/<bill_id>/merchant?name=美团` | 商户画像（笔数/金额/间隔/按月/时段/分类/商品） |
| GET | `/api/bills/<bill_id>/category-trend?top=6` | 分类逐月堆叠趋势 |
| GET | `/api/bills/<bill_id>/cumulative` | 按日累计支出曲线 |
| GET | `/api/bills/<bill_id>/annotations` | 标注汇总（标签/备注/忽略） |
| POST | `/api/bills/<bill_id>/annotations` | 保存标注（`{key, tag, note, ignored}`） |
| DELETE | `/api/bills/<bill_id>/annotations` | 删除标注（`{key}` 或 `?key=`） |
| GET | `/api/search?q=美团&limit=100&bill_id=` | 跨账单关键词检索 |
| GET | `/api/store/stats` | 索引统计（账单数/行数/金额） |
| POST | `/api/store/rebuild` | 全量重建 SQLite 索引 |
| GET | `/api/bills/<bill_id>/export?format=xlsx\|csv` | 导出 |
| GET | `/report/<bill_id>` | 打印友好 HTML 报告页 |
| GET | `/apidocs` | API 文档页（自动列出全部路由） |
| GET | `/api/backup` | 打包下载整库备份 ZIP |
| POST | `/api/restore` | 上传备份 ZIP 还原 |
| GET | `/api/health` | 健康检查 |
| GET | `/api/meta` | 元信息（分类列表、币种等） |

### 通用筛选参数

`start_date`、`end_date`、`direction`、`category`、`keyword`、`min_amount`、`max_amount`、`weekday`（1-7，周一=1）、`exclude_transfer`（传 `1` 剔除转账/退款）、`exclude_ignored`（传 `1` 排除已忽略交易）

### 调用示例

```bash
# 上传单个账单
curl -F "file=@data/sample/wx_sample.csv" http://127.0.0.1:5105/api/bills/upload

# 多文件合并上传
curl -F "files=@wx_2025.csv" -F "files=@alipay_2025.csv" http://127.0.0.1:5105/api/bills/upload

# 上传加密 ZIP（密码 6 位）
curl -F "files=@bills.zip" -F "zip_password=123456" http://127.0.0.1:5105/api/bills/upload

# 查询支出中关键词为"美团"的记录
curl "http://127.0.0.1:5105/api/bills/<bill_id>/transactions?direction=支出&keyword=美团&page=1&size=20"

# 自然语言查询
curl "http://127.0.0.1:5105/api/bills/<bill_id>/nl-query?q=本月支出大于100"

# 导出 Excel 报告
curl -o report.xlsx "http://127.0.0.1:5105/api/bills/<bill_id>/export?format=xlsx"

# 跨账单搜索
curl "http://127.0.0.1:5105/api/search?q=美团&limit=20"

# 商户画像
curl "http://127.0.0.1:5105/api/bills/<bill_id>/merchant?name=美团"

# 给交易打标（key 可由明细接口返回的 row_key 获得）
curl -X POST -H "Content-Type: application/json" \
  -d '{"key":"no:4200001234","tag":"报销","note":"出差","ignored":false}' \
  "http://127.0.0.1:5105/api/bills/<bill_id>/annotations"

# 整库备份 / 恢复
curl -o backup.zip "http://127.0.0.1:5105/api/backup"
curl -F "file=@backup.zip" "http://127.0.0.1:5105/api/restore"
```

---

## 支持的账单格式

### 微信支付账单（CSV/ZIP）
微信「我 → 服务 → 钱包 → 账单 → 常见问题 → 下载账单」导出。系统会自动跳过开头的昵称/时间说明行，定位到 `交易时间,交易类型,交易对方,商品,收/支,金额(元),...` 表头，并忽略末尾的 `----------------------微信支付账单明细列表--------------------` 与 `共 N 笔记录`。官方导出的加密 ZIP 可直接上传，填写邮件中收到的 6 位密码即可。

### 支付宝账单（CSV）
支付宝「我的 → 账单 → 开具交易流水证明」导出。列名 `交易创建时间 / 交易对方 / 商品名称 / 金额（元）/ 收/支 / 交易状态 / 交易号 / 商家订单号` 已内置映射，GBK 编码自动识别。

### 银行流水（Excel/CSV）
需包含日期、金额列；`摘要`、`对方户名`、`借贷标志`、`流水号` 等列自动识别。支持表头上方存在标题行的情况。

---

## 测试

```bash
# 基础单元测试（11 个用例）
python -m unittest tests.test_bill -v

# 扩展功能测试（41 个用例：支付宝/ZIP/去重/热力图/环比/洞察/NL/预算/
#   SQLite 索引/标注/年度报告/商户画像/分类趋势/累计曲线/新路由）
python -m unittest tests.test_features -v

# 全量回归（52 个用例）
python -m unittest tests.test_bill tests.test_features

# 生成示例数据
python tests/make_sample.py

# 接口冒烟（需先启动 app.py）
python tests/_smoke_new.py
python tests/_smoke_extra.py

# 页面渲染冒烟（Playwright）
python tests/_ui_check.py

# 服务冒烟测试
python tests/smoke_api.py
```

---

## 技术栈

- Python 3.9+
- Flask 3.x（Web 服务）
- pandas（数据处理）
- SQLite（可重建的检索索引，随 Python 内置）
- openpyxl（Excel 读写）
- Chart.js 4（前端图表，CDN 加载）
- Docker / docker-compose（可选部署方式）

---

## 常见问题

**Q: 上传后提示「无法识别必要列」？**
A: 说明没找到表头行。确认账单中含有「交易时间/交易日期/交易创建时间」与「金额/发生额」列，可在 `/api/bills/preview` 查看识别结果。

**Q: 支付宝账单被识别成微信支付？**
A: 旧版本会把「收/支」列误判为微信特征。现已改为优先匹配「支付宝交易记录 / 商家订单号」等支付宝特征，重新上传即可。

**Q: 上传 ZIP 提示已加密？**
A: 在左侧「ZIP 解压密码」填写微信/支付宝邮件里的 6 位数字密码后重新上传。

**Q: 分类不正确？**
A: 编辑 `config.yaml` 的 `billing.categories`，关键词越长优先级越高，无需重启可直接生效于新上传的账单。

**Q: 筛选 1~100 元后，合计金额比预期大？**
A: 所有筛选条件都会同时作用于卡片、图表、日历、明细和导出，属于同一口径。若合计仍不符，请确认是否勾选了「剔除转账」——转账/红包/退款也会计入收支。

**Q: 交易对方 TOP 里金额特别高（如美团 ¥4093）？**
A: 这是该对方在当前区间内的**累计金额**，不是单笔金额。可在「消费洞察」里看到笔均与笔数。

**Q: 分类占比是按笔数还是按金额？**
A: 按金额。计算方式为「该分类金额合计 ÷ 全部支出合计 × 100%」。星期/时段分布同理，统计金额并求和，不做百分比。

**Q: 自然语言查询识别不到我的商户名？**
A: 该功能是规则匹配（非大模型），会把问题中的中文片段与账单里的对方名称做互相包含匹配；商户名差异过大时建议直接用「关键词」筛选。

**Q: 账单数据存哪里？**
A: 解析后的 DataFrame 以 pickle 格式存于 `data/bills/<bill_id>.pkl`（权威数据源），原始文件存于 `data/upload/`，预算存于 `data/budgets.json`，交易标注存于 `data/annotations.json`，跨账单检索索引存于 `data/bills.db`（SQLite，可随时重建，删除不影响主流程）。删除记录调用 `DELETE /api/bills/<bill_id>`。

**Q: 搜索框搜不到刚上传的账单？**
A: 搜索依赖 SQLite 索引，正常上传会自动写入。若手动删过 `data/bills.db`，到「数据管理」面板点「重建索引」即可（等价于 `POST /api/store/rebuild`）。

**Q: 勾选「排除已忽略的交易」后金额变小了？**
A: 这是预期行为。被标记为忽略的交易会在卡片、图表、日历、明细和导出中统一排除，与其它筛选参数同一口径。

**Q: 如何备份或迁移数据？**
A: 顶栏「备份」导出 ZIP（包含全部 pkl、索引、预算、标注），在新环境通过「恢复」上传该 ZIP 即可；恢复后会自动清空内存缓存。
