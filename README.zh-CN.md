# mcap2lerobot：Galbot MCAP 到 LeRobot 数据集转换器

[English](./README.md) | **中文**

将 Galbot G1 人形机器人的 ROS MCAP 录制数据转换为可用于模仿学习的 [LeRobot v2.1](https://github.com/huggingface/lerobot) 数据集。

## 版本范围说明（重要）

本项目输出的是 **LeRobotDataset v2.1 格式**。

本文讨论的是 **LeRobotDataset 数据格式版本**，不是 `lerobot` 软件发布版本。两者需要严格区分：

| 类别 | 示例版本 | 含义 |
|------|----------|------|
| LeRobot 软件版本 | `v0.4.0`、`v0.5.0` | Hugging Face `lerobot` 代码库的发布版本 |
| LeRobotDataset 格式版本 | `v2.1`、`v3.0` | 数据集目录结构、元数据组织方式与读取方式的版本 |

截至官方 `lerobot v0.5.0` 发布，数据格式主线为 **LeRobotDataset v3.0**。

如果需要 **LeRobotDataset v3.0** 格式，可以使用 `lerobot v0.4.0+` 提供的转换脚本：

```bash
python -m lerobot.datasets.v30.convert_dataset_v21_to_v30 --repo-id=<HF_USER/DATASET_ID>
```

### 数据版本与 Tag 对应

数据集中 `meta/info.json` 的 `codebase_version` 需与训练所用 LeRobot 代码 tag 一致：

| 数据集版本 | 推荐 LeRobot 代码版本 | 说明 |
|------------|------------------------|------|
| `v2.1` | `v0.3.x` | 旧版 dataset 结构，很多旧流程仍沿用 |
| `v3.0` | `v0.4+`  | 新版 dataset 结构 |

## 功能概览

```
┌─────────────┐      ┌──────────────────┐     ┌─────────────────────┐
│  MCAP Files │────▶ │  mcap2lerobot    │────▶│  LeRobot Dataset    │
│  (ROS msgs) │      │  (this tool)     │     │  (parquet + video)  │
└─────────────┘      └──────────────────┘     └─────────────────────┘
```

**输入**：包含 ROS protobuf 消息的 MCAP 文件（4 路相机 + 关节状态）

**输出**：LeRobot v2.1 数据集，包含：
- `data/`：Parquet 文件（关节状态 + 动作，23 维向量）
- `videos/`：AV1 编码视频流（4 路相机，30 FPS）
- `meta/`：数据集元信息（`info.json`、`modality.json`、`episodes.jsonl` 等）

## Galbot G1 数据规格

### 关节结构（23 维）

| 索引范围 | 关节分组       | 数量 | 说明                      |
|----------|----------------|------|-----------------------|
| 0–4      | leg            | 5    | 腿部关节                |
| 5–6      | head           | 2    | 头部云台（pan/tilt）    |
| 7–13     | left_arm       | 7    | 左臂关节                |
| 14       | left_gripper   | 1    | 原始值 / 1000，单位为米   |
| 15–21    | right_arm      | 7    | 右臂关节                |
| 22       | right_gripper  | 1    | 原始值 / 1000，单位为米   |

### 相机流（4 路）

| ROS Topic                                      | 数据集字段 Key                                        | 分辨率   |
|------------------------------------------------|-----------------------------------------------------|----------|
| `/left_arm_camera/color/image_raw`             | `observation.images.left_arm_camera_color`          | 480×640  |
| `/front_head_camera/left_color/image_raw`      | `observation.images.front_head_camera_left_color`   | 480×640  |
| `/front_head_camera/right_color/image_raw`     | `observation.images.front_head_camera_right_color`  | 480×640  |
| `/right_arm_camera/color/image_raw`            | `observation.images.right_arm_camera_color`         | 480×640  |

### 状态 Topic

| ROS Topic             | 内容                          |
|-----------------------|------------------------------|
| `singorix/wbcs/sensor`| 关节位置（可含速度/力矩）        |

## 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/GalaxyGeneralRobotics/galbot-mcap2lerobot.git
cd galbot-mcap2lerobot

# 安装包
pip install .
```

## 使用方法

```bash
galbot-mcap2lerobot <mcap_directory> <output_directory>
```

**示例:**
```bash
galbot-mcap2lerobot ./mcap ./output
```

**注意**：运行前请编辑 `src/galbot_mcap2lerobot/config.py` 来配置你的机器人 ROS Topic、任务描述和其他设置。详见下方[配置参考](#配置参考)。

## 输出目录结构

```
output_galbot/galbot_lerobot_dataset/
├── meta/
│   ├── info.json                  # 数据集元信息（features、fps、robot_type）
│   ├── modality.json              # state/action 的关节索引映射
│   ├── episodes.jsonl             # 每个 episode 的元信息
│   ├── tasks.jsonl                # 任务描述
│   └── episodes_stats.jsonl       # 每个 episode 的统计值（min/max/mean/std）
├── data/
│   └── chunk-000/
│       ├── episode_000000.parquet # 关节状态 + 动作
│       ├── episode_000001.parquet
│       └── ...
└── videos/
    └── chunk-000/
        ├── observation.images.left_arm_camera_color/
        │   ├── episode_000000.mp4
        │   └── ...
        ├── observation.images.front_head_camera_left_color/
        │   └── ...
        ├── observation.images.front_head_camera_right_color/
        │   └── ...
        └── observation.images.right_arm_camera_color/
            └── ...
```

### Parquet 字段说明

每个 `episode_XXXXXX.parquet` 包含：

| 字段名              | 类型          | 说明                                |
|---------------------|---------------|-------------------------------------|
| `timestamp`         | float32       | 相对 episode 起始时间（秒）         |
| `frame_index`       | int64         | episode 内帧序号                    |
| `index`             | int64         | 全数据集全局帧序号                  |
| `episode_index`     | int64         | episode 编号                        |
| `task_index`        | int64         | 任务描述索引                        |
| `observation.state` | list[float32] | 23 维关节位置                       |
| `action`            | list[float32] | 23 维动作（等于下一帧状态）         |

## 转换流程

### 第 1 步：解析 MCAP

`McapParser` 会读取每个 `.mcap` 文件并提取：
- `image_buffers`：`{topic: [(timestamp, decoded_msg), ...]}`，4 路相机
- `state_buffers`：`{topic: [(timestamp, decoded_msg), ...]}`，关节状态
- `camera_info_buffers`：`{topic: camera_info_dict}`，相机标定信息

Protobuf 消息会使用 MCAP 内嵌的 schema descriptor 动态解码。

### 第 2 步：时间戳对齐

以**头部左相机**作为时间基准（主时钟）：

1. 对每个头部左相机帧时间戳 `t`：
   - **关节状态**：用 `scipy.interpolate.interp1d` 线性插值到 `t`
   - **其他相机**：按时间戳选择最近帧

### 第 3 步：状态扁平化

关节传感器原始数据是嵌套 protobuf 结构：

```python
# 解码后的 protobuf 结构示例
joint_sensor_map = {
    "leg":            {"position": [5 floats], "velocity": [...], "effort": [...]},
    "right_arm":      {"position": [7 floats], ...},
    "right_gripper":  {"position": [1 float],  ...},
    "left_arm":       {"position": [7 floats], ...},
    "left_gripper":   {"position": [1 float],  ...},
    "head":           {"position": [2 floats], ...},
}
```

最终会按顺序扁平为 23 维向量：`leg -> head -> left_arm -> left_gripper -> right_arm -> right_gripper`

夹爪值会除以 1000，并以米制宽度写入数据集。

### 第 4 步：动作定义

```
action[t] = observation.state[t+1]   (下一帧状态)
action[last] = observation.state[last]  (最后一帧重复自身)
```

### 第 5 步：多进程转换与合并

- 将 MCAP 文件分配到 `NUM_WORKERS` 个进程
- 每个进程独立生成子数据集
- 最后合并子数据集，并重排 episode 索引

## 配置说明

### `src/galbot_mcap2lerobot/config.py`

```python
# 输入/输出路径
MCAP_DIR = "./mcap"          # .mcap 文件目录
OUTPUT_DIR = "./output"      # 输出根目录

# 导出配置
EXPORT_CONFIG = {
    "enable": True,
    "repo_id": "galbot/galbot_lerobot_dataset",  # 数据集名称
    "fps": 30,                                    # 视频帧率
    "robot_type": "G1_V2.2B",                     # LeRobot 元信息中的 robot_type
    "use_videos": True,                           # 是否将图像观测保存为视频
    "video_codec": "av1",                         # 视频编码器（如 av1/h264/hevc）
    "video_pix_fmt": "yuv420p",                   # 视频像素格式
    "save_parsed_info": False,                    # 是否导出调试 JSON
    "enable_undistort": False,                    # 是否启用去畸变
    "primary_camera_topic": "/front_head_camera/left_color/image_raw",  # 时间轴参考相机
    "task": "your task description here",         # 任务标注
}

# ROS topics
IMAGE_TOPICS = [
    "/left_arm_camera/color/image_raw",
    "/front_head_camera/left_color/image_raw",
    "/front_head_camera/right_color/image_raw",
    "/right_arm_camera/color/image_raw",
]

IMAGE_INFO_TOPICS = [
    "/left_arm_camera/color/camera_info",
    "/front_head_camera/left_color/camera_info",
    "/front_head_camera/right_color/camera_info",
    "/right_arm_camera/color/camera_info",
]

# Galbot G1（固定值）：使用自定义 protobuf 消息，包含 joint_sensor_map 字段
STATE_TOPICS = [
    "singorix/wbcs/sensor",
]

NUM_WORKERS = 10  # 并行进程数
```

## 依赖

```
numpy>=1.21.0
opencv-python>=4.5.0
scipy>=1.7.0
mcap>=0.0.1
protobuf>=3.20.0
lerobot==0.3.3
ffmpeg-python>=0.2.0
tqdm>=4.62.0
pandas>=1.3.0
termcolor>=2.0.0
```

AV1 编码需要系统安装 `ffmpeg`：

```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# macOS
brew install ffmpeg
```

## 实用工具

### 数据集合并

将多个 LeRobot 数据集合并为一个，默认会合并：

```bash
merge-lerobot-v2-1 \
    --source_folders dataset_a dataset_b dataset_c \
    --output_folder merged_dataset
```

## 许可证

请查看仓库根目录中的许可证文件。
