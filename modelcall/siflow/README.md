# SiFlow 任务提交模块

这个模块提供了 SiFlow 任务批量提交的功能，用于大规模数据蒸馏任务。

## 模块结构

```
modelcall/siflow/
├── __init__.py           # 模块入口
├── client.py             # SiFlow 客户端封装
├── task_generator.py     # 任务生成器
├── batch_submitter.py    # 批量任务提交器
└── README.md            # 本文档
```

## 配置文件

```
configs/siflow/
├── task_template.yaml    # 任务 YAML 模板
└── default_config.yaml   # 默认配置
```

## 使用方法

### 1. 作为模块使用

```python
from modelcall.siflow import BatchSubmitter

# 创建批量提交器
submitter = BatchSubmitter(
    region="cn-beijing",
    cluster="auriga"
)

# 提交数据蒸馏任务
results = submitter.submit_distillation_tasks(
    split_dir="/path/to/split/files",
    output_base_dir="/path/to/output",
    model_config="/path/to/model/config.yaml",
    name_prefix="my-task",
    concurrency=30,
    batch_size=30,
    count_per_pod=10,
    resource_pool="eval-cpu",
    dry_run=False
)
```

### 2. 使用命令行脚本

```bash
# 提交任务
python scripts/submit_distillation_tasks.py \
    --split-dir /path/to/split/files \
    --output-dir /path/to/output \
    --model-config /path/to/model/config.yaml \
    --name-prefix my-task \
    --concurrency 30 \
    --batch-size 30 \
    --count-per-pod 10 \
    --resource-pool eval-cpu

# Dry run 模式（只生成命令不提交）
python scripts/submit_distillation_tasks.py \
    --split-dir /path/to/split/files \
    --output-dir /path/to/output \
    --model-config /path/to/model/config.yaml \
    --dry-run
```

## 核心类

### SiFlowClient

SiFlow 客户端封装类，负责与 SiFlow API 交互。

**方法：**
- `create_task(yaml_file)`: 创建任务

### TaskGenerator

任务生成器类，负责生成任务配置和命令。

**方法：**
- `create_task_yaml()`: 创建任务 YAML 配置
- `generate_distillation_cmds()`: 生成蒸馏任务命令列表

### BatchSubmitter

批量任务提交器类，整合客户端和生成器功能。

**方法：**
- `submit_single_task()`: 提交单个任务
- `batch_submit_tasks()`: 批量提交任务
- `submit_distillation_tasks()`: 提交数据蒸馏任务（高级接口）

## 配置说明

### 任务模板 (task_template.yaml)

定义了 SiFlow 任务的 YAML 结构，包括：
- 资源配置（CPU、内存）
- 镜像配置
- 容错配置
- 命令执行

### 默认配置 (default_config.yaml)

定义了默认的连接和资源参数：
- SiFlow 连接信息
- 资源池配置
- 并发和批量大小

## 注意事项

1. 确保 SiFlow 认证信息正确配置
2. 资源池名称需要与集群实际资源池匹配
3. 使用 dry-run 模式验证任务配置
4. 大批量任务建议分批提交

