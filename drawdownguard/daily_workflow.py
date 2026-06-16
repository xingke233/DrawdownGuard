from datetime import date
from contextlib import contextmanager
import os
import socket
from time import perf_counter
import traceback


STEP_STATUS_LABELS = {
    "success": "OK",
    "warning": "WARNING",
    "failed": "FAILED",
    "skipped": "SKIPPED",
}

PROXY_ENV_KEYS = ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY")


def run_daily_workflow(
    steps,
    save_report,
    final_report="data/committee_report.md",
    today=None,
    conclusion_builder=None,
    clean_proxy=False,
):
    report = {
        "date": today or date.today().isoformat(),
        "status": "success",
        "clean_proxy": clean_proxy,
        "network_proxy_mode": "clean_proxy" if clean_proxy else "inherited_env",
        "run_step_source": None,
        "steps": [],
        "final_report": final_report,
        "warnings": [],
        "errors": [],
    }

    with proxy_environment(clean_proxy):
        for step in steps:
            result = _run_step(step)
            report["steps"].append(result)
            if result["name"] == "run":
                report["run_step_source"] = result.get("result_source", "cached_or_previous")
            report["warnings"].extend(result.get("warnings", []))
            if result["status"] == "failed":
                report["errors"].append(f"{result['name']}: {result['message']}")
            elif result["status"] == "warning":
                report["warnings"].append(f"{result['name']}: {result['message']}")

        if conclusion_builder:
            report["today_conclusion"] = conclusion_builder()
        else:
            report["today_conclusion"] = {}

    report["status"] = overall_status(report)
    if report["run_step_source"] is None:
        report["run_step_source"] = "cached_or_previous"
    save_report(report)
    return report


@contextmanager
def proxy_environment(clean_proxy=False):
    if not clean_proxy:
        yield
        return
    previous = {key: os.environ.get(key) for key in PROXY_ENV_KEYS}
    try:
        for key in PROXY_ENV_KEYS:
            os.environ.pop(key, None)
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _run_step(step):
    name = step["name"]
    if step.get("skip"):
        return {
            "name": name,
            "status": "skipped",
            "message": step.get("skip_message", "已跳过。"),
            "duration_seconds": 0,
            "warnings": [],
        }

    started = perf_counter()
    try:
        value = step["func"]() or {}
        status = value.get("status", "success")
        message = value.get("message", "OK")
        warnings = list(value.get("warnings", []))
        result_source = value.get("result_source")
    except Exception as exc:
        status = "failed"
        message = str(exc)
        warnings = []
        result_source = None
        value = {"traceback": traceback.format_exc()}

    return {
        "name": name,
        "status": status,
        "message": message,
        "duration_seconds": round(perf_counter() - started, 3),
        "warnings": warnings,
        **({"result_source": result_source} if result_source else {}),
        **({"traceback": value["traceback"]} if value.get("traceback") else {}),
    }


def build_network_debug_report(provider_name="NavDataProvider"):
    proxies = {
        "http_proxy": os.environ.get("http_proxy") or os.environ.get("HTTP_PROXY"),
        "https_proxy": os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY"),
        "no_proxy": os.environ.get("no_proxy") or os.environ.get("NO_PROXY"),
    }
    try:
        addrinfo = socket.getaddrinfo("fund.eastmoney.com", 443)
        dns_result = [f"{item[4][0]}:{item[4][1]}" for item in addrinfo[:5]]
    except Exception as exc:
        dns_result = [f"ERROR: {exc}"]

    try:
        from requests.utils import get_environ_proxies

        request_proxies = get_environ_proxies("https://fund.eastmoney.com")
    except Exception as exc:
        request_proxies = {"error": str(exc)}

    return {
        "http_proxy": proxies["http_proxy"],
        "https_proxy": proxies["https_proxy"],
        "no_proxy": proxies["no_proxy"],
        "fund_eastmoney_getaddrinfo": dns_result,
        "requests_environ_proxies": request_proxies,
        "data_provider": provider_name,
        "run_call_path": "direct_internal_function",
    }


def overall_status(report):
    committee = next((step for step in report["steps"] if step["name"] == "committee-report"), None)
    if committee and committee["status"] == "failed":
        return "failed"
    if any(step["status"] == "failed" for step in report["steps"]):
        return "warning"
    if any(step["status"] == "warning" for step in report["steps"]) or report.get("warnings"):
        return "warning"
    return "success"


def format_daily_summary(report):
    lines = ["DrawdownGuard Daily Workflow", ""]
    lines.append(f"网络代理模式：{report.get('network_proxy_mode', 'inherited_env')}")
    lines.append(f"run结果来源：{report.get('run_step_source', 'cached_or_previous')}")
    lines.append("")
    for index, step in enumerate(report.get("steps", []), start=1):
        lines.append(f"{index}. {step['name']}: {STEP_STATUS_LABELS.get(step['status'], step['status'])}")
    lines.append("")
    lines.append("最终报告：")
    lines.append(report.get("final_report", "data/committee_report.md"))
    lines.append("")
    lines.append("今日结论：")
    conclusion = report.get("today_conclusion", {})
    lines.append(f"* 是否触发补仓：{conclusion.get('drawdown_triggered', 'N/A')}")
    lines.append(f"* 是否需要立即再平衡：{conclusion.get('needs_immediate_rebalance', 'N/A')}")
    lines.append(f"* 未来定投方向：{conclusion.get('future_dca_bias', 'N/A')}")
    if report.get("warnings"):
        lines.append("")
        lines.append("Warnings:")
        for warning in report["warnings"][:10]:
            lines.append(f"- {warning}")
    if report.get("errors"):
        lines.append("")
        lines.append("Errors:")
        for error in report["errors"]:
            lines.append(f"- {error}")
    return "\n".join(lines)
