from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze search strategies from a benchmark report.")
    parser.add_argument("report", help="Path to benchmark JSON report.")
    parser.add_argument(
        "--model-id",
        default="",
        help="Specific model id to analyze. Defaults to all models in the report.",
    )
    parser.add_argument(
        "--variants",
        default="",
        help="Comma-separated variant ids to analyze. Defaults to all variants in the report.",
    )
    parser.add_argument(
        "--weight-step",
        type=float,
        default=0.05,
        help="Hybrid best-score weight sweep step. Centroid weight is 1-step.",
    )
    return parser.parse_args()


def evaluate_strategy(details: list[dict], strategy: str, best_weight: float = 0.0) -> dict:
    correct = 0
    total = 0
    for row in details:
        ranking = []
        for candidate in row.get("ranking", []):
            if strategy == "centroid":
                score = candidate["centroid_score"]
            elif strategy == "hybrid":
                score = (best_weight * candidate["best_score"]) + ((1.0 - best_weight) * candidate["centroid_score"])
            else:
                score = candidate["best_score"]
            ranking.append((candidate["canonical"], score))

        if len(ranking) < 2:
            continue

        ranking.sort(key=lambda item: item[1], reverse=True)
        total += 1
        if ranking[0][0] == row["expected"]:
            correct += 1

    return {
        "accuracy": round(correct / total, 4) if total else 0.0,
        "correct": correct,
        "total": total,
    }


def main() -> None:
    args = parse_args()
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    report_search = report.get("search", {})

    model_ids = [args.model_id] if args.model_id else list(report_search.keys())
    variant_filter = {variant.strip() for variant in args.variants.split(",") if variant.strip()}
    weight_step = max(min(args.weight_step, 1.0), 0.01)
    weight_points = int(round(1.0 / weight_step))

    results: dict[str, dict] = {}
    for model_id in model_ids:
        model_report = report_search.get(model_id)
        if not model_report:
            continue

        per_variant: dict[str, dict] = {}
        for variant, variant_report in model_report.items():
            if variant_filter and variant not in variant_filter:
                continue

            details = variant_report.get("details", [])
            best = evaluate_strategy(details, "best")
            centroid = evaluate_strategy(details, "centroid")

            best_hybrid: dict | None = None
            for idx in range(weight_points + 1):
                best_weight = round(idx * weight_step, 4)
                hybrid = evaluate_strategy(details, "hybrid", best_weight=best_weight)
                candidate = {
                    "best_weight": best_weight,
                    "centroid_weight": round(1.0 - best_weight, 4),
                    **hybrid,
                }
                if best_hybrid is None or (candidate["accuracy"], candidate["correct"]) > (
                    best_hybrid["accuracy"],
                    best_hybrid["correct"],
                ):
                    best_hybrid = candidate

            per_variant[variant] = {
                "best": best,
                "centroid": centroid,
                "best_hybrid": best_hybrid,
            }
        results[model_id] = per_variant

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()