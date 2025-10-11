"""JSONL文件合并器 - 数据蒸馏第二步"""

import json
import logging
from pathlib import Path
from typing import List, Generator, Dict, Any

import jsonlines
from tqdm import tqdm


class JSONLMerger:
    """JSONL文件合并器"""
    
    def __init__(
        self,
        input_files: List[str],
        output_path: str,
        chunk_size: int = 1000
    ):
        """
        初始化JSONL合并器
        
        Args:
            input_files: 待合并的JSONL文件列表
            output_path: 合并后输出的JSONL路径
            chunk_size: 分块写入的大小
        """
        self.input_files = input_files
        self.output_path = output_path
        self.chunk_size = chunk_size
        
        # 配置日志
        self.logger = logging.getLogger(__name__)
    
    @staticmethod
    def ensure_directory_exists(path: str, type: str = "file"):
        """
        确保指定路径的父目录存在。
        type="file" 表示 path 是文件路径，创建其父目录；
        type="dir" 表示 path 是目录路径，直接创建。
        """
        p = Path(path).absolute()
        if type == "file":
            p.parent.mkdir(parents=True, exist_ok=True)
        else:
            p.mkdir(parents=True, exist_ok=True)
    
    def write_jsonl_streaming(self, objs_generator: Generator, out_path: str) -> int:
        """
        分块将 objs_generator 中的 dict 对象写入 out_path（jsonlines 格式）。
        
        Args:
            objs_generator: 生成器，产出dict对象
            out_path: 输出文件路径
            
        Returns:
            写入的记录总数
        """
        self.ensure_directory_exists(out_path, "file")
        total = 0
        # mode="w" 表示每次运行都会重写文件
        with jsonlines.open(out_path, mode="w", flush=True) as writer:
            buffer = []
            for obj in objs_generator:
                buffer.append(obj)
                if len(buffer) >= self.chunk_size:
                    writer.write_all(buffer)
                    total += len(buffer)
                    buffer.clear()
            # 写入剩余
            if buffer:
                writer.write_all(buffer)
                total += len(buffer)
        
        self.logger.info(f"\n[ Done ] 共写入 {total} 条记录到 {out_path}")
        return total
    
    def merge_jsonl_files_streaming(self) -> int:
        """
        流式合并多个 .jsonl 文件，遇到无效 JSON 行时跳过并打印警告。
        
        Returns:
            合并的记录总数
        """
        def generator():
            n_files = len(self.input_files)
            for idx, fp in enumerate(self.input_files, start=1):
                self.logger.info(f"\n=== [{idx}/{n_files}] processing {fp} ===")

                # ---------- 1. 首行 Preview ----------
                try:
                    with jsonlines.open(fp, mode="r") as reader:
                        first_obj = reader.read()  # 读第一条
                    self.logger.info(f"  first line preview: {first_obj}")
                except Exception as e:
                    self.logger.warning(f"  ⚠️  Preview 失败: {e}")

                # ---------- 2. 统计总行数（用于 tqdm） ----------
                try:
                    with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                        total_lines = sum(1 for _ in f)
                except Exception:
                    total_lines = None

                # ---------- 3. 真正开始流式读取并 yield ----------
                with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                    # 直接按行读，保留所有原始字符
                    pbar = tqdm(f,
                                total=total_lines,
                                desc=f"  reading {Path(fp).name}",
                                unit=" lines",
                                ncols=80)
                    for raw in pbar:
                        line = raw.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                            yield obj
                        except json.JSONDecodeError as ex:
                            self.logger.warning(f"    ⚠️  skip invalid JSON in {fp}: {ex}")
                            continue

        # 调用写入
        return self.write_jsonl_streaming(generator(), self.output_path)
    
    def validate_input_files(self) -> bool:
        """
        校验输入文件是否存在
        
        Returns:
            所有文件都存在返回True，否则返回False
        """
        all_exist = True
        for fn in self.input_files:
            if not Path(fn).is_file():
                self.logger.error(f"Error: 找不到文件 {fn}")
                all_exist = False
        return all_exist
    
    def run(self) -> int:
        """
        运行合并任务
        
        Returns:
            合并的记录总数
        """
        # 校验输入文件
        if not self.validate_input_files():
            self.logger.error("部分输入文件不存在，终止合并")
            return 0
        
        self.logger.info(f"开始合并 {len(self.input_files)} 个文件到 -> {self.output_path}")
        total = self.merge_jsonl_files_streaming()
        self.logger.info(f"\n全部完成！合并记录总数：{total}")
        
        return total

