import unittest
from unittest.mock import patch

from drawdownguard.email_notifier import build_email_body, send_daily_email


class EmailNotifierTest(unittest.TestCase):
    def setUp(self):
        self.config = {
            "peak_window_trading_days": 250,
            "bullet_account": {"name": "余额宝", "balance": 2000},
            "email": {
                "enabled": True,
                "smtp_host": "smtp.example.com",
                "smtp_port": 587,
                "use_tls": True,
                "username": "sender@example.com",
                "password": "app_password",
                "sender": "sender@example.com",
                "receivers": ["receiver@example.com"],
                "send_only_when_action_required": True,
            },
        }
        self.no_action_results = [
            {
                "fund_name": "观察基金",
                "current_date": "2026-06-09",
                "current_nav": 1.0,
                "peak_nav": 1.02,
                "drawdown": -0.0196,
                "status": "观察中",
                "suggested_amounts": {},
                "warnings": [],
            }
        ]
        self.action_results = [
            {
                "fund_name": "补仓基金",
                "current_date": "2026-06-09",
                "current_nav": 0.88,
                "peak_nav": 1.0,
                "drawdown": -0.12,
                "status": "第一档已触发",
                "suggested_amounts": {"10": 300},
                "warnings": [],
            }
        ]

    @patch("drawdownguard.email_notifier.smtplib.SMTP")
    def test_disabled_email_does_not_send(self, smtp):
        config = {**self.config, "email": {**self.config["email"], "enabled": False}}

        result = send_daily_email(config, self.action_results)

        self.assertFalse(result["sent"])
        smtp.assert_not_called()

    @patch("drawdownguard.email_notifier.smtplib.SMTP")
    def test_empty_receivers_does_not_send(self, smtp):
        config = {**self.config, "email": {**self.config["email"], "receivers": []}}

        result = send_daily_email(config, self.action_results)

        self.assertFalse(result["sent"])
        self.assertEqual(result["reason"], "no receivers configured")
        smtp.assert_not_called()

    @patch("drawdownguard.email_notifier.smtplib.SMTP")
    def test_send_only_when_action_required_skips_without_suggestions(self, smtp):
        result = send_daily_email(self.config, self.no_action_results)

        self.assertFalse(result["sent"])
        self.assertEqual(result["reason"], "no action required")
        smtp.assert_not_called()

    @patch("drawdownguard.email_notifier.smtplib.SMTP")
    def test_sends_when_action_required_exists(self, smtp):
        smtp_instance = smtp.return_value.__enter__.return_value

        result = send_daily_email(self.config, self.action_results)

        self.assertTrue(result["sent"])
        smtp.assert_called_once_with("smtp.example.com", 587)
        smtp_instance.starttls.assert_called_once()
        smtp_instance.login.assert_called_once_with("sender@example.com", "app_password")
        smtp_instance.send_message.assert_called_once()
        message = smtp_instance.send_message.call_args.args[0]
        self.assertEqual(message["Subject"], "DrawdownGuard 每日检查 2026-06-09")
        self.assertIn("建议补仓金额：10% 档 300 元", message.get_content())

    @patch("drawdownguard.email_notifier.smtplib.SMTP")
    def test_smtp_exception_does_not_raise(self, smtp):
        smtp.side_effect = RuntimeError("smtp down")

        result = send_daily_email(self.config, self.action_results)

        self.assertFalse(result["sent"])
        self.assertIn("邮件发送失败", result["warning"])

    def test_email_body_contains_historical_drawdown_hint(self):
        results = [
            {
                "fund_name": "历史基金",
                "current_date": "2026-06-09",
                "current_nav": 0.7071,
                "peak_nav": 1.0,
                "drawdown": -0.2929,
                "historical_drawdown": -0.2929,
                "status": "深度回撤中",
                "advice": "不追补历史档位，继续观察",
                "suggested_amounts": {},
                "warnings": [],
            }
        ]

        body = build_email_body(self.config, results)

        self.assertIn("子弹仓余额：2000 元", body)
        self.assertIn("历史回撤：-29.29%", body)
        self.assertIn("历史回撤提示：不追补历史档位，继续观察", body)


if __name__ == "__main__":
    unittest.main()
