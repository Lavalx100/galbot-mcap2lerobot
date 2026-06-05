"""Galbot G1 joint vector layout used by generated LeRobot datasets.

The 23-D ``observation.state`` and ``action`` vectors are stored in this order:

    0   leg_joint1
    1   leg_joint2
    2   leg_joint3
    3   leg_joint4
    4   leg_joint5
    5   head_joint1
    6   head_joint2
    7   left_arm_joint1
    8   left_arm_joint2
    9   left_arm_joint3
    10  left_arm_joint4
    11  left_arm_joint5
    12  left_arm_joint6
    13  left_arm_joint7
    14  left_gripper_joint1
    15  right_arm_joint1
    16  right_arm_joint2
    17  right_arm_joint3
    18  right_arm_joint4
    19  right_arm_joint5
    20  right_arm_joint6
    21  right_arm_joint7
    22  right_gripper_joint1

Gripper values from MCAP are divided by 1000 before being written to LeRobot,
so gripper entries in the dataset are meter-scale widths.
"""

from __future__ import annotations

JOINT_GROUP_ORDER = [
    "leg",
    "head",
    "left_arm",
    "left_gripper",
    "right_arm",
    "right_gripper",
]

GRIPPER_GROUPS = {"right_gripper", "left_gripper"}
GRIPPER_VALUE_SCALE = 1.0 / 1000.0

JOINT_STRUCTURE = {
    "leg": {"start": 0, "end": 5},
    "head": {"start": 5, "end": 7},
    "left_arm": {"start": 7, "end": 14},
    "left_gripper": {"start": 14, "end": 15},
    "right_arm": {"start": 15, "end": 22},
    "right_gripper": {"start": 22, "end": 23},
}

JOINT_NAMES = [
    "leg_joint1",
    "leg_joint2",
    "leg_joint3",
    "leg_joint4",
    "leg_joint5",
    "head_joint1",
    "head_joint2",
    "left_arm_joint1",
    "left_arm_joint2",
    "left_arm_joint3",
    "left_arm_joint4",
    "left_arm_joint5",
    "left_arm_joint6",
    "left_arm_joint7",
    "left_gripper_joint1",
    "right_arm_joint1",
    "right_arm_joint2",
    "right_arm_joint3",
    "right_arm_joint4",
    "right_arm_joint5",
    "right_arm_joint6",
    "right_arm_joint7",
    "right_gripper_joint1",
]
