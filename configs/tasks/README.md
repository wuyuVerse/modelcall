# 任务配置目录

本目录包含所有任务的配置文件，按任务类型分组。

## 📁 目录结构

```
tasks/
├── data_scoring/           # 数据评分任务
│   ├── filter_rendergit_quality_rating.yaml
│   ├── rendergit_quality_rating.yaml
│   ├── repomix_quality_rating.yaml
│   └── github_raw_code_with_preprocess.yaml
│
├── data_distillation/      # 数据蒸馏任务
│   ├── chatml_conversion.yaml
│   ├── chatml_conversion_with_system.yaml
│   ├── jsonl_merge.yaml
│   ├── jsonl_merge_qa.yaml
│   ├── generate_response.yaml
│   └── generate_response_retry.yaml
│
└── templates/              # 配置模板（即将添加）
    ├── data_scoring_template.yaml
    └── data_distillation_template.yaml
```

## 🎯 任务类型说明

### 数据评分 (data_scoring)
使用大模型对数据进行质量评分。

**典型场景**：
- 代码仓库打包质量评分
- GitHub原始代码质量评分
- 自定义数据质量评估

**运行示例**：
```bash
python -m modelcall run-task configs/tasks/data_scoring/filter_rendergit_quality_rating.yaml
```

### 数据蒸馏 (data_distillation)
数据格式转换和蒸馏处理，包含三个步骤。

**步骤1 - ChatML转换**：
```bash
python -m modelcall run-task configs/tasks/data_distillation/chatml_conversion.yaml
```

**步骤2 - JSONL合并**：
```bash
python -m modelcall run-task configs/tasks/data_distillation/jsonl_merge.yaml
```

**步骤3 - 响应生成**：
```bash
python -m modelcall run-task configs/tasks/data_distillation/generate_response.yaml
```

## 📝 创建新任务

### 方法1：使用模板
```bash
# 复制模板
cp configs/tasks/templates/data_scoring_template.yaml configs/tasks/data_scoring/my_new_task.yaml

# 编辑配置
vim configs/tasks/data_scoring/my_new_task.yaml
```

### 方法2：参考现有任务
选择一个类似的任务配置作为起点，复制并修改相关字段。

## 🔧 配置文件说明

### 必需字段
- `task_name`: 任务名称（唯一标识）
- `task_type`: 任务类型（`data_scoring` 或 `data_distillation`）
- `description`: 任务描述

### 数据评分任务特有字段
- `data`: 数据配置（输入/输出路径）
- `model`: 模型配置路径
- `prompt`: 提示词配置路径
- `concurrency`: 并发配置
- `environment`: 环境配置（API密钥等）

### 数据蒸馏任务特有字段
- `distillation`: 蒸馏配置
  - `step`: 蒸馏步骤（`chatml_conversion`/`jsonl_merge`/`generate_response`）
  - 其他步骤特定字段

## 💡 最佳实践

1. **命名规范**：使用小写字母和下划线，例如 `my_task_name.yaml`
2. **任务名称**：保持简短且描述性，例如 `code_quality_rating`
3. **路径使用**：尽量使用绝对路径或相对于项目根目录的路径
4. **配置复用**：相同的模型/提示词配置可以复用
5. **注释说明**：在配置文件中添加注释说明关键参数

## 📚 参考文档
- [PROJECT_STRUCTURE.md](../../PROJECT_STRUCTURE.md) - 完整项目结构说明
- [INTEGRATION_SUMMARY.md](../../INTEGRATION_SUMMARY.md) - 数据蒸馏模块集成总结

