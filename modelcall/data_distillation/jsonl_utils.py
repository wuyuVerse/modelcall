"""JSONL 文件处理工具模块"""

import math
from pathlib import Path
from typing import List, Optional, Tuple
import jsonlines
from tqdm import tqdm


def ensure_directory_exists(path: Path, is_file: bool = True):
    """
    确保指定路径的目录存在
    
    Args:
        path: 路径
        is_file: 是否为文件路径（如果是，创建父目录；如果否，创建目录本身）
    """
    if not path.is_absolute():
        path = path.absolute()
    
    if is_file:
        path.parent.mkdir(parents=True, exist_ok=True)
    else:
        path.mkdir(parents=True, exist_ok=True)


def read_jsonl_file(file_path: str, max_lines: Optional[int] = None) -> List[dict]:
    """
    读取 JSONL 文件
    
    Args:
        file_path: 文件路径
        max_lines: 最大读取行数（None 表示读取全部）
        
    Returns:
        数据列表
    """
    data = []
    with jsonlines.open(file_path, "r") as reader:
        for i, obj in enumerate(reader):
            if max_lines is not None and i >= max_lines:
                break
            data.append(obj)
    return data


def write_jsonl_file(data: List[dict], file_path: str, chunk_size: int = 1000):
    """
    写入 JSONL 文件
    
    Args:
        data: 数据列表
        file_path: 文件路径
        chunk_size: 批量写入大小
    """
    path = Path(file_path)
    ensure_directory_exists(path, is_file=True)
    
    with jsonlines.open(file_path, "w", flush=True) as writer:
        for i in range(0, len(data), chunk_size):
            writer.write_all(data[i: i + chunk_size])


def split_jsonl(
    input_file: str,
    num_chunks: Optional[int] = None,
    lines_per_chunk: Optional[int] = None,
    output_dir: Optional[str] = None
) -> str:
    """
    分割 JSONL 文件
    
    Args:
        input_file: 输入文件路径
        num_chunks: 分割成多少份（与 lines_per_chunk 二选一）
        lines_per_chunk: 每份多少行（与 num_chunks 二选一）
        output_dir: 输出目录（可选，默认为输入文件同目录下的同名目录）
        
    Returns:
        输出目录路径
    """
    input_path = Path(input_file)
    if not input_path.exists():
        raise FileNotFoundError(f"输入文件不存在: {input_file}")
    
    # 读取所有数据
    print(f"读取文件: {input_file}")
    data = read_jsonl_file(input_file)
    total_lines = len(data)
    print(f"总行数: {total_lines}")
    
    # 计算分割参数
    if num_chunks is not None:
        lines_per_chunk = math.ceil(total_lines / num_chunks)
        actual_chunks = num_chunks
    elif lines_per_chunk is not None:
        actual_chunks = math.ceil(total_lines / lines_per_chunk)
    else:
        raise ValueError("必须指定 num_chunks 或 lines_per_chunk")
    
    print(f"分割参数: {actual_chunks} 份，每份约 {lines_per_chunk} 行")
    
    # 创建输出目录
    if output_dir is None:
        output_path = input_path.parent / input_path.stem
    else:
        output_path = Path(output_dir)
    
    ensure_directory_exists(output_path, is_file=False)
    print(f"输出目录: {output_path}")
    
    # 分割并保存
    for i in range(actual_chunks):
        start_idx = i * lines_per_chunk
        end_idx = min((i + 1) * lines_per_chunk, total_lines)
        chunk_data = data[start_idx:end_idx]
        
        if len(chunk_data) == 0:
            break
        
        output_file = output_path / f"{input_path.stem}_split_{i+1:04d}.jsonl"
        write_jsonl_file(chunk_data, str(output_file))
        print(f"已保存分片 {i+1:04d}: {len(chunk_data)} 行 -> {output_file.name}")
    
    print(f"分割完成! 共生成 {actual_chunks} 个文件到目录: {output_path}")
    return str(output_path)


def detect_output_filename(input_dir: str) -> str:
    """
    根据输入目录和分片文件自动检测输出文件名
    
    Args:
        input_dir: 输入目录
        
    Returns:
        推断的输出文件路径
    """
    input_path = Path(input_dir)
    
    # 查找分片文件
    split_files = sorted(list(input_path.glob("*_split_*.jsonl")))
    if not split_files:
        # 如果没有找到分片文件，使用目录名
        return str(input_path.parent / f"{input_path.name}.jsonl")
    
    # 从第一个分片文件推断原始文件名
    first_file = split_files[0]
    filename = first_file.stem
    
    # 移除 _split_数字 后缀
    if "_split_" in filename:
        original_name = filename.split("_split_")[0]
    else:
        original_name = filename
    
    # 生成输出文件路径（在输入目录的父目录下）
    output_file = input_path.parent / f"{original_name}.jsonl"
    
    return str(output_file)


def merge_jsonl(input_dir: str, output_file: Optional[str] = None) -> str:
    """
    合并 JSONL 文件
    
    Args:
        input_dir: 包含分割文件的目录
        output_file: 输出文件路径（可选，如果不指定则自动检测）
        
    Returns:
        输出文件路径
    """
    input_path = Path(input_dir)
    if not input_path.exists():
        raise FileNotFoundError(f"输入目录不存在: {input_dir}")
    
    # 自动检测输出文件名
    if output_file is None:
        output_file = detect_output_filename(input_dir)
        print(f"自动检测输出文件: {output_file}")
    
    # 查找所有 split 文件
    split_files = sorted(list(input_path.glob("*_split_*.jsonl")))
    # 过滤 _error_retry 文件
    split_files = [f for f in split_files if "_error" not in f.name and "_retry" not in f.name]
    
    if not split_files:
        raise FileNotFoundError(f"在目录 {input_dir} 中没有找到 *_split_*.jsonl 文件")
    
    print(f"找到 {len(split_files)} 个分片文件")
    
    # 合并所有数据
    merged_data = []
    total_lines = 0
    
    for split_file in tqdm(split_files, desc="合并文件"):
        data = read_jsonl_file(str(split_file))
        merged_data.extend(data)
        total_lines += len(data)
    
    # 保存合并结果
    write_jsonl_file(merged_data, output_file)
    print(f"合并完成! 总计 {total_lines} 行 -> {output_file}")
    return output_file


def find_split_output_files(base_dir: str, file_pattern: str = "*.jsonl") -> Tuple[List[Path], List[Path]]:
    """
    查找所有切分任务的输出文件
    
    Args:
        base_dir: 基础目录
        file_pattern: 文件匹配模式
        
    Returns:
        (成功文件列表, 错误文件列表)
    """
    base_path = Path(base_dir)
    
    if not base_path.exists():
        raise FileNotFoundError(f"基础目录不存在: {base_dir}")
    
    # 查找所有子目录
    split_dirs = sorted([d for d in base_path.iterdir() if d.is_dir() and "split" in d.name])
    
    if not split_dirs:
        # 如果没有子目录，直接在当前目录查找
        split_dirs = [base_path]
    
    output_files = []
    error_files = []
    
    for split_dir in split_dirs:
        # 在每个子目录中查找输出文件（排除 error 和 retry 文件）
        for file in split_dir.glob(file_pattern):
            if "_error" not in file.name and "_retry" not in file.name:
                output_files.append(file)
            elif "_error" in file.name and "_retry" not in file.name:
                error_files.append(file)
    
    return sorted(output_files), sorted(error_files)


def merge_split_results(input_dir: str, output_file: str, merge_errors: bool = True) -> dict:
    """
    合并所有切分任务的结果
    
    Args:
        input_dir: 包含切分结果的目录
        output_file: 合并后的输出文件路径
        merge_errors: 是否合并错误文件
        
    Returns:
        统计信息字典
    """
    print(f"正在扫描目录: {input_dir}")
    
    # 查找所有输出文件
    output_files, error_files = find_split_output_files(input_dir)
    
    print(f"找到 {len(output_files)} 个成功输出文件")
    print(f"找到 {len(error_files)} 个错误输出文件")
    
    if not output_files:
        print("警告: 没有找到任何输出文件!")
        return {}
    
    # 合并成功的结果
    print("\n合并成功结果...")
    all_success_data = []
    
    for file in tqdm(output_files, desc="读取成功文件"):
        try:
            data = read_jsonl_file(str(file))
            all_success_data.extend(data)
            print(f"  {file.name}: {len(data)} 条")
        except Exception as e:
            print(f"  ⚠️  读取失败 {file.name}: {e}")
    
    # 写入合并后的成功结果
    output_path = Path(output_file)
    write_jsonl_file(all_success_data, str(output_path))
    print(f"\n✅ 成功结果已合并: {output_path}")
    print(f"   总计: {len(all_success_data)} 条")
    
    # 合并错误结果
    error_count = 0
    if merge_errors and error_files:
        print("\n合并错误结果...")
        all_error_data = []
        
        for file in tqdm(error_files, desc="读取错误文件"):
            try:
                data = read_jsonl_file(str(file))
                all_error_data.extend(data)
                print(f"  {file.name}: {len(data)} 条")
            except Exception as e:
                print(f"  ⚠️  读取失败 {file.name}: {e}")
        
        # 写入合并后的错误结果
        error_output_path = output_path.parent / f"{output_path.stem}_error.jsonl"
        write_jsonl_file(all_error_data, str(error_output_path))
        print(f"\n✅ 错误结果已合并: {error_output_path}")
        print(f"   总计: {len(all_error_data)} 条")
        error_count = len(all_error_data)
    
    # 统计
    print("\n" + "=" * 60)
    print("合并完成统计")
    print("=" * 60)
    print(f"处理的文件数: {len(output_files)}")
    print(f"成功记录数: {len(all_success_data)}")
    
    if merge_errors and error_files:
        print(f"错误记录数: {error_count}")
    
    success_rate = (len(all_success_data) / (len(all_success_data) + error_count) * 100) if (len(all_success_data) + error_count) > 0 else 100
    print(f"成功率: {success_rate:.2f}%")
    print("=" * 60)
    
    return {
        "total_files": len(output_files),
        "success_count": len(all_success_data),
        "error_count": error_count,
        "success_rate": success_rate
    }

