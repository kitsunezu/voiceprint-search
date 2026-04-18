"""Benchmark dataset accuracy and latency for voiceprint variants."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from shutil import rmtree

import numpy as np

sys.path.insert(0, "/app")

from app.config import settings
from app.core.audio import normalize_audio, repeat_pad, segment_waveform
from app.core.calibration import CalibratorRegistry
from app.core.denoise import Denoiser
from app.core.embedder import EmbedderRegistry, embed_segments
from app.core.preprocessing import PreprocessError, PreprocessResult, SAMPLE_RATE
from app.core.separator import VocalSeparator
from app.core.vad import VoiceActivityDetector


AUDIO_SUFFIXES = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".webm", ".aac", ".mp4"}

VARIANTS = {
    "full": {"separate": True, "denoise": True},
    "no_denoise": {"separate": True, "denoise": False},
    "no_separation": {"separate": False, "denoise": True},
    "fast": {"separate": False, "denoise": False},
}


@dataclass
class Sample:
    key: str
    folder: str
    canonical: str
    path: Path


def collect_samples(root: Path) -> list[Sample]:
    samples: list[Sample] = []
    for folder in sorted(child for child in root.iterdir() if child.is_dir()):
        audio_files = sorted(
            path for path in folder.iterdir()
            if path.is_file() and path.suffix.lower() in AUDIO_SUFFIXES
        )
        for path in audio_files:
            samples.append(
                Sample(
                    key=f"{folder.name}/{path.name}",
                    folder=folder.name,
                    canonical=folder.name,
                    path=path,
                )
            )
    return samples


def group_samples(samples: list[Sample]) -> dict[str, list[Sample]]:
    grouped: dict[str, list[Sample]] = defaultdict(list)
    for sample in samples:
        grouped[sample.canonical].append(sample)
    return grouped


def mean(values: list[float]) -> float:
    return round(float(sum(values) / len(values)), 4) if values else 0.0


def process_with_timings(
    raw_path: Path,
    *,
    separate: bool,
    denoise: bool,
    vad: VoiceActivityDetector,
    separator: VocalSeparator,
    denoiser: Denoiser,
) -> tuple[PreprocessResult, dict[str, float]]:
    timings: dict[str, float] = {}
    cleanup_files: list[str] = []
    cleanup_dirs: list[str] = []
    try:
        t0 = time.perf_counter()
        wav_path = normalize_audio(
            str(raw_path),
            max_duration_seconds=settings.preprocess_normalize_max_seconds,
        )
        timings["normalize"] = time.perf_counter() - t0
        cleanup_files.append(wav_path)

        if separate:
            t0 = time.perf_counter()
            vocals_path, sep_dir = separator.separate(wav_path)
            timings["separate"] = time.perf_counter() - t0
            cleanup_dirs.append(sep_dir)

            if vocals_path != wav_path:
                t0 = time.perf_counter()
                wav_path = normalize_audio(
                    vocals_path,
                    max_duration_seconds=settings.preprocess_normalize_max_seconds,
                )
                timings["renormalize_after_separation"] = time.perf_counter() - t0
                cleanup_files.append(wav_path)

        if denoise:
            t0 = time.perf_counter()
            import scipy.io.wavfile as _wavfile

            rate, data = _wavfile.read(wav_path)
            if data.ndim > 1:
                data = data[:, 0]
            float_data = data.astype(np.float32) / 32768.0
            clean = denoiser.reduce(float_data, sample_rate=rate)
            int16 = (np.clip(clean, -1.0, 1.0) * 32767).astype(np.int16)
            _wavfile.write(wav_path, rate, int16)
            timings["denoise"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        speech = vad.extract_speech(
            wav_path,
            min_speech_seconds=settings.preprocess_min_speech_seconds,
            max_speech_seconds=settings.preprocess_max_speech_seconds,
            fallback_to_raw=not separate,
        )
        timings["vad"] = time.perf_counter() - t0

        if speech is None:
            raise PreprocessError(
                "No usable speech detected in the audio. "
                "The file may be pure music, silence, or too noisy."
            )

        total_speech_seconds = len(speech) / SAMPLE_RATE
        min_samples = int(settings.preprocess_min_speech_seconds * SAMPLE_RATE)
        seg_samples = int(settings.preprocess_segment_length_seconds * SAMPLE_RATE)
        step_samples = int(settings.preprocess_segment_step_seconds * SAMPLE_RATE)

        t0 = time.perf_counter()
        if len(speech) < min_samples and settings.preprocess_short_repeat:
            speech = repeat_pad(speech, min_samples)

        if len(speech) <= seg_samples:
            segments = [speech]
        else:
            segments = segment_waveform(speech, seg_samples, step_samples)
        timings["segment"] = time.perf_counter() - t0
        timings["preprocess_total"] = round(sum(timings.values()), 4)

        return PreprocessResult(segments=segments, total_speech_seconds=total_speech_seconds), timings
    finally:
        for path in cleanup_files:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
        for path in cleanup_dirs:
            rmtree(path, ignore_errors=True)


def build_registries(selected_model_ids: set[str] | None = None) -> tuple[EmbedderRegistry, CalibratorRegistry]:
    registry = EmbedderRegistry()
    calibrators = CalibratorRegistry()
    for cfg in settings.get_enabled_models():
        if selected_model_ids is not None and cfg.id not in selected_model_ids:
            continue
        registry.register(cfg)
        calibrators.register(cfg)

    for model_id in registry.available_ids:
        registry.preload(model_id)
    return registry, calibrators


def evaluate_verify(
    samples: list[Sample],
    embeddings: dict[str, dict[str, dict[str, np.ndarray | None]]],
    registry: EmbedderRegistry,
    variants: list[str],
) -> dict[str, dict]:
    results: dict[str, dict] = {}
    pairs: list[tuple[Sample, Sample, bool]] = []
    for idx, sample_a in enumerate(samples):
        for sample_b in samples[idx + 1:]:
            pairs.append((sample_a, sample_b, sample_a.canonical == sample_b.canonical))

    for model_id in registry.available_ids:
        embedder = registry.get(model_id)
        threshold = (settings.get_model(model_id) or settings).verify_threshold
        model_results: dict[str, dict] = {}
        for variant in variants:
            tp = fp = tn = fn = skipped = 0
            mistakes: list[dict] = []
            scores: list[dict] = []
            variant_embeddings = embeddings.get(variant, {})
            for sample_a, sample_b, expected_same in pairs:
                emb_a = variant_embeddings.get(sample_a.key, {}).get(model_id)
                emb_b = variant_embeddings.get(sample_b.key, {}).get(model_id)
                if emb_a is None or emb_b is None:
                    skipped += 1
                    continue
                score = float(embedder.similarity(emb_a, emb_b))
                predicted_same = score >= threshold
                scores.append(
                    {
                        "a": sample_a.key,
                        "b": sample_b.key,
                        "expected_same": expected_same,
                        "score": round(score, 4),
                    }
                )
                if predicted_same and expected_same:
                    tp += 1
                elif predicted_same and not expected_same:
                    fp += 1
                    mistakes.append({"type": "fp", "a": sample_a.key, "b": sample_b.key, "score": round(score, 4)})
                elif (not predicted_same) and expected_same:
                    fn += 1
                    mistakes.append({"type": "fn", "a": sample_a.key, "b": sample_b.key, "score": round(score, 4)})
                else:
                    tn += 1

            total = tp + fp + tn + fn
            model_results[variant] = {
                "threshold": threshold,
                "accuracy": round((tp + tn) / total, 4) if total else 0.0,
                "precision": round(tp / (tp + fp), 4) if (tp + fp) else 0.0,
                "recall": round(tp / (tp + fn), 4) if (tp + fn) else 0.0,
                "tp": tp,
                "fp": fp,
                "tn": tn,
                "fn": fn,
                "skipped": skipped,
                "mistakes": mistakes[:12],
                "scores": scores,
            }
        results[model_id] = model_results
    return results


def evaluate_search(
    samples: list[Sample],
    embeddings: dict[str, dict[str, dict[str, np.ndarray | None]]],
    registry: EmbedderRegistry,
    *,
    variants: list[str],
    strategy: str,
    hybrid_best_weight: float,
    hybrid_centroid_weight: float,
) -> dict[str, dict]:
    results: dict[str, dict] = {}
    grouped = group_samples(samples)

    for model_id in registry.available_ids:
        embedder = registry.get(model_id)
        model_results: dict[str, dict] = {}
        for variant in variants:
            correct = 0
            total = 0
            details: list[dict] = []
            variant_embeddings = embeddings.get(variant, {})
            for sample in samples:
                query_vec = variant_embeddings.get(sample.key, {}).get(model_id)
                if query_vec is None:
                    continue

                own_refs = [
                    variant_embeddings.get(candidate.key, {}).get(model_id)
                    for candidate in grouped[sample.canonical]
                    if candidate.key != sample.key
                ]
                own_refs = [vec for vec in own_refs if vec is not None]
                if not own_refs:
                    continue

                rankings: list[dict] = []
                for canonical, speaker_samples in grouped.items():
                    ref_vecs = [
                        variant_embeddings.get(candidate.key, {}).get(model_id)
                        for candidate in speaker_samples
                        if candidate.key != sample.key
                    ]
                    ref_vecs = [vec for vec in ref_vecs if vec is not None]
                    if not ref_vecs:
                        continue

                    best_score = max(float(embedder.similarity(query_vec, ref_vec)) for ref_vec in ref_vecs)
                    centroid_vec = np.mean(ref_vecs, axis=0)
                    centroid_score = float(embedder.similarity(query_vec, centroid_vec))

                    if strategy == "centroid":
                        score = centroid_score
                    elif strategy == "hybrid":
                        score = (hybrid_best_weight * best_score) + (hybrid_centroid_weight * centroid_score)
                    else:
                        score = best_score

                    rankings.append(
                        {
                            "canonical": canonical,
                            "score": round(score, 4),
                            "best_score": round(best_score, 4),
                            "centroid_score": round(centroid_score, 4),
                            "reference_count": len(ref_vecs),
                        }
                    )

                if len(rankings) < 2:
                    continue

                rankings.sort(key=lambda row: row["score"], reverse=True)
                total += 1
                if rankings[0]["canonical"] == sample.canonical:
                    correct += 1
                details.append(
                    {
                        "query": sample.key,
                        "expected": sample.canonical,
                        "predicted": rankings[0]["canonical"],
                        "top1_score": rankings[0]["score"],
                        "top1_gap": round(rankings[0]["score"] - rankings[1]["score"], 4),
                        "ranking": rankings,
                    }
                )

            model_results[variant] = {
                "accuracy": round(correct / total, 4) if total else 0.0,
                "correct": correct,
                "total": total,
                "details": details,
                "search_strategy": strategy,
            }
        results[model_id] = model_results
    return results


def recommend_verify_fast_margin(
    verify_results: dict[str, dict],
) -> dict[str, dict]:
    recommendations: dict[str, dict] = {}
    for model_id, model_results in verify_results.items():
        fast_result = model_results.get("fast")
        if not fast_result:
            recommendations[model_id] = {"margin": None, "coverage": 0.0, "accuracy": 0.0}
            continue
        threshold = fast_result["threshold"]
        fast_scores = fast_result["scores"]
        best: dict | None = None
        for margin_int in range(2, 31):
            margin = margin_int / 100
            selected = [
                row for row in fast_scores
                if row["score"] >= threshold + margin or row["score"] <= threshold - margin
            ]
            if not selected:
                continue

            correct = 0
            for row in selected:
                predicted_same = row["score"] >= threshold
                if predicted_same == row["expected_same"]:
                    correct += 1
            accuracy = correct / len(selected)
            candidate = {
                "margin": round(margin, 2),
                "coverage": round(len(selected) / len(fast_scores), 4),
                "accuracy": round(accuracy, 4),
            }
            if accuracy == 1.0:
                if best is None or candidate["coverage"] > best["coverage"]:
                    best = candidate
        recommendations[model_id] = best or {"margin": None, "coverage": 0.0, "accuracy": 0.0}
    return recommendations


def suggest_verify_thresholds(verify_results: dict[str, dict]) -> dict[str, dict]:
    suggestions: dict[str, dict] = {}
    for model_id, model_results in verify_results.items():
        per_variant: dict[str, dict] = {}
        for variant, result in model_results.items():
            rows = result.get("scores", [])
            best: dict | None = None
            for threshold_int in range(20, 96):
                threshold = threshold_int / 100
                correct = 0
                tp = fp = fn = 0
                for row in rows:
                    predicted_same = row["score"] >= threshold
                    expected_same = row["expected_same"]
                    if predicted_same == expected_same:
                        correct += 1
                    if predicted_same and expected_same:
                        tp += 1
                    elif predicted_same and not expected_same:
                        fp += 1
                    elif (not predicted_same) and expected_same:
                        fn += 1
                total = len(rows)
                accuracy = correct / total if total else 0.0
                f1 = (2 * tp) / ((2 * tp) + fp + fn) if ((2 * tp) + fp + fn) else 0.0
                candidate = {
                    "threshold": round(threshold, 2),
                    "accuracy": round(accuracy, 4),
                    "f1": round(f1, 4),
                }
                if best is None or (candidate["accuracy"], candidate["f1"]) > (best["accuracy"], best["f1"]):
                    best = candidate
            per_variant[variant] = best or {"threshold": None, "accuracy": 0.0, "f1": 0.0}
        suggestions[model_id] = per_variant
    return suggestions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark voiceprint dataset variants.")
    default_model_ids = ",".join(cfg.id for cfg in settings.get_enabled_models())
    parser.add_argument(
        "dataset_root",
        nargs="?",
        default="/tmp/test",
        help="Directory containing benchmark dataset folders.",
    )
    parser.add_argument(
        "--output",
        dest="output_path",
        help="Optional path to write the JSON report.",
    )
    parser.add_argument(
        "--variants",
        default=",".join(VARIANTS.keys()),
        help="Comma-separated variant ids to run, e.g. full,no_denoise.",
    )
    parser.add_argument(
        "--model-ids",
        default=default_model_ids,
        help="Comma-separated embedder model ids to run, e.g. ecapa_tdnn,resemblyzer.",
    )
    parser.add_argument(
        "--separator-profile",
        default=settings.separator_profile,
        help="Separator profile id to benchmark (demucs | mdx | roformer).",
    )
    parser.add_argument(
        "--separator-model",
        default="",
        help="Optional explicit model override for the chosen separator profile.",
    )
    parser.add_argument(
        "--search-strategy",
        default=settings.search_strategy,
        choices=["best", "centroid", "hybrid"],
        help="Speaker aggregation strategy used for 1:N search evaluation.",
    )
    parser.add_argument(
        "--hybrid-best-weight",
        type=float,
        default=settings.search_hybrid_best_weight,
        help="Weight of per-speaker best similarity in hybrid search mode.",
    )
    parser.add_argument(
        "--hybrid-centroid-weight",
        type=float,
        default=settings.search_hybrid_centroid_weight,
        help="Weight of per-speaker centroid similarity in hybrid search mode.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset_root = Path(args.dataset_root)
    samples = collect_samples(dataset_root)
    if not samples:
        raise SystemExit(f"No supported audio files found under {dataset_root}")

    grouped = group_samples(samples)
    if len(grouped) < 2:
        raise SystemExit("Need at least two speaker folders to benchmark")

    selected_variants = [variant.strip() for variant in args.variants.split(",") if variant.strip()]
    if not selected_variants:
        raise SystemExit("At least one variant must be selected")
    unknown_variants = [variant for variant in selected_variants if variant not in VARIANTS]
    if unknown_variants:
        raise SystemExit(f"Unknown variants: {', '.join(unknown_variants)}")

    available_model_ids = {cfg.id for cfg in settings.get_enabled_models()}
    selected_model_ids = [model_id.strip() for model_id in args.model_ids.split(",") if model_id.strip()]
    if not selected_model_ids:
        raise SystemExit("At least one model id must be selected")
    unknown_model_ids = [model_id for model_id in selected_model_ids if model_id not in available_model_ids]
    if unknown_model_ids:
        raise SystemExit(f"Unknown model ids: {', '.join(unknown_model_ids)}")

    best_weight = max(float(args.hybrid_best_weight), 0.0)
    centroid_weight = max(float(args.hybrid_centroid_weight), 0.0)
    if best_weight + centroid_weight <= 0:
        best_weight = 0.7
        centroid_weight = 0.3
    else:
        total_weight = best_weight + centroid_weight
        best_weight /= total_weight
        centroid_weight /= total_weight

    registry, _ = build_registries(set(selected_model_ids))
    vad = VoiceActivityDetector()
    separator_profile = settings.get_separator_profile(args.separator_profile, args.separator_model)
    separator = VocalSeparator(cfg=settings, profile=separator_profile)
    denoiser = Denoiser()

    timings_by_variant: dict[str, dict[str, dict[str, float]]] = defaultdict(dict)
    embeddings: dict[str, dict[str, dict[str, np.ndarray | None]]] = defaultdict(dict)
    embedding_times: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    failures: dict[str, list[dict]] = defaultdict(list)

    active_variants = {variant: VARIANTS[variant] for variant in selected_variants}

    for variant, options in active_variants.items():
        print(
            f"[benchmark] separator={separator_profile.id} variant={variant} search={args.search_strategy} ...",
            flush=True,
        )
        for index, sample in enumerate(samples, start=1):
            print(f"  [sample {index}/{len(samples)}] {sample.key}", flush=True)
            start = time.perf_counter()
            try:
                result, timings = process_with_timings(
                    sample.path,
                    separate=options["separate"],
                    denoise=options["denoise"],
                    vad=vad,
                    separator=separator,
                    denoiser=denoiser,
                )
            except Exception as exc:
                failures[variant].append({"sample": sample.key, "error": str(exc)})
                embeddings[variant][sample.key] = {model_id: None for model_id in registry.available_ids}
                continue

            timings["wall_total"] = round(time.perf_counter() - start, 4)
            timings_by_variant[variant][sample.key] = timings

            sample_embeddings: dict[str, np.ndarray | None] = {}
            for model_id in registry.available_ids:
                t0 = time.perf_counter()
                vec = embed_segments(registry.get(model_id), result.segments)
                embedding_times[variant][model_id].append(time.perf_counter() - t0)
                sample_embeddings[model_id] = vec
            embeddings[variant][sample.key] = sample_embeddings

    verify_results = evaluate_verify(samples, embeddings, registry, selected_variants)
    search_results = evaluate_search(
        samples,
        embeddings,
        registry,
        variants=selected_variants,
        strategy=args.search_strategy,
        hybrid_best_weight=best_weight,
        hybrid_centroid_weight=centroid_weight,
    )
    fast_margin = recommend_verify_fast_margin(verify_results)
    threshold_suggestions = suggest_verify_thresholds(verify_results)

    timing_summary: dict[str, dict] = {}
    for variant, sample_timings in timings_by_variant.items():
        all_step_names = sorted({step for steps in sample_timings.values() for step in steps.keys()})
        timing_summary[variant] = {
            "samples": len(sample_timings),
            "step_mean_seconds": {
                step: mean([steps.get(step, 0.0) for steps in sample_timings.values()])
                for step in all_step_names
            },
            "embedding_mean_seconds": {
                model_id: mean(times)
                for model_id, times in embedding_times[variant].items()
            },
        }

    timing_details = {
        variant: {
            sample_key: {step: round(value, 4) for step, value in steps.items()}
            for sample_key, steps in sample_timings.items()
        }
        for variant, sample_timings in timings_by_variant.items()
    }

    report = {
        "dataset_root": str(dataset_root),
        "speaker_count": len(grouped),
        "sample_count": len(samples),
        "selected_models": selected_model_ids,
        "separator_profile": separator_profile.model_dump(),
        "selected_variants": selected_variants,
        "search_strategy": args.search_strategy,
        "search_hybrid_weights": {
            "best": round(best_weight, 4),
            "centroid": round(centroid_weight, 4),
        },
        "samples": [
            {"key": sample.key, "folder": sample.folder, "canonical": sample.canonical}
            for sample in samples
        ],
        "variants": active_variants,
        "timings": timing_summary,
        "timing_details": timing_details,
        "failures": failures,
        "verify": verify_results,
        "verify_threshold_suggestions": threshold_suggestions,
        "search": search_results,
        "fast_margin": fast_margin,
    }

    report_json = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output_path:
        output_path = Path(args.output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report_json, encoding="utf-8")
        print(f"\n=== REPORT_SAVED ===\n{output_path}")
        return

    print("\n=== REPORT ===")
    print(report_json)


if __name__ == "__main__":
    main()