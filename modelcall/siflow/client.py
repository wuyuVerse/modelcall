"""SiFlow 客户端封装"""

import os
from typing import Optional
from siflow import SiFlow


class SiFlowClient:
    """SiFlow 客户端封装类"""
    
    def __init__(
        self,
        region: str = "cn-beijing",
        cluster: str = "auriga",
        access_key_id: Optional[str] = None,
        access_key_secret: Optional[str] = None
    ):
        """
        初始化 SiFlow 客户端
        
        Args:
            region: SiFlow 区域
            cluster: SiFlow 集群
            access_key_id: 访问密钥 ID（可从环境变量读取）
            access_key_secret: 访问密钥（可从环境变量读取）
        """
        self.region = region
        self.cluster = cluster
        
        # 从环境变量或参数获取认证信息
        self.access_key_id = access_key_id or os.environ.get("SIFLOW_ACCESS_KEY_ID")
        self.access_key_secret = access_key_secret or os.environ.get("SIFLOW_ACCESS_KEY_SECRET")
        
        if not self.access_key_id or not self.access_key_secret:
            raise ValueError(
                "SiFlow 认证信息未配置。请设置环境变量 SIFLOW_ACCESS_KEY_ID 和 SIFLOW_ACCESS_KEY_SECRET，"
                "或在 env/.env.siflow 文件中配置。"
            )
        
        self.client = self._create_client()
    
    def _create_client(self) -> SiFlow:
        """创建 SiFlow 客户端实例"""
        return SiFlow(
            region=self.region,
            cluster=self.cluster,
            access_key_id=self.access_key_id,
            access_key_secret=self.access_key_secret,
        )
    
    def create_task(self, yaml_file: str):
        """
        创建任务
        
        Args:
            yaml_file: YAML 配置文件路径
            
        Returns:
            任务创建结果
        """
        return self.client.tasks.create(yaml_file=yaml_file)

