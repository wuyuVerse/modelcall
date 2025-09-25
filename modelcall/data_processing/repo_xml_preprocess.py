"""代码仓库XML/CXML打包效果评分预处理器 (支持Repomix和RenderGit)"""

import os
import json
import random
import argparse
import copy
import xml.etree.ElementTree as ET
from uuid import uuid4
from pathlib import Path
from typing import List, Dict, Any, Tuple
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm
import pandas as pd
import numpy as np
import re
from datetime import datetime

from ..utils import get_tos_config, get_filesystem, process_text, save_progress_stat
from .base import BasePreprocessor


DEFAULT_FILE_STAT = {
    "prompt_conf": "",
    "model_conf": "",
    "rating_times": 0,
    "voting_status": False,
    "raw_file_path": "",
    "formatted_file_path": "",
    "taged_file_paths": [],
    "voting_file_path": "",
    "n_sample": 0,
}


class RepoXMLPreprocessor(BasePreprocessor):
    """代码仓库XML/CXML文件预处理器 (支持Repomix和RenderGit)"""
    
    def __init__(self, raw_path: str, output_dir: str, stat_dir: str, 
                 fs_cfg: Dict[str, Any], max_tokens: int = 32768, 
                 num_proc: int = 32, seed: int = 42, num_files: int = -1,
                 languages: List[str] = None, batch_size: int = 1000):
        
        super().__init__(raw_path, output_dir, stat_dir, fs_cfg, max_tokens, num_proc, batch_size)
        
        self.seed = seed
        self.num_files = num_files
        self.languages = languages or []  # 如果指定，只处理这些语言
        
        # 设置随机种子
        random.seed(seed)
        np.random.seed(seed)
        
        print(f"RepoXMLPreprocessor initialized:")
        print(f"  Raw path: {raw_path}")
        print(f"  Output dir: {output_dir}")
        print(f"  Stat dir: {stat_dir}")
        print(f"  Max tokens: {max_tokens}")
        print(f"  Num processes: {num_proc}")
        if self.languages:
            print(f"  Target languages: {self.languages}")
    
    def get_file_list(self) -> Dict[str, List[Tuple[str, str, str]]]:
        """获取要处理的XML/CXML文件列表，按语言分组"""
        
        base_path = Path(self.raw_path)
        
        # 获取所有语言目录
        if self.languages:
            # 只处理指定语言
            language_dirs = [base_path / lang for lang in self.languages if (base_path / lang).exists()]
        else:
            # 处理所有语言
            language_dirs = [d for d in base_path.iterdir() if d.is_dir()]
        
        print(f"Found {len(language_dirs)} language directories")
        
        # 按语言收集文件
        files_by_language = {}
        total_files = 0
        
        for lang_dir in language_dirs:
            language = lang_dir.name
            # 支持XML和CXML格式
            xml_files = list(lang_dir.glob("*.xml")) + list(lang_dir.glob("*.cxml"))
            
            if xml_files:
                files_by_language[language] = []
                for xml_file in xml_files:
                    files_by_language[language].append(str(xml_file))
                    total_files += 1
        
        print(f"Found {total_files} total XML/CXML files across {len(files_by_language)} languages")
        
        # 限制处理文件数量（按语言平均分配）
        if self.num_files > 0 and len(files_by_language) > 0:
            files_per_lang = max(1, self.num_files // len(files_by_language))
            for language in files_by_language:
                files_by_language[language] = files_by_language[language][:files_per_lang]
            
            total_limited = sum(len(files) for files in files_by_language.values())
            print(f"Limited to {total_limited} files for processing (~{files_per_lang} per language)")
        
        return files_by_language
    
    def extract_xml_content(self, xml_path: str) -> Dict[str, Any]:
        """提取XML文件的关键信息"""
        try:
            with open(xml_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 提取基本信息
            repo_info = self.extract_repo_info(content)
            
            # 提取文件结构信息
            structure_info = self.extract_structure_info(content)
            
            # 提取代码内容
            code_content = self.extract_code_content(content)
            
            # 计算统计信息
            stats = self.calculate_stats(content, code_content)
            
            return {
                "repo_info": repo_info,
                "structure_info": structure_info,
                "code_content": code_content,
                "stats": stats,
                "raw_content": content  # 保留原始内容用于评分
            }
            
        except Exception as e:
            print(f"Error extracting XML content from {xml_path}: {e}")
            return None
    
    def extract_repo_info(self, content: str) -> Dict[str, str]:
        """提取仓库基本信息"""
        # 从文件名提取用户/仓库信息
        repo_pattern = r'([^_]+)_([^_]+)_([a-f0-9]+)\.xml'
        
        info = {
            "user": "",
            "repo": "",
            "commit_hash": "",
            "full_name": ""
        }
        
        # 这里可以进一步从XML内容中提取更多信息
        return info
    
    def extract_structure_info(self, content: str) -> Dict[str, Any]:
        """提取结构信息（基于实际文件内容）"""
        # 不再从directory_structure提取，而是基于实际的<files>部分
        # 获取<files>部分的文件路径来推断结构信息
        files_section = re.search(r'<files>(.*?)</files>', content, re.DOTALL)
        
        if files_section:
            files_content = files_section.group(1)
            file_entries = re.findall(r'<file path="([^"]+)">', files_content)
            
            return {
                "files": file_entries,
                "total_files": len(file_entries),  # 基于实际文件数
                "has_readme": any('readme' in f.lower() for f in file_entries),
                "has_license": any('license' in f.lower() for f in file_entries),
                "has_gitignore": '.gitignore' in file_entries
            }
        
        return {"files": [], "total_files": 0}
    
    def extract_code_content(self, content: str) -> Dict[str, Any]:
        """提取代码内容"""
        # 提取<files>部分
        files_section = re.search(r'<files>(.*?)</files>', content, re.DOTALL)
        
        if files_section:
            files_content = files_section.group(1)
            
            # 计算代码行数和文件数
            file_entries = re.findall(r'<file path="([^"]+)">(.*?)</file>', 
                                    files_content, re.DOTALL)
            
            total_lines = 0
            file_types = {}
            
            for file_path, file_content in file_entries:
                lines = len(file_content.split('\n'))
                total_lines += lines
                
                ext = os.path.splitext(file_path)[1].lower()
                file_types[ext] = file_types.get(ext, 0) + 1
            
            return {
                "total_files_with_content": len(file_entries),
                "total_lines": total_lines,
                "file_types": file_types,
                "avg_lines_per_file": total_lines / len(file_entries) if file_entries else 0
            }
        
        return {"total_files_with_content": 0, "total_lines": 0}
    
    def calculate_stats(self, content: str, code_info: Dict) -> Dict[str, Any]:
        """计算统计信息"""
        content_length = len(content)
        content_lines = len(content.split('\n'))
        
        return {
            "content_length": content_length,
            "content_lines": content_lines,
            "avg_line_length": content_length / max(content_lines, 1),
        }
    
    def process_language_files(self, language: str, xml_files: List[str]) -> Tuple[bool, int]:
        """处理一个语言的所有XML文件，合并为一个Parquet，支持分批写入和断点续传"""
        try:
            print(f"Processing {len(xml_files)} {language} files...")
            
            output_path = os.path.join(self.output_dir, f"{language}.parquet")
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # 创建进度状态文件路径
            progress_file = os.path.join(self.stat_dir, f"{language}_progress.json")
            
            # 检查断点续传状态
            processed_files = set()
            all_items = []
            
            if os.path.exists(output_path) and os.path.exists(progress_file):
                try:
                    # 读取已处理的文件列表
                    with open(progress_file, 'r', encoding='utf-8') as f:
                        progress_data = json.load(f)
                    processed_files = set(progress_data.get('processed_files', []))
                    
                    # 读取已有的结果
                    existing_df = pd.read_parquet(output_path)
                    all_items = existing_df.to_dict('records')
                    
                    print(f"📊 断点续传: 已处理 {len(processed_files)} 个文件, 包含 {len(all_items)} 条记录")
                except Exception as e:
                    print(f"⚠️ 无法读取断点续传数据: {e}, 从头开始处理")
                    processed_files = set()
                    all_items = []
            
            # 过滤掉已处理的文件
            remaining_files = [f for f in xml_files if f not in processed_files]
            print(f"📁 需要处理 {len(remaining_files)} 个新文件")
            
            if not remaining_files:
                print(f"✅ {language} 语言所有文件已处理完成")
                return True, len(all_items)
            
            # 累积模式处理文件（不是分批，而是累积式保存）
            items_since_last_save = 0
            
            for i, xml_file in enumerate(tqdm(remaining_files, desc=f"Processing {language}", unit="files")):
                try:
                    # 提取XML内容
                    extracted_data = self.extract_xml_content(xml_file)
                    if not extracted_data:
                        continue
                    
                    # 从文件名提取仓库信息 (支持XML和CXML格式)
                    filename = os.path.basename(xml_file)
                    repo_match = re.match(r'([^_]+)_([^_]+)_([a-f0-9]+)\.(xml|cxml)', filename)
                    
                    if repo_match:
                        user, repo, commit_hash, file_ext = repo_match.groups()
                        extracted_data["repo_info"].update({
                            "user": user,
                            "repo": repo,
                            "commit_hash": commit_hash,
                            "full_name": f"{user}/{repo}",
                            "packaging_tool": "repomix" if file_ext == "xml" else "rendergit"
                        })
                    
                    # 构建标准格式数据
                    item = {
                        "id": str(uuid4()),
                        "text": extracted_data["raw_content"],  # 完整的XML内容作为评分对象
                        "source": "repo_xml",
                        
                        # 仓库信息
                        "repo_user": extracted_data["repo_info"]["user"],
                        "repo_name": extracted_data["repo_info"]["repo"],
                        "repo_full_name": extracted_data["repo_info"]["full_name"],
                        "commit_hash": extracted_data["repo_info"]["commit_hash"],
                        "language": language,
                        "packaging_tool": extracted_data["repo_info"].get("packaging_tool", "unknown"),
                        
                        # 结构信息（基于实际文件）
                        "files_with_content": extracted_data["code_content"]["total_files_with_content"],
                        "total_lines": extracted_data["code_content"]["total_lines"],
                        "avg_lines_per_file": extracted_data["code_content"]["avg_lines_per_file"],
                        
                        # 质量指标（基于实际文件）
                        "has_readme": extracted_data["structure_info"]["has_readme"],
                        "has_license": extracted_data["structure_info"]["has_license"],
                        "has_gitignore": extracted_data["structure_info"]["has_gitignore"],
                        
                        # 内容统计
                        "content_length": extracted_data["stats"]["content_length"],
                        "content_lines": extracted_data["stats"]["content_lines"],
                        "avg_line_length": extracted_data["stats"]["avg_line_length"],
                        
                        # 文件类型分布
                        "file_types": json.dumps(extracted_data["code_content"]["file_types"]),
                        
                        # 原始文件路径
                        "xml_file_path": xml_file,
                        "file_extension": filename.split('.')[-1]  # xml 或 cxml
                    }
                    
                    # 创建截断版本用于API调用
                    truncated_text = process_text(item["text"], self.enc, self.max_tokens)
                    item[f'content_truncate_{self.max_tokens//1024}k'] = truncated_text
                    
                    all_items.append(item)
                    processed_files.add(xml_file)
                    items_since_last_save += 1
                    
                    # 按批次保存进度（避免频繁IO）
                    if items_since_last_save >= self.batch_size or i == len(remaining_files) - 1:
                        # 保存数据文件
                        df = pd.DataFrame(all_items)
                        df.to_parquet(output_path, engine='pyarrow')
                        
                        # 更新进度文件
                        progress_data = {
                            "language": language,
                            "processed_files": list(processed_files),
                            "total_items": len(all_items),
                            "last_update": datetime.now().isoformat(),
                            "batch_size": self.batch_size
                        }
                        
                        with open(progress_file, 'w', encoding='utf-8') as f:
                            json.dump(progress_data, f, indent=2, ensure_ascii=False)
                        
                        print(f"💾 进度保存: {len(all_items)} 条记录, 处理了 {len(processed_files)} 个文件")
                        items_since_last_save = 0
                    
                except Exception as e:
                    print(f"❌ 处理文件失败 {os.path.basename(xml_file)}: {e}")
                    continue
            
            if all_items:
                print(f"✅ {language} 处理完成: {len(all_items)} 条记录")
                return True, len(all_items)
            else:
                print(f"❌ {language} 没有有效数据")
                return False, 0
            
        except Exception as e:
            print(f"❌ 处理 {language} 语言失败: {e}")
            return False, 0
    
    def run(self):
        """运行预处理"""
        print("=== Repomix XML Preprocessing ===")
        
        # 保存配置
        os.makedirs(self.stat_dir, exist_ok=True)
        config_path = os.path.join(self.stat_dir, "preprocess_config.json")
        config_to_save = {
            "raw_path": self.raw_path,
            "output_dir": self.output_dir,
            "stat_dir": self.stat_dir,
            "max_tokens": self.max_tokens,
            "num_proc": self.num_proc,
            "seed": self.seed,
            "num_files": self.num_files,
            "languages": self.languages
        }
        
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_to_save, f, indent=2, ensure_ascii=False)
        
        # 获取按语言分组的文件
        files_by_language = self.get_file_list()
        
        if not files_by_language:
            print("No files to process!")
            return
        
        total_languages = len(files_by_language)
        total_files = sum(len(files) for files in files_by_language.values())
        print(f"Processing {total_files} files across {total_languages} languages")
        
        # 按语言处理（顺序处理，避免内存压力）
        n_success_languages = 0
        n_fail_languages = 0
        total_items = 0
        
        for language, xml_files in files_by_language.items():
            print(f"\n=== Processing {language} ({len(xml_files)} files) ===")
            
            success, n_items = self.process_language_files(language, xml_files)
            
            if success:
                n_success_languages += 1
                total_items += n_items
                
                # 保存增强的统计信息
                from datetime import datetime
                stat = copy.deepcopy(DEFAULT_FILE_STAT)
                stat["raw_file_path"] = f"{language}_combined"
                stat["formatted_file_path"] = os.path.join(self.output_dir, f"{language}.parquet")
                stat["n_sample"] = n_items
                stat["processing_complete"] = True
                stat["language"] = language
                stat["num_xml_files"] = len(xml_files)
                stat["batch_size"] = self.batch_size
                stat["max_tokens"] = self.max_tokens
                stat["processing_time"] = datetime.now().isoformat()
                
                # 添加输出文件检查
                output_file = os.path.join(self.output_dir, f"{language}.parquet")
                if os.path.exists(output_file):
                    stat["output_file_exists"] = True
                    stat["output_file_size_bytes"] = os.path.getsize(output_file)
                else:
                    stat["output_file_exists"] = False
                
                stat_file = os.path.join(self.stat_dir, f"{language}_combined.json")
                try:
                    save_progress_stat(stat_file, stat)
                    print(f"📊 Saved statistics for {language}: {n_items} items")
                except Exception as e:
                    print(f"Failed to write stat file {stat_file}: {e}")
            else:
                n_fail_languages += 1
        
        print(f"\n=== Processing completed ===")
        print(f"Languages processed: {n_success_languages}/{total_languages}")
        print(f"Total items: {total_items}")
        success_rate = n_success_languages / total_languages * 100 if total_languages > 0 else 0
        print(f"Success rate: {success_rate:.2f}%")


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(description="Preprocess repository XML/CXML files for scoring (Repomix and RenderGit)")
    
    parser.add_argument("--raw_path", type=str, required=True,
                       help="Path to repomix_output or rendergit_output directory")
    parser.add_argument("--output_dir", type=str, required=True,
                       help="Directory to save the processed dataset")
    parser.add_argument("--stat_dir", type=str, required=True,
                       help="Directory to save processing statistics")
    parser.add_argument("--num_proc", type=int, default=16,
                       help="Number of processes to use for preprocessing")
    parser.add_argument("--max_tokens", type=int, default=32768,
                       help="Maximum number of tokens per example")
    parser.add_argument("--num_files", type=int, default=-1,
                       help="Number of files to process (-1 for all)")
    parser.add_argument("--seed", type=int, default=42,
                       help="Random seed for sampling")
    parser.add_argument("--languages", type=str, nargs="+", default=None,
                       help="Specific languages to process (e.g., Python Java)")
    
    args = parser.parse_args()
    
    # 获取文件系统配置（这里主要是本地处理）
    fs_cfg = {"local": {}}
    
    # 创建并运行预处理器
    preprocessor = RepoXMLPreprocessor(
        raw_path=args.raw_path,
        output_dir=args.output_dir,
        stat_dir=args.stat_dir,
        fs_cfg=fs_cfg,
        max_tokens=args.max_tokens,
        num_proc=args.num_proc,
        seed=args.seed,
        num_files=args.num_files,
        languages=args.languages
    )
    
    preprocessor.run()


if __name__ == "__main__":
    main()
