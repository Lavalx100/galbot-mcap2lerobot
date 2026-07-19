"""Configuration file for MCAP to LeRobot dataset conversion.

This module contains configuration constants for converting MCAP (Message Capture)
files to LeRobot dataset format. It includes settings for input/output directories,
export options, ROS topic names, and processing parameters.

Adapt these settings to match your robot's ROS topics, joint structure, and
desired output configuration.
"""

from typing import Any

# ---------------------------------------------------------------------------
# Input / Output directory configuration
# NOTE: These are overridden by command line arguments
# ---------------------------------------------------------------------------
MCAP_DIR: str = ""  # Directory containing source .mcap files
OUTPUT_DIR: str = ""  # Root directory for converted datasets

# ---------------------------------------------------------------------------
# Export and parsing configuration
# ---------------------------------------------------------------------------
EXPORT_CONFIG: dict[str, Any] = {
    # default=True; enable/disable conversion.
    "enable": True,
    # default="galbot/galbot_lerobot_dataset"; HuggingFace repo_id or local dataset name.
    "repo_id": "galbot/galbot_lerobot_dataset",
    # default=30; video frame rate (must match your camera FPS).
    "fps": 30,
    # default="G1_V2.2B"; robot_type in LeRobot metadata.
    "robot_type": "G1_V2.2B",
    # default=True; store image observations as videos.
    "use_videos": True,
    # default="av1"; video codec (e.g. av1/h264/hevc).
    "video_codec": "av1",
    # default="yuv420p"; video pixel format.
    "video_pix_fmt": "yuv420p",
    # default=False; dump decoded messages to JSON for debugging.
    "save_parsed_info": False,
    # default=False; enable undistortion (requires calibration data).
    "enable_undistort": False,
    # default="/front_head_camera/left_color/image_raw"; primary timeline camera.
    "primary_camera_topic": "/front_head_camera/left_color/image_raw",
    # Task description annotated in every frame.
    "task": "Default placeholder. Please replce this with the actual task instructions.",
}

# ---------------------------------------------------------------------------
# ROS Topic Configuration — Galbot G1
# ---------------------------------------------------------------------------
# Image topics: ROS topics that publish sensor_msgs/Image or compressed images.
# The converter extracts raw image bytes and timestamps from these topics.
IMAGE_TOPICS: list[str] = [
    "/left_arm_camera/color/image_raw",
    "/front_head_camera/left_color/image_raw",
    "/front_head_camera/right_color/image_raw",
    "/right_arm_camera/color/image_raw",
]

# Camera info topics: Must correspond 1:1 to IMAGE_TOPICS (replace image_raw → camera_info).
# Used to read camera resolution (width, height) and optional distortion coefficients.
IMAGE_INFO_TOPICS: list[str] = [
    "/left_arm_camera/color/camera_info",
    "/front_head_camera/left_color/camera_info",
    "/front_head_camera/right_color/camera_info",
    "/right_arm_camera/color/camera_info",
]

# State topics: ROS topics carrying robot joint positions/velocities.
#
# For Galbot G1 (fixed value): custom protobuf message with `joint_sensor_map` field
# For standard ROS robots (sensor_msgs/JointState): use "/joint_states"
STATE_TOPICS: list[str] = [
    "singorix/wbcs/sensor",
]

# ---------------------------------------------------------------------------
# Processing Configuration
# ---------------------------------------------------------------------------
# Number of parallel worker processes for batch conversion.
# Each worker processes a subset of MCAP files independently, then results are merged.
# Set to 1 for debugging. For production, use min(NUM_WORKERS, num_mcap_files).
NUM_WORKERS: int = 10

# Max allowed timestamp gap (in units of 1/fps frame periods) when matching a
# non-primary camera frame to the primary camera's timestamp via nearest
# neighbor. If the closest available frame is farther than this many frame
# periods away (e.g. that camera dropped out mid-episode), conversion aborts
# for that episode instead of silently reusing a stale frame.
MAX_CAMERA_SYNC_GAP_FRAMES: float = 3
