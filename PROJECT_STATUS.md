# DrawdownGuard Project Status

## 1. 当前项目完成情况

DrawdownGuard 当前已完成命令行版本的核心闭环：

- 可读取配置中的基金列表、补仓规则、子弹仓余额和数据源设置。
- 可按基金代码获取净值数据，优先使用 AKShare，失败后 fallback 到本地 `nav_data.json`。
- 可根据最新策略计算回撤、判断补仓档位、生成补仓建议。
- 可按 `strategy_activation_date` 识别历史回撤，避免追补策略启用日前已经发生的档位。
- 可在用户确认后记录补仓执行日志并扣减子弹仓余额。
- 可在每次每日检查后写入 `data/daily_log.json`，并支持同日同基金更新。
- 可通过 `scripts/run_daily.sh` 自动运行每日检查，并将终端输出保存到 `reports/logs/run_YYYY-MM-DD.txt`。
- 可按配置发送每日邮件检查报告，邮件失败不会中断主流程。
- 可运行历史回测并输出 `data/backtest_report.json`。
- 可基于补仓事件估算策略模拟收益，包括份额、市值、浮盈和总收益率。
- 可运行资产级回测并输出 `data/asset_backtest_report.json`，用于与基金级回测对照。
- 可运行组合级定投加补仓回测并输出 `data/portfolio_backtest_report.json`。
- 可基于回测报告生成 PNG 可视化图表，输出到 `reports/backtest_plots/`。
- 可在单只基金缺少净值数据时跳过该基金，不影响其他基金继续计算。
- 已有单元测试覆盖策略、数据源 fallback、数据不足提示和缺数据跳过。

本次结构整理将核心模块移动到 `drawdownguard/` 包，JSON 运行产物移动到 `data/`，文本日志和图表移动到 `reports/`。这是项目结构重构，不改变任何策略计算逻辑。

## 2. 已实现功能

- `python3 main.py run`：运行每日基金补仓检查。
- `python3 main.py confirm <基金代码或名称> <档位>`：确认某只基金某档补仓已执行。
- `python3 main.py set-cash <金额>`：设置子弹仓余额。
- `python3 main.py transactions`：查看补仓执行日志。
- `python3 main.py logs`：查看最近 10 条每日检查日志。
- `./scripts/run_daily.sh`：运行自动检查脚本，并保存当天文本日志。
- 邮件推送：使用标准库 SMTP，根据 `email.enabled` 和 `send_only_when_action_required` 控制发送。
- `python3 main.py backtest`：使用历史净值数据回测当前策略。
- `python3 main.py backtest-report`：查看最近一次回测摘要。
- `python3 main.py backtest-return`：查看最近一次回测收益估算。
- `python3 main.py asset-backtest`：运行资产级历史回测。
- `python3 main.py asset-backtest-report`：查看最近一次资产级回测摘要。
- `python3 main.py portfolio-backtest`：运行组合级定投加补仓回测，支持 `--start-date` / `--end-date` 自定义回测区间。
- `python3 main.py fund-check`：检查组合配置中所有代表基金的净值起止日期、交易日数、当前净值和回测区间覆盖情况。
- `python3 main.py asset-dca-audit DIVIDEND_LOW_VOL`：审计单个资产的定投买入、净值口径、累计净值尝试、高位买入和 WARNING，用于排查收益异常。
- `python3 main.py portfolio-report`：查看最近一次组合回测摘要。
- `python3 main.py contribution-report`：基于最近一次组合回测生成资产收益贡献、权重和风险摘要。
- `python3 main.py contribution-detail`：查看每个资产的贡献分析明细和数据不足提示。
- `python3 main.py weekly-dca`：分析周一到周五不同定投日的组合回测表现。
- `python3 main.py dca-strategy-lab --preset quick`：为每个资产测试动态 DCA 策略组合，支持 quick/full、并行、进度和 checkpoint。
- `python3 main.py dca-strategy-report`：查看最近一次动态 DCA 策略实验摘要。
- `python3 main.py portfolio-strategy-synth`：基于组合回测、DCA 策略实验和资产审计报告合成组合级策略、风险预算和现金流调度。
- `python3 main.py portfolio-strategy-report`：查看组合策略合成摘要。
- `python3 main.py portfolio-optimize --preset quick`：在回撤、单资产权重、现金仓位和高波动预算约束下优化组合权重。
- `python3 main.py portfolio-optimize-report`：查看组合约束优化摘要、binding constraints 和推荐组合。
- `python3 main.py portfolio-optimize-continuous --preset quick`：使用固定 seed 的 differential evolution 在连续权重空间优化组合。
- `python3 main.py portfolio-optimize-continuous-report`：查看连续优化权重、离散对比、active constraints、敏感性和 Pareto 判断。
- `python3 main.py strategy-lab`：比较不同 NASDAQ100 回撤补仓策略对组合回测表现的影响。
- `python3 main.py strategy-lab-report`：查看 Strategy Lab 收益率、子弹仓剩余、触发次数排名和推荐策略。
- `python3 main.py take-profit-backtest`：运行 NASDAQ100 保守阶梯止盈回测，支持 `--start-date` / `--end-date`。
- `python3 main.py take-profit-report`：查看最近一次保守阶梯止盈回测摘要。
- `python3 main.py risk-compare`：对比 NASDAQ100 原始策略和保守阶梯止盈策略的收益、最大回撤、波动率和现金比例，支持 `--start-date` / `--end-date`。
- `python3 main.py risk-compare-report`：查看最近一次止盈策略风险对比摘要。
- `python3 main.py take-profit-optimizer`：自动测试 NASDAQ100 阶梯止盈档位、卖出比例和增量卖出比例组合，支持 `--preset quick|full`、`--workers` 和 `--max-combinations`，输出风险/收益排序。
- `python3 main.py take-profit-optimizer-report`：查看最近一次阶梯止盈档位优化摘要。
- `python3 main.py backtest-scenarios`：运行多参数回测场景并输出 `data/scenarios_report.json`，同时打印场景摘要。
- `python3 main.py scenarios-return`：查看多参数场景收益估算。
- `python3 main.py backtest-plot`：读取 `data/backtest_report.json` 或 `data/scenarios_report.json` 生成回测可视化图表。
- `data_source: real`：使用 AKShare 获取真实基金单位净值走势。
- `data_source: local`：从本地 `nav_data.json` 读取备用净值数据。
- real 数据获取失败时自动 fallback 到 local，并在报告中提示。
- 数据不足 250 条时仍继续计算，并在报告中提示。
- 数据完全缺失时显示“净值数据缺失，已跳过”。
- 策略启用日前已发生的回撤显示为历史回撤，不自动建议补仓。
- 每日检查日志字段包含 `date`、`fund_code`、`fund_name`、`nav`、`peak_nav`、`drawdown`、`status`、`suggestions`、`data_source`、`warnings`。
- `reports/logs/run_YYYY-MM-DD.txt` 保存脚本运行输出；`reports/logs/*.txt` 已加入 `.gitignore`，仅保留 `reports/logs/.gitkeep`。
- 邮件正文包含子弹仓余额、基金名称、净值、高点、回撤、状态、建议补仓金额和历史回撤提示。
- 回测配置包含 `enabled`、`start_date`、`initial_cash`、`monthly_cash_addition`、`include_regular_dca` 和基金列表。
- 回测报告按基金输出，包含 `fund_code`、`fund_name`、`start_date`、`end_date`、`initial_cash`、`final_cash`、`total_invested`、`total_shares`、`final_nav`、`final_market_value`、`total_profit`、`total_return_rate`、`trigger_count_total`、`trigger_count_by_level`、`max_drawdown_seen` 和 `events`。
- 回测报告每只基金包含 `series`，用于绘制净值、高点、回撤和现金变化曲线。
- `asset_config` 已配置第一批资产：`NASDAQ100` 包含 `270042` / `539001`，`HSTECH` 包含 `012349`。
- 资产级回测按资产计算回撤和档位触发，`NASDAQ100` 的 10% / 15% / 20% 档位只触发一次，子弹仓按资产消耗。
- `data/asset_backtest_report.json` 输出资产级触发次数、收益率和现金消耗。
- `portfolio_backtest` 已配置组合回测：`NASDAQ100` 使用 `270042` 做 `drawdown_plus_dca`，`HSTECH` 使用 `012349` 做 `dca_only`，`CASHFLOW` 使用 `023918`、`DIVIDEND_LOW_VOL` 使用 `008163`、`GOLD` 使用 `000216` 做 `dca_only`。
- `portfolio_backtest.assets` 支持 `nav_mode`：`unit_nav` 使用单位净值，`accumulated_nav` 使用累计净值；当前 `DIVIDEND_LOW_VOL` 默认使用 `accumulated_nav`，其余资产默认使用 `unit_nav`。
- 如果 `accumulated_nav` 获取失败，会回退到 `unit_nav` 并输出 warning。
- `data/portfolio_backtest_report.json` 输出实际回测区间、组合总投入、定投投入、补仓投入、组合估算市值、浮盈亏、总收益率、子弹仓剩余、资产贡献和 skipped 资产。
- `data/fund_check_report.json` 输出 portfolio 代表基金的最早净值日期、最新净值日期、交易日数、当前净值和区间覆盖 WARNING。
- `data/asset_dca_audit_<ASSET_ID>.json` 输出单个资产定投审计、买入记录抽样、单位净值/累计净值口径检查和数据问题 WARNING。
- `data/contribution_report.json` 输出各资产收益贡献占比、投入权重、市值权重、最大回撤、波动率、简化夏普比率和组合贡献判断。
- `data/weekly_dca_analysis.json` 输出周一到周五定投日对组合总投入、组合市值、浮盈亏、总收益率、子弹仓剩余和补仓触发次数的影响。
- `data/dca_strategy_report.json` 输出每个资产的动态 DCA 策略排名、最优策略、收益率、最大回撤、波动率和简化夏普；`data/dca_strategy_checkpoint.json` 保存中断恢复进度。
- `data/portfolio_strategy_report.json` 输出 growth_leaning / balanced / defensive 三套组合策略、资产角色、权重、DCA 映射、现金流调度、回撤联动、最优组合选择和结构健康结论。
- `data/portfolio_optimize_report.json` 输出约束优化候选组合、max_return/min_risk/balanced 三种模式、约束检查、binding constraints、自动压缩权重资产和可解释优化结论。
- `data/portfolio_optimize_continuous_report.json` 输出连续组合优化权重、离散优化对比、风险指标、约束检查、active constraints、敏感性分析和 Pareto frontier 判断。
- `data/strategy_lab_report.json` 输出 A_current / B_conservative / C_aggressive / D_balanced 四组 NASDAQ100 回撤补仓档位的组合收益、子弹仓剩余、触发次数和 NASDAQ100 单独收益率，并给出收益率、子弹仓剩余、触发次数排名和推荐策略。
- `data/take_profit_report.json` 输出 NASDAQ100 定投、补仓、保守阶梯止盈卖出、剩余现金、剩余持仓市值、总资产、总收益率和买卖事件。
- `data/risk_compare_report.json` 输出原始策略和阶梯止盈策略的收益率、最大回撤、波动率、现金占比、买入次数和卖出次数，并给出风险改善和收益代价结论。
- `data/take_profit_optimizer_report.json` 输出阶梯止盈档位组合、卖出比例、总收益率、最大回撤、波动率、子弹仓剩余、卖出次数和推荐组合；运行中断时尽量保留 `data/take_profit_optimizer_partial.json`。
- 多参数回测场景默认覆盖 `initial_cash` 为 2000/3000/5000，`monthly_cash_addition` 为 0/200/500 的组合。
- `data/scenarios_report.json` 包含 `summary.scenarios` 和 `summary.fund_comparisons`，用于比较子弹仓使用、剩余现金、触发频率和策略模拟收益。
- V2.2 可视化输出按 scenario 分目录保存 PNG，例如 `reports/backtest_plots/S001/270042_..._S001.png`。

## 3. 当前策略规则

- 阶段高点：最近 250 个交易日最高单位净值。
- 回撤计算：`(current_nav - peak_nav) / peak_nav`。
- 补仓触发档位：
  - 回撤达到 10%：第一档补仓。
  - 回撤达到 15%：第二档补仓。
  - 回撤达到 20%：第三档补仓。
- 补仓金额：
  - 10% 档：剩余子弹仓 * 15%。
  - 15% 档：剩余子弹仓 * 25%。
  - 20% 档：剩余子弹仓 * 35%。
- 金额向上取整到 10 元。
- 多档同时触发时，按 10%、15%、20% 顺序逐档扣减剩余子弹仓后再计算下一档。
- 策略启用日：`strategy_activation_date`。
  - 启用日前已经发生的回撤不追补。
  - 已处于 10% 或 15% 历史回撤时，状态显示为“历史回撤”，建议“不追补历史档位。”
  - 已处于 20% 以上深度历史回撤时，状态显示为“深度回撤中”，建议“不追补历史档位，继续观察”。
  - 启用日后新跌破的档位才允许生成补仓建议。
- 每档只触发一次。
- 当前净值创新高后重置所有触发记录。
- 已删除旧规则：120 日高点、13% 档位、23% 风险观察、25% 风险观察。

## 4. 已知问题/风险

- WSL 当前环境缺少 pip/ensurepip，创建 `.venv` 需要先安装 `python3.14-venv` 和 `python3-pip`。
- AKShare 依赖网络和上游接口稳定性；接口字段或返回结构变化时，需要更新字段映射。
- 回测收益率是基于历史净值和补仓事件的策略模拟收益，不代表真实账户收益。
- 资产级 NAV 使用资产内基金首个共同日期归一化后的等权平均，仅用于策略对照回测，不代表真实指数或账户净值。
- 组合级回测中如果某资产代表基金为空、仍是占位或上游接口无数据，该资产会被 skipped 并写入 warnings。
- 回测图表中文显示依赖系统 CJK 字体；缺少中文字体时，基金中文名可能显示为方框，但 PNG 仍会正常生成。
- 当前配置文件名为 `config.yaml`，但内容使用 JSON/YAML 兼容格式，由标准库 `json` 读取。
- 已提供自动运行脚本，但 Windows 任务计划程序需要用户在本机手动创建任务。
- `nav_data.json` 不存在时 local 只能报告缺数据，无法计算。
- 当前项目没有真实交易接口，所有补仓执行都必须用户手动确认。
- `config.yaml` 中的邮箱密码仅为示例；真实邮箱授权码需要用户本地填写，不能提交到 Git。

## 5. 下一步开发计划

- 安装并验证 AKShare 真实数据拉取，确认三只基金代码的数据可用性。
- 增加 `nav_data.json` 示例文件或导入脚本，便于离线测试。
- 验证 Windows 任务计划程序在本机每天 13:30 自动运行。
- 后续可补充 cron/systemd timer 示例。
- 后续可增加微信或其他通知渠道。
- 验证真实 SMTP 邮件推送，并按邮箱服务商补充授权码配置说明。
- 增加更严格的数据校验，例如单位净值为空、日期重复、净值非正数。
- 后续可扩展 Web 管理后台。

## 6. 如何运行测试和运行项目

从零开始准备环境：

```bash
cd /home/xingke233/projects/apps/DrawdownGuard
sudo apt update
sudo apt install -y python3.14-venv python3-pip
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

运行测试：

```bash
python3 -m unittest discover -s tests
python3 -m py_compile main.py data_provider.py notifier.py storage.py strategy.py tests/test_strategy.py
```

运行项目：

```bash
python3 main.py run
```

运行每日脚本并保存终端输出：

```bash
./scripts/run_daily.sh
```

确认补仓：

```bash
python3 main.py confirm 270042 10
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

查看最近一次回测摘要：

```bash
python3 main.py backtest-report
```

查看最近一次回测收益估算：

```bash
python3 main.py backtest-return
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
```

运行定投周几分析：

```bash
python3 main.py weekly-dca
python3 main.py weekly-dca --source scenarios
```

运行多参数回测场景：

```bash
python3 main.py backtest-scenarios
```

查看多参数场景收益估算：

```bash
python3 main.py scenarios-return
```

生成回测可视化图表：

```bash
python3 main.py backtest-plot
python3 main.py backtest-plot --all
python3 main.py backtest-plot --source scenarios --scenario S001
python3 main.py backtest-plot --source backtest
```

可视化依赖 `matplotlib`：

```bash
python3 -m pip install matplotlib
```

验证多参数回测报告结构：

```bash
python3 -m json.tool data/scenarios_report.json >/tmp/drawdownguard_scenarios_check.json
```

真实数据验收需要用户本机具备 AKShare 和网络：

```bash
source .venv/bin/activate
python3 main.py backtest-scenarios
```

如果 AKShare、网络或上游接口不可用，需要标记：【真实验收未完成，等待用户本机运行】。

Windows 任务计划程序建议：

- 程序或脚本：`wsl.exe`
- 参数：`bash -lc "cd /home/xingke233/projects/apps/DrawdownGuard && ./scripts/run_daily.sh"`
- 触发器：每天 `13:30`
- 脚本只生成提醒和日志，不自动交易。
- 用户需要在 `15:00` 前手动决定是否执行补仓。
- 如果电脑当天未开机，则不会自动运行，需要手动执行 `bash scripts/run_daily.sh`。

使用本地备用数据：

```bash
# 修改 config.yaml，把 "data_source": "real" 改为 "local"
# 准备 nav_data.json 后运行
python3 main.py run
```

## V3.7 Real Portfolio Profile Integration

本次为配置层、资产层和真实持仓层接入，不改变现有策略计算逻辑。

当前真实配置版本：`2026-06 投委会最终版`。

新增真实配置文件：

- `data/user_profile.json`：投资者画像、余额宝子弹仓、生活账户隔离规则。
- `data/current_holdings.json`：真实持仓、资产分组、角色、当前金额和权重。
- `data/dca_plan.json`：真实定投计划，每周四定投，黄金每月 1 日定投。
- `data/policy_config.json`：允许补仓/禁止补仓基金与 10/15/20 回撤补仓规则。

新增命令：

```bash
python3 main.py profile-report
python3 main.py holdings-report
python3 main.py policy-check
```

接入结果：

- 子弹仓已更新为余额宝 `1883` 元。
- 生活账户 `investable=false`，不进入补仓、回测、优化或再平衡计算。
- NASDAQ100 已按资产合并 `270042 + 012752`；组合回测使用 `270042` 作为代表净值。
- 真实组合回测支持每周四定投，并支持黄金 `000216` 每月 1 日定投。
- 红利低波 `008163` 使用 `accumulated_nav`。
- `portfolio-backtest`、`portfolio-report`、`portfolio-strategy-synth` 和 `portfolio-optimize` 可读取真实配置生成的资产字段。

允许补仓基金：`270042`、`012752`、`012349`。

禁止补仓基金：`023918`、`008163`、`000216`、`110017`、`420102`、`000546`、`018125`、`016708`。

## V3.8 Rebalancing Advisor

本次新增再平衡建议模块，只生成建议，不自动交易，不修改补仓策略逻辑，不修改 `portfolio-backtest` 逻辑。

新增命令：

```bash
python3 main.py rebalance-advice
python3 main.py rebalance-detail
```

输出文件：

- `data/rebalance_advice.json`

目标权重配置已加入 `data/user_profile.json`：

- `CASH`：15%，区间 10% 到 25%。
- `CORE`：35%，区间 25% 到 50%。
- `SATELLITE`：20%，区间 10% 到 30%。
- `DEFENSIVE`：30%，区间 20% 到 45%。

当前建议规则：

- 当前核心资产低配时，建议未来定投优先流向 NASDAQ100。
- 防守资产高于目标但未超上限时，建议维持，不立即卖债券。
- HSTECH 维持小仓位观察，不使用子弹仓主动追补。
- 红利低波继续按 `accumulated_nav` 观察。
- 主动基金和有色金属不新增定投，仅观察。
