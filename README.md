# ModelCall Data Processing Pipeline

一个可扩展的数据处理框架：读取数据 -> 打分 -> 写入数据。支持多种文件系统(本地/TOS)和格式(JSONL/Parquet)。

## 功能特性

- **多文件系统**: 支持本地文件系统和TOS对象存储
- **多格式支持**: JSONL、Parquet自动识别和处理
- **二级并发模型**: 文件级 + 请求级双重并发控制
- **批量处理**: 多进程并行处理大规模数据  
- **进度跟踪**: 自动保存处理进度，支持断点续传
- **智能重试**: 网络错误 + JSON格式验证失败双重重试机制
- **统一日志**: 分级日志、进度条、批量报告和统计分析
- **模块化设计**: 可插拔的评分器和预处理器
- **API集成**: 支持OpenAI兼容API进行智能评分

## 快速开始

1. 使用uv安装依赖:

```bash
# 使用uv管理项目依赖 (推荐)
uv sync

# 或者使用传统方式
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

2. 配置环境:

```bash
# 复制环境配置模板
cp .env.example .env

# 配置TOS(如需要)
source env/add_tos_key.env
```

3. 运行示例:

```bash
# 🚀 新的统一任务执行方式

# 查看可用任务
./scripts/run_task.sh

# 运行GitHub代码评分任务（自动后台模式）
./scripts/run_task.sh configs/tasks/github_code_rating.yaml

# 运行包含预处理的GitHub任务
./scripts/run_task.sh configs/tasks/github_raw_code_with_preprocess.yaml

# 运行英文语料评分任务  
./scripts/run_task.sh configs/tasks/en_corpus_rating.yaml

# 运行分布式评分任务 (节点 0/5)
./scripts/run_task.sh configs/tasks/distributed_rating.yaml 0 5

# 创建新的任务配置
uv run python scripts/create_task.py my_new_task --template basic

# 任务管理
./scripts/manage_tasks.sh list                     # 查看运行中的任务
./scripts/manage_tasks.sh monitor github_code      # 监控任务日志  
./scripts/manage_tasks.sh stop github_code         # 停止任务
./scripts/manage_tasks.sh status github_code       # 查看任务状态

# 系统演示
./scripts/demo.sh                              # 完整功能演示
```

## 主要命令

### 1. 数据评分管线

```bash
# 本地文件
uv run modelcall pipeline input.jsonl output.jsonl --fs local

# TOS文件
uv run modelcall pipeline tos://bucket/input.parquet tos://bucket/output.parquet --fs tos
```

### 2. 数据预处理 ⭐

支持多种输入格式 (JSONL/Parquet) 和存储 (本地/TOS)，强制输出Parquet格式。

```bash
# GitHub原始代码预处理 (支持JSONL/Parquet输入)
uv run modelcall preprocess github \
    --raw_path "users/data/github_raw_code/" \
    --output_dir "users/data/github_preprocessed/" \
    --stat_dir "./stats/github_preprocess/" \
    --num_files 2 \
    --num_proc 16

# 在任务中启用预处理（推荐方式）
# 编辑任务配置文件：configs/tasks/xxx.yaml
# preprocess:
#   enabled: true
#   script_type: "github_raw_code"           # 专用预处理脚本
#   input_folder: "users/raw_data/github"    # 支持本地/TOS
#   output_folder: "users/formatted_data/"   # 强制Parquet输出
```

### 3. 任务配置运行 (推荐方式) ⭐

```bash
# 使用任务配置文件运行
uv run modelcall run-task configs/tasks/github_code_rating.yaml

# 分布式运行 (节点 2/10)
uv run modelcall run-task configs/tasks/distributed_rating.yaml --job_index 2 --world_size 10
```

### 4. 传统API调用方式 (仍支持)

```bash
# 直接使用API调用命令
uv run modelcall api-call \
    --input_folder "users/data/formatted/" \
    --output_folder "users/data/scored/" \
    --model_config_path "configs/models/dpsk-v3-0526.yaml" \
    --prompt_config_path "configs/prompts/code_corpus_rating_v0.3.yaml" \
    --max_concurrent_files 2 \
    --max_concurrent_requests 10 \
    --chunk_size 100
```

## 🏗️ 架构说明

### 新的简化架构 ⭐

```
modelcall/
├── configs/
│   ├── tasks/             # 📋 任务配置中心 (核心特性)
│   │   ├── github_code_rating.yaml
│   │   ├── en_corpus_rating.yaml
│   │   └── distributed_rating.yaml
│   ├── models/            # 🤖 模型配置
│   │   └── dpsk-v3-0526.yaml
│   └── prompts/           # 💬 提示词配置
│       ├── code_corpus_rating_v0.3.yaml
│       └── en_corpus_rating_v0.1.yaml
├── modelcall/             # 🛠️ 核心代码
│   ├── task_manager.py    # 📋 任务管理器
│   ├── fs/                # 文件系统抽象
│   ├── pipeline/          # 处理管线
│   └── cli.py             # 命令行接口
└── scripts/
    ├── run_task.sh        # 🚀 统一任务执行器
    ├── create_task.py     # 📝 任务配置生成器
    └── utils/             # 🔧 工具脚本
```

### 核心设计理念

**一个任务 = 一个YAML配置文件**

所有的复杂参数、路径、并发设置都在YAML文件中配置，执行时只需要指定配置文件即可。

## 环境变量

### TOS配置
```bash
export TOS_ENDPOINT=https://tos-cn-beijing.ivolces.com
export REGION=cn-beijing
export TOS_ACCESS_KEY=your_access_key
export TOS_SECRET_KEY=your_secret_key
export TOS_BUCKET=agi-data
```

### 模型API
```bash
export OPENAI_API_KEY=your_key
export ANTHROPIC_API_KEY=your_key
export DEEPSEEK_API_KEY=your_key
```

## 🔄 智能重试机制

系统实现了双层重试机制，确保API调用的成功率和输出格式的一致性：

### 1. 网络/API错误重试
- 网络连接失败
- API服务临时不可用
- 超时错误
- 其他API相关错误

### 2. JSON格式验证重试 ⭐
- **自动检测**: 模型返回的JSON格式不符合配置要求时自动重试
- **智能分析**: 根据错误类型提供不同的重试策略
- **详细日志**: 清晰显示重试原因和过程

#### 触发重试的情况：
- ❌ JSON解析失败
- ❌ 缺少必需字段 (如 `score`)  
- ❌ 字段类型不匹配
- ❌ 返回空响应

#### 重试配置：
```bash
# 启用格式验证重试 (默认)
uv run modelcall api-call --input_folder ... --output_folder ...

# 禁用格式验证重试
uv run modelcall api-call --disable_format_validation_retry --input_folder ... --output_folder ...
```

#### 示例日志：
```
❌ JSON validation failed: Missing required keys: {'score'}
📄 Raw response (first 200 chars): This is a good code example with...
🔑 Missing required keys - retrying with emphasis on required fields...
🔄 Format validation error, retrying: JSON format validation failed...
✅ Valid JSON response received with keys: ['score', 'quality_tags', 'main_languages']
```

## 📊 统一日志系统

### 日志特性
- **分级日志**: DEBUG、INFO、WARNING、ERROR、CRITICAL
- **实时进度条**: 文件级和批次级进度显示
- **批量报告**: 避免频繁输出，每N条记录批量汇总
- **统计分析**: 自动计算成功率、处理速度等指标
- **多格式输出**: 控制台显示 + 文件记录 + JSON详情

### 日志文件结构
```
logs/
├── github_code_rating_20241201_143022.log          # 主日志文件
├── github_code_rating_20241201_143022_job001.log   # 分布式节点日志
├── github_code_rating_batch_details.jsonl         # 批量处理详情
└── github_code_rating_final_stats.json            # 最终统计
```

### 日志配置
```yaml
# 在任务配置文件中
logging:
  level: "INFO"                    # 日志级别
  batch_size: 100                  # 批量报告大小
  progress_report_interval: 10     # 进度报告间隔
```

### 查看日志
```bash
# 查看所有日志文件
uv run python scripts/utils/view_logs.py

# 查看特定任务日志
uv run python scripts/utils/view_logs.py --task github_code_rating

# 查看批量处理详情
uv run python scripts/utils/view_logs.py --task github_code_rating --details

# 查看最终统计
uv run python scripts/utils/view_logs.py --task github_code_rating --stats
```

### 示例日志输出
```
2024-12-01 14:30:22 | INFO | 🚀 任务启动: github_code_rating
2024-12-01 14:30:22 | INFO | 🌐 分布式配置: Job 0/5
2024-12-01 14:30:25 | INFO | 📁 找到 50 个文件需要处理
2024-12-01 14:30:25 | INFO | 🟢 开始处理文件: data_001.parquet
2024-12-01 14:30:30 | INFO | 📊 批量处理完成: 100 项, 成功 95, 失败 5, 成功率 95.0%
2024-12-01 14:30:35 | INFO | 进度: 批次 10, 成功率 94.2%
2024-12-01 14:30:40 | INFO | ✅ 文件处理完成: data_001.parquet
2024-12-01 14:30:40 | INFO |    总体成功率: 950/1000 (95.0%)
```

## 扩展开发

### 添加新的评分器
```python
from modelcall.pipeline.scorer import Scorer

class MyScorer:
    def score(self, item):
        # 实现你的评分逻辑
        result = dict(item)
        result["score"] = my_scoring_function(item["text"])
        return result
```

### 添加新的预处理器
```python
from modelcall.data_processing.base import BasePreprocessor

class MyPreprocessor(BasePreprocessor):
    def get_file_list(self):
        # 返回要处理的文件列表
        pass
    
    def process_item(self, item):
        # 处理单个数据项
        pass
```

### 添加新的文件系统
```python
from modelcall.fs.base import FileSystem

class MyFileSystem(FileSystem):
    def open(self, path, mode="rb"):
        # 实现文件打开逻辑
        pass
    # ... 实现其他接口方法
```
