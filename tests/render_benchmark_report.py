"""Render a self-contained HTML report from benchmark_dataset.py JSON output."""

from __future__ import annotations

import argparse
import json
from html import escape
from pathlib import Path


VARIANT_ORDER = ["full", "no_denoise", "no_separation", "fast"]
STEP_ORDER = [
    "normalize",
    "separate",
    "renormalize_after_separation",
    "denoise",
    "vad",
    "segment",
]
STEP_COLORS = {
    "normalize": "#3b82f6",
    "separate": "#f97316",
    "renormalize_after_separation": "#facc15",
    "denoise": "#14b8a6",
    "vad": "#8b5cf6",
    "segment": "#ec4899",
}
VARIANT_LABELS = {
    "full": "完整流程",
    "no_denoise": "關閉降噪",
    "no_separation": "關閉人聲分離",
    "fast": "快速路徑",
}
MODEL_LABELS = {
    "ecapa-tdnn-v1": "ECAPA-TDNN",
    "resemblyzer-v1": "Resemblyzer",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render benchmark report HTML.")
    parser.add_argument("input_json", help="Path to the benchmark JSON report.")
    parser.add_argument("output_html", help="Path to the HTML report to generate.")
    return parser.parse_args()


def fmt_seconds(value: float) -> str:
    return f"{value:.2f}s"


def fmt_percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def nice_variant_name(variant: str) -> str:
    return VARIANT_LABELS.get(variant, variant)


def nice_model_name(model_id: str) -> str:
    return MODEL_LABELS.get(model_id, model_id)


def render_summary_cards(report: dict) -> str:
    full_timing = report["timings"].get("full", {}).get("step_mean_seconds", {})
    separate_mean = full_timing.get("separate", 0.0)
    separator_profile = report.get("separator_profile", {})
    search_strategy = report.get("search_strategy", "best")

    best_search = None
    for model_id, variants in report["search"].items():
        result = variants.get("full")
        if not result:
            continue
        candidate = (result["accuracy"], model_id)
        if best_search is None or candidate > best_search:
            best_search = candidate

    best_verify = None
    for model_id, variants in report["verify"].items():
        result = variants.get("full")
        if not result:
            continue
        candidate = (result["accuracy"], model_id)
        if best_verify is None or candidate > best_verify:
            best_verify = candidate

    cards = [
        (
            "資料集規模",
            f"{report.get('speaker_count', 0)} 位 / {report.get('sample_count', 0)} 檔",
        ),
        ("完整流程平均人聲分離時間", fmt_seconds(separate_mean)),
        (
            "完整流程最佳 1:1 準確率",
            f"{fmt_percent(best_verify[0])} · {nice_model_name(best_verify[1])}" if best_verify else "-",
        ),
        (
            "目前測試配置",
            (
                f"{separator_profile.get('id', '-')} / {search_strategy}"
                if separator_profile
                else search_strategy
            ),
        ),
    ]

    return "".join(
        f"<div class='card metric'><div class='eyebrow'>{escape(label)}</div><div class='metric-value'>{escape(value)}</div></div>"
        for label, value in cards
    )


def render_step_legend() -> str:
    items = []
    for step in STEP_ORDER:
        items.append(
            "<div class='legend-item'>"
            f"<span class='legend-swatch' style='background:{STEP_COLORS[step]}'></span>"
            f"<span>{escape(step)}</span>"
            "</div>"
        )
    return "".join(items)


def render_timing_chart(report: dict) -> str:
    timings = report["timings"]
    chart_width = 900
    chart_height = 340
    margin_left = 170
    margin_right = 30
    margin_top = 30
    margin_bottom = 50
    plot_width = chart_width - margin_left - margin_right
    row_height = 56
    bar_height = 28

    totals = []
    for variant in VARIANT_ORDER:
        step_values = timings.get(variant, {}).get("step_mean_seconds", {})
        totals.append(sum(step_values.get(step, 0.0) for step in STEP_ORDER))
    max_total = max(totals) if totals else 1.0
    if max_total <= 0:
        max_total = 1.0

    svg = [f"<svg viewBox='0 0 {chart_width} {chart_height}' role='img' aria-label='前處理耗時圖'>"]
    for tick in range(6):
        x = margin_left + plot_width * tick / 5
        seconds = max_total * tick / 5
        svg.append(
            f"<line x1='{x:.1f}' y1='{margin_top}' x2='{x:.1f}' y2='{chart_height - margin_bottom}' class='grid' />"
        )
        svg.append(
            f"<text x='{x:.1f}' y='{chart_height - 18}' class='axis-label' text-anchor='middle'>{seconds:.1f}s</text>"
        )

    for index, variant in enumerate(VARIANT_ORDER):
        top = margin_top + index * row_height + 8
        step_values = timings.get(variant, {}).get("step_mean_seconds", {})
        current_x = margin_left
        total = 0.0
        for step in STEP_ORDER:
            value = step_values.get(step, 0.0)
            total += value
            width = plot_width * value / max_total
            if width <= 0:
                continue
            svg.append(
                f"<rect x='{current_x:.1f}' y='{top}' width='{width:.1f}' height='{bar_height}' rx='8' fill='{STEP_COLORS[step]}' />"
            )
            if width >= 54:
                svg.append(
                    f"<text x='{current_x + width / 2:.1f}' y='{top + 18:.1f}' class='bar-label' text-anchor='middle'>{value:.1f}s</text>"
                )
            current_x += width

        svg.append(
            f"<text x='{margin_left - 16}' y='{top + 18:.1f}' class='axis-label variant-label' text-anchor='end'>{escape(nice_variant_name(variant))}</text>"
        )
        svg.append(
            f"<text x='{margin_left + plot_width + 10}' y='{top + 18:.1f}' class='axis-label'>{total:.1f}s</text>"
        )

    svg.append("</svg>")
    return "".join(svg)


def render_verify_scatter(model_id: str, variants: dict) -> str:
    width = 900
    height = 360
    margin_left = 70
    margin_right = 20
    margin_top = 25
    margin_bottom = 50
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom

    threshold = variants.get("full", {}).get("threshold", 0.65)
    svg = [
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='{escape(nice_model_name(model_id))} 驗證分數圖'>"
    ]

    for tick in range(6):
        score = tick / 5
        y = margin_top + plot_height - plot_height * score
        svg.append(f"<line x1='{margin_left}' y1='{y:.1f}' x2='{width - margin_right}' y2='{y:.1f}' class='grid' />")
        svg.append(f"<text x='{margin_left - 10}' y='{y + 4:.1f}' class='axis-label' text-anchor='end'>{score:.1f}</text>")

    threshold_y = margin_top + plot_height - plot_height * threshold
    svg.append(
        f"<line x1='{margin_left}' y1='{threshold_y:.1f}' x2='{width - margin_right}' y2='{threshold_y:.1f}' class='threshold-line' />"
    )
    svg.append(
        f"<text x='{width - margin_right}' y='{threshold_y - 8:.1f}' class='threshold-label' text-anchor='end'>threshold {threshold:.2f}</text>"
    )

    group_width = plot_width / max(len(VARIANT_ORDER), 1)
    for variant_index, variant in enumerate(VARIANT_ORDER):
        center_x = margin_left + group_width * variant_index + group_width / 2
        left_x = center_x - group_width * 0.3
        right_x = center_x + group_width * 0.3
        svg.append(
            f"<text x='{center_x:.1f}' y='{height - 18}' class='axis-label' text-anchor='middle'>{escape(nice_variant_name(variant))}</text>"
        )

        scores = variants.get(variant, {}).get("scores", [])
        same_scores = [row["score"] for row in scores if row["expected_same"]]
        diff_scores = [row["score"] for row in scores if not row["expected_same"]]

        for idx, score in enumerate(same_scores):
            jitter = ((idx % 7) - 3) * 6
            y = margin_top + plot_height - plot_height * score
            svg.append(
                f"<circle cx='{left_x + jitter:.1f}' cy='{y:.1f}' r='5' fill='#10b981' fill-opacity='0.82' />"
            )

        for idx, score in enumerate(diff_scores):
            jitter = ((idx % 7) - 3) * 6
            y = margin_top + plot_height - plot_height * score
            svg.append(
                f"<circle cx='{right_x + jitter:.1f}' cy='{y:.1f}' r='5' fill='#ef4444' fill-opacity='0.82' />"
            )

        svg.append(f"<text x='{left_x:.1f}' y='{margin_top + 14}' class='axis-caption' text-anchor='middle'>same</text>")
        svg.append(f"<text x='{right_x:.1f}' y='{margin_top + 14}' class='axis-caption' text-anchor='middle'>different</text>")

    svg.append("</svg>")
    return "".join(svg)


def render_search_accuracy(report: dict) -> str:
    search = report["search"]
    width = 900
    height = 320
    margin_left = 70
    margin_right = 20
    margin_top = 25
    margin_bottom = 50
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom
    variant_group_width = plot_width / max(len(VARIANT_ORDER), 1)
    bar_width = variant_group_width / max(len(search), 1) * 0.55

    svg = [f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='1:N 搜尋準確率圖'>"]
    for tick in range(6):
        value = tick / 5
        y = margin_top + plot_height - plot_height * value
        svg.append(f"<line x1='{margin_left}' y1='{y:.1f}' x2='{width - margin_right}' y2='{y:.1f}' class='grid' />")
        svg.append(f"<text x='{margin_left - 10}' y='{y + 4:.1f}' class='axis-label' text-anchor='end'>{value:.1f}</text>")

    colors = ["#0f766e", "#1d4ed8", "#c2410c", "#7c3aed"]
    model_ids = list(search.keys())
    for variant_index, variant in enumerate(VARIANT_ORDER):
        group_left = margin_left + variant_group_width * variant_index + variant_group_width * 0.15
        svg.append(
            f"<text x='{group_left + variant_group_width * 0.35:.1f}' y='{height - 18}' class='axis-label' text-anchor='middle'>{escape(nice_variant_name(variant))}</text>"
        )
        for model_index, model_id in enumerate(model_ids):
            accuracy = search[model_id].get(variant, {}).get("accuracy", 0.0)
            x = group_left + model_index * (bar_width + 14)
            y = margin_top + plot_height - plot_height * accuracy
            height_px = plot_height * accuracy
            color = colors[model_index % len(colors)]
            svg.append(
                f"<rect x='{x:.1f}' y='{y:.1f}' width='{bar_width:.1f}' height='{height_px:.1f}' rx='8' fill='{color}' />"
            )
            svg.append(
                f"<text x='{x + bar_width / 2:.1f}' y='{max(y - 8, margin_top + 12):.1f}' class='axis-label' text-anchor='middle'>{accuracy:.2f}</text>"
            )

    svg.append("</svg>")

    legend = "".join(
        f"<div class='legend-item'><span class='legend-swatch' style='background:{colors[idx % len(colors)]}'></span><span>{escape(nice_model_name(model_id))}</span></div>"
        for idx, model_id in enumerate(model_ids)
    )
    return "".join(svg) + f"<div class='legend'>{legend}</div>"


def render_failure_table(report: dict) -> str:
    rows = []
    failures = report.get("failures", {})
    timing_details = report.get("timing_details", {})
    for variant in VARIANT_ORDER:
        failed = len(failures.get(variant, []))
        succeeded = len(timing_details.get(variant, {}))
        rows.append(
            "<tr>"
            f"<td>{escape(nice_variant_name(variant))}</td>"
            f"<td>{succeeded}</td>"
            f"<td>{failed}</td>"
            "</tr>"
        )
    return (
        "<table class='data-table'><thead><tr><th>Variant</th><th>成功樣本</th><th>失敗樣本</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def render_fast_margin_table(report: dict) -> str:
    rows = []
    for model_id, result in report.get("fast_margin", {}).items():
        margin = "-" if result.get("margin") is None else f"{result['margin']:.2f}"
        rows.append(
            "<tr>"
            f"<td>{escape(nice_model_name(model_id))}</td>"
            f"<td>{margin}</td>"
            f"<td>{fmt_percent(result.get('coverage', 0.0))}</td>"
            f"<td>{fmt_percent(result.get('accuracy', 0.0))}</td>"
            "</tr>"
        )
    return (
        "<table class='data-table'><thead><tr><th>模型</th><th>安全 margin</th><th>coverage</th><th>accuracy</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def build_html(report: dict) -> str:
    model_sections = []
    separator_profile = report.get("separator_profile", {})
    separator_text = " / ".join(
        part for part in [separator_profile.get("id"), separator_profile.get("backend"), separator_profile.get("model")] if part
    ) or "-"
    search_strategy = report.get("search_strategy", "best")
    for model_id, variants in report.get("verify", {}).items():
        model_sections.append(
            "<section class='card section'>"
            f"<div class='section-head'><div><h2>{escape(nice_model_name(model_id))} 1:1 分數分布</h2><p>綠點代表同人，紅點代表不同人；橫線是決策門檻。</p></div></div>"
            f"{render_verify_scatter(model_id, variants)}"
            "</section>"
        )

    return f"""
<!doctype html>
<html lang='zh-Hant'>
<head>
  <meta charset='utf-8' />
  <meta name='viewport' content='width=device-width, initial-scale=1' />
  <title>Voiceprint Benchmark Report</title>
  <style>
    :root {{
      --bg: #f4efe8;
      --surface: rgba(255,255,255,0.74);
      --surface-strong: rgba(255,255,255,0.92);
      --text: #1f2937;
      --muted: #6b7280;
      --line: rgba(31,41,55,0.12);
      --accent: #c2410c;
      --accent-soft: rgba(194,65,12,0.12);
      --grid: rgba(31,41,55,0.08);
      --shadow: 0 20px 60px rgba(120, 53, 15, 0.12);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "Noto Sans TC", sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(249,115,22,0.18), transparent 32%),
        radial-gradient(circle at bottom right, rgba(59,130,246,0.12), transparent 28%),
        var(--bg);
    }}
    .wrap {{ max-width: 1180px; margin: 0 auto; padding: 40px 24px 72px; }}
    .hero {{ margin-bottom: 28px; }}
    .eyebrow {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.12em; color: var(--accent); font-weight: 700; }}
    h1, h2, h3, p {{ margin: 0; }}
    h1 {{ font-size: clamp(34px, 4vw, 54px); line-height: 0.96; margin-top: 12px; max-width: 10ch; }}
    .hero p {{ margin-top: 16px; max-width: 72ch; color: var(--muted); font-size: 15px; line-height: 1.7; }}
    .grid {{ display: grid; gap: 18px; }}
    .grid.metrics {{ grid-template-columns: repeat(4, minmax(0, 1fr)); margin-bottom: 24px; }}
    .card {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(14px);
    }}
    .metric {{ padding: 20px; min-height: 136px; }}
    .metric-value {{ margin-top: 14px; font-size: 28px; font-weight: 700; line-height: 1.15; }}
    .section {{ padding: 24px; margin-top: 18px; }}
    .section-head {{ display: flex; justify-content: space-between; gap: 16px; margin-bottom: 18px; align-items: end; }}
    .section-head p {{ color: var(--muted); margin-top: 6px; line-height: 1.6; }}
    .legend {{ display: flex; flex-wrap: wrap; gap: 10px 16px; margin-top: 14px; }}
    .legend-item {{ display: inline-flex; align-items: center; gap: 8px; color: var(--muted); font-size: 13px; }}
    .legend-swatch {{ width: 12px; height: 12px; border-radius: 999px; display: inline-block; }}
    .data-grid {{ display: grid; gap: 18px; grid-template-columns: 1.25fr 0.95fr; margin-top: 18px; }}
    .data-table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    .data-table th, .data-table td {{ padding: 12px 14px; border-bottom: 1px solid var(--line); text-align: left; }}
    .data-table th {{ color: var(--muted); font-weight: 600; }}
    .data-table tbody tr:last-child td {{ border-bottom: 0; }}
    svg {{ width: 100%; height: auto; display: block; }}
    .grid line, line.grid {{ stroke: var(--grid); stroke-width: 1; }}
    .axis-label {{ fill: var(--muted); font-size: 12px; }}
    .axis-caption {{ fill: var(--muted); font-size: 11px; }}
    .variant-label {{ font-weight: 600; }}
    .bar-label {{ fill: rgba(255,255,255,0.92); font-size: 11px; font-weight: 700; }}
    .threshold-line {{ stroke: #111827; stroke-width: 1.5; stroke-dasharray: 6 6; opacity: 0.45; }}
    .threshold-label {{ fill: #111827; font-size: 12px; font-weight: 700; opacity: 0.65; }}
    .footer-note {{ color: var(--muted); font-size: 13px; line-height: 1.7; margin-top: 18px; }}
    @media (max-width: 980px) {{
      .grid.metrics, .data-grid {{ grid-template-columns: 1fr; }}
      .wrap {{ padding: 28px 16px 48px; }}
      .section {{ padding: 18px; border-radius: 18px; }}
      .metric {{ min-height: auto; }}
    }}
  </style>
</head>
<body>
  <main class='wrap'>
    <section class='hero'>
      <div class='eyebrow'>Voiceprint Benchmark</div>
      <h1>人聲分離值得跑嗎？</h1>
            <p>這份報告把 benchmark 結果直接轉成可視化圖表，重點不是只看單一準確率，而是同時看延遲、分數分布、失敗率，以及快速路徑到底能不能安全提早回傳。此次執行配置：separator = {escape(separator_text)}；search strategy = {escape(search_strategy)}。</p>
    </section>

    <section class='grid metrics'>
      {render_summary_cards(report)}
    </section>

    <section class='card section'>
      <div class='section-head'>
        <div>
          <h2>平均前處理耗時拆解</h2>
          <p>如果橘色的人聲分離段明顯吃掉大多數時間，就表示真正該優化的是 separator，不是後面的 embedding 或資料庫搜尋。</p>
        </div>
      </div>
      {render_timing_chart(report)}
      <div class='legend'>{render_step_legend()}</div>
    </section>

    {''.join(model_sections)}

    <section class='card section'>
      <div class='section-head'>
        <div>
          <h2>1:N 搜尋準確率</h2>
          <p>這張圖用來看不同 variant 在資料庫搜尋場景的 top-1 準確率，通常會比單純看 1:1 更接近實際產品體驗。</p>
        </div>
      </div>
      {render_search_accuracy(report)}
    </section>

    <section class='data-grid'>
      <section class='card section'>
        <div class='section-head'>
          <div>
            <h2>成功 / 失敗樣本數</h2>
            <p>如果關掉人聲分離後失敗樣本暴增，表示這一步雖慢，但對歌聲素材仍是必要條件。</p>
          </div>
        </div>
        {render_failure_table(report)}
      </section>

      <section class='card section'>
        <div class='section-head'>
          <div>
            <h2>快速回傳安全 margin</h2>
            <p>這裡顯示 fast profile 需要離 threshold 多遠，才有機會做到 100% 正確。</p>
          </div>
        </div>
        {render_fast_margin_table(report)}
      </section>
    </section>

    <p class='footer-note'>資料來源：benchmark_dataset.py 的 JSON 輸出。這份圖表是靜態 HTML，適合附在實驗記錄或產品評估文件中。若後續要比較 MDX-Net、Spleeter、Demucs，只要讓 benchmark JSON 多一個 separator 維度，這份報告格式可以直接延用。</p>
  </main>
</body>
</html>
"""


def main() -> None:
    args = parse_args()
    input_path = Path(args.input_json)
    output_path = Path(args.output_html)
    report = json.loads(input_path.read_text(encoding="utf-8"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_html(report), encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()