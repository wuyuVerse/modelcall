"""批量任务提交器"""

from typing import List, Dict, Any
from .client import SiFlowClient
from .task_generator import TaskGenerator


class BatchSubmitter:
    """批量任务提交器类"""
    
    def __init__(
        self,
        region: str = "cn-beijing",
        cluster: str = "auriga",
        template_path: str = None
    ):
        """
        初始化批量提交器
        
        Args:
            region: SiFlow 区域
            cluster: SiFlow 集群
            template_path: YAML 模板文件路径（可选）
        """
        self.client = SiFlowClient(region=region, cluster=cluster)
        self.generator = TaskGenerator(template_path=template_path)
    
    def submit_single_task(
        self,
        name_prefix: str,
        cmd: str,
        count_per_pod: int = 10,
        resource_pool: str = "eval-cpu",
        guarantee: bool = False,
        priority: str = "medium"
    ) -> Dict[str, Any]:
        """
        提交单个任务
        
        Args:
            name_prefix: 任务名称前缀
            cmd: 要执行的命令
            count_per_pod: 每个 pod 的 CPU 核心数
            resource_pool: 资源池名称
            guarantee: 是否保证资源
            priority: 任务优先级
            
        Returns:
            任务提交结果
        """
        yaml_path = self.generator.create_task_yaml(
            name_prefix=name_prefix,
            cmd=cmd,
            count_per_pod=count_per_pod,
            resource_pool=resource_pool,
            guarantee=guarantee,
            priority=priority
        )
        
        try:
            result = self.client.create_task(yaml_file=yaml_path)
            return {
                "success": True,
                "result": result,
                "yaml_path": yaml_path,
                "cmd": cmd,
                "task_name": name_prefix
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "yaml_path": yaml_path,
                "cmd": cmd,
                "task_name": name_prefix
            }
    
    def batch_submit_tasks(
        self,
        cmds: List[str],
        name_prefix: str = "distillation",
        count_per_pod: int = 10,
        resource_pool: str = "eval-cpu",
        guarantee: bool = False,
        priority: str = "medium"
    ) -> List[Dict[str, Any]]:
        """
        批量提交任务
        
        Args:
            cmds: 命令列表
            name_prefix: 任务名称前缀
            count_per_pod: 每个 pod 的 CPU 核心数
            resource_pool: 资源池名称
            guarantee: 是否保证资源
            priority: 任务优先级
            
        Returns:
            任务提交结果列表
        """
        results = []
        
        for i, cmd in enumerate(cmds, 1):
            task_name = f"{name_prefix}-{i:04d}"
            print(f"[{i}/{len(cmds)}] 提交任务: {task_name}")
            
            result = self.submit_single_task(
                name_prefix=task_name,
                cmd=cmd,
                count_per_pod=count_per_pod,
                resource_pool=resource_pool,
                guarantee=guarantee,
                priority=priority
            )
            
            if result["success"]:
                print(f"  ✅ 成功: {result['result']}")
            else:
                print(f"  ❌ 失败: {result['error']}")
            
            results.append(result)
        
        return results
    
    def submit_distillation_tasks(
        self,
        split_dir: str,
        output_base_dir: str,
        model_config: str,
        name_prefix: str = "distillation",
        concurrency: int = 30,
        batch_size: int = 30,
        count_per_pod: int = 10,
        resource_pool: str = "eval-cpu",
        guarantee: bool = False,
        priority: str = "medium",
        subtask_log_dir: str = None,
        script_path: str = None,
        dry_run: bool = False
    ) -> List[Dict[str, Any]]:
        """
        提交数据蒸馏任务
        
        Args:
            split_dir: 切分文件目录
            output_base_dir: 输出基础目录
            model_config: 模型配置文件路径
            name_prefix: 任务名称前缀
            concurrency: 并发数
            batch_size: 批量保存大小
            count_per_pod: 每个 pod 的 CPU 核心数
            resource_pool: 资源池名称
            guarantee: 是否保证资源
            priority: 任务优先级
            script_path: 响应生成脚本路径
            dry_run: 是否只生成命令不提交
            
        Returns:
            任务提交结果列表
        """
        # 生成命令
        cmds = self.generator.generate_distillation_cmds(
            split_dir=split_dir,
            output_base_dir=output_base_dir,
            model_config=model_config,
            concurrency=concurrency,
            batch_size=batch_size,
            subtask_log_dir=subtask_log_dir,
            script_path=script_path
        )
        
        print(f"生成了 {len(cmds)} 个任务命令")
        
        if dry_run:
            print("\n【Dry Run 模式】命令预览（前3个）：")
            for i, cmd in enumerate(cmds[:3], 1):
                print(f"\n任务 {i}:")
                print(cmd)
            if len(cmds) > 3:
                print(f"\n... 还有 {len(cmds) - 3} 个任务")
            print(f"\n总任务数: {len(cmds)}")
            print(f"资源配置: resourcePool={resource_pool}, countPerPod={count_per_pod}")
            return []
        
        # 批量提交
        return self.batch_submit_tasks(
            cmds=cmds,
            name_prefix=name_prefix,
            count_per_pod=count_per_pod,
            resource_pool=resource_pool,
            guarantee=guarantee,
            priority=priority
        )

