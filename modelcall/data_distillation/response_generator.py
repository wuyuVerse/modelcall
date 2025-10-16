"""响应生成器 - 数据蒸馏第三步，使用大模型生成响应"""

import asyncio
import json
import logging
import os
import random
import sys
import copy
import traceback
import datetime
import time
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional

import aiofiles
import jsonlines
from tqdm import tqdm

from ..common.model_client import UnifiedModelClient

# 优先尝试使用 uvloop 提升事件循环性能（若不可用则忽略）
try:
    import uvloop  # type: ignore
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except Exception:
    pass

class ResponseGenerator:
    """异步响应生成器"""
    
    def __init__(
        self,
        input_path: str,
        output_path: str,
        client_config: Dict[str, Any],
        chat_config: Dict[str, Any],
        concurrency: int = 20,
        batch_size: int = 20,
        flush_interval_secs: float = 2.0,
        retry_mode: bool = False,
        resume_mode: bool = True
    ):
        """
        初始化响应生成器
        
        Args:
            input_path: 输入JSONL文件路径
            output_path: 输出目录路径
            client_config: OpenAI客户端配置
            chat_config: 聊天配置
            concurrency: 并发数量
            batch_size: 批量保存大小
            flush_interval_secs: 定时刷新间隔（秒）
            retry_mode: 是否为重试模式（重新处理失败的任务）
            resume_mode: 是否启用断点续传（跳过已完成的任务）
        """
        self.input_path = input_path
        self.output_path = output_path
        self.concurrency = concurrency
        self.batch_size = batch_size
        self.flush_interval_secs = flush_interval_secs
        self.retry_mode = retry_mode
        self.resume_mode = resume_mode
        
        # 配置日志
        self.logger = logging.getLogger(__name__)
        
        # 创建统一模型客户端（配置已传入，不再需要保存）
        unified_config = {
            "client_config": client_config,
            "chat_config": chat_config
        }
        self.model_client = UnifiedModelClient(
            config=unified_config,
            max_concurrent_requests=concurrency,
            timeout=client_config.get("timeout", 600),
            max_retries=client_config.get("max_retries", 3)
        )
        
        # 确保输出目录存在
        self.ensure_directory_exists(output_path, type="dir")
        
        # 写文件互斥锁，避免并发写入交错
        self.file_lock = asyncio.Lock()
        
        # 异步写入队列（在 run() 中初始化并启动 writer 任务）
        self.writer_queue = None
        self.writer_task = None
    
    @staticmethod
    def ensure_directory_exists(path, type="file"):
        """确保指定路径的目录存在，如果不存在则递归创建"""
        if not os.path.isabs(path):
            path = os.path.abspath(path)
        path = Path(path)
        if type == "file":
            parent_dir = path.parent
            os.makedirs(parent_dir, exist_ok=True)
        elif type == "dir":
            os.makedirs(path, exist_ok=True)
        else:
            raise ValueError(f"Invalid type: {type}")
    
    @staticmethod
    def read_jsonl_file(file_name, max_sentence=None):
        """读取JSONL文件"""
        data = []
        with jsonlines.open(file_name, "r") as r:
            for i, obj in enumerate(r):
                if max_sentence is not None and i >= max_sentence:
                    break
                data.append(obj)
        return data
    
    @staticmethod
    def write_jsonl_file(objs, path, chunk_size=1000, format="w"):
        """同步写入JSONL文件"""
        ResponseGenerator.ensure_directory_exists(path, type="file")
        with jsonlines.open(path, format, flush=True) as w:
            for i in range(0, len(objs), chunk_size):
                w.write_all(objs[i: i + chunk_size])
    
    @staticmethod
    async def write_jsonl_file_async(objs, path, chunk_size=100, format="w"):
        """异步写入JSONL文件 - 优化版"""
        ResponseGenerator.ensure_directory_exists(path, type="file")
        mode = 'w' if format == 'w' else 'a'
        async with aiofiles.open(path, mode, encoding='utf-8') as f:
            for i in range(0, len(objs), chunk_size):
                chunk = objs[i: i + chunk_size]
                # ⚡ 优化：批量序列化后一次性写入（减少 I/O 调用 99%）
                lines = '\n'.join(json.dumps(obj, ensure_ascii=False) for obj in chunk)
                await f.write(lines + '\n')
            await f.flush()
    
    @staticmethod
    def count_lines_in_file(file_path):
        """计算文件行数"""
        try:
            with open(file_path, "r", encoding='utf-8') as f:
                return sum(1 for _ in f)
        except FileNotFoundError:
            return 0
    
    @staticmethod
    def ensure_uid(obj: Dict[str, Any]) -> str:
        """
        确保对象有唯一ID，如果没有则基于内容生成稳定的 UID
        
        Args:
            obj: 数据对象
            
        Returns:
            uid: 对象的唯一标识符
        """
        # 优先使用已有的 uid 或 id
        if 'uid' in obj:
            return obj['uid']
        if 'id' in obj:
            return obj['id']
        
        # 如果没有 uid，基于内容生成稳定的 UID
        # 使用 messages 的第一条内容（最稳定）
        if 'messages' in obj and isinstance(obj['messages'], list) and len(obj['messages']) > 0:
            content = obj['messages'][0].get('content', '')
            if content:
                uid = hashlib.md5(content.encode('utf-8')).hexdigest()
                obj['uid'] = uid  # 添加到对象中
                return uid
        
        # 最后兜底：基于整个对象生成（排序键以保证稳定性）
        content_str = json.dumps(obj, sort_keys=True, ensure_ascii=False)
        uid = hashlib.md5(content_str.encode('utf-8')).hexdigest()
        obj['uid'] = uid
        return uid
    
    @staticmethod
    def deduplicate_by_uid(existing_objs, new_objs):
        """根据uid去重，返回去重后的新对象列表"""
        existing_uids = set()
        
        # 收集现有对象的uid
        for obj in existing_objs:
            if 'uid' in obj:
                existing_uids.add(obj['uid'])
            elif 'id' in obj:
                existing_uids.add(obj['id'])
        
        # 过滤新对象
        deduplicated = []
        for obj in new_objs:
            obj_uid = obj.get('uid', obj.get('id', None))
            if obj_uid is None or obj_uid not in existing_uids:
                deduplicated.append(obj)
            # 如果有uid就添加到已存在集合中
            if obj_uid is not None:
                existing_uids.add(obj_uid)
        
        return deduplicated
    
    async def _chat_async(self, messages: List[Dict[str, str]]) -> str:
        """异步调用统一模型客户端"""
        # 使用统一客户端的聊天补全方法（带重试）
        return await self.model_client.chat_completion(messages)
    
    async def task_worker_async(self, task_args):
        """异步任务工作器
        
        并发控制由 UnifiedModelClient 内部管理。
        """
        try:
            obj = task_args.get("obj", {})
            
            if "messages" not in obj:
                raise ValueError("Object missing 'messages' field")

            # ⚡ 优化：使用浅拷贝代替深拷贝（性能提升 10-50 倍）
            raw_text = obj["messages"][0]["content"]
            messages = [{"role": "user", "content": raw_text}]
            
            # 使用统一客户端进行调用（内置超时和重试机制）
            response = await self._chat_async(messages)
            
            # 构建结果（浅拷贝 + 新字段）
            result = obj.copy()  # 浅拷贝足够，原始数据不会被修改
            result["response"] = response
            result["final_messages"] = [
                {
                    "role": "user",
                    "content": raw_text
                },
                {
                    "role": "assistant",
                    "content": response
                }
            ]
            return result
        except Exception as e:
            obj_id = task_args.get("obj", {}).get('uid', task_args.get("obj", {}).get('id', 'unknown'))
            error_detail = {
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": traceback.format_exc(),
                "timestamp": datetime.datetime.now().isoformat()
            }
            raise Exception(f"Task failed for object {obj_id}: {error_detail}")
    
    async def save_results_batch(self, output_objs, error_objs, output_path, error_path):
        """批量保存结果（串行+加锁，避免并发写入交错）"""
        async with self.file_lock:
            if output_objs:
                await self.write_jsonl_file_async(output_objs, output_path, format="a")
            if error_objs:
                await self.write_jsonl_file_async(error_objs, error_path, format="a")

    async def writer_loop(self, output_path: str, error_path: str):
        """后台写入协程：串行消费队列，避免阻塞主调度循环"""
        while True:
            item = await self.writer_queue.get()
            try:
                if item is None or item == (None, None):
                    # 终止信号
                    return
                output_objs, error_objs = item
                await self.save_results_batch(output_objs, error_objs, output_path, error_path)
            finally:
                # 标记该项处理完成
                self.writer_queue.task_done()
    
    def handle_retry_mode(self, input_path, output_path, retry_iter):
        """处理重试模式的文件路径"""
        # 构建正确的error文件路径
        base_filename = os.path.basename(input_path)
        error_filename = base_filename.replace('.jsonl', '_error.jsonl')
        error_input_path = os.path.join(output_path, error_filename)
        
        if not os.path.exists(error_input_path):
            self.logger.error(f"Error file not found for retry: {error_input_path}")
            return None, None, None
        
        # 移动原来的error文件
        retry_error_filename = base_filename.replace('.jsonl', f'_error_retry_{retry_iter}.jsonl')
        retry_error_path = os.path.join(output_path, retry_error_filename)
        os.rename(error_input_path, retry_error_path)
        self.logger.info(f"Moved previous error file: {error_input_path} -> {retry_error_path}")
        
        # 读取现有的成功结果用于去重
        existing_success_objs = []
        success_output_path = os.path.join(output_path, base_filename)
        if os.path.exists(success_output_path):
            existing_success_objs = self.read_jsonl_file(success_output_path)
            self.logger.info(f"Found {len(existing_success_objs)} existing successful results")

        # 移动原来成功的文件
        success_filename = base_filename.replace('.jsonl', f'_success_retry_{retry_iter}.jsonl')
        success_path = os.path.join(output_path, success_filename)
        os.rename(success_output_path, success_path)
        self.logger.info(f"Moved previous success file: {success_output_path} -> {success_path}")
        
        return error_input_path, existing_success_objs, success_path
    
    async def run(self):
        """运行响应生成任务（优化版：动态任务池）"""
        # 处理重试模式
        existing_success_objs = []
        retry_iter = 1
        
        if self.retry_mode:
            base_filename = os.path.basename(self.input_path)
            # 查找重试轮数
            while True:
                retry_error_filename = base_filename.replace('.jsonl', f'_error_retry_{retry_iter}.jsonl')
                retry_error_path = os.path.join(self.output_path, retry_error_filename)
                if not os.path.exists(retry_error_path):
                    break
                retry_iter += 1
            
            retry_result = self.handle_retry_mode(self.input_path, self.output_path, retry_iter)
            if retry_result[0] is None:
                return
            
            # 重试模式下，实际读取的是error文件，但已经被重命名了
            retry_error_filename = os.path.basename(self.input_path).replace('.jsonl', f'_error_retry_{retry_iter}.jsonl')
            input_file_path = os.path.join(self.output_path, retry_error_filename)
            existing_success_objs = retry_result[1]
            self.logger.info(f"Retry mode: iteration {retry_iter}, reading from {input_file_path}")
        else:
            input_file_path = self.input_path
        
        # 读取输入数据
        if not os.path.exists(input_file_path):
            raise FileNotFoundError(f"Input file not found: {input_file_path}")
        
        objs = self.read_jsonl_file(input_file_path)
        self.logger.info(f"Loaded {len(objs)} objects from {input_file_path}")

        if not objs:
            self.logger.info("No objects to process")
            return

        # 准备任务队列，并确保每个对象都有唯一 UID
        # ⚡ 优化：UID 只计算一次并缓存到 task 字典中，避免重复计算
        task_queue = []
        uid_missing_count = 0
        for obj in objs:
            original_has_uid = 'uid' in obj or 'id' in obj
            if not original_has_uid:
                uid_missing_count += 1
            # 确保有 UID（如果没有则自动生成）并缓存
            uid = self.ensure_uid(obj)
            task_queue.append({"obj": obj, "uid": uid})  # 缓存 UID，避免重复计算
        
        if uid_missing_count > 0:
            self.logger.info(f"📋 自动为 {uid_missing_count} 个任务生成了稳定 UID")
        
        # 设置输出路径
        output_objs_path = os.path.join(self.output_path, os.path.basename(self.input_path))
        error_objs_path = os.path.join(self.output_path, os.path.basename(self.input_path).replace(".jsonl", "_error.jsonl"))
        self.logger.info(f"Output path: {output_objs_path}")
        self.logger.info(f"Error path: {error_objs_path}")
        
        # ============ 断点续传：跳过已完成的任务 ============
        if self.resume_mode and not self.retry_mode and os.path.exists(output_objs_path):
            self.logger.info("🔄 检测到断点续传模式，正在加载已完成任务...")
            
            # 读取已完成任务的 UID
            completed_uids = set()
            try:
                with jsonlines.open(output_objs_path, mode='r') as reader:
                    for obj in reader:
                        # ✅ 优先使用现有 uid，避免因为追加的 response/final_messages 影响哈希
                        uid = obj.get('uid')
                        if not uid:
                            uid = self.ensure_uid(obj)
                        completed_uids.add(uid)
                
                if completed_uids:
                    self.logger.info(f"📋 已完成任务数量: {len(completed_uids)}")
                    
                    # ⚡ 优化：使用缓存的 UID，无需重新计算（性能提升 10-100 倍）
                    original_count = len(task_queue)
                    task_queue = [
                        task for task in task_queue
                        if task['uid'] not in completed_uids  # 直接使用缓存的 UID
                    ]
                    
                    skipped_count = original_count - len(task_queue)
                    self.logger.info(f"✅ 跳过 {skipped_count} 个已完成任务")
                    self.logger.info(f"📝 剩余 {len(task_queue)} 个任务需要处理")
                    
                    if not task_queue:
                        self.logger.info("🎉 所有任务已完成，无需继续处理")
                        return
                else:
                    self.logger.info("⚠️  输出文件存在但为空，从头开始")
                    
            except Exception as e:
                self.logger.warning(f"⚠️  读取已完成任务时出错: {e}，将从头开始")
        
        # 打乱任务顺序（在过滤后）
        random.shuffle(task_queue)
        
        # 在重试模式下准备去重集合
        existing_uids_set = set()
        if self.retry_mode and existing_success_objs:
            for obj in existing_success_objs:
                uid = obj.get('uid', obj.get('id', None))
                if uid is not None:
                    existing_uids_set.add(uid)
        
        # 批量缓冲区
        buffer_output = []
        buffer_errors = []
        last_flush_time = time.monotonic()
        
        # 进度跟踪和性能统计
        total_tasks = len(task_queue)
        completed_count = 0
        success_count = 0
        error_count = 0
        start_time = time.monotonic()
        update_counter = 0  # ⚡ 优化：批量更新进度条的计数器
        update_interval = 10  # 每10个任务更新一次进度条
        
        # 创建进度条（动态显示统计信息）
        progress_bar = tqdm(
            total=total_tasks,
            desc="Processing",
            file=sys.stdout,
            ncols=120,
            leave=True,
            bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]'
        )
        
        # 启动后台写入任务与队列
        self.writer_queue = asyncio.Queue(maxsize=10)
        self.writer_task = asyncio.create_task(self.writer_loop(output_objs_path, error_objs_path))

        # ============ 核心优化：动态任务池 ============
        # 任务池大小 = concurrency * 2（平衡内存和效率）
        pool_size = self.concurrency * 2
        task_index = 0  # 当前待创建任务的索引
        pending_tasks = set()  # 飞行中的任务集合
        
        # 初始填充任务池（保存任务索引以便错误追踪）
        task_to_index = {}  # 任务 -> 索引映射
        while task_index < min(pool_size, total_tasks):
            task = asyncio.create_task(self.task_worker_async(task_queue[task_index]))
            pending_tasks.add(task)
            task_to_index[task] = task_index
            task_index += 1
        
        # 动态处理任务完成和补充
        while pending_tasks:
            # 等待任意一个任务完成
            done, pending_tasks = await asyncio.wait(
                pending_tasks, 
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # 处理完成的任务
            for task in done:
                task_idx = task_to_index.pop(task, -1)  # 获取并移除任务索引
                
                try:
                    result = task.result()  # ⚡ 优化：直接获取结果，无需 await（任务已完成）
                    
                    # 重试模式下的去重
                    if self.retry_mode:
                        uid = result.get('uid', result.get('id', None))
                        if uid is not None and uid in existing_uids_set:
                            # 跳过重复（但计入完成数）
                            pass
                        else:
                            if uid is not None:
                                existing_uids_set.add(uid)
                            buffer_output.append(result)
                            success_count += 1
                    else:
                        buffer_output.append(result)
                        success_count += 1
                        
                except Exception as e:
                    # 完整错误处理：保留原始任务数据
                    error_count += 1
                    original_task = task_queue[task_idx] if task_idx >= 0 else {}
                    # ⚡ 优化：使用浅拷贝（错误对象不需要深拷贝）
                    error_obj = original_task.get("obj", {}).copy()
                    error_obj["error"] = str(e)
                    error_obj["error_type"] = type(e).__name__
                    error_obj["traceback"] = traceback.format_exc()
                    error_obj["timestamp"] = datetime.datetime.now().isoformat()
                    error_obj["task_index"] = task_idx
                    buffer_errors.append(error_obj)
                
                completed_count += 1
                update_counter += 1
                
                # ⚡ 优化：批量更新进度条（减少开销）
                if update_counter >= update_interval:
                    elapsed_time = time.monotonic() - start_time
                    rate = completed_count / elapsed_time if elapsed_time > 0 else 0
                    progress_bar.set_description(
                        f"✅ {success_count} | ❌ {error_count} | {rate:.1f} tasks/s"
                    )
                    progress_bar.update(update_counter)
                    update_counter = 0
                
                # 立即补充新任务（如果还有）
                if task_index < total_tasks:
                    new_task = asyncio.create_task(self.task_worker_async(task_queue[task_index]))
                    pending_tasks.add(new_task)
                    task_to_index[new_task] = task_index
                    task_index += 1
            
            # 优化的批量刷新：分离批量触发和定时触发（改为后台队列写入，非阻塞）
            buffer_size = len(buffer_output) + len(buffer_errors)
            
            # 优先检查批量大小（避免不必要的时间检查）
            if buffer_size >= self.batch_size:
                await self.writer_queue.put((buffer_output.copy(), buffer_errors.copy()))
                buffer_output.clear()
                buffer_errors.clear()
                last_flush_time = time.monotonic()
            elif buffer_size > 0:
                # 只有在有数据时才检查时间
                current_time = time.monotonic()
                if current_time - last_flush_time >= self.flush_interval_secs:
                    await self.writer_queue.put((buffer_output.copy(), buffer_errors.copy()))
                    buffer_output.clear()
                    buffer_errors.clear()
                    last_flush_time = current_time
        
        # ⚡ 优化：更新剩余的进度
        if update_counter > 0:
            progress_bar.update(update_counter)
        
        # 最终刷新：将残余缓冲推送至队列
        if buffer_output or buffer_errors:
            await self.writer_queue.put((buffer_output.copy(), buffer_errors.copy()))
            buffer_output.clear()
            buffer_errors.clear()
        
        # 等待队列处理完所有写入，再优雅关闭 writer
        await self.writer_queue.join()
        await self.writer_queue.put((None, None))
        await self.writer_task

        # 关闭进度条
        progress_bar.close()
        
        # ============ Retry 模式：自动合并历史成功结果 ============
        if self.retry_mode and existing_success_objs:
            self.logger.info(f"\n🔄 Retry 模式：正在合并历史成功结果...")
            
            # 读取当前 retry 新生成的结果
            current_success = []
            if os.path.exists(output_objs_path):
                current_success = self.read_jsonl_file(output_objs_path)
            
            # 合并：历史成功 + retry 新成功
            merged_count = len(existing_success_objs) + len(current_success)
            self.logger.info(f"   历史成功: {len(existing_success_objs)} 条")
            self.logger.info(f"   Retry 新成功: {len(current_success)} 条")
            self.logger.info(f"   合并总数: {merged_count} 条")
            
            # 写入合并后的结果（覆盖模式）
            all_success = existing_success_objs + current_success
            self.write_jsonl_file(all_success, output_objs_path, chunk_size=1000, format="w")
            
            self.logger.info(f"✅ 已自动合并到: {output_objs_path}")
        
        # 统计最终结果和性能指标
        total_time = time.monotonic() - start_time
        avg_rate = completed_count / total_time if total_time > 0 else 0
        success_rate = (success_count / completed_count * 100) if completed_count > 0 else 0
        
        len_output_objs = self.count_lines_in_file(output_objs_path)
        len_error_objs = self.count_lines_in_file(error_objs_path)
        
        self.logger.info(f"\n{'='*60}")
        self.logger.info(f"📊 任务完成统计")
        self.logger.info(f"{'='*60}")
        if self.retry_mode:
            self.logger.info(f"🔄 Retry 本轮成功: {success_count} 条")
            self.logger.info(f"🔄 Retry 本轮失败: {error_count} 条")
            self.logger.info(f"📁 最终合并总数: {len_output_objs} 条")
        else:
            self.logger.info(f"✅ 成功: {success_count} 条")
            self.logger.info(f"❌ 失败: {error_count} 条")
        self.logger.info(f"📈 成功率: {success_rate:.1f}%")
        self.logger.info(f"⏱️  总耗时: {total_time:.1f}s")
        self.logger.info(f"🚀 平均速率: {avg_rate:.1f} tasks/s")
        self.logger.info(f"📁 输出文件: {output_objs_path} ({len_output_objs} 条)")
        self.logger.info(f"📁 错误文件: {error_objs_path} ({len_error_objs} 条)")
        self.logger.info(f"{'='*60}")

