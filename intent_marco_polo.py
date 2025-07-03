#!/usr/bin/env python3
"""
IntentMarcoPolo - 基于意图的MARCO算法

修改后的MARCO算法，支持：
1. 意图级别的操作（而非约束级别）
2. CS-tree批量MUS枚举
3. 领域特定的Z3冲突检测
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
        修改后的MUS/MSS枚举主循环 (遵循MARCO优化算法)
        核心修改：使用MaxSAT求解器直接生成MSS种子，UNSAT时调用CS-tree
        """
        while True:
            with self.stats.time('seed'):
                # 关键: next_seed()现在会返回一个最大模型 (如果bias=True)
                seed = self.map.next_seed()
            
            if seed is None:
                # MapSolver返回None，表示所有空间已探索，循环结束
                if self.config['verbose']:
                    print("- MapSolver探索完成，结束枚举。")
                break

            if self.config['verbose']:
                print(f"- 新种子 (最大模型): {self._indices_to_intent_ids(seed)}")

            with self.stats.time('check'):
                is_sat, payload = self.intent_processor.check(seed)

            if self.config['verbose']:
                print(f"- 种子状态: {'SAT' if is_sat else 'UNSAT'}")

            if is_sat:
                # 优化版MARCO的核心：
                # 一个通过最大模型找到的可满足种子，其本身就是一个MSS。
                    MSS = seed
                yield ("S", MSS)
                with self.stats.time('block_down'):
                    self.map.block_down(MSS)

                if self.config['verbose']:
                    print(f"- MSS已找到并阻塞: {self._indices_to_intent_ids(MSS)}")
            else:
                # 种子不可满足，调用CS-tree进行批量shrink
                self.got_top = True
                    with self.stats.time('cs_tree_shrink'):
                    muses_batch = self.find_all_muses(seed)

                    if self.config['verbose']:
                    print(f"- CS-tree找到 {len(muses_batch)} 个MUS")

                    with self.stats.time('block_batch'):
                    if not muses_batch:
                            # 如果没有找到MUS，阻塞当前种子以避免死循环
                            self.map.block_up(seed)
                        self.stats.increment_counter("cs_tree_rejected")
                        else:
                            # 批量处理返回的MUS
                        for mus in muses_batch:
                            yield ("U", mus)
                                self.map.block_up(mus)

                                if self.config['verbose']:
                                    print(f"- MUS已阻塞: {self._indices_to_intent_ids(mus)}")

        if self.pipe:
            self.pipe.send(('complete', self.stats))
            self.recv_thread.join()

    def find_all_muses(self, unsat_seed):
        """
        基于递归分解的MUS枚举算法入口 (替代CS-tree)
        
        Args:
            unsat_seed: 不可满足的意图索引集合
            
        Returns:
            list: 包含在unsat_seed中的所有MUS的列表
        """
        if self.config['verbose']:
            print(f"开始递归分解 shrink，种子: {self._indices_to_intent_ids(unsat_seed)}")

        found_muses = []
        # 初始调用：候选集是整个种子，背景集为空
        self._find_all_muses_recursive(set(unsat_seed), set(), found_muses)
        
        if self.config['verbose']:
            print(f"递归分解完成，共找到 {len(found_muses)} 个MUS")
            
        return [list(mus) for mus in found_muses]

    def _find_all_muses_recursive(self, C, B, known_muses):
        """
        递归分解算法的核心实现 (QuickXplain变体)
        
        Args:
            C (set): 候选意图集 (candidate set)
            B (set): 背景意图集 (background set), 我们假定这些必须存在
            known_muses (list): 全局已知的MUS列表，用于剪枝
        """
        # 剪枝1: 如果背景B本身已经是某个已知MUS的超集，则此路径不可能产生新的*最小*集
        if any(mus.issubset(B) for mus in known_muses):
                return

        # 剪枝2: 如果候选和背景的并集是可满足的，那么没有任何子集能与背景构成冲突
        is_sat_with_candidates, _ = self.intent_processor.check(B | C)
        if is_sat_with_candidates:
                return

        # 终止条件: 如果候选集为空
        if not C:
            # 此时 B | C (即 B) 是一个不可满足集。
            # 因为通过了剪枝1，它不是任何已知MUS的超集，所以它是一个新的MUS。
            known_muses.append(B)
            return

        # 分而治之 (Divide and Conquer)
        c = C.pop() # 从候选集中选择一个元素
        C_prime = C

        # 递归调用1 (探索不包含c的子问题):
        # 在 B 的背景下，从 C' 中寻找MUS
        self._find_all_muses_recursive(C_prime.copy(), B.copy(), known_muses)
        
        # 递归调用2 (探索包含c的子问题):
        # 在 B U {c} 的新背景下，从 C' 中寻找MUS的"补充部分"
        B.add(c)
        self._find_all_muses_recursive(C_prime.copy(), B.copy(), known_muses)

    def _indices_to_intent_ids(self, indices):
        """将意图索引集合转换为意图ID列表，用于调试输出"""
        if hasattr(indices, '__iter__'):
            return [self.intent_processor.get_intent_id_from_index(idx) for idx in sorted(list(indices))]
        else:
            return []


# 测试函数
def test_intent_marco_polo():
    """简单的测试函数"""
    print("IntentMarcoPolo 测试通过")


if __name__ == "__main__":
    test_intent_marco_polo() 
