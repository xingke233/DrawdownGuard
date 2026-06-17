# DrawdownGuard 个人投委会日报

生成日期：2026-06-17
账户状态：关注
今日结论：今日不补仓，不卖出，未来资金按建议倾斜，核心资产低于目标区间，未来定投倾斜

## 一页摘要

| 项目 | 状态 | 结论 |
| --- | --- | --- |
| 补仓状态 | 🟢 无触发 | 今日不补仓 |
| 子弹仓 | 🟢 健康 | 17.56%，处于健康区间 |
| 核心资产 | 🟡 低配 | 核心资产低于目标区间，未来定投倾斜 |
| 卫星资产 | 🟢 合理 | 保持观察 |
| 防守资产 | 🟡 偏高 | 不卖出，未来少新增债券 |
| 再平衡 | 🟡 定投倾斜 | 不卖出，未来资金按建议倾斜 |
| 市场环境 | 🟡 neutral | 市场环境中性，继续观察 |

## 今日操作清单

- [ ] 是否需要补仓：否
- [ ] 是否需要卖出：否
- [ ] 是否需要调整定投：暂不调整
- [ ] 是否需要关注：HSTECH 深度回撤，但不追补历史档位
- [ ] 下一次建议运行：python3 main.py daily --quick

## 系统健康状态

| 模块 | 状态 |
| --- | --- |
| policy-check | OK |
| run | OK |
| portfolio-backtest | WARNING |
| contribution-report | OK |
| quant-signal | OK |
| rebalance-advice | OK |
| committee-report | OK |

## Infos / Warnings / Errors

### Infos
- 270042: 真实净值获取失败，已切换到缓存数据：HTTPSConnectionPool(host='fund.eastmoney.com', port=443): Max retries exceeded with url: /pingzhongdata/270042.js (Caused by ProxyError('Unable to connect to proxy', NewConnectionError("HTTPSConnection(host='172.23.80.1', port=7893): Failed to establish a new connection: [Errno 1] Operation not permitted")))
- 012752: 真实净值获取失败，已切换到缓存数据：HTTPSConnectionPool(host='fund.eastmoney.com', port=443): Max retries exceeded with url: /pingzhongdata/012752.js (Caused by ProxyError('Unable to connect to proxy', NewConnectionError("HTTPSConnection(host='172.23.80.1', port=7893): Failed to establish a new connection: [Errno 1] Operation not permitted")))
- 012349: 真实净值获取失败，已切换到缓存数据：HTTPSConnectionPool(host='fund.eastmoney.com', port=443): Max retries exceeded with url: /pingzhongdata/012349.js (Caused by ProxyError('Unable to connect to proxy', NewConnectionError("HTTPSConnection(host='172.23.80.1', port=7893): Failed to establish a new connection: [Errno 1] Operation not permitted")))
- 使用缓存净值
- NASDAQ100: 012752 定投在资产级回测中使用代表基金 270042 净值作为 fallback。
- NASDAQ100: 真实净值获取失败，已切换到缓存数据：HTTPSConnectionPool(host='fund.eastmoney.com', port=443): Max retries exceeded with url: /pingzhongdata/270042.js (Caused by ProxyError('Unable to connect to proxy', NewConnectionError("HTTPSConnection(host='172.23.80.1', port=7893): Failed to establish a new connection: [Errno 1] Operation not permitted")))
- HSTECH: 真实净值获取失败，已切换到缓存数据：HTTPSConnectionPool(host='fund.eastmoney.com', port=443): Max retries exceeded with url: /pingzhongdata/012349.js (Caused by ProxyError('Unable to connect to proxy', NewConnectionError("HTTPSConnection(host='172.23.80.1', port=7893): Failed to establish a new connection: [Errno 1] Operation not permitted")))
- CASHFLOW: 真实净值获取失败，已切换到缓存数据：HTTPSConnectionPool(host='fund.eastmoney.com', port=443): Max retries exceeded with url: /pingzhongdata/023918.js (Caused by ProxyError('Unable to connect to proxy', NewConnectionError("HTTPSConnection(host='172.23.80.1', port=7893): Failed to establish a new connection: [Errno 1] Operation not permitted")))
- DIVIDEND_LOW_VOL: 累计净值获取失败，已回退到单位净值：HTTPSConnectionPool(host='fund.eastmoney.com', port=443): Max retries exceeded with url: /pingzhongdata/008163.js (Caused by ProxyError('Unable to connect to proxy', NewConnectionError("HTTPSConnection(host='172.23.80.1', port=7893): Failed to establish a new connection: [Errno 1] Operation not permitted")))
- DIVIDEND_LOW_VOL: 单位净值获取失败，已切换到缓存数据：HTTPSConnectionPool(host='fund.eastmoney.com', port=443): Max retries exceeded with url: /pingzhongdata/008163.js (Caused by ProxyError('Unable to connect to proxy', NewConnectionError("HTTPSConnection(host='172.23.80.1', port=7893): Failed to establish a new connection: [Errno 1] Operation not permitted")))
- GOLD: 真实净值获取失败，已切换到缓存数据：HTTPSConnectionPool(host='fund.eastmoney.com', port=443): Max retries exceeded with url: /pingzhongdata/000216.js (Caused by ProxyError('Unable to connect to proxy', NewConnectionError("HTTPSConnection(host='172.23.80.1', port=7893): Failed to establish a new connection: [Errno 1] Operation not permitted")))

### Warnings
- NASDAQ100: 真实净值获取失败，已切换到缓存数据：HTTPSConnectionPool(host='fund.eastmoney.com', port=443): Max retries exceeded with url: /pingzhongdata/270042.js (Caused by ProxyError('Unable to connect to proxy', NewConnectionError("HTTPSConnection(host='172.23.80.1', port=7893): Failed to establish a new connection: [Errno 1] Operation not permitted")))
- HSTECH: 真实净值获取失败，已切换到缓存数据：HTTPSConnectionPool(host='fund.eastmoney.com', port=443): Max retries exceeded with url: /pingzhongdata/012349.js (Caused by ProxyError('Unable to connect to proxy', NewConnectionError("HTTPSConnection(host='172.23.80.1', port=7893): Failed to establish a new connection: [Errno 1] Operation not permitted")))
- CASHFLOW: 真实净值获取失败，已切换到缓存数据：HTTPSConnectionPool(host='fund.eastmoney.com', port=443): Max retries exceeded with url: /pingzhongdata/023918.js (Caused by ProxyError('Unable to connect to proxy', NewConnectionError("HTTPSConnection(host='172.23.80.1', port=7893): Failed to establish a new connection: [Errno 1] Operation not permitted")))
- DIVIDEND_LOW_VOL: 累计净值获取失败，已回退到单位净值：HTTPSConnectionPool(host='fund.eastmoney.com', port=443): Max retries exceeded with url: /pingzhongdata/008163.js (Caused by ProxyError('Unable to connect to proxy', NewConnectionError("HTTPSConnection(host='172.23.80.1', port=7893): Failed to establish a new connection: [Errno 1] Operation not permitted")))
- DIVIDEND_LOW_VOL: 单位净值获取失败，已切换到缓存数据：HTTPSConnectionPool(host='fund.eastmoney.com', port=443): Max retries exceeded with url: /pingzhongdata/008163.js (Caused by ProxyError('Unable to connect to proxy', NewConnectionError("HTTPSConnection(host='172.23.80.1', port=7893): Failed to establish a new connection: [Errno 1] Operation not permitted")))
- GOLD: 真实净值获取失败，已切换到缓存数据：HTTPSConnectionPool(host='fund.eastmoney.com', port=443): Max retries exceeded with url: /pingzhongdata/000216.js (Caused by ProxyError('Unable to connect to proxy', NewConnectionError("HTTPSConnection(host='172.23.80.1', port=7893): Failed to establish a new connection: [Errno 1] Operation not permitted")))
- portfolio-backtest: 组合回测完成，但存在数据 warning。

### Errors
- 当前无 error。

## 一、账户总览

- 总资产：10721.00 元
- 子弹仓余额：1883.00 元
- 子弹仓占比：17.56%
- 核心资产占比：20.35%
- 卫星资产占比：18.01%
- 防守资产占比：44.08%
- 最大可接受回撤：30.00%

## 二、当前持仓结构

- NASDAQ100 / 纳斯达克100：2181.00 元，权重 20.35%，role core_growth
- HSTECH / 恒生科技：290.00 元，权重 2.71%，role satellite_opportunity
- CASHFLOW / 自由现金流：574.00 元，权重 5.36%，role quality_factor
- DIVIDEND_LOW_VOL / 红利低波：419.00 元，权重 3.90%，role value_factor
- GOLD / 黄金：763.00 元，权重 7.12%，role hedge
- BONDS / 债券：3963.00 元，权重 36.96%，role bond_stabilizer
- ACTIVE_ADVANCED_MANUFACTURING / 先进制造：542.00 元，权重 5.05%，role active_fund
- NONFERROUS_METALS / 有色金属：106.00 元，权重 0.99%，role cyclical_theme

## 三、今日补仓检查

- 允许补仓资产：270042, 012752, 012349
- 检查日期：2026-06-17

| 基金 | 当前回撤 | 状态 | 建议 |
| --- | ---: | --- | --- |
| 012349 天弘恒生科技ETF联接(QDII)C | -30.70% | 观察中 | 无 |

## 四、组合回测摘要

- 回测区间：2018-01-02 至 2026-06-17
- 总投入：42603.00 元
- 当前估算市值：83968.14 元
- 总收益率：97.09%
- 补仓次数：18
- 子弹仓消耗：1883.00 元

## 五、资产贡献分析

- 最大收益贡献资产：NASDAQ100 / 纳斯达克100
- 最大拖累资产：HSTECH / 恒生科技

| 资产 | 投入权重 | 市值权重 | 收益率 | 收益贡献 | 最大回撤 |
| --- | ---: | ---: | ---: | ---: | ---: |
| NASDAQ100 | 55.47% | 69.46% | 146.83% | 83.88% | -25.25% |
| HSTECH | 15.26% | 7.66% | -1.14% | -0.18% | -26.91% |
| CASHFLOW | 4.15% | 2.07% | -1.87% | -0.08% | -7.05% |
| DIVIDEND_LOW_VOL | 15.54% | 10.20% | 29.33% | 4.69% | -8.93% |
| GOLD | 9.58% | 10.62% | 118.52% | 11.69% | -26.32% |

- NASDAQ100 是核心收益来源。
- GOLD 是重要收益贡献资产，但不是无风险资产。
- DIVIDEND_LOW_VOL / 008163 使用 accumulated_nav 口径观察，避免分红基金单位净值低估。
- HSTECH 维持小仓位卫星。

## 六、再平衡建议

| 大类 | 当前权重 | 目标区间 | 状态 | 建议 |
| --- | ---: | --- | --- | --- |
| CASH | 17.56% | 10.00%-25.00% | 健康 | 保持 |
| CORE | 20.35% | 25.00%-50.00% | 低配 | 定投倾斜 |
| SATELLITE | 18.01% | 10.00%-30.00% | 合理 | 维持 |
| DEFENSIVE | 44.08% | 20.00%-45.00% | 偏高但可接受 | 维持 |

- 当前是否需要立即再平衡：False
- 低配资产：CORE
- 高配资产：无
- 是否建议卖出：False
- 未来定投应偏向：CORE
- 摘要：当前组合不需要立即卖出再平衡；核心资产低配，防守资产高于目标但未超上限，建议通过未来定投逐步向 NASDAQ100 倾斜。

## 七、量化信号

- 组合市场状态：neutral
- 组合平均分：39

| 资产 | 分数 | 状态 | 趋势 | 风险 | 结论 |
| --- | ---: | --- | ---: | ---: | --- |
| NASDAQ100 | 92 | strong_uptrend | 90 | 90 | 当前接近250日高点，趋势健康，未触发补仓，适合继续定投。 |
| HSTECH | 20 | weak | 25 | 15 | 当前处于深度回撤区，历史回撤不追补，维持小仓位观察。 |
| CASHFLOW | 27 | weak | 25 | 40 | 自由现金流作为质量因子资产，当前量化信号用于判断趋势和波动状态。 |
| DIVIDEND_LOW_VOL | 40 | weak | 25 | 90 | 红利低波使用 accumulated_nav 口径，当前作为价值因子观察。 |
| GOLD | 18 | high_risk | 25 | 15 | 黄金长期表现可作为对冲资产观察，但需注意阶段性高位和回撤风险。 |

## 八、投委会结论

- 当前不需要立即卖出。
- NASDAQ100 仍是长期核心。
- 子弹仓应保留用于规则内补仓：270042, 012752, 012349。
- HSTECH 不追补历史回撤。
- 债券不新增或少新增，未来现金流向 CORE 倾斜。
- 黄金维持月定投。
- 红利低波维持观察，并使用 accumulated_nav 口径。

## 九、风险提示

- 历史回测不代表未来收益。
- 系统只辅助决策，不自动交易。
- 生活账户不参与投资。

