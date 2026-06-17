from types import SimpleNamespace

from .config_manager import ConfigManager


MENU = """
DrawdownGuard 控制中心

1. 查看账户总览
2. 查看当前持仓
3. 查看今日投委会报告
4. 运行 daily --quick
5. 运行完整体检 daily --start-date 2018-01-01
6. 更新子弹仓金额
7. 更新基金持仓金额
8. 添加观察基金
9. 删除观察基金
10. 添加定投计划
11. 修改定投金额
12. 暂停定投计划
13. 恢复定投计划
14. 查看 policy-check
15. 备份当前配置
16. 回滚到上一个备份
17. 退出
"""


def run_interactive_control(actions, base_args):
    while True:
        print(MENU)
        choice = input("请选择操作编号：").strip()
        try:
            if choice == "1":
                actions["profile"](base_args)
            elif choice == "2":
                actions["holdings"](base_args)
            elif choice == "3":
                actions["committee"](SimpleNamespace(**vars(base_args), plain=False))
            elif choice == "4":
                actions["daily"](SimpleNamespace(**vars(base_args), quick=True, skip_backtest=False, skip_quant=False, include_watchlist=False, start_date="2018-01-01", open_report=False, clean_proxy=False, debug_network=False))
            elif choice == "5":
                actions["daily"](SimpleNamespace(**vars(base_args), quick=False, skip_backtest=False, skip_quant=False, include_watchlist=False, start_date="2018-01-01", open_report=False, clean_proxy=False, debug_network=False))
            elif choice == "6":
                _update_cash(actions, base_args)
            elif choice == "7":
                _update_holding(actions, base_args)
            elif choice == "8":
                _watchlist_add(actions, base_args)
            elif choice == "9":
                _watchlist_remove(actions, base_args)
            elif choice == "10":
                _dca_add(actions, base_args)
            elif choice == "11":
                _dca_update(actions, base_args)
            elif choice == "12":
                _dca_status(actions, base_args, paused=True)
            elif choice == "13":
                _dca_status(actions, base_args, paused=False)
            elif choice == "14":
                actions["policy"](base_args)
            elif choice == "15":
                actions["backup"](base_args)
            elif choice == "16":
                if _confirm("确认回滚到上一个备份？"):
                    actions["rollback"](SimpleNamespace(**vars(base_args), latest=True))
            elif choice == "17":
                print("已退出 DrawdownGuard 控制中心。")
                return 0
            else:
                print("输入无效，请输入 1-17。")
        except Exception as exc:
            print(f"操作失败：{exc}")
        print("下一步建议：可运行 daily --quick 或继续选择菜单操作。")


def _update_cash(actions, base_args):
    amount = _read_float("请输入新的子弹仓金额：")
    if _confirm(f"确认将子弹仓更新为 {amount} 元？"):
        actions["cash_update"](SimpleNamespace(**vars(base_args), amount=amount, dry_run=False))


def _update_holding(actions, base_args):
    fund_code = input("请输入基金代码：").strip()
    amount = _read_float("请输入新的持仓金额：")
    if _confirm(f"确认将 {fund_code} 持仓金额更新为 {amount} 元？"):
        actions["holding_update"](SimpleNamespace(**vars(base_args), fund_code=fund_code, amount=amount, dry_run=False))


def _watchlist_add(actions, base_args):
    fund_code = input("基金代码：").strip()
    name = input("基金名称：").strip()
    role = input("候选角色 satellite/core/hedge/factor/theme/bond/unknown：").strip() or "unknown"
    reason = input("关注原因：").strip()
    if _confirm(f"确认添加观察基金 {fund_code} {name}？"):
        actions["watchlist_add"](SimpleNamespace(**vars(base_args), fund_code=fund_code, name=name, role=role, reason=reason, nav_mode="unit_nav"))


def _watchlist_remove(actions, base_args):
    fund_code = input("请输入要删除的观察基金代码：").strip()
    if _confirm(f"确认从观察池删除 {fund_code}？"):
        actions["watchlist_remove"](SimpleNamespace(**vars(base_args), fund_code=fund_code))


def _dca_add(actions, base_args):
    fund_code = input("基金代码：").strip()
    amount = _read_float("定投金额：")
    frequency = input("频率 weekly/monthly：").strip() or "weekly"
    weekday = input("周几 mon/tue/wed/thu/fri，可留空：").strip() or None
    if _confirm(f"确认添加 {fund_code} 定投 {amount} 元？"):
        actions["dca_add"](SimpleNamespace(**vars(base_args), fund_code=fund_code, amount=amount, frequency=frequency, weekday=weekday, dry_run=False))


def _dca_update(actions, base_args):
    fund_code = input("基金代码：").strip()
    amount = _read_float("新的定投金额：")
    if _confirm(f"确认修改 {fund_code} 定投金额为 {amount} 元？"):
        actions["dca_update"](SimpleNamespace(**vars(base_args), fund_code=fund_code, amount=amount, dry_run=False))


def _dca_status(actions, base_args, paused):
    fund_code = input("基金代码：").strip()
    label = "暂停" if paused else "恢复"
    if _confirm(f"确认{label} {fund_code} 定投？"):
        key = "dca_pause" if paused else "dca_resume"
        actions[key](SimpleNamespace(**vars(base_args), fund_code=fund_code, dry_run=False))


def _read_float(prompt):
    while True:
        raw = input(prompt).strip()
        try:
            return float(raw)
        except ValueError:
            print("请输入有效数字。")


def _confirm(prompt):
    value = input(f"{prompt} 输入 yes 确认：").strip().lower()
    return value == "yes"
