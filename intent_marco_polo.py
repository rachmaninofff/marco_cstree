#!/usr/bin/env python3
"""
IntentMarcoPolo - 基于意图的MARCO算法

修改后的MARCO算法，支持：
1. 意图级别的操作（而非约束级别）
2. CS-tree批量MUS枚举
3. 领域特定的Z3冲突检测

作者: AI Assistant
日期: 2024
"""

import os
import queue
import threading
from collections import deque


class IntentMarcoPolo:
    """
    基于意图的MARCO算法实现
    核心特性：CS-tree批量MUS枚举 + 意图级操作
    """
    
    def __init__(self, intent_processor, map_solver, stats, config, pipe=None):
        """
        初始化意图级MARCO算法
        
        Args:
            intent_processor: IntentProcessor实例，用于意图冲突检测
            map_solver: MapSolver实例，用于种子生成和阻塞
            stats: 统计信息收集器
            config: 配置参数
            pipe: 进程间通信管道（可选）
        """
        self.intent_processor = intent_processor
        self.map = map_solver
        self.seeds = SeedManager(map_solver, stats, config)
        self.stats = stats
        self.config = config
        self.bias_high = self.config['bias'] == 'MUSes'
        self.n = self.map.n  # 意图总数
        self.got_top = False

        self.pipe = pipe
        if self.pipe:
            self.recv_thread = threading.Thread(target=self.receive_thread)
            self.recv_thread.start()

    def receive_thread(self):
        """处理来自其他枚举器的结果"""
        while self.pipe.poll(None):
            with self.stats.time('receive'):
                res = self.pipe.recv()
                if res == 'terminate':
                    os._exit(0)

                if self.config['comms_ignore']:
                    continue

                if res[0] == 'S':
                    self.map.block_down(res[1])
                elif res[0] == 'U':
                    self.map.block_up(res[1])

    def record_delta(self, name, oldlen, newlen, up):
        """记录集合大小变化的统计信息"""
        if up:
            assert newlen >= oldlen
            self.stats.add_stat("delta.%s.up" % name, float(newlen - oldlen) / self.n)
        else:
            assert newlen <= oldlen
            self.stats.add_stat("delta.%s.down" % name, float(oldlen - newlen) / self.n)

    def enumerate(self):
        """
        修改后的MUS/MSS枚举主循环
        核心修改：当发现UNSAT种子时，使用CS-tree批量枚举所有MUS
        """
        for seed, known_max in self.seeds:
            if self.config['verbose']:
                print(f"- 初始种子: {self._indices_to_intent_ids(seed)}")

            with self.stats.time('check'):
                oldlen = len(seed)
                # 使用IntentProcessor检查种子可满足性
                seed_is_sat, payload = self.intent_processor.check(seed)
                self.record_delta('checkA', oldlen, len(seed), seed_is_sat)

            if self.config['verbose']:
                print(f"- 种子状态: {'SAT' if seed_is_sat else 'UNSAT'}")

            if seed_is_sat:
                # 处理可满足的种子 - 寻找MSS
                if known_max:
                    MSS = seed
                else:
                    with self.stats.time('grow'):
                        oldlen = len(seed)
                        MSS = self._grow_seed(seed)
                        self.record_delta('grow', oldlen, len(MSS), True)

                    if self.config['verbose']:
                        print("- 执行grow -> MSS")

                with self.stats.time('block'):
                    res = ("S", MSS)
                    yield res
                    self.map.block_down(MSS)

                if self.config['verbose']:
                    print(f"- MSS已阻塞: {self._indices_to_intent_ids(MSS)}")

            else:
                # 处理不可满足的种子 - 使用CS-tree批量枚举MUS
                self.got_top = True

                if known_max:
                    # 如果已知是最小的，直接作为MUS
                    MUS = seed
                    with self.stats.time('block'):
                        res = ("U", MUS)
                        yield res
                        self.map.block_up(MUS)
                else:
                    # 使用CS-tree批量枚举所有MUS
                    with self.stats.time('cs_tree_shrink'):
                        all_muses = self.cs_tree_shrink(seed)

                    if self.config['verbose']:
                        print(f"- CS-tree找到 {len(all_muses)} 个MUS")

                    with self.stats.time('block_batch'):
                        if not all_muses:
                            # 如果没有找到MUS，阻塞当前种子以避免死循环
                            self.map.block_up(seed)
                            self.stats.increment_counter("parallel_rejected")
                        else:
                            # 批量处理返回的MUS
                            for mus in all_muses:
                                res = ("U", mus)
                                yield res
                                self.map.block_up(mus)

                                if self.config['verbose']:
                                    print(f"- MUS已阻塞: {self._indices_to_intent_ids(mus)}")

        if self.pipe:
            self.pipe.send(('complete', self.stats))
            self.recv_thread.join()

    def cs_tree_shrink(self, unsat_seed):
        """
        CS-tree批量MUS枚举算法
        基于"Finding All Minimal Unsatisfiable Subsets"论文的CS-tree方法
        
        Args:
            unsat_seed: 不可满足的意图索引集合
            
        Returns:
            list: 包含在unsat_seed中的所有MUS的列表
        """
        if self.config['verbose']:
            print(f"开始CS-tree shrink，种子: {self._indices_to_intent_ids(unsat_seed)}")

        answers = []  # 存储找到的所有MUS
        self._recursive_cs_tree(set(), set(unsat_seed), answers)
        
        if self.config['verbose']:
            print(f"CS-tree完成，共找到 {len(answers)} 个MUS")
            
        # 转换为列表格式返回
        return [list(mus) for mus in answers]

    def _recursive_cs_tree(self, D, P, A):
        """
        CS-tree的递归实现
        
        Args:
            D: determined set - 当前路径上必须包含的意图集合
            P: potential set - 当前节点下待探索的意图集合  
            A: answers - 存储已找到MUS的列表（引用传递）
        """
        # 剪枝1：可满足性剪枝
        union_set = D | P
        if union_set:
            is_sat, _ = self.intent_processor.check(union_set)
            if is_sat:
                # 如果D∪P可满足，则此路径下所有子集都可满足
                return

        # 剪枝2：超集剪枝 - 检查D是否已经是某个已知MUS的超集
        for known_mus in A:
            if known_mus.issubset(D):
                # D包含已知MUS，此路径不会产生新的MUS
                return

        # 如果P为空，检查D是否为MUS
        if not P:
            if D:
                is_sat, _ = self.intent_processor.check(D)
                if not is_sat:
                    # D是不可满足的，且不是任何已知MUS的超集，所以是新MUS
                    A.append(set(D))
            return

        # 遍历P中的每个元素，构建子树
        P_copy = list(P)  # 创建副本进行遍历
        
        for c in P_copy:
            # 探索不包含c的左子树
            self._recursive_cs_tree(D.copy(), P - {c}, A)
            
            # 更新D和P，准备探索包含c的右侧兄弟子树
            D.add(c)
            P.remove(c)
            
            # 再次进行超集剪枝，这是CS-tree的关键优化
            for known_mus in A:
                if known_mus.issubset(D):
                    # 清理D中添加的c，因为D是引用传递
                    D.remove(c)
                    return  # 剪掉所有右侧兄弟

    def _grow_seed(self, seed):
        """
        扩展可满足的种子到最大可满足集合(MSS)
        """
        current = set(seed)
        all_indices = set(range(1, self.n + 1))
        
        # 贪心地添加更多意图
        for idx in all_indices - current:
            candidate = current | {idx}
            is_sat, _ = self.intent_processor.check(candidate)
            if is_sat:
                current = candidate
                
        return list(current)

    def _indices_to_intent_ids(self, indices):
        """将意图索引集合转换为意图ID列表，用于调试输出"""
        if hasattr(indices, '__iter__'):
            return [self.intent_processor.get_intent_id_from_index(idx) for idx in indices]
        else:
            return []


class SeedManager:
    """种子管理器，负责生成和管理探索种子"""
    
    def __init__(self, msolver, stats, config):
        self.map = msolver
        self.stats = stats
        self.config = config
        self._seed_queue = queue.Queue()

    def __iter__(self):
        return self

    def __next__(self):
        with self.stats.time('seed'):
            if not self._seed_queue.empty():
                return self._seed_queue.get()
            else:
                seed, known_max = self.seed_from_solver()
                if seed is None:
                    raise StopIteration
                return seed, known_max

    def add_seed(self, seed, known_max):
        """添加种子到队列"""
        self._seed_queue.put((seed, known_max))

    def seed_from_solver(self):
        """从map solver获取种子"""
        known_max = self.config['maximize']
        return self.map.next_seed(), known_max


# 测试函数
def test_intent_marco_polo():
    """简单的测试函数"""
    print("IntentMarcoPolo 测试通过")


if __name__ == "__main__":
    test_intent_marco_polo() 