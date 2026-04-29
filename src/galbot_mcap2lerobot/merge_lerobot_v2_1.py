"""Merge multiple LeRobot v2.1 datasets into a single dataset.

This module merges multiple LeRobot dataset folders that were produced by
parallel workers into one unified dataset. It handles:
- Merging episodes, statistics, and metadata
- Reindexing episode and frame indices
- Handling dimension mismatches with padding
- Copying video files and parquet data files

Usage:
    python -m galbot_mcap2lerobot.merge_lerobot_v2_1 \
        --source_folders ds_1 ds_2 ds_3 \
        --output_folder merged_dataset
"""

import argparse
import contextlib
import json
import os
import shutil
from typing import Any

import numpy as np
import pandas as pd
from termcolor import colored
from tqdm import tqdm

# ============================================================
# JSONL I/O
# ============================================================


def load_jsonl(file_path: str) -> list[dict[str, Any]]:
    """Load data from a JSONL file.

    Handles episodes_stats.jsonl which may be formatted as a JSON array.
    """
    data = []

    if "episodes_stats.jsonl" in file_path:
        try:
            with open(file_path) as f:
                content = f.read()
                if content.strip().startswith("[") and content.strip().endswith("]"):
                    return json.loads(content)
                else:
                    try:
                        return json.loads("[" + content + "]")
                    except json.JSONDecodeError:
                        pass
        except Exception as e:
            print(f"Error loading {file_path} as JSON array: {e}")

        try:
            with open(file_path) as f:
                for line in f:
                    if line.strip():
                        with contextlib.suppress(json.JSONDecodeError):
                            data.append(json.loads(line))
        except Exception as e:
            print(f"Error loading {file_path} line by line: {e}")
    else:
        with open(file_path) as f:
            for line in f:
                if line.strip():
                    with contextlib.suppress(json.JSONDecodeError):
                        data.append(json.loads(line))

    return data


def save_jsonl(data: list[dict[str, Any]], file_path: str) -> None:
    """Save data in JSONL format (one JSON object per line)."""
    with open(file_path, "w") as f:
        for item in data:
            f.write(json.dumps(item) + "\n")


# ============================================================
# Statistics Merging
# ============================================================


def merge_stats(stats_list: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge per-episode statistics from multiple datasets.

    Handles:
    - Weighted mean/std when count is available
    - Min/max aggregation
    - Dimension mismatches via padding
    - Nested image feature structures

    Args:
        stats_list: List of stats dicts, one per source dataset.

    Returns:
        Merged stats dict.
    """
    merged_stats: dict[str, Any] = {}

    common_features = set(stats_list[0].keys())
    for stats in stats_list[1:]:
        common_features &= set(stats.keys())

    for feature in stats_list[0]:
        if feature not in common_features:
            continue

        merged_stats[feature] = {}

        common_stat_types = [
            st
            for st in ["mean", "std", "max", "min"]
            if all(st in stats[feature] for stats in stats_list)
        ]

        original_shapes = []
        for stats in stats_list:
            if "mean" in stats[feature]:
                original_shapes.append(np.array(stats[feature]["mean"]).shape)

        # --- Image features: preserve nested [C, H, W] structure ---
        if feature.startswith("observation.images."):
            for stat_type in common_stat_types:
                try:
                    values = [stats[feature][stat_type] for stats in stats_list]
                    result = []
                    for ch in range(len(values[0])):
                        channel_result = []
                        for row in range(len(values[0][ch])):
                            pixel_result = []
                            for col in range(len(values[0][ch][row])):
                                if stat_type in ("mean", "std"):
                                    val = sum(v[ch][row][col] for v in values) / len(values)
                                elif stat_type == "max":
                                    val = max(v[ch][row][col] for v in values)
                                else:
                                    val = min(v[ch][row][col] for v in values)
                                pixel_result.append(val)
                            channel_result.append(pixel_result)
                        result.append(channel_result)
                    merged_stats[feature][stat_type] = result
                except Exception as e:
                    print(f"Warning: Error processing image {feature}.{stat_type}: {e}")
                    merged_stats[feature][stat_type] = values[0]

        # --- Same-shape features ---
        elif len({str(s) for s in original_shapes}) == 1:
            for stat_type in common_stat_types:
                values = [stats[feature][stat_type] for stats in stats_list]
                try:
                    if stat_type == "mean":
                        if all("count" in stats[feature] for stats in stats_list):
                            counts = [stats[feature]["count"][0] for stats in stats_list]
                            total = sum(counts)
                            weighted = [
                                np.array(v) * c / total
                                for v, c in zip(values, counts, strict=False)
                            ]
                            merged_stats[feature][stat_type] = np.sum(weighted, axis=0).tolist()
                        else:
                            merged_stats[feature][stat_type] = np.mean(values, axis=0).tolist()
                    elif stat_type == "std":
                        if all("count" in stats[feature] for stats in stats_list):
                            counts = [stats[feature]["count"][0] for stats in stats_list]
                            total = sum(counts)
                            variances = [np.array(s) ** 2 for s in values]
                            weighted = [
                                v * c / total for v, c in zip(variances, counts, strict=False)
                            ]
                            merged_stats[feature][stat_type] = np.sqrt(
                                np.sum(weighted, axis=0)
                            ).tolist()
                        else:
                            merged_stats[feature][stat_type] = np.mean(values, axis=0).tolist()
                    elif stat_type == "max":
                        merged_stats[feature][stat_type] = np.maximum.reduce(values).tolist()
                    elif stat_type == "min":
                        merged_stats[feature][stat_type] = np.minimum.reduce(values).tolist()
                except Exception as e:
                    print(f"Warning: Error processing {feature}.{stat_type}: {e}")

        # --- Different-shape state/action vectors: pad to max dim ---
        elif feature in ("observation.state", "action"):
            max_dim = max(len(np.array(stats[feature]["mean"]).flatten()) for stats in stats_list)
            for stat_type in common_stat_types:
                try:
                    pairs = [
                        (
                            np.array(stats[feature][stat_type]).flatten(),
                            len(np.array(stats[feature][stat_type]).flatten()),
                        )
                        for stats in stats_list
                    ]
                    result = np.zeros(max_dim)

                    if stat_type == "mean":
                        if all("count" in stats[feature] for stats in stats_list):
                            counts = [stats[feature]["count"][0] for stats in stats_list]
                            for d in range(max_dim):
                                vals = [
                                    (v[d], c)
                                    for (v, dim), c in zip(pairs, counts, strict=False)
                                    if d < dim
                                ]
                                if vals:
                                    result[d] = sum(v * w for v, w in vals) / sum(
                                        w for _, w in vals
                                    )
                        else:
                            for d in range(max_dim):
                                vals = [v[d] for v, dim in pairs if d < dim]
                                if vals:
                                    result[d] = sum(vals) / len(vals)
                    elif stat_type == "std":
                        if all("count" in stats[feature] for stats in stats_list):
                            counts = [stats[feature]["count"][0] for stats in stats_list]
                            for d in range(max_dim):
                                vals = [
                                    (v[d] ** 2, c)
                                    for (v, dim), c in zip(pairs, counts, strict=False)
                                    if d < dim
                                ]
                                if vals:
                                    result[d] = np.sqrt(
                                        sum(v * w for v, w in vals) / sum(w for _, w in vals)
                                    )
                        else:
                            for d in range(max_dim):
                                vals = [v[d] for v, dim in pairs if d < dim]
                                if vals:
                                    result[d] = sum(vals) / len(vals)
                    elif stat_type == "max":
                        for d in range(max_dim):
                            vals = [v[d] for v, dim in pairs if d < dim]
                            if vals:
                                result[d] = max(vals)
                    elif stat_type == "min":
                        for d in range(max_dim):
                            vals = [v[d] for v, dim in pairs if d < dim]
                            if vals:
                                result[d] = min(vals)

                    merged_stats[feature][stat_type] = result.tolist()
                except Exception as e:
                    print(f"Warning: Error processing {feature}.{stat_type}: {e}")
        else:
            for stat_type in common_stat_types:
                try:
                    merged_stats[feature][stat_type] = stats_list[0][feature][stat_type]
                except Exception as e:
                    print(f"Warning: Error processing {feature}.{stat_type}: {e}")

        if all("count" in stats[feature] for stats in stats_list):
            try:
                merged_stats[feature]["count"] = [
                    sum(stats[feature]["count"][0] for stats in stats_list)
                ]
            except Exception as e:
                print(f"Warning: Error processing {feature}.count: {e}")

    return merged_stats


# ============================================================
# Video Copying
# ============================================================


def copy_videos(
    source_folders: list[str], output_folder: str, episode_mapping: list[tuple]
) -> None:
    """Copy video files from source folders with correct episode reindexing.

    Args:
        source_folders: Source dataset folder paths.
        output_folder: Destination folder path.
        episode_mapping: List of (old_folder, old_index, new_index) tuples.
    """
    info_path = os.path.join(source_folders[0], "meta", "info.json")
    with open(info_path) as f:
        info = json.load(f)

    video_path_template = info["video_path"]
    video_keys = [name for name, feat in info["features"].items() if feat.get("dtype") == "video"]
    print(f"Found video keys: {video_keys}")

    for old_folder, old_index, new_index in episode_mapping:
        episode_chunk = old_index // info["chunks_size"]
        new_chunk = new_index // info["chunks_size"]

        for video_key in video_keys:
            source_patterns = [
                os.path.join(
                    old_folder,
                    video_path_template.format(
                        episode_chunk=episode_chunk,
                        video_key=video_key,
                        episode_index=old_index,
                    ),
                ),
                os.path.join(
                    old_folder,
                    video_path_template.format(
                        episode_chunk=0, video_key=video_key, episode_index=0
                    ),
                ),
                os.path.join(old_folder, f"videos/chunk-000/{video_key}/episode_000000.mp4"),
            ]

            source_path = None
            for pattern in source_patterns:
                if os.path.exists(pattern):
                    source_path = pattern
                    break

            if source_path:
                dest_path = os.path.join(
                    output_folder,
                    video_path_template.format(
                        episode_chunk=new_chunk,
                        video_key=video_key,
                        episode_index=new_index,
                    ),
                )
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                print(f"Copying video: {source_path} -> {dest_path}")
                shutil.copy2(source_path, dest_path)
            else:
                # Fallback: recursive search
                found = False
                videos_dir = os.path.join(old_folder, "videos")
                if os.path.isdir(videos_dir):
                    for root, _, files in os.walk(videos_dir):
                        for file in files:
                            if file.endswith(".mp4") and video_key in root:
                                source_path = os.path.join(root, file)
                                dest_path = os.path.join(
                                    output_folder,
                                    video_path_template.format(
                                        episode_chunk=new_chunk,
                                        video_key=video_key,
                                        episode_index=new_index,
                                    ),
                                )
                                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                                shutil.copy2(source_path, dest_path)
                                found = True
                                break
                        if found:
                            break
                if not found:
                    print(
                        f"Warning: Video not found for {video_key}, "
                        f"episode {old_index} in {old_folder}"
                    )


# ============================================================
# Main Merge Logic
# ============================================================


def merge_datasets(source_folders: list[str], output_folder: str) -> None:
    """Merge multiple LeRobot datasets into a single dataset.

    Args:
        source_folders: List of source dataset directory paths.
        output_folder: Path for the merged output dataset.
    """
    # Filter to existing folders
    valid_folders = [f for f in source_folders if os.path.exists(f)]
    if not valid_folders:
        print("No valid source folders found.")
        return

    print(f"Merging {len(valid_folders)} datasets into {output_folder}")

    os.makedirs(os.path.join(output_folder, "meta"), exist_ok=True)
    os.makedirs(os.path.join(output_folder, "data", "chunk-000"), exist_ok=True)

    # --- Load info.json from first dataset as template ---
    template_info_path = os.path.join(valid_folders[0], "meta", "info.json")
    with open(template_info_path) as f:
        info = json.load(f)

    # --- Merge episodes ---
    all_episodes = []
    all_episode_stats = []
    all_tasks = []
    episode_mapping = []  # (old_folder, old_index, new_index)
    current_episode = 0
    current_frame = 0

    for folder in tqdm(valid_folders, desc="Merging datasets"):
        episodes_path = os.path.join(folder, "meta", "episodes.jsonl")
        stats_path = os.path.join(folder, "meta", "episodes_stats.jsonl")
        tasks_path = os.path.join(folder, "meta", "tasks.jsonl")

        if not os.path.exists(episodes_path):
            print(f"Skipping {folder}: no episodes.jsonl")
            continue

        episodes = load_jsonl(episodes_path)
        ep_stats = load_jsonl(stats_path) if os.path.exists(stats_path) else []
        tasks = load_jsonl(tasks_path) if os.path.exists(tasks_path) else []

        for ep in episodes:
            old_index = ep.get("episode_index", 0)
            new_index = current_episode

            # Update episode metadata
            ep_length = ep.get("length", 0)
            new_ep = dict(ep)
            new_ep["episode_index"] = new_index
            all_episodes.append(new_ep)

            episode_mapping.append((folder, old_index, new_index))
            current_episode += 1
            current_frame += ep_length

        all_episode_stats.extend(ep_stats)

        for task in tasks:
            if task not in all_tasks:
                all_tasks.append(task)

    # --- Copy and reindex parquet files ---
    for old_folder, old_index, new_index in tqdm(episode_mapping, desc="Copying parquet"):
        old_chunk = old_index // info["chunks_size"]
        new_chunk = new_index // info["chunks_size"]

        data_path_template = info.get(
            "data_path",
            "data/chunk-{episode_chunk:03d}/episode_{episode_index:06d}.parquet",
        )

        source_patterns = [
            os.path.join(
                old_folder,
                data_path_template.format(episode_chunk=old_chunk, episode_index=old_index),
            ),
            os.path.join(old_folder, "data/chunk-000/episode_000000.parquet"),
        ]

        source_path = None
        for pattern in source_patterns:
            if os.path.exists(pattern):
                source_path = pattern
                break

        if source_path:
            dest_path = os.path.join(
                output_folder,
                data_path_template.format(episode_chunk=new_chunk, episode_index=new_index),
            )
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)

            df = pd.read_parquet(source_path)
            df["episode_index"] = new_index
            df.to_parquet(dest_path, index=False)

    # --- Copy videos ---
    copy_videos(valid_folders, output_folder, episode_mapping)

    # --- Save per-episode statistics ---
    if all_episode_stats:
        save_jsonl(
            all_episode_stats,
            os.path.join(output_folder, "meta", "episodes_stats.jsonl"),
        )

    # --- Save metadata ---
    save_jsonl(all_episodes, os.path.join(output_folder, "meta", "episodes.jsonl"))
    save_jsonl(all_tasks, os.path.join(output_folder, "meta", "tasks.jsonl"))

    # Update info.json
    info["total_episodes"] = current_episode
    info["total_frames"] = current_frame
    with open(os.path.join(output_folder, "meta", "info.json"), "w") as f:
        json.dump(info, f, indent=2)

    print(
        colored(
            f"Merge complete: {current_episode} episodes, {current_frame} frames",
            "green",
        )
    )


# ============================================================
# CLI Entry Point
# ============================================================


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge LeRobot v2.1 datasets")
    parser.add_argument(
        "--source_folders",
        nargs="+",
        required=True,
        help="Paths to source dataset folders",
    )
    parser.add_argument(
        "--output_folder", required=True, help="Path to output merged dataset folder"
    )
    args = parser.parse_args()
    merge_datasets(args.source_folders, args.output_folder)


if __name__ == "__main__":
    main()
