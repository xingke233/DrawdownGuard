import json
import os
import re
import warnings
from pathlib import Path


os.environ.setdefault("MPLCONFIGDIR", "/tmp/drawdownguard_matplotlib")


def plot_report_file(report_path, output_dir="backtest_plots", scenario_id=None):
    path = Path(report_path)
    with path.open("r", encoding="utf-8") as file:
        report = json.load(file)
    return plot_report(report, output_dir=output_dir, scenario_id=scenario_id)


def plot_report(report, output_dir="backtest_plots", scenario_id=None):
    scenarios = _normalize_report(report)
    if scenario_id:
        scenarios = [item for item in scenarios if item["scenario_id"] == scenario_id]
        if not scenarios:
            raise ValueError(f"未找到 scenario：{scenario_id}")

    output_base = Path(output_dir)
    results = []
    for scenario in scenarios:
        scenario_dir = output_base / scenario["scenario_id"]
        scenario_dir.mkdir(parents=True, exist_ok=True)
        for fund in scenario["funds"]:
            if not fund.get("series"):
                continue
            title = build_plot_title(fund, scenario)
            output_path = scenario_dir / build_plot_filename(fund, scenario)
            _draw_fund_plot(fund, scenario, title, output_path)
            results.append(
                {
                    "scenario_id": scenario["scenario_id"],
                    "fund_code": fund["fund_code"],
                    "fund_name": fund["fund_name"],
                    "title": title,
                    "path": str(output_path),
                }
            )
    return results


def build_plot_title(fund, scenario):
    return (
        f"{fund['fund_code']} {fund['fund_name']} | {scenario['scenario_id']} | "
        f"Initial Cash {scenario['initial_cash']} | Monthly Add {scenario['monthly_cash_addition']}"
    )


def build_plot_filename(fund, scenario):
    safe_name = _safe_filename(fund["fund_name"])
    return f"{fund['fund_code']}_{safe_name}_{scenario['scenario_id']}.png"


def _normalize_report(report):
    if "scenarios" in report:
        return [
            {
                "scenario_id": scenario["scenario_id"],
                "initial_cash": scenario.get("initial_cash", 0),
                "monthly_cash_addition": scenario.get("monthly_cash_addition", 0),
                "funds": scenario.get("funds", []),
            }
            for scenario in report.get("scenarios", [])
        ]

    backtest_config = report.get("backtest", {})
    return [
        {
            "scenario_id": "backtest",
            "initial_cash": backtest_config.get("initial_cash", 0),
            "monthly_cash_addition": backtest_config.get("monthly_cash_addition", 0),
            "funds": report.get("fund_reports", []),
        }
    ]


def _draw_fund_plot(fund, scenario, title, output_path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _configure_matplotlib_font()
    plt.rcParams["axes.unicode_minus"] = False

    series = fund["series"]
    events = fund.get("events", [])
    dates = [item["date"] for item in series]
    nav_values = [item["nav"] for item in series]
    peak_values = [item["peak_nav"] for item in series]
    drawdowns = [item["drawdown"] * 100 for item in series]
    cash_values = [item["cash_after"] for item in series]

    figure, axes = plt.subplots(3, 1, figsize=(13, 10), sharex=True)
    figure.suptitle(title, fontsize=14)

    axes[0].plot(dates, nav_values, label="NAV", color="#2563eb", linewidth=1.8)
    axes[0].plot(dates, peak_values, label="Rolling Peak", color="#f97316", linewidth=1.4)
    axes[0].set_ylabel("NAV")
    axes[0].legend(loc="best")
    axes[0].grid(True, alpha=0.25)

    axes[1].plot(dates, drawdowns, label="Drawdown", color="#dc2626", linewidth=1.5)
    for level in (10, 15, 20):
        axes[1].axhline(-level, color="#9ca3af", linestyle="--", linewidth=0.8)
    axes[1].set_ylabel("Drawdown (%)")
    axes[1].legend(loc="best")
    axes[1].grid(True, alpha=0.25)

    axes[2].plot(dates, cash_values, label="Cash Remaining", color="#059669", linewidth=1.8)
    axes[2].set_ylabel("Cash")
    axes[2].set_xlabel("Date")
    axes[2].legend(loc="best")
    axes[2].grid(True, alpha=0.25)

    _mark_events(axes, events)

    tick_step = max(1, len(dates) // 12)
    axes[2].set_xticks(dates[::tick_step])
    axes[2].tick_params(axis="x", rotation=35)

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Glyph .* missing from font.*")
        figure.tight_layout(rect=(0, 0, 1, 0.96))
        figure.savefig(output_path, dpi=150)
    plt.close(figure)


def _mark_events(axes, events):
    colors = {"10": "#16a34a", "15": "#ca8a04", "20": "#dc2626"}
    labels_seen = set()

    for event in events:
        level = str(event["level"])
        color = colors.get(level, "#111827")
        label = f"{level}% Trigger"
        display_label = label if label not in labels_seen else None
        labels_seen.add(label)

        axes[0].scatter(event["date"], event["nav"], color=color, s=42, zorder=5, label=display_label)
        axes[1].scatter(
            event["date"],
            event["drawdown"] * 100,
            color=color,
            s=42,
            zorder=5,
            label=display_label,
        )
        axes[2].axvline(event["date"], color=color, alpha=0.18, linewidth=1)

    for axis in axes[:2]:
        handles, labels = axis.get_legend_handles_labels()
        unique = {}
        for handle, label in zip(handles, labels):
            unique.setdefault(label, handle)
        axis.legend(unique.values(), unique.keys(), loc="best")


def _safe_filename(value):
    value = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", value, flags=re.UNICODE)
    return value.strip("._") or "fund"


def _configure_matplotlib_font():
    from matplotlib import font_manager, pyplot as plt

    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/arphic/uming.ttc",
    ]
    for font_path in candidates:
        path = Path(font_path)
        if not path.exists():
            continue
        font_manager.fontManager.addfont(str(path))
        font_name = font_manager.FontProperties(fname=str(path)).get_name()
        plt.rcParams["font.family"] = font_name
        return
