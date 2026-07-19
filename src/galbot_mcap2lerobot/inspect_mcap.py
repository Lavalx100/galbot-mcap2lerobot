"""Inspect a raw .mcap file without running the full conversion pipeline.

Usage:
  inspect-mcap <file.mcap>                 # list topics/schemas/message counts
  inspect-mcap <file.mcap> --topic TOPIC    # decode and print sample messages
  inspect-mcap <file.mcap> --topic TOPIC --limit 5
  inspect-mcap <file.mcap> --metadata       # list embedded metadata records
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mcap.reader import make_reader

from .galbot_mcap_to_lerobot import decode_protobuf


def print_summary(mcap_path: str) -> None:
    with open(mcap_path, "rb") as f:
        reader = make_reader(f)
        summary = reader.get_summary()
        if summary is None:
            print("No summary index in this file (unindexed .mcap).")
            return

        stats = summary.statistics
        duration_s = (stats.message_end_time - stats.message_start_time) / 1e9
        print(f"file:     {mcap_path}")
        print(f"messages: {stats.message_count}")
        print(f"duration: {duration_s:.2f}s")
        print()
        print(f"{'topic':<45} {'count':>7}  {'schema'}")
        print("-" * 100)
        rows = []
        for channel_id, count in summary.statistics.channel_message_counts.items():
            channel = summary.channels[channel_id]
            schema = summary.schemas.get(channel.schema_id)
            rows.append((channel.topic, count, schema.name if schema else "?"))
        for topic, count, schema_name in sorted(rows):
            print(f"{topic:<45} {count:>7}  {schema_name}")

        if summary.metadata_indexes:
            print()
            print(f"metadata records: {len(summary.metadata_indexes)} (use --metadata to view)")


def print_metadata(mcap_path: str) -> None:
    with open(mcap_path, "rb") as f:
        reader = make_reader(f)
        found = False
        for metadata in reader.iter_metadata():
            found = True
            print(f"[{metadata.name}]")
            print(json.dumps(metadata.metadata, indent=2, ensure_ascii=False))
            print()
        if not found:
            print("No metadata records in this file.")


def print_topic_samples(mcap_path: str, topic: str, limit: int) -> None:
    with open(mcap_path, "rb") as f:
        reader = make_reader(f)
        summary = reader.get_summary()
        if summary is None or not any(c.topic == topic for c in summary.channels.values()):
            print(f"Topic {topic!r} not found in this file.")
            return

        shown = 0
        for schema, _channel, message in reader.iter_messages(topics=[topic]):
            decoded = decode_protobuf(schema, message.data)
            if decoded is None:
                print(f"[{message.log_time}] <could not decode schema {schema.name}>")
            else:
                print(f"[{message.log_time}] {schema.name}")
                print(json.dumps(decoded, indent=2, ensure_ascii=False, default=str))
            print()
            shown += 1
            if shown >= limit:
                break

        if shown == 0:
            print(f"No messages found on topic {topic!r}.")


def cli_main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect a raw .mcap file: list topics/schemas, or decode sample messages.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("mcap_file", type=str, help="Path to a .mcap file")
    parser.add_argument("--topic", type=str, default=None, help="Decode and print sample messages from this topic")
    parser.add_argument("--limit", type=int, default=3, help="Number of sample messages to print (default: 3)")
    parser.add_argument("--metadata", action="store_true", help="List embedded metadata records instead of topics")
    args = parser.parse_args()

    mcap_path = Path(args.mcap_file)
    if not mcap_path.is_file():
        parser.error(f"File not found: {mcap_path}")

    if args.metadata:
        print_metadata(str(mcap_path))
    elif args.topic:
        print_topic_samples(str(mcap_path), args.topic, args.limit)
    else:
        print_summary(str(mcap_path))


if __name__ == "__main__":
    cli_main()
