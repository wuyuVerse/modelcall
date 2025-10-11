"""任务生成器 - 生成蒸馏任务的命令和配置"""

import tempfile
from pathlib import Path
from typing import List, Dict, Any


class TaskGenerator:
    """任务生成器类"""
    
    def __init__(self, template_path: str = None):
        """
        初始化任务生成器
        
        Args:
            template_path: YAML 模板文件路径（可选）
        """
        self.template_path = template_path or self._get_default_template_path()
        self.template_content = self._load_template()
    
    def _get_default_template_path(self) -> str:
        """获取默认模板路径"""
        # 获取当前文件所在目录的上上级目录（项目根目录）
        current_file = Path(__file__)
        project_root = current_file.parent.parent.parent
        return str(project_root / "configs" / "siflow" / "task_template.yaml")
    
    def _load_template(self) -> str:
        """加载 YAML 模板"""
        with open(self.template_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def create_task_yaml(
        self,
        name_prefix: str,
        cmd: str,
        count_per_pod: int = 10,
        resource_pool: str = "eval-cpu",
        guarantee: bool = False,
        priority: str = "medium"
    ) -> str:
        """
        创建任务 YAML 配置文件
        
        Args:
            name_prefix: 任务名称前缀
            cmd: 要执行的命令
            count_per_pod: 每个 pod 的 CPU 核心数
            resource_pool: 资源池名称
            guarantee: 是否保证资源
            priority: 任务优先级
            
        Returns:
            临时 YAML 文件路径
        """
        # 缩进 cmd
        cmd_indented = "\n".join(f"  {line}" for line in cmd.strip().split("\n"))
        
        yaml_content = self.template_content.format(
            name_prefix=name_prefix,
            count_per_pod=count_per_pod,
            resource_pool=resource_pool,
            guarantee=str(guarantee).lower(),
            priority=priority,
            cmd=cmd_indented
        )
        
        # 创建临时文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            return f.name
    
    def generate_distillation_cmds(
        self,
        split_dir: str,
        output_base_dir: str,
        model_config: str,
        concurrency: int = 30,
        batch_size: int = 30,
        subtask_log_dir: str = None,
        script_path: str = None
    ) -> List[str]:
        """
        为切分后的文件生成蒸馏命令
        
        Args:
            split_dir: 切分文件目录
            output_base_dir: 输出基础目录
            model_config: 模型配置文件路径
            concurrency: 并发数
            batch_size: 批量保存大小
            subtask_log_dir: 子任务日志目录
            script_path: 蒸馏脚本路径（已弃用，保留参数用于兼容性）
            
        Returns:
            命令列表
        """
        split_path = Path(split_dir)
        split_files = sorted(list(split_path.glob("*_split_*.jsonl")))
        
        if not split_files:
            raise ValueError(f"在 {split_dir} 中没有找到切分文件")
        
        # 读取模型配置以确定输出子目录名称
        model_name = Path(model_config).stem
        
        cmds = []
        for split_file in split_files:
            split_name = split_file.stem
            output_dir = Path(output_base_dir) / model_name / split_name
            
            # 构建命令
            cmd_parts = [
                "#!/bin/bash",
                "set -e",
                "",
                "cd /volume/pt-train/users/wzhang/wjj-workspace/modelcall",
                "",
                "# 加载环境变量",
                'if [ -f "env/add_siflow.env" ]; then',
                "    export $(cat env/add_siflow.env | grep -v '^#' | xargs)",
                "fi",
                "",
                f'INPUT_PATH="{split_file}"',
                f'OUTPUT_PATH="{output_dir}"',
                f'MODEL_CONFIG="{model_config}"',
                'VENV_PYTHON="/volume/pt-train/users/wzhang/wjj-workspace/modelcall/.venv/bin/python"',
                "",
                "# 使用统一的 CLI 入口",
                "$VENV_PYTHON -m modelcall distillation-generate \\",
                '    --input-path "$INPUT_PATH" \\',
                '    --output-path "$OUTPUT_PATH" \\',
                '    --model-config "$MODEL_CONFIG" \\',
                f'    --concurrency {concurrency} \\',
                f'    --batch-size {batch_size}'
            ]
            
            # 如果指定了子任务日志目录，添加参数
            if subtask_log_dir:
                cmd_parts[-1] = cmd_parts[-1] + " \\"
                cmd_parts.append(f'    --log-dir "{subtask_log_dir}"')
            
            cmd = "\n".join(cmd_parts)
            cmds.append(cmd)
        
        return cmds

