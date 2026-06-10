# 基金补仓管家

按最新投委会规则实现的命令行版本，用于根据 250 个交易日高点回撤规则提醒补仓。

## 功能

- 仅监控纳指和恒生科技等高波动成长资产。
- 使用最近 250 个交易日最高净值作为阶段高点。
- 回撤达到 10%、15%、20% 时分别触发三档补仓提醒。
- 支持 `strategy_activation_date` 策略启用日；启用日前已经发生的回撤不追补。
- 每档只触发一次，创新高后重置触发记录。
- 用户确认后才记录补仓成功，并扣减子弹仓余额。
- 每次每日检查会写入 `daily_log.json`，同一天同一基金重复运行会更新记录。
- 支持每日检查邮件推送，邮件发送失败不会中断主流程。
- 生活账户资金永不参与补仓计算。

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
python3 main.py portfolio-report
python3 main.py weekly-dca
python3 main.py strategy-lab
python3 main.py strategy-lab-report
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

脚本会自动进入项目目录、激活 `.venv`、执行 `python3 main.py run`，并将输出保存到 `logs/run_YYYY-MM-DD.txt`。

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

`python3 main.py run` 每次运行后会写入 `daily_log.json`。

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

`scripts/run_daily.sh` 的终端输出会额外保存到 `logs/run_YYYY-MM-DD.txt`，该目录下的 `.txt` 运行日志默认不纳入版本管理。

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

`python3 main.py backtest` 会使用基金历史净值数据回测当前 250 日高点回撤策略，并写入 `backtest_report.json`。V2.3 会基于补仓事件估算策略模拟收益。

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

`python3 main.py backtest-scenarios` 会对多组子弹仓参数进行批量回测，并写入 `scenarios_report.json`。

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

`scenarios_report.json` 中每个 scenario 包含：

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
python3 -m json.tool scenarios_report.json >/tmp/drawdownguard_scenarios_check.json
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
asset_backtest_report.json
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

- `NASDAQ100`：代表基金 `270042`，策略 `drawdown_plus_dca`，每周定投 50 元，同时启用 10% / 15% / 20% 回撤补仓。
- `HSTECH`：代表基金 `012349`，策略 `dca_only`，每周定投 20 元。
- `CASHFLOW`：代表基金 `023918`，策略 `dca_only`，每周定投 30 元。
- `DIVIDEND_LOW_VOL`：代表基金 `008163`，策略 `dca_only`，每周定投 20 元。
- `GOLD`：代表基金 `000216`，策略 `dca_only`，每周定投 10 元。

如果某资产的 `representative_fund` 仍是占位、为空或无法获取净值数据，该资产会被 skipped，并在报告 warnings / skipped assets 中说明原因。

运行：

```bash
python3 main.py portfolio-backtest
python3 main.py portfolio-report
```

输出文件：

```text
portfolio_backtest_report.json
```

回测规则：

- 每周定投一次，默认每周一。
- 如果周一不是交易日，则使用之后最近一个交易日。
- 普通定投资金不受子弹仓限制。
- 子弹仓只用于 `drawdown_plus_dca` 资产的回撤补仓。
- `NASDAQ100` 的回撤补仓使用 250 交易日阶段高点。
- `HSTECH`、`CASHFLOW`、`DIVIDEND_LOW_VOL`、`GOLD` 只做普通定投，不启用补仓。

`portfolio_summary` 包含：

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

## 定投周几分析

V2.6 新增 `weekly-dca`，用于比较每周一到周五作为定投日时的组合回测差异。它读取 `portfolio_backtest` 配置和代表基金净值历史，保持 `NASDAQ100` 的 10% / 15% / 20% 回撤补仓逻辑，其它资产只做定投。

运行：

```bash
python3 main.py weekly-dca
python3 main.py weekly-dca --source scenarios
```

输出文件：

```text
weekly_dca_analysis.json
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

## Strategy Lab

V2.7 新增 `strategy-lab`，用于比较不同回撤补仓档位在组合回测中的长期效果。它基于 `portfolio_backtest` 运行，只替换 `drawdown_plus_dca` 资产的回撤档位；现金比例固定为 15% / 25% / 35%。

默认比较：

- A：10 / 15 / 20
- B：10 / 20 / 30
- C：5 / 10 / 15
- D：8 / 16 / 24

运行：

```bash
python3 main.py strategy-lab
python3 main.py strategy-lab-report
```

输出文件：

```text
strategy_lab_report.json
```

每组策略输出：

- `strategy_name`
- `drawdown_levels`
- `total_return_rate`
- `total_profit`
- `final_market_value`
- `trigger_count`
- `bullet_cash_remaining`
- `max_drawdown`

`strategy-lab-report` 输出：

- 收益率排名
- 现金效率排名
- 风险排名

## 回测可视化

`python3 main.py backtest-plot` 会读取已有回测报告并输出 PNG 图表到 `backtest_plots/`。

默认行为：

- `--source auto`：优先读取 `scenarios_report.json`，不存在时读取 `backtest_report.json`。
- `--source backtest`：读取 `backtest_report.json`。
- `--source scenarios`：读取 `scenarios_report.json`。
- `--scenario S001`：只绘制指定 scenario；不传则绘制全部 scenario。
- `--all`：显式绘制全部 scenario。
- `--output-dir backtest_plots`：指定图表输出目录。

输出结构示例：

```text
backtest_plots/
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
