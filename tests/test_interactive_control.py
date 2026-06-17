import unittest
from types import SimpleNamespace
from unittest.mock import patch

from drawdownguard.interactive_control import run_interactive_control


class InteractiveControlTest(unittest.TestCase):
    def test_invalid_input_does_not_crash(self):
        calls = []
        actions = _actions(calls)

        with patch("builtins.input", side_effect=["bad", "17"]):
            code = run_interactive_control(actions, SimpleNamespace(config="config.yaml", nav_file="nav_data.json"))

        self.assertEqual(code, 0)
        self.assertEqual(calls, [])

    def test_menu_can_call_policy_check(self):
        calls = []
        actions = _actions(calls)

        with patch("builtins.input", side_effect=["14", "17"]):
            code = run_interactive_control(actions, SimpleNamespace(config="config.yaml", nav_file="nav_data.json"))

        self.assertEqual(code, 0)
        self.assertIn("policy", calls)


def _actions(calls):
    def action(name):
        def run(args):
            calls.append(name)
            return 0

        return run

    return {
        "profile": action("profile"),
        "holdings": action("holdings"),
        "committee": action("committee"),
        "daily": action("daily"),
        "cash_update": action("cash_update"),
        "holding_update": action("holding_update"),
        "watchlist_add": action("watchlist_add"),
        "watchlist_remove": action("watchlist_remove"),
        "dca_add": action("dca_add"),
        "dca_update": action("dca_update"),
        "dca_pause": action("dca_pause"),
        "dca_resume": action("dca_resume"),
        "policy": action("policy"),
        "backup": action("backup"),
        "rollback": action("rollback"),
    }
