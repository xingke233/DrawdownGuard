import smtplib
from datetime import date
from email.message import EmailMessage


def send_daily_email(config, results, report_date=None):
    email_config = config.get("email", {})
    if not email_config.get("enabled", False):
        return {"sent": False, "reason": "email disabled"}

    receivers = email_config.get("receivers", [])
    if not receivers:
        return {"sent": False, "reason": "no receivers configured"}

    if email_config.get("send_only_when_action_required", True) and not has_action_required(results):
        return {"sent": False, "reason": "no action required"}

    message = build_daily_email(config, results, report_date=report_date)

    try:
        with smtplib.SMTP(email_config["smtp_host"], int(email_config.get("smtp_port", 587))) as smtp:
            if email_config.get("use_tls", True):
                smtp.starttls()
            username = email_config.get("username")
            password = email_config.get("password")
            if username and password:
                smtp.login(username, password)
            smtp.send_message(message)
    except Exception as exc:
        return {"sent": False, "warning": f"邮件发送失败：{exc}"}

    return {"sent": True}


def build_daily_email(config, results, report_date=None):
    email_config = config["email"]
    current_date = report_date or _report_date(results)
    message = EmailMessage()
    message["Subject"] = f"DrawdownGuard 每日检查 {current_date}"
    message["From"] = email_config.get("sender") or email_config.get("username", "")
    message["To"] = ", ".join(email_config.get("receivers", []))
    message.set_content(build_email_body(config, results))
    return message


def build_email_body(config, results):
    bullet = config["bullet_account"]
    lines = [
        "DrawdownGuard 每日检查",
        f"子弹仓余额：{bullet['balance']} 元",
        "",
    ]

    for result in results:
        lines.append(result["fund_name"])
        if result.get("skipped"):
            lines.append("当前净值：-")
            lines.append(f"{config['peak_window_trading_days']}日高点：-")
            lines.append("回撤：-")
            lines.append(f"状态：{result['status']}")
            lines.append("建议补仓金额：无")
            _append_warnings(lines, result)
            lines.append("")
            continue

        lines.append(f"当前净值：{result['current_nav']:.4f}")
        lines.append(f"{config['peak_window_trading_days']}日高点：{result['peak_nav']:.4f}")
        lines.append(f"回撤：{result['drawdown'] * 100:.2f}%")
        lines.append(f"状态：{result['status']}")

        if result.get("historical_drawdown") is not None and result["status"] in (
            "历史回撤",
            "深度回撤中",
        ):
            lines.append(f"历史回撤：{result['historical_drawdown'] * 100:.2f}%")
        if result.get("advice"):
            lines.append(f"历史回撤提示：{result['advice']}")

        suggestions = result.get("suggested_amounts", {})
        if suggestions:
            suggestion_text = "，".join(f"{level}% 档 {amount} 元" for level, amount in suggestions.items())
            lines.append(f"建议补仓金额：{suggestion_text}")
        else:
            lines.append("建议补仓金额：无")
        _append_warnings(lines, result)
        lines.append("")

    return "\n".join(lines).rstrip()


def has_action_required(results):
    return any(result.get("suggested_amounts") for result in results)


def _append_warnings(lines, result):
    for warning in result.get("warnings", []):
        lines.append(f"提示：{warning}")


def _report_date(results):
    for result in results:
        if result.get("current_date"):
            return result["current_date"]
    return date.today().isoformat()
