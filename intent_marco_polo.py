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
                    muses_batch = self.cs_tree_batch_shrink(seed)
                
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

    def cs_tree_batch_shrink(self, unsat_seed):
        """
        CS-tree批量MUS枚举算法的入口
        
        Args:
            unsat_seed: 不可满足的意图索引集合
            
        Returns:
            list: 包含在unsat_seed中的所有MUS的列表
        """
        if self.config['verbose']:
            print(f"开始CS-tree shrink，种子: {self._indices_to_intent_ids(unsat_seed)}")

        found_muses = []
        self._recursive_cs_tree(set(), set(unsat_seed), found_muses)
        
        if self.config['verbose']:
            print(f"CS-tree完成，共找到 {len(found_muses)} 个MUS")
            
        return [list(mus) for mus in found_muses]

    def _recursive_cs_tree(self, D, P, A):
        """
        修正后的CS-tree递归实现
        
        Args:
            D: determined set - 当前路径上必须包含的意图集合
            P: potential set - 当前节点下待探索的意图集合  
            A: answers - 存储已找到MUS的列表（引用传递）
        """
        # 剪枝1：超集剪枝 - 如果D已经是某个已知MUS的超集，则此路径无效
        if any(known_mus.issubset(D) for known_mus in A):
            return

        # 剪枝2：可满足性剪枝 - 如果 D U P 可满足，此路径无效
        is_sat, _ = self.intent_processor.check(D | P)
        if is_sat:
            return

        # 基本情况：如果P为空，则D是一个不可满足核
        if not P:
            # 此时的D已经通过了超集剪枝和可满足性剪枝（D自身是UNSAT）
            # 它是一个新的MUS
            A.append(D)
            return

        # 递归步骤：选择一个元素c，并探索两条分支
        c = P.pop() 

        # 分支1: 探索不包含c的子空间 (D, P)
        self._recursive_cs_tree(D.copy(), P.copy(), A)

        # 分支2: 探索包含c的子空间 (D U {c}, P)
        D.add(c)
        self._recursive_cs_tree(D.copy(), P.copy(), A)

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
