# 基金补仓管家

按最新投委会规则实现的命令行版本，用于根据 250 个交易日高点回撤规则提醒补仓。

## 功能

- 仅监控纳指和恒生科技等高波动成长资产。
- 使用最近 250 个交易日最高净值作为阶段高点。
- 回撤达到 10%、15%、20% 时分别触发三档补仓提醒。
- 支持 `strategy_activation_date` 策略启用日；启用日前已经发生的回撤不追补。
- 每档只触发一次，创新高后重置触发记录。
- 用户确认后才记录补仓成功，并扣减子弹仓余额。
- 每次每日检查会写入 `data/daily_log.json`，同一天同一基金重复运行会更新记录。
- 支持每日检查邮件推送，邮件发送失败不会中断主流程。
- 生活账户资金永不参与补仓计算。

## 项目结构

```text
DrawdownGuard/
├── main.py                  # CLI 入口
├── drawdownguard/           # 策略、数据、回测、通知等核心模块
├── tests/                   # 单元测试
├── scripts/                 # 自动运行脚本
├── data/                    # JSON 运行产物
├── reports/                 # 文本日志和图表输出
└── docs/                    # PRD 和补充使用文档
```

核心业务代码已移动到 `drawdownguard/` 包内；`main.py` 保留在根目录，所有既有 CLI 命令仍从根目录执行。

## 使用

安装依赖：

```bash
python3 -m pip install -r requirements.txt
```

V2.2 回测可视化依赖 `matplotlib`。如果只安装最小依赖，也可以单独安装：

```bash
python3 -m pip install matplotlib
```

默认配置使用 AKShare 读取真实基金历史净值：

```json
{
  "data_source": "real",
  "strategy_activation_date": "2026-06-09"
}
```

运行每日检查：

```bash
python3 main.py run
```

确认某只基金某档补仓已执行：

```bash
python3 main.py confirm 270042 10
```

设置子弹仓余额：

```bash
python3 main.py set-cash 3000
```

查看执行日志：

```bash
python3 main.py transactions
```

查看最近 10 条每日检查日志：

```bash
python3 main.py logs
```

运行历史回测：

```bash
python3 main.py backtest
```

运行资产级历史回测：

```bash
python3 main.py asset-backtest
python3 main.py asset-backtest-report
```

运行组合级定投加补仓回测：

```bash
python3 main.py portfolio-backtest
python3 main.py fund-check
python3 main.py asset-dca-audit DIVIDEND_LOW_VOL
python3 main.py portfolio-report
python3 main.py contribution-report
python3 main.py contribution-detail
python3 main.py weekly-dca
python3 main.py dca-strategy-lab --preset quick
python3 main.py dca-strategy-report
python3 main.py portfolio-strategy-synth
python3 main.py portfolio-strategy-report
python3 main.py portfolio-optimize --preset quick
python3 main.py portfolio-optimize-report
python3 main.py portfolio-optimize-continuous --preset quick
python3 main.py portfolio-optimize-continuous-report
python3 main.py strategy-lab
python3 main.py strategy-lab-report
python3 main.py take-profit-backtest
python3 main.py take-profit-report
python3 main.py risk-compare
python3 main.py risk-compare-report
python3 main.py take-profit-optimizer
python3 main.py take-profit-optimizer-report
```

查看最近一次回测摘要：

```bash
python3 main.py backtest-report
```

运行多参数回测场景：

```bash
python3 main.py backtest-scenarios
```

生成回测可视化图表：

```bash
python3 main.py backtest-plot
python3 main.py backtest-plot --all
```

只绘制单个 scenario：

```bash
python3 main.py backtest-plot --source scenarios --scenario S001
```

发送邮件提醒：

```json
{
  "email": {
    "enabled": true,
    "send_only_when_action_required": true
  }
}
```

手动运行每日检查脚本：

```bash
./scripts/run_daily.sh
```

脚本会自动进入项目目录、激活 `.venv`、执行 `python3 main.py run`，并将输出保存到 `reports/logs/run_YYYY-MM-DD.txt`。

## 数据

配置文件是 `config.yaml`。当前使用 JSON/YAML 兼容格式，避免引入第三方依赖。

`data_source` 支持：

- `real`：使用 AKShare 按基金代码获取单位净值走势。
- `local`：读取本地 `nav_data.json`。

当 `data_source` 为 `real` 且 AKShare 获取失败时，系统会自动 fallback 到 `local`，并在报告中输出提示。

本地备用净值数据文件是 `nav_data.json`，格式如下：

```json
{
  "270042": [
    { "date": "2026-01-01", "nav": 1.5 },
    { "date": "2026-06-09", "nav": 1.32 }
  ]
}
```

数据不足 250 条时系统仍会运行，但报告中会提示当前净值数据条数不足。

## 每日检查日志

`python3 main.py run` 每次运行后会写入 `data/daily_log.json`。

每条日志包含：

- `date`
- `fund_code`
- `fund_name`
- `nav`
- `peak_nav`
- `drawdown`
- `status`
- `suggestions`
- `data_source`
- `warnings`

同一天同一基金重复运行时，会更新当天记录，不会重复追加。

`scripts/run_daily.sh` 的终端输出会额外保存到 `reports/logs/run_YYYY-MM-DD.txt`，该目录下的 `.txt` 运行日志默认不纳入版本管理。

## Windows 任务计划程序

可以用 Windows 任务计划程序每天 13:30 自动运行 WSL 中的脚本。

注意：

- 脚本只生成提醒和日志，不自动交易。
- 用户需要在 15:00 前手动决定是否执行补仓。
- 如果电脑当天未开机，则不会自动运行，需要手动执行 `bash scripts/run_daily.sh`。

1. 打开“任务计划程序”。
2. 选择“创建基本任务”。
3. 名称填写 `DrawdownGuard Daily Run`。
4. 触发器选择“每天”，时间设置为 `13:30`。
5. 操作选择“启动程序”。
6. 程序或脚本填写：

```text
wsl.exe
```

7. 添加参数填写：

```text
bash -lc "cd /home/xingke233/projects/apps/DrawdownGuard && ./scripts/run_daily.sh"
```

8. 保存后可右键任务选择“运行”进行一次手动验证。

如果你的 WSL 发行版不是默认发行版，可以把参数改为：

```text
-d Ubuntu bash -lc "cd /home/xingke233/projects/apps/DrawdownGuard && ./scripts/run_daily.sh"
```

## 策略启用日

`strategy_activation_date` 用于避免追补历史回撤。

- 策略启用日前已经跌破的 10%、15%、20% 档位，不自动生成补仓建议。
- 这类基金会显示 `状态：历史回撤`，建议为 `不追补历史档位。`
- 如果启用日已处于 20% 以上深度回撤，会显示 `状态：深度回撤中`，建议为 `不追补历史档位，继续观察`。
- 启用日后继续下跌并新跌破的档位，才会生成补仓建议。
- 创新高后会重置触发记录和历史回撤基线，后续重新按正常规则运行。

## 邮件推送

`config.yaml` 中的 `email` 配置控制每日邮件推送。默认是示例配置，且 `enabled` 为 `false`。

```json
{
  "email": {
    "enabled": false,
    "smtp_host": "smtp.example.com",
    "smtp_port": 587,
    "use_tls": true,
    "username": "sender@example.com",
    "password": "your_app_password",
    "sender": "sender@example.com",
    "receivers": ["receiver@example.com"],
    "send_only_when_action_required": true
  }
}
```

安全要求：

- 不要把真实邮箱密码提交到 Git。
- 建议使用邮箱 app password / 授权码，不要使用邮箱登录密码。
- `config.yaml` 只保留示例配置；真实密码由用户在本地自行填写。
- 如果担心误提交，可在本地改完后用 `git diff config.yaml` 检查是否包含真实密码。

发送规则：

- `enabled: false` 时不发送邮件。
- `send_only_when_action_required: true` 时，只有存在待确认补仓建议才发送。
- `send_only_when_action_required: false` 时，每次每日检查都发送报告。
- 邮件发送失败只会输出警告，不会中断 `python3 main.py run`。

手动测试邮件发送：

1. 在本地填写 `config.yaml` 的 SMTP、账号、授权码和收件人。
2. 如需无补仓建议也发送测试邮件，将 `send_only_when_action_required` 临时改为 `false`。
3. 运行：

```bash
python3 main.py run
```

4. 检查终端是否有邮件警告，并检查收件箱。

## 历史回测

`python3 main.py backtest` 会使用基金历史净值数据回测当前 250 日高点回撤策略，并写入 `data/backtest_report.json`。V2.3 会基于补仓事件估算策略模拟收益。

回测配置位于 `config.yaml`：

```json
{
  "backtest": {
    "enabled": true,
    "start_date": "2023-01-01",
    "initial_cash": 2000,
    "monthly_cash_addition": 0,
    "include_regular_dca": false,
    "funds": ["270042", "539001", "012349"]
  }
}
```

回测规则：

- 每只基金单独回测。
- 从 `start_date` 开始统计，但阶段高点仍可使用 start_date 前的历史净值。
- 使用 250 日高点计算回撤。
- 10%、15%、20% 三档补仓。
- 采用剩余子弹仓比例法：10% 档 15%，15% 档 25%，20% 档 35%。
- 每档只触发一次。
- 创新高后重置档位触发记录。
- 子弹仓从 `initial_cash` 开始。
- `monthly_cash_addition` 已支持配置，默认 0。

每只基金报告包含：

- `fund_code`
- `fund_name`
- `start_date`
- `end_date`
- `initial_cash`
- `final_cash`
- `total_invested`：回测期间累计投入金额。
- `total_shares`：所有补仓事件累计买入份额。
- `final_nav`：回测期末最后一个单位净值。
- `final_market_value`：`total_shares * final_nav` 估算期末市值。
- `total_profit`：`final_market_value - total_invested`。
- `total_return_rate`：`total_profit / total_invested`，无补仓时为 0。
- `trigger_count_total`：总触发次数。
- `trigger_count_by_level`：各档触发次数。
- `max_drawdown_seen`：回测期间观察到的最大回撤。
- `events`：每次触发事件明细。

`events` 每条包含：

- `date`
- `nav`
- `peak_nav`
- `drawdown`
- `level`
- `amount`
- `shares`
- `cash_after`

收益率说明：

- 这是基于历史净值和补仓事件的策略模拟收益，不代表真实账户收益。
- 当前未实现年化收益率，避免对多次现金流做过度简化。
- 查看最近一次回测收益估算：

```bash
python3 main.py backtest-return
```

## 多参数回测场景

`python3 main.py backtest-scenarios` 会对多组子弹仓参数进行批量回测，并写入 `data/scenarios_report.json`。

默认参数组合：

- `initial_cash`：`2000`、`3000`、`5000`
- `monthly_cash_addition`：`0`、`200`、`500`

每个场景会对配置中的每只基金单独回测，规则与 `backtest` 一致：

- 最近 250 交易日高点。
- 10%、15%、20% 三档触发。
- 每档只触发一次。
- 创新高重置档位。
- 子弹仓按初始现金加每月追加现金计算。
- 补仓金额向上取整到 10 元。

`data/scenarios_report.json` 中每个 scenario 包含：

- `scenario_id`
- `initial_cash`
- `monthly_cash_addition`
- `funds`
- `summary`：用于快速比较场景总触发次数、累计投入和剩余现金

每只基金包含：

- `trigger_count_total`
- `trigger_count_by_level`
- `total_invested`
- `total_shares`
- `final_nav`
- `final_market_value`
- `total_profit`
- `total_return_rate`
- `final_cash`
- `max_drawdown_seen`

`summary.scenarios` 按场景汇总：

- `fund_count`
- `trigger_count_total`
- `total_invested`
- `final_market_value_total`
- `total_profit`
- `total_return_rate`
- `final_cash_total`

`summary.fund_comparisons` 按基金汇总所有场景，便于横向比较同一基金在不同 `initial_cash` 和 `monthly_cash_addition` 下的子弹仓使用和触发频率。

查看多参数场景收益估算：

```bash
python3 main.py scenarios-return
```

本地真实数据验收：

```bash
source .venv/bin/activate
python3 main.py backtest-scenarios
python3 -m json.tool data/scenarios_report.json >/tmp/drawdownguard_scenarios_check.json
python3 -m unittest discover -s tests
python3 -m py_compile main.py backtest.py data_provider.py email_notifier.py notifier.py storage.py strategy.py
```

如果 AKShare、网络或上游接口不可用，命令会 fallback 到本地数据；没有 `nav_data.json` 时会生成空基金结果和 warnings。此时请标记：【真实验收未完成，等待用户本机运行】。

## 资产级回测

V2.4 新增 Asset Layer，不删除原有基金级回测。资产级回测会把同一资产下的多个基金合成为一个资产 NAV，只在资产层触发一次 10% / 15% / 20% 档位，子弹仓也按资产消耗。

当前资产配置在 `config.yaml` 的 `asset_config`：

```json
{
  "asset_config": {
    "assets": [
      {
        "code": "NASDAQ100",
        "name": "NASDAQ100",
        "fund_codes": ["270042", "539001"]
      },
      {
        "code": "HSTECH",
        "name": "HSTECH",
        "fund_codes": ["012349"]
      }
    ]
  }
}
```

运行：

```bash
python3 main.py asset-backtest
python3 main.py asset-backtest-report
```

输出文件：

```text
data/asset_backtest_report.json
```

报告包含：

- `asset_code`
- `asset_name`
- `fund_codes`
- `trigger_count_total`
- `trigger_count_by_level`
- `total_invested`
- `final_cash`
- `total_shares`
- `final_nav`
- `final_market_value`
- `total_profit`
- `total_return_rate`
- `events`
- `series`

资产 NAV 计算假设：

- 资产内基金使用首个共同日期作为基准。
- 每只基金净值归一化为 1。
- 资产 NAV 为归一化净值的等权平均。
- 该 NAV 仅用于资产层策略对照回测，不代表任何真实可交易指数或账户收益。

## 组合级回测

V2.5 的 `portfolio-backtest` 用于评估整个组合的定投、补仓、现金消耗和资产贡献。它不替代现有基金级或资产级回测。

当前第一版支持：

- `NASDAQ100`：代表基金 `270042`，策略 `drawdown_plus_dca`，净值口径 `unit_nav`，每周定投 50 元，同时启用 10% / 15% / 20% 回撤补仓。
- `HSTECH`：代表基金 `012349`，策略 `dca_only`，净值口径 `unit_nav`，每周定投 20 元。
- `CASHFLOW`：代表基金 `023918`，策略 `dca_only`，净值口径 `unit_nav`，每周定投 30 元。
- `DIVIDEND_LOW_VOL`：代表基金 `008163`，策略 `dca_only`，净值口径 `accumulated_nav`，每周定投 20 元。
- `GOLD`：代表基金 `000216`，策略 `dca_only`，净值口径 `unit_nav`，每周定投 10 元。

如果某资产的 `representative_fund` 仍是占位、为空或无法获取净值数据，该资产会被 skipped，并在报告 warnings / skipped assets 中说明原因。

每个资产可配置 `nav_mode`：

- `unit_nav`：使用单位净值走势，适合纳指、恒生科技、黄金等不需要分红复权对照的资产。
- `accumulated_nav`：使用累计净值走势，适合红利低波等分红可能影响单位净值收益的基金。

如果 `accumulated_nav` 获取失败，系统会自动回退到 `unit_nav`，并在 warnings 中提示。

运行：

```bash
python3 main.py portfolio-backtest
python3 main.py portfolio-backtest --start-date 2018-01-01
python3 main.py portfolio-backtest --start-date 2020-01-01 --end-date 2022-12-31
python3 main.py portfolio-report
```

输出文件：

```text
data/portfolio_backtest_report.json
```

检查组合配置中所有代表基金的净值覆盖：

```bash
python3 main.py fund-check
```

输出文件：

```text
data/fund_check_report.json
```

`fund-check` 会输出基金名称、基金代码、最早净值日期、最新净值日期、总交易日数、当前净值，并判断是否覆盖当前组合回测区间。如果基金最早可用净值晚于回测起点，会显示 `WARNING`。
同时会显示该资产当前使用的 `nav_mode`。

审计单个资产的定投买入和净值口径：

```bash
python3 main.py asset-dca-audit DIVIDEND_LOW_VOL
python3 main.py asset-dca-audit 008163
```

输出文件示例：

```text
data/asset_dca_audit_DIVIDEND_LOW_VOL.json
```

`asset-dca-audit` 用于排查单个资产回测收益异常，不修改组合回测结果。报告包含基础信息、单位净值/累计净值口径检查、定投买入审计、前 10 笔和后 10 笔买入记录、高位买入诊断、基金自身涨幅与 DCA 收益对比，以及可能的数据问题 WARNING。

回测规则：

- 每周定投一次，默认每周一。
- 如果周一不是交易日，则使用之后最近一个交易日。
- 可通过 `--start-date YYYY-MM-DD` 和 `--end-date YYYY-MM-DD` 自定义组合回测区间。
- 如果某资产代表基金最早可用净值晚于开始日期，该资产会从最早可用净值开始，不追补此前定投。
- 普通定投资金不受子弹仓限制。
- 子弹仓只用于 `drawdown_plus_dca` 资产的回撤补仓。
- `NASDAQ100` 的回撤补仓使用 250 交易日阶段高点。
- `HSTECH`、`CASHFLOW`、`DIVIDEND_LOW_VOL`、`GOLD` 只做普通定投，不启用补仓。

`portfolio_summary` 包含：

- `start_date`：实际参与回测的首个交易日。
- `end_date`：实际参与回测的最后一个交易日。
- `total_dca_invested`
- `total_bullet_invested`
- `total_invested`
- `final_market_value`
- `total_profit`
- `total_return_rate`
- `bullet_cash_initial`
- `bullet_cash_final`
- `trigger_count_total`
- `skipped_assets`

每个资产包含：

- `asset_id`
- `asset_name`
- `representative_fund`
- `strategy`
- `status`
- `skip_reason`
- `dca_invested`
- `bullet_invested`
- `total_invested`
- `total_shares`
- `final_nav`
- `final_market_value`
- `total_profit`
- `total_return_rate`
- `trigger_count_total`
- `trigger_count_by_level`
- `events`

收益率说明：组合收益是基于历史净值、定投和补仓事件的策略模拟收益，不代表真实账户收益。

## 资产贡献分析

V3.3 新增 `contribution-report`，用于读取 `data/portfolio_backtest_report.json`，分析组合中每个资产贡献了多少收益、承担了多少风险。

运行：

```bash
python3 main.py contribution-report
python3 main.py contribution-detail
```

如果缺少组合回测报告，先运行：

```bash
python3 main.py portfolio-backtest --start-date 2018-01-01
```

输出文件：

```text
data/contribution_report.json
```

每个资产输出投入、市值、浮盈亏、收益率、收益贡献占比、投入权重、市值权重、最大回撤、日收益率波动率和简化夏普比率。风险指标优先基于资产 `series` 和买入事件重建每日估算市值；如果数据不足，则退回可用净值序列近似计算并在明细中提示。

## 定投周几分析

V2.6 新增 `weekly-dca`，用于比较每周一到周五作为定投日时的组合回测差异。它读取 `portfolio_backtest` 配置和代表基金净值历史，保持 `NASDAQ100` 的 10% / 15% / 20% 回撤补仓逻辑，其它资产只做定投。

运行：

```bash
python3 main.py weekly-dca
python3 main.py weekly-dca --source scenarios
```

输出文件：

```text
data/weekly_dca_analysis.json
```

每个定投日输出：

- `total_invested`
- `final_market_value`
- `total_profit`
- `total_return_rate`
- `bullet_cash_final`
- `trigger_count_total`
- `skipped_assets`
- `asset_returns`

`--source backtest|scenarios` 当前作为分析来源标签写入报告，不改变净值读取方式。

## Dynamic DCA Strategy Lab

V3.4 新增 `dca-strategy-lab`，用于为每个资产测试不同定投频率、金额模式、回撤加仓和高位抑制组合，判断是否需要拆分 DCA 策略体系。

运行：

```bash
python3 main.py dca-strategy-lab --preset quick
python3 main.py dca-strategy-lab --preset full --workers 8
python3 main.py dca-strategy-lab --preset quick --start-date 2018-01-01 --end-date 2026-06-15
python3 main.py dca-strategy-report
```

输出文件：

```text
data/dca_strategy_report.json
data/dca_strategy_checkpoint.json
```

策略维度：

- 频率：`weekly` / `biweekly` / `monthly`
- 金额模式：`fixed` / `increasing` / `decreasing` / `volatility_scaled`
- 回撤加仓：`none` / `mild` / `aggressive`
- 高位抑制：`none` / `reduce` / `strong_reduce`

`quick` 使用少量代表组合，`full` 覆盖完整组合。命令支持多进程、进度输出和 checkpoint，中断后会尽量保留已完成结果。

## Portfolio Strategy Synthesizer

V3.5 新增 `portfolio-strategy-synth`，这是组合层决策系统，用于统一不同资产策略、风险预算和现金流分配。它读取 `portfolio_backtest_report.json`、`dca_strategy_report.json` 和已有 `asset_dca_audit_*` 报告，不修改任何底层回测逻辑。

运行：

```bash
python3 main.py portfolio-strategy-synth
python3 main.py portfolio-strategy-report
```

输出文件：

```text
data/portfolio_strategy_report.json
```

系统会自动分类资产角色：

- `NASDAQ100`：growth
- `GOLD`：hedge
- `DIVIDEND_LOW_VOL`：defensive
- `HSTECH`：satellite
- `CASHFLOW`：experimental

合成器会生成 `growth_leaning`、`balanced`、`defensive` 三套组合策略，输出资产权重、DCA 策略映射、牛/熊/震荡市现金流调度、组合回撤联动动作、收益/风险/稳定/成长评分，并给出结构健康、冗余资产、降权/加权和核心-卫星结构建议。

## Portfolio Constraint Optimizer

V3.6 新增 `portfolio-optimize`。Portfolio Optimizer introduces constraint-based portfolio construction similar to institutional portfolio management systems.

运行：

```bash
python3 main.py portfolio-optimize --preset quick
python3 main.py portfolio-optimize --preset full --workers 8
python3 main.py portfolio-optimize-report
```

输出文件：

```text
data/portfolio_optimize_report.json
```

约束条件：

- 最大回撤不超过 25%。
- 单资产权重上限：NASDAQ100 60%、HSTECH 15%、GOLD 25%、CASHFLOW 10%、DIVIDEND_LOW_VOL 30%。
- 子弹仓现金保留至少 5%。
- 高波动资产总权重不超过 70%。

优化目标：

```text
score = 0.5 * total_return_rate - 0.3 * max_drawdown + 0.2 * sharpe_like_ratio
```

报告会输出 `max_return_mode`、`min_risk_mode`、`balanced_mode`，并解释 binding constraints、自动压缩权重资产和是否仍存在更优组合空间。

## Portfolio Continuous Optimizer

V3.7 新增 `portfolio-optimize-continuous`。Continuous optimization introduces convex-like portfolio solving on top of heuristic optimization.

运行：

```bash
python3 main.py portfolio-optimize-continuous --preset quick
python3 main.py portfolio-optimize-continuous --preset full --seed 42
python3 main.py portfolio-optimize-continuous-report
```

输出文件：

```text
data/portfolio_optimize_continuous_report.json
```

连续优化器使用固定 seed 的 differential evolution，在连续权重空间中最大化：

```text
score = 0.5 * return - 0.3 * max_drawdown + 0.2 * sharpe
```

约束包括权重和为 1、单资产上限、最大回撤不超过 25%、子弹仓现金至少 5%、高波动资产权重不超过 70%。报告会输出连续最优权重、与离散优化结果的收益差异、风险指标、active constraints、权重 ±10% 敏感性分析和 Pareto frontier 判断。

## Strategy Lab

V2.8 的 `strategy-lab` 用于比较不同 NASDAQ100 回撤补仓策略对整个组合收益的影响。它基于 `portfolio_backtest` 运行，只替换 `NASDAQ100` 的回撤档位；`HSTECH`、`CASHFLOW`、`DIVIDEND_LOW_VOL`、`GOLD` 仍按原定投策略执行。现金比例固定为 15% / 25% / 35%。

默认比较：

- `A_current`：10 / 15 / 20
- `B_conservative`：10 / 20 / 30
- `C_aggressive`：5 / 10 / 15
- `D_balanced`：8 / 16 / 24

运行：

```bash
python3 main.py strategy-lab
python3 main.py strategy-lab-report
```

输出文件：

```text
data/strategy_lab_report.json
```

每组策略输出：

- `strategy_name`
- `drawdown_levels`
- `total_invested`
- `final_market_value`
- `total_profit`
- `total_return_rate`
- `bullet_cash_final`
- `trigger_count_total`
- `nasdaq100_return_rate`

`strategy-lab-report` 输出：

- 收益率排名
- 子弹仓剩余排名
- 触发次数排名
- 推荐策略

## 保守阶梯止盈回测

V3.1 新增 `take-profit-backtest`，用于在 NASDAQ100 定投和回撤补仓基础上模拟保守阶梯止盈。卖出所得资金回到子弹仓，后续可继续用于回撤补仓。

运行：

```bash
python3 main.py take-profit-backtest
python3 main.py take-profit-backtest --start-date 2018-01-01 --end-date 2026-06-09
python3 main.py take-profit-report
```

输出文件：

```text
data/take_profit_report.json
```

止盈规则：

- 持仓收益率达到 15%：卖出原始持仓市值的 15%；之后每上涨 1%，增量卖出 1%。
- 持仓收益率达到 25%：卖出原始持仓市值的 20%；之后每上涨 1%，增量卖出 2%。
- 持仓收益率达到 35%：卖出原始持仓市值的 25%；保留底仓，不再卖出。
- 卖出资金进入子弹仓，未来可用于补仓。

报告包含：

- `total_dca_invested`
- `total_buy_amount`
- `total_sell_amount`
- `final_market_value`
- `final_cash`
- `total_asset_value`
- `total_profit`
- `total_return_rate`
- `buy_events`
- `sell_events`
- `trigger_count_buy`
- `trigger_count_sell`

## 止盈风险对比

V3.2 新增 `risk-compare`，用于比较 NASDAQ100 原始策略和保守阶梯止盈策略的收益、回撤和波动率。

对比对象：

- 原始策略：NASDAQ100 定投 + 回撤补仓，不止盈。
- 阶梯止盈策略：NASDAQ100 定投 + 回撤补仓 + 当前保守阶梯止盈规则。

运行：

```bash
python3 main.py risk-compare
python3 main.py risk-compare --start-date 2018-01-01 --end-date 2026-06-09
python3 main.py risk-compare-report
```

输出文件：

```text
data/risk_compare_report.json
```

每个策略输出：

- `total_invested`
- `final_market_value`
- `final_cash`
- `total_asset_value`
- `total_profit`
- `total_return_rate`
- `max_drawdown`
- `volatility`
- `cash_ratio_final`
- `buy_count`
- `sell_count`

`risk-compare-report` 输出收益率差异、最大回撤改善幅度、波动率降低幅度和结论。

## 阶梯止盈档位优化

V3.3 新增 `take-profit-optimizer`，用于自动测试 NASDAQ100 回撤补仓 + 阶梯止盈的多组档位组合，并按风险和收益排序。

运行：

```bash
python3 main.py take-profit-optimizer
python3 main.py take-profit-optimizer --preset quick --workers 8
python3 main.py take-profit-optimizer --preset full --max-combinations 1000
python3 main.py take-profit-optimizer --start-date 2018-01-01 --end-date 2026-06-09
python3 main.py take-profit-optimizer-report
```

输出文件：

```text
data/take_profit_optimizer_report.json
data/take_profit_optimizer_partial.json
```

默认搜索范围：

- 第一档触发收益率：10% 到 20%，步长 2%。
- 第二档触发收益率：20% 到 35%，步长 3%。
- 第三档触发收益率：30% 到 50%，步长 5%。
- `--preset quick` 默认只测试 27 组代表组合，适合快速验证。
- `--preset full` 测试完整组合，卖出比例按 5% 步长覆盖第一档 5% 到 20%、第二档 10% 到 25%、第三档 15% 到 30%。
- 后续增量卖出比例：1% 到 5%。
- `--workers` 指定 CPU 并行进程数，默认使用 CPU 核心数减 1，不使用 GPU。
- `--max-combinations` 可限制本次最多测试组合数，避免完整组合一次运行过久。
- 运行中会显示总组合数、当前进度、已耗时和预计剩余时间；中断时会尽量保留 `data/take_profit_optimizer_partial.json`。

每个组合输出：

- 档位收益阈值
- 卖出比例
- 总收益率
- 最大回撤
- 波动率
- 子弹仓剩余
- 总卖出次数
- 单档触发次数

摘要会输出最大回撤改善排名、收益率排名和推荐组合。

## 回测可视化

`python3 main.py backtest-plot` 会读取已有回测报告并输出 PNG 图表到 `reports/backtest_plots/`。

默认行为：

- `--source auto`：优先读取 `data/scenarios_report.json`，不存在时读取 `data/backtest_report.json`。
- `--source backtest`：读取 `data/backtest_report.json`。
- `--source scenarios`：读取 `data/scenarios_report.json`。
- `--scenario S001`：只绘制指定 scenario；不传则绘制全部 scenario。
- `--all`：显式绘制全部 scenario。
- `--output-dir reports/backtest_plots`：指定图表输出目录。

输出结构示例：

```text
reports/backtest_plots/
  backtest/
    270042_广发纳斯达克100ETF联接A_backtest.png
  S001/
    270042_广发纳斯达克100ETF联接A_S001.png
```

每张图包含：

- 净值 vs 阶段高点
- 回撤曲线
- 10% / 15% / 20% 补仓触发点
- 子弹仓剩余现金变化曲线

图表标题包含基金名称、scenario 编号、初始现金和月追加金额。旧版报告如果缺少 `series` 字段，请先重新运行：

```bash
python3 main.py backtest
python3 main.py backtest-scenarios
```

如果 Linux 环境没有中文字体，图表中的中文基金名称可能显示为方框；可安装 Noto CJK 或文泉驿字体后重新生成图表。

## V3.7 真实账户配置接入

真实账户配置已从代码中拆出，集中放在 `data/`：

```text
data/user_profile.json       # 投资者画像、子弹仓、生活账户隔离
data/current_holdings.json   # 当前真实持仓、资产分组、角色和 nav_mode
data/dca_plan.json           # 每周四/每月1日定投计划
data/policy_config.json      # 允许补仓资产、禁止补仓资产和回撤补仓规则
```

当前配置版本：`2026-06 投委会最终版`。

常用命令：

```bash
python3 main.py profile-report
python3 main.py holdings-report
python3 main.py policy-check
python3 main.py portfolio-backtest --start-date 2018-01-01
python3 main.py portfolio-report
```

真实配置要点：

- 子弹仓账户为余额宝，金额 `1883` 元；生活账户不参与补仓、回测、优化或再平衡计算。
- NASDAQ100 合并 `270042` 和 `012752`，组合回测仍使用 `270042` 作为资产代表净值。
- 真实定投计划使用每周四：`270042` 10 元、`012752` 40 元、`012349` 25 元、`008163` 20 元、`023918` 30 元。
- 黄金 `000216` 使用每月 1 日定投 40 元。
- `DIVIDEND_LOW_VOL` 默认使用 `accumulated_nav`，其余当前定投资产默认使用 `unit_nav`。
- 允许补仓基金：`270042`、`012752`、`012349`。
- 禁止补仓基金：`023918`、`008163`、`000216`、`110017`、`420102`、`000546`、`018125`、`016708`。

更新真实持仓时，只修改 `data/current_holdings.json`、`data/dca_plan.json` 和 `data/policy_config.json`，不要把真实配置写进 Python 代码。

## V3.8 再平衡建议

Rebalancing Advisor 基于真实持仓、四大类资产分类、当前权重和目标权重生成建议，只输出辅助决策，不自动交易，也不改变补仓策略或组合回测逻辑。

运行：

```bash
python3 main.py rebalance-advice
python3 main.py rebalance-detail
```

输出文件：

```text
data/rebalance_advice.json
```

默认目标权重位于 `data/user_profile.json` 的 `target_allocation`：

- `CASH`：目标 15%，区间 10% 到 25%。
- `CORE`：目标 35%，区间 25% 到 50%。
- `SATELLITE`：目标 20%，区间 10% 到 30%。
- `DEFENSIVE`：目标 30%，区间 20% 到 45%。

建议原则：

- 优先通过未来定投流向调整完成再平衡。
- NASDAQ100 是核心资产，低配时提高未来定投优先级。
- 债券偏高但未超上限时，不建议立即卖出。
- HSTECH 作为小仓位卫星资产观察，不使用子弹仓主动追补。
- 主动基金和有色金属保持观察，不新增定投。

## V3.9 投委会报告

Investment Committee Report Generator 会把真实画像、持仓、策略检查、每日补仓检查、组合回测、资产贡献和再平衡建议整合为一份 Markdown 报告，同时输出 JSON，便于后续生成 PDF 或网页。

运行：

```bash
python3 main.py committee-report
```

输出文件：

```text
data/committee_report.md
data/committee_report.json
```

报告包含：

- 账户总览
- 当前持仓结构
- 今日补仓检查
- 组合回测摘要
- 资产贡献分析
- 再平衡建议
- 投委会结论
- 风险提示

如果某个上游报告不存在，投委会报告会显示“暂无数据，请先运行对应命令”，不会中断生成。

### V4.3 一页投委会日报

`committee-report` 默认生成美化版个人投委会日报，顶部包含一页摘要、今日操作清单、系统健康状态，以及 Infos / Warnings / Errors 分级提示。

```bash
python3 main.py committee-report
python3 main.py committee-report --plain
```

美化版报告新增：

- 一页摘要：补仓状态、子弹仓、核心资产、卫星资产、防守资产、再平衡。
- 红黄绿状态：绿色表示正常，黄色表示关注或未来定投倾斜，红色表示需要处理。
- 今日补仓检查表格：基金、当前回撤、状态、建议。
- 资产贡献表格：投入权重、市值权重、收益率、收益贡献、最大回撤。
- 再平衡建议表格：大类当前权重、目标区间、状态、建议。
- 系统健康状态：优先读取 `data/daily_run_report.json`。

`--plain` 会输出无 emoji 的简洁版本，便于复制到不支持表格或 emoji 的环境。

## V4.0 Daily Workflow

`daily` 命令把每日常用流程合并为一键执行。它只编排已有功能，不自动交易，不改变补仓策略或组合回测计算。

日常快速检查推荐：

```bash
python3 main.py daily --quick
```

每周或每月完整运行：

```bash
python3 main.py daily --start-date 2018-01-01
```

可选参数：

```bash
python3 main.py daily --skip-backtest
python3 main.py daily --quick --clean-proxy
python3 main.py daily --quick --skip-quant
python3 main.py daily --quick --include-watchlist
python3 main.py daily --open-report
```

默认流程：

1. `policy-check`
2. `run`
3. `portfolio-backtest`
4. `contribution-report`
5. `quant-signal`
6. `rebalance-advice`
7. `committee-report`

`--quick` 流程：

1. `policy-check`
2. `run`
3. `quant-signal`
4. `rebalance-advice`
5. `committee-report`

新增输出：

```text
data/daily_run_report.json
data/committee_report.md
data/committee_report.json
```

如果某一步失败，workflow 会记录 failed step，继续执行后续能执行的步骤；如果投委会报告无法生成，daily 状态为 `failed`。

`--clean-proxy` 会在 daily 执行期间临时移除 `http_proxy`、`https_proxy`、`HTTP_PROXY`、`HTTPS_PROXY`、`all_proxy`、`ALL_PROXY`，用于排查代理环境导致的净值拉取问题。

`--skip-quant` 会跳过本次量化信号刷新，并让投委会报告使用已有 `data/quant_signal_report.json`；如果文件不存在，报告显示暂无量化信号。

`--include-watchlist` 会在 daily 中额外分析观察池基金；默认不启用，避免日常 quick 变慢。

## V4.2 本地净值缓存

Local NAV Cache 会在真实净值获取成功后自动写入 `data/nav_cache.json`。当 AKShare、东方财富接口、代理或 DNS 异常时，系统会优先使用最近一次成功缓存，提升每日检查稳定性。

fallback 顺序：

1. real 数据源
2. `data/nav_cache.json`
3. `nav_data.json`
4. skipped / 数据缺失

缓存支持不同净值口径：

- `unit_nav`
- `accumulated_nav`

同一基金不同口径使用不同缓存 key，例如 `008163:unit_nav` 和 `008163:accumulated_nav`。

配置项：

```json
"nav_cache": {
  "enabled": true,
  "max_age_days_for_run": 7,
  "max_age_days_for_backtest": 90,
  "min_history_for_run": 250
}
```

命令：

```bash
python3 main.py cache-status
python3 main.py cache-clear --yes
```

说明：

- `run` 使用缓存超过 7 天会提示“缓存净值已过期，仅供参考”。
- `portfolio-backtest` 使用缓存超过 90 天会提示过期。
- run 使用缓存不足 250 条会提示阶段高点可能不准确。
- `data/nav_cache.json` 是运行缓存文件，不提交到 Git。

## V4.4 Quant Signal Engine

Quant Signal Engine 是量化分析层，只生成趋势、动量、波动和风险信号，不自动交易，不改变补仓策略、组合回测或再平衡建议。

命令：

```bash
python3 main.py quant-signal
python3 main.py quant-signal-detail
```

输出：

```text
data/quant_signal_report.json
```

第一版支持资产：

- `NASDAQ100`：270042，`unit_nav`
- `HSTECH`：012349，`unit_nav`
- `CASHFLOW`：023918，`unit_nav`
- `DIVIDEND_LOW_VOL`：008163，`accumulated_nav`
- `GOLD`：000216，`unit_nav`

量化指标包括：

- 250 日高点与当前回撤
- MA20 / MA60 / MA120
- 当前净值相对均线位置
- 20 / 60 / 120 日收益率
- 20 / 60 日波动率
- 250 日最大回撤
- `trend_score`、`momentum_score`、`risk_score`、`volatility_score`
- `quant_score`

`quant_score` 范围为 0-100，计算权重：

```text
quant_score =
0.35 * trend_score
+ 0.30 * momentum_score
+ 0.25 * risk_score
+ 0.10 * volatility_score
```

`signal_status`：

- `strong_uptrend`：80-100
- `healthy`：60-80
- `neutral`：40-60
- `weak`：20-40
- `high_risk`：0-20

`committee-report` 会自动读取 `data/quant_signal_report.json`，在一页摘要中显示市场环境，并新增“量化信号”表格。

## V5.2 Watchlist / Candidate Fund Analyzer

观察池用于研究用户感兴趣但尚未买入的基金。观察池基金只保存在 `data/watchlist_funds.json`，不会进入真实持仓、定投计划、补仓 allow list 或历史触发记录。

新增文件：

```text
data/watchlist_funds.json
```

新增命令：

```bash
python3 main.py watchlist-add <fund_code> --name "基金名称" --role satellite --reason "关注原因" --notes "备注"
python3 main.py watchlist-report
python3 main.py watchlist-analyze <fund_code>
python3 main.py watchlist-analyze <fund_code> --weekly-dca 20 --start-date 2021-01-01
python3 main.py watchlist-remove <fund_code>
python3 main.py watchlist-promote <fund_code>
```

默认安全规则：

- `allow_dca = false`
- `allow_drawdown_buy = false`
- 不修改 `data/current_holdings.json`
- 不修改 `data/dca_plan.json`
- 不修改 `data/policy_config.json`
- 不修改 `data/records.json`

`watchlist-analyze` 会输出：

- 基金数据检查
- 250 日高点和当前回撤
- MA20 / MA60 / MA120
- 20 / 60 / 120 日收益率
- 20 / 60 日波动率
- 最大回撤
- `quant_score` 和 `signal_status`
- 默认每周 20 元的候选基金 DCA 模拟
- 与当前组合的关系分析

`watchlist-promote` 第一版只生成手动配置片段，不会自动修改真实持仓或策略配置。

`committee-report` 会读取 `data/watchlist_funds.json` 和 `data/watchlist_analysis_report.json`，显示“观察基金”板块；未分析的基金会显示“尚未分析”。

默认 daily 不分析观察池，避免日常 quick 变慢。如需刷新观察池分析：

```bash
python3 main.py daily --quick --include-watchlist
```

## V5.0 Interactive Control Center

Interactive Control Center 让用户可以在本地交互式维护账户配置，不需要通过 Codex 手动改 JSON。

启动：

```bash
python3 main.py interactive
```

控制中心支持：

- 查看账户总览
- 查看当前持仓
- 查看今日投委会报告
- 运行 `daily --quick`
- 运行完整体检 `daily --start-date 2018-01-01`
- 更新子弹仓金额
- 更新基金持仓金额
- 添加/删除观察基金
- 添加、修改、暂停、恢复定投计划
- 查看 `policy-check`
- 备份当前配置
- 回滚到上一个备份

命令式配置管理：

```bash
python3 main.py cash-update --amount 1883
python3 main.py holding-update 270042 --amount 2038
python3 main.py holding-add 999999 --name "基金名称" --asset-id SATELLITE_TEST --role satellite --amount 100
python3 main.py holding-remove 999999
python3 main.py dca-add 270042 --amount 10 --frequency weekly --weekday thu
python3 main.py dca-update 012752 --amount 40
python3 main.py dca-pause 012752
python3 main.py dca-resume 012752
python3 main.py config-backup
python3 main.py config-backup-list
python3 main.py config-rollback --latest
python3 main.py config-change-log
```

所有修改类命令都支持 dry-run：

```bash
python3 main.py holding-update 270042 --amount 2200 --dry-run
```

自动备份：

- 每次实际修改前自动备份真实配置到 `data/backups/YYYY-MM-DD_HH-MM-SS/`
- 修改后自动运行 `policy-check`
- 修改记录写入 `data/config_change_log.json`
- `config-rollback --latest` 会恢复最近一次备份并重新运行 `policy-check`

安全限制：

- 不自动交易
- 不修改补仓策略核心规则
- 不修改 `strategy_activation_date`
- 不修改历史触发记录或 `records.json`
- 观察基金不会自动进入真实持仓、定投计划或补仓 allow list

## V5.1 Config State Enforcement

配置状态现在会真正进入系统计算链路。

### DCA 状态管理

`data/dca_plan.json` 中每条定投支持：

- `status: active`
- `status: paused`

缺少 `status` 时默认视为 `active`。

暂停定投：

```bash
python3 main.py dca-pause 012752
```

恢复定投：

```bash
python3 main.py dca-resume 012752
```

查看定投状态：

```bash
python3 main.py dca-report
```

`paused` 定投不会参与：

- `portfolio-backtest`
- `profile-report` active 定投金额
- `rebalance-advice` 未来资金流向
- `committee-report` active 定投表

`committee-report` 和 `dca-report` 会单独显示 paused DCA。

### 移除但保留历史持仓

`holding-remove` 不再物理删除基金，而是标记：

```json
{
  "status": "removed",
  "archived": true
}
```

示例：

```bash
python3 main.py holding-remove 016708 --dry-run
```

removed / archived 持仓不会参与当前资产总额、权重、回测、再平衡或投委会当前持仓结构。`holdings-report` 会在“历史/已移除持仓”中显示这些记录。

### Watchlist 隔离

`data/watchlist_funds.json` 只用于观察池命令和投委会观察区，不参与真实组合计算、回测、再平衡或补仓检查。

### 配置修改日志

`data/config_change_log.json` 会记录状态变化，例如 `dca-pause`、`dca-resume`、`holding-remove`、`holding-update`、`cash-update`。

## V5.3 Daily Online News Fetcher

Daily Online News Fetcher 用于自动抓取、缓存、筛选和分析与当前组合相关的财经新闻。新闻信号只进入投委会报告，不自动交易，不修改持仓、定投或补仓策略。

新增配置和运行产物：

- `data/news_sources.json`：新闻源配置，支持 `rss` 和简单 `web`。
- `data/news_cache.json`：新闻缓存和去重结果，运行产物，默认不提交。
- `data/news_analysis_report.json`：每日新闻分析报告，运行产物。

常用命令：

```bash
python3 main.py news-sources
python3 main.py news-source-add --name "示例RSS" --type rss --url "https://example.com/rss.xml" --category market
python3 main.py news-source-enable "示例RSS"
python3 main.py news-source-disable "示例RSS"
python3 main.py news-fetch
python3 main.py news-analyze
python3 main.py news-analyze --days 3
python3 main.py news-report
python3 main.py news-import --title "美联储释放降息信号，科技股走强" --content "市场预期美联储可能降息，纳斯达克科技股上涨。" --source "manual"
```

在 daily 中启用新闻：

```bash
python3 main.py daily --quick --include-news
```

默认 daily 不抓取新闻，避免日常 quick 受网络波动影响。启用 `--include-news` 后会执行：

1. `news-fetch`
2. `news-analyze`
3. `committee-report`

新闻会按关键词映射到资产：

- `NASDAQ100`：纳斯达克、美股、科技股、AI、英伟达、半导体、美联储、降息、加息等。
- `HSTECH`：恒生科技、港股科技、阿里、腾讯、平台经济、互联网监管等。
- `GOLD`：黄金、金价、避险、美元、实际利率、地缘冲突、通胀等。
- `BONDS`：债券、国债、利率、央行、货币政策、信用风险、收益率等。
- 观察池：从 `watchlist_funds.json` 的基金名称、关注原因、角色和备注中提取关键词。

分析字段包括：

- `news_category`
- `sentiment`
- `impact_score`
- `news_importance_score`
- `matched_assets`
- `matched_keywords`
- `suggested_follow_up`

`committee-report` 会新增“每日新闻分析”板块，一页摘要会显示“新闻风险”。新闻结论只作为投委会辅助判断，不作为买卖指令。
