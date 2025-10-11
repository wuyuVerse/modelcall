# 模型配置文件索引

所有模型配置已统一为 YAML 格式，不再需要环境变量配置。

## 📋 配置文件列表

### Claude 系列

#### 1. claude-sonnet-4.5-thinking.yaml
- **模型**: claude-sonnet-4-5-20250929-thinking
- **特点**: 支持思维链推理（thinking mode）
- **提供商**: Vectortara API
- **适用场景**: 需要深度推理和解释的复杂任务
- **配置**:
  - temperature: 0.7
  - max_tokens: 8000

#### 2. claude-sonnet-4.5.yaml
- **模型**: claude-sonnet-4-5-20250929
- **特点**: 标准版本，平衡性能和成本
- **提供商**: Vectortara API
- **适用场景**: 一般对话和代码生成任务
- **配置**:
  - temperature: 0.7
  - max_tokens: 8000

---

### DeepSeek V3 系列

#### 3. deepseek-v3.yaml
- **模型**: deepseek-v3-inner
- **提供商**: 内部 API
- **适用场景**: 通用代码相关任务
- **配置**:
  - temperature: 0.7
  - max_tokens: 4000

#### 4. deepseek-v3-local.yaml
- **模型**: deepseek-v3
- **部署**: 本地集群
- **URL**: `http://generalsvc-dpsk-v3-gpu128-train.t-skyinfer-yzli02.svc.cluster.local:30000/v1`
- **备选**: `http://deepseek-v3-train.t-skyinfer-fjing.svc.cluster.local/v1`
- **适用场景**: 本地部署的高性能推理
- **配置**:
  - temperature: 0.7
  - max_tokens: 4000

#### 5. dpsk-v3-0526.yaml ⭐
- **模型**: deepseek-ai/DeepSeek-V3
- **版本**: 0526版本
- **部署**: 本地集群
- **特点**: 较低温度，适合确定性输出
- **适用场景**: 代码质量评分、需要事实性输出的任务
- **配置**:
  - temperature: 0.6 (更确定)
  - max_tokens: 512

#### 6. dpsk-v3-pro.yaml ⭐
- **模型**: Pro/deepseek-ai/DeepSeek-V3
- **版本**: Pro版本
- **部署**: 本地集群
- **特点**: Pro版本提供更好的性能
- **适用场景**: 高要求的代码分析任务
- **配置**:
  - temperature: 0.6
  - max_tokens: 512

---

### Qwen3-480B 系列

#### 7. qwen3-480b.yaml ⭐
- **模型**: qwen3-480b
- **参数量**: 480B 超大规模
- **部署**: 集群内部服务
- **URL**: `http://qwen3-480b-0.t-skyinfer-fjing.svc.cluster.local`
- **适用场景**: 通用大规模语言处理任务
- **配置**:
  - temperature: 0.6
  - max_tokens: 512

#### 8. qwen3-480b-internal.yaml
- **模型**: qwen3-480b
- **部署**: 集群内部访问
- **URL**: `http://qwen3-480b-0.t-skyinfer-fjing.svc.cluster.local`
- **适用场景**: 内部网络高速访问
- **配置**:
  - temperature: 0.7
  - max_tokens: 4000

#### 9. qwen3-480b-external.yaml
- **模型**: qwen3-480b
- **部署**: SiliconFlow Console 外部访问
- **URL**: `https://console.siflow.cn/siflow/auriga/skyinfer/fjing/qwen3-480b-0/v1`
- **适用场景**: 外部网络访问
- **配置**:
  - temperature: 0.7
  - max_tokens: 4000
  - timeout: 180 (较短超时)

#### 10. qwen3-coder-480b.yaml ⭐
- **模型**: /volume/pt-train/models/Qwen3-Coder-480B-A35B-Instruct
- **参数量**: 480B 超大规模
- **专长**: 代码理解、逻辑推理、多语言编程
- **上下文**: 262,144 tokens (超长上下文)
- **适用场景**: 
  - 代码质量评估
  - 代码仓库分析
  - 复杂代码逻辑推理
- **配置**:
  - temperature: 0.3 (低温度确保一致性)
  - max_tokens: 1024 (支持详细分析)
  - top_p: 0.9

---

### 其他服务

#### 11. siliconflow.yaml
- **提供商**: SiliconFlow 公共 API
- **模型**: deepseek-ai/DeepSeek-V3
- **URL**: `https://api.siliconflow.cn/v1`
- **适用场景**: 使用 SiliconFlow 公共服务
- **配置**:
  - temperature: 0.7
  - max_tokens: 4000

---

## 🎯 推荐使用场景

### 代码质量评分任务
推荐配置：
1. **dpsk-v3-0526.yaml** - 平衡性能和速度
2. **qwen3-coder-480b.yaml** - 最高质量，适合复杂代码
3. **dpsk-v3-pro.yaml** - Pro版本，高性能

### 代码生成和重写
推荐配置：
1. **claude-sonnet-4.5.yaml** - 代码生成质量高
2. **qwen3-coder-480b.yaml** - 代码专用模型
3. **qwen3-480b.yaml** - 大规模模型，通用性强

### 需要推理解释
推荐配置：
1. **claude-sonnet-4.5-thinking.yaml** - 思维链模式
2. **qwen3-coder-480b.yaml** - 超长上下文

### 快速批量处理
推荐配置：
1. **dpsk-v3-0526.yaml** - max_tokens 512，速度快
2. **dpsk-v3-pro.yaml** - Pro版本，性能优化

---

## 📖 配置文件格式

所有配置文件统一使用以下格式：

```yaml
# 模型描述信息

client_config:
  base_url: "https://api.example.com/v1"  # API 端点
  api_key: "your-api-key"                  # API 密钥
  timeout: 600                             # 超时时间（秒）
  max_retries: 3                           # 最大重试次数

chat_config:
  model: "model-name"                      # 模型名称
  temperature: 0.7                         # 温度参数 (0.0-2.0)
  max_tokens: 8000                         # 最大生成token数
  stream: false                            # 是否流式输出
  # 其他可选参数
  # top_p: 0.9
  # frequency_penalty: 0.0
  # presence_penalty: 0.0
```

---

## 🚀 使用方法

### 方法1：在任务配置中引用（推荐）

```yaml
# configs/tasks/data_scoring/my_task.yaml
task_name: "code_quality_rating"
task_type: "data_scoring"

# 引用模型配置
model_config_path: "configs/models/dpsk-v3-0526.yaml"

# 提示词配置
prompt_config_path: "configs/prompts/quality_rating.yaml"

# 其他配置...
```

### 方法2：Python 代码中使用

```python
from modelcall.data_scoring import APIScorer

# 使用统一配置格式
scorer = APIScorer(
    model_config_path="configs/models/dpsk-v3-0526.yaml",
    prompt_config_path="configs/prompts/quality_rating.yaml",
    max_concurrent_requests=20
)

# 进行评分
result = await scorer.score_async(item)
```

### 方法3：使用统一模型客户端

```python
from modelcall.common import ModelClientFactory

# 创建客户端
client = ModelClientFactory.from_config_file(
    "configs/models/qwen3-coder-480b.yaml",
    max_concurrent_requests=50
)

# 调用 API
response = await client.chat_completion([
    {"role": "user", "content": "Analyze this code..."}
])
```

---

## 🔄 从环境变量迁移

**旧方式（已废弃）**:
```bash
# env/add_local_dpsk_v3.env
export BASE_URL="http://..."
export API_KEY="EMPTY"
```

**新方式（推荐）**:
直接使用 YAML 配置文件，无需设置环境变量：
```bash
python -m modelcall run-task configs/tasks/my_task.yaml
```

任务配置中指定模型：
```yaml
model_config_path: "configs/models/dpsk-v3-0526.yaml"
```

---

## ⚙️ 配置参数说明

### client_config 参数

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| base_url | str | 是 | - | API 服务端点 |
| api_key | str | 是 | - | API 密钥 |
| timeout | int | 否 | 600 | 请求超时（秒） |
| max_retries | int | 否 | 3 | 失败重试次数 |

### chat_config 参数

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| model | str | 是 | - | 模型名称或路径 |
| temperature | float | 否 | 0.7 | 随机性控制 (0.0-2.0) |
| max_tokens | int | 否 | 4000 | 最大生成token数 |
| stream | bool | 否 | false | 是否流式输出 |
| top_p | float | 否 | 1.0 | 核采样 (0.0-1.0) |
| frequency_penalty | float | 否 | 0.0 | 频率惩罚 (-2.0~2.0) |
| presence_penalty | float | 否 | 0.0 | 存在惩罚 (-2.0~2.0) |

---

## 🔍 配置选择指南

### 按性能需求选择

| 性能要求 | 推荐配置 | 说明 |
|---------|---------|------|
| 最高质量 | qwen3-coder-480b.yaml | 480B参数，超长上下文 |
| 高质量 | claude-sonnet-4.5-thinking.yaml | 思维链推理 |
| 平衡 | dpsk-v3-0526.yaml | 性能和速度平衡 |
| 快速 | dpsk-v3-0526.yaml (512 tokens) | 短输出，快速响应 |

### 按任务类型选择

| 任务类型 | 推荐配置 | 理由 |
|---------|---------|------|
| 代码评分 | dpsk-v3-0526.yaml | 低温度，确定性强 |
| 代码生成 | claude-sonnet-4.5.yaml | 代码质量高 |
| 代码分析 | qwen3-coder-480b.yaml | 代码专用，超长上下文 |
| 批量处理 | dpsk-v3-pro.yaml | Pro版本，高吞吐 |
| 推理任务 | claude-sonnet-4.5-thinking.yaml | 思维链模式 |

### 按部署环境选择

| 环境 | 推荐配置 | URL类型 |
|------|---------|---------|
| 集群内部 | qwen3-480b-internal.yaml | HTTP内网 |
| 外部访问 | qwen3-480b-external.yaml | HTTPS公网 |
| 本地服务 | deepseek-v3-local.yaml | HTTP本地 |
| 云API | claude-sonnet-4.5.yaml | HTTPS云端 |

---

## 🛠️ 自定义配置

### 创建新配置

```bash
cp configs/models/dpsk-v3-0526.yaml configs/models/my-model.yaml
# 编辑 my-model.yaml
```

### 调整参数

根据任务需求调整参数：

```yaml
chat_config:
  model: "your-model-name"
  temperature: 0.3     # 降低随机性
  max_tokens: 2048     # 增加输出长度
  top_p: 0.95         # 调整采样
```

---

## ⚠️ 注意事项

1. **API 密钥安全**: 
   - 不要将包含真实密钥的配置文件提交到 Git
   - 生产环境建议使用密钥管理服务

2. **超时设置**:
   - 大模型推理可能需要较长时间
   - 建议至少设置 600 秒超时

3. **并发控制**:
   - 根据 API 限额调整并发数
   - 避免触发速率限制

4. **模型选择**:
   - 代码任务优先选择代码专用模型
   - 注意模型的上下文长度限制

---

## 📞 故障排查

### 问题：连接超时

**解决方案**:
```yaml
client_config:
  timeout: 1200  # 增加超时时间到20分钟
```

### 问题：API 密钥错误

**检查**:
1. 确认 `api_key` 配置正确
2. 检查密钥是否有效
3. 验证访问权限

### 问题：模型不可用

**解决方案**:
1. 检查 `base_url` 是否正确
2. 确认服务是否运行
3. 尝试备选地址（如 deepseek-v3-local.yaml 中的备注）

---

## 📊 配置文件对比

| 配置文件 | 模型 | 温度 | Max Tokens | 特点 |
|---------|------|------|-----------|------|
| claude-sonnet-4.5-thinking | Claude | 0.7 | 8000 | 思维链 |
| claude-sonnet-4.5 | Claude | 0.7 | 8000 | 标准 |
| dpsk-v3-0526 | DeepSeek | 0.6 | 512 | 快速确定 |
| dpsk-v3-pro | DeepSeek | 0.6 | 512 | Pro版本 |
| qwen3-480b | Qwen | 0.6 | 512 | 通用 |
| qwen3-coder-480b | Qwen | 0.3 | 1024 | 代码专用 |

---

**最后更新**: 2024-10-11
**格式版本**: 2.0 (统一YAML格式)
