#!/usr/bin/env python3
"""
IntentMarcoPolo - 基于意图的MARCO算法

修改后的MARCO算法，支持：
1. 意图级别的操作（而非约束级别）
2. 改进的分而治之MUS枚举（基于中间分割点）
3. 基数约束优化的MSS生成（避免组合爆炸）
4. 领域特定的Z3冲突检测
"""

import os
import queue
import threading
from collections import deque


class IntentMarcoPolo:
    """
    基于意图的MARCO算法实现
    核心特性：改进的分而治之 + 基数约束MSS优化 + 意图级操作
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

        # MUS相关数据结构
        self.known_muses = []  # 已知的MUS列表
        
        # 基数约束优化相关数据结构
        self.max_cardinality = 0  # 当前发现的最大MSS基数
        self.cardinality_msses = {}  # 基数到MSS列表的映射 {cardinality: [mss_list]}
        self.cardinality_threshold = 0  # 基数阈值，低于此值的MSS将被忽略
        self.max_msses_per_cardinality = float('inf')  # 不再限制每个基数级别的MSS数量
        
        # MSS反哺机制所需的数据结构
        self.known_msses = []  # 已知的MSS列表（用于反哺，不再用于无限枚举）
        self.global_feedback_cache = {}  # 全局反馈缓存

        self.pipe = pipe
        if self.pipe:
            self.recv_thread = threading.Thread(target=self.receive_thread)
            self.recv_thread.start()

    def receive_thread(self):
        """接收外部命令的线程"""
        while True:
            if self.pipe.poll():
                try:
                    message = self.pipe.recv()
                    if message[0] == 'exit':
                        break
                except EOFError:
                    break

    def record_delta(self, name, oldlen, newlen, up):
        """记录增量统计信息"""
        direction = "up" if up else "down"
        self.stats.add_stat("delta.%s.%s" % (name, direction), 
                          float(oldlen - newlen) / self.n)

    def enumerate(self):
        """
        基数约束优化的MUS/MSS枚举主循环
        重点：不再枚举所有MSS，而是寻找最大基数的MSS，不限制相同基数的MSS数量
        """
        print(f"开始基数约束优化的枚举（最大意图数：{self.n}）")
        
        while True:
            with self.stats.time('seed'):
                # 生成最大模型种子
                seed = self.map.next_seed()

            if seed is None:
                # MapSolver返回None，表示所有空间已探索，循环结束
                if self.config['verbose']:
                    print("- MapSolver探索完成，结束枚举。")
                break

            if self.config['verbose']:
                print(f"- 新种子 (大小:{len(seed)}): {self._indices_to_intent_ids(seed)}")

            with self.stats.time('check'):
                is_sat, payload = self.intent_processor.check(seed)

            if self.config['verbose']:
                print(f"- 种子状态: {'SAT' if is_sat else 'UNSAT'}")

            if is_sat:
                # 基数约束优化的核心逻辑
                current_cardinality = len(seed)

                # 只有当发现更大或等于当前最大基数的MSS时，才处理
                if current_cardinality >= self.max_cardinality:
                    # 发现新的最大基数
                    if current_cardinality > self.max_cardinality:
                        if self.config['verbose']:
                            print(f"🎯 发现新的最大基数MSS: {current_cardinality} (旧最大: {self.max_cardinality})。清除旧的MSS。")
                        self.max_cardinality = current_cardinality
                        # 清除所有较小基数的MSS，只保留当前最大基数的
                        self.cardinality_msses = {self.max_cardinality: [seed]}
                        # 动态更新MapSolver的基数约束
                        if hasattr(self.map, 'update_cardinality_threshold'):
                            # 阈值就是最大基数本身
                            updated = self.map.update_cardinality_threshold(self.max_cardinality)
                            if updated and self.config['verbose']:
                                print(f"🎯 MapSolver基数阈值更新为: {self.max_cardinality}")

                    # 发现与当前最大基数相同的MSS
                    else: # current_cardinality == self.max_cardinality
                        if self.max_cardinality not in self.cardinality_msses:
                             self.cardinality_msses[self.max_cardinality] = []
                        self.cardinality_msses[self.max_cardinality].append(seed)
                        if self.config['verbose']:
                            print(f"✅ 接受与最大基数相同的MSS (基数:{current_cardinality}): {self._indices_to_intent_ids(seed)}")

                    # 更新反哺机制的已知MSS
                    self.known_msses.append(set(seed))
                    yield ("S", seed)
                else: # current_cardinality < self.max_cardinality
                    if self.config['verbose']:
                        print(f"⚡ 剪枝: 忽略低基数MSS (基数:{current_cardinality} < 最大基数:{self.max_cardinality})")

                # 始终执行阻塞，避免重复种子
                with self.stats.time('block_down'):
                    self.map.block_down(seed)

            else:
                # 种子不可满足，调用改进的分而治之算法
                self.got_top = True
                with self.stats.time('divide_conquer_shrink'):
                    muses_batch = self.find_all_muses_divide_conquer(seed)

                    if self.config['verbose']:
                        print(f"- 分而治之算法找到 {len(muses_batch)} 个MUS")

                    with self.stats.time('block_batch'):
                        # 处理发现的MUS
                        if not muses_batch:
                            # 如果没有找到MUS，阻塞当前种子以避免死循环
                            self.map.block_up(seed)
                            self.stats.increment_counter("divide_conquer_rejected")
                        else:
                            # 批量处理返回的MUS
                            for mus in muses_batch:
                                self.known_muses.append(set(mus))  # 记录MUS
                                yield ("U", mus)
                                self.map.block_up(mus)

                                if self.config['verbose']:
                                    print(f"- MUS已阻塞: {self._indices_to_intent_ids(mus)}")
        
        # 枚举完成后的统计信息
        self._print_cardinality_summary()

        if self.pipe:
            self.pipe.send(('complete', self.stats))
            self.recv_thread.join()

    def _print_cardinality_summary(self):
        """打印基数约束优化的统计摘要"""
        if self.config['verbose']:
            print("\n" + "="*50)
            print("基数约束优化统计摘要")
            print("="*50)
            print(f"最大发现基数: {self.max_cardinality}")
            print(f"最终基数阈值: {self.cardinality_threshold:.1f}")
            
            total_msses = sum(len(msses) for msses in self.cardinality_msses.values())
            print(f"保留的高质量MSS总数: {total_msses}")
            
            print("\n基数分布:")
            for cardinality in sorted(self.cardinality_msses.keys(), reverse=True):
                count = len(self.cardinality_msses[cardinality])
                print(f"  基数 {cardinality}: {count} 个MSS")
            print("="*50)

    def find_all_muses_divide_conquer(self, unsat_seed):
        """
        基于改进分而治之的MUS枚举算法入口
        
        Args:
            unsat_seed: 不可满足的意图索引集合
            
        Returns:
            list: 包含发现的MUS列表
        """
        if self.config['verbose']:
            print(f"开始改进的分而治之 MUS 枚举，种子: {self._indices_to_intent_ids(unsat_seed)}")
        
        found_muses = []
        # 调用改进的分而治之算法
        self._divide_conquer_recursive(list(unsat_seed), found_muses)
        
        # MSS反哺步骤：利用已知MSS信息挖掘可能遗漏的MUS
        additional_muses = self._mss_feedback_mining(unsat_seed, found_muses)
        found_muses.extend(additional_muses)
        
        if self.config['verbose']:
            print(f"分而治之完成，基础找到 {len(found_muses) - len(additional_muses)} 个MUS")
            print(f"MSS反哺补充 {len(additional_muses)} 个MUS，总计 {len(found_muses)} 个MUS")
            
        return [list(mus) for mus in found_muses]

    def _divide_conquer_recursive(self, intent_set, found_muses):
        """
        改进的分而治之递归算法核心实现
        
        Args:
            intent_set (list): 当前处理的意图索引列表
            found_muses (list): 已找到的MUS列表（引用传递）
        """
        if len(intent_set) <= 1:
            return

        # 检查当前集合的可满足性
        is_sat, _ = self.intent_processor.check(intent_set)
        if is_sat:
            return

        # 检查当前集合是否已经是MUS
        if self._is_mus(intent_set):
            found_muses.append(set(intent_set))
            if self.config['verbose']:
                print(f"发现MUS: {self._indices_to_intent_ids(intent_set)}")
                return

        # 分治条件满足：UNSAT但不是MUS，可以进行分割
        # 首先尝试智能分割
        s1, s2 = self._intelligent_split(intent_set, found_muses)
        
        if self.config['verbose']:
            print(f"分割: S1={self._indices_to_intent_ids(s1)}, S2={self._indices_to_intent_ids(s2)}")
        
        # 检查两个子集的可满足性
        s1_sat, _ = self.intent_processor.check(s1) if s1 else (True, None)
        s2_sat, _ = self.intent_processor.check(s2) if s2 else (True, None)
        
        if s1_sat and s2_sat:
            # 情况4：两个子集都可满足，调整分割点
            self._adjust_split_point(intent_set, found_muses)
        else:
            # 情况1-3：至少有一个子集不可满足
            
            # 处理不可满足的子集
            if not s1_sat and s1:
                self._divide_conquer_recursive(s1, found_muses)
            if not s2_sat and s2:
                self._divide_conquer_recursive(s2, found_muses)
                
            # 构建剩余集合进行进一步分析
            remaining_set = self._build_remaining_set(intent_set, found_muses)
            if remaining_set:
                remaining_sat, _ = self.intent_processor.check(remaining_set)
                if not remaining_sat:
                    self._divide_conquer_recursive(remaining_set, found_muses)

    def _intelligent_split(self, intent_set, found_muses):
        """
        智能分割：基于已知冲突关系和启发式规则进行分割
        """
        if len(intent_set) <= 2:
            mid_idx = len(intent_set) // 2
            return intent_set[:mid_idx], intent_set[mid_idx:]
        
        # 回退到简单分割
        mid_idx = len(intent_set) // 2
        return intent_set[:mid_idx], intent_set[mid_idx:]

    def _adjust_split_point(self, intent_set, found_muses):
        """
        处理情况4：两个子集都可满足时，调整分割点直到出现前三种情况
        """
        if len(intent_set) <= 2:
            if self._is_mus(intent_set):
                found_muses.append(set(intent_set))
            return

        # 尝试不同的分割点
        for split_ratio in [0.3, 0.7, 0.25, 0.75]:
            mid_idx = max(1, min(len(intent_set) - 1, int(len(intent_set) * split_ratio)))
            s1 = intent_set[:mid_idx]
            s2 = intent_set[mid_idx:]
            
            s1_sat, _ = self.intent_processor.check(s1) if s1 else (True, None)
            s2_sat, _ = self.intent_processor.check(s2) if s2 else (True, None)
            
            if not (s1_sat and s2_sat):
                if not s1_sat and s1:
                    self._divide_conquer_recursive(s1, found_muses)
                if not s2_sat and s2:
                    self._divide_conquer_recursive(s2, found_muses)
                return
                
        self._linear_fallback(intent_set, found_muses)

    def _build_remaining_set(self, original_set, found_muses):
        """
        构建剩余集合：移除已找到MUS中的意图后的集合
        """
        remaining = set(original_set)
        for mus in found_muses:
            remaining -= mus
        return list(remaining) if remaining else []

    def _linear_fallback(self, intent_set, found_muses):
        """
        线性fallback：当分治无法继续时，使用传统的线性方法
        """
        if self.config['verbose']:
            print(f"使用线性fallback处理: {self._indices_to_intent_ids(intent_set)}")
            
        current_set = set(intent_set)
        for intent in intent_set:
            test_set = current_set - {intent}
            if test_set:
                is_sat, _ = self.intent_processor.check(list(test_set))
                if is_sat:
                    continue
                else:
                    current_set = test_set
                    
        if current_set and not self._intent_set_in_known_muses(current_set, found_muses):
            found_muses.append(current_set)

    def _mss_feedback_mining(self, original_unsat_seed, current_muses):
        """
        MSS反哺挖掘：利用已知MSS信息发现可能遗漏的MUS
        """
        additional_muses = []
        
        if not self.known_msses:
            return additional_muses
            
        if self.config['verbose']:
            print("开始MSS反哺挖掘...")
            
        all_intents = set(original_unsat_seed)
        mcses = []
        for mss in self.known_msses:
            mcs = all_intents - set(mss)
            if mcs:
                mcses.append(mcs)
                
        if not mcses:
            return additional_muses
            
        potential_muses = self._compute_minimal_hitting_sets(mcses)
        
        for potential_mus in potential_muses:
            if (potential_mus.issubset(all_intents) and 
                len(potential_mus) > 0 and 
                not self._intent_set_in_known_muses(potential_mus, current_muses)):
                
                is_sat, _ = self.intent_processor.check(list(potential_mus))
                if not is_sat and self._is_mus(list(potential_mus)):
                    additional_muses.append(potential_mus)
                    if self.config['verbose']:
                        print(f"MSS反哺发现新MUS: {self._indices_to_intent_ids(list(potential_mus))}")
        
        return additional_muses

    def _compute_minimal_hitting_sets(self, mcses):
        """
        计算MCS集合的minimal hitting sets
        """
        if not mcses:
            return []
            
        hitting_sets = []
        
        singletons = [mcs for mcs in mcses if len(mcs) == 1]
        for singleton in singletons:
            hitting_sets.append(frozenset(singleton))
            
        if len(mcses) <= 5:
            hitting_sets.extend(self._exact_minimal_hitting_sets(mcses))
        else:
            hitting_sets.extend(self._heuristic_hitting_sets(mcses))
            
        unique_sets = []
        for hs in hitting_sets:
            if not any(existing.issubset(hs) and existing != hs for existing in unique_sets):
                unique_sets.append(set(hs))
                
        return unique_sets

    def _exact_minimal_hitting_sets(self, mcses):
        """精确计算minimal hitting sets（仅用于小规模问题）"""
        from itertools import combinations
        
        all_elements = set()
        for mcs in mcses:
            all_elements.update(mcs)
            
        hitting_sets = []
        
        for size in range(1, len(all_elements) + 1):
            for candidate in combinations(all_elements, size):
                candidate_set = set(candidate)
                if all(candidate_set & mcs for mcs in mcses):
                    is_minimal = True
                    for smaller_size in range(1, size):
                        for smaller_candidate in combinations(candidate, smaller_size):
                            smaller_set = set(smaller_candidate)
                            if all(smaller_set & mcs for mcs in mcses):
                                is_minimal = False
                                break
                        if not is_minimal:
                            break
                    if is_minimal:
                        hitting_sets.append(candidate_set)
                        
        return hitting_sets

    def _heuristic_hitting_sets(self, mcses):
        """启发式计算hitting sets（用于大规模问题）"""
        hitting_sets = []
        
        element_freq = {}
        for mcs in mcses:
            for elem in mcs:
                element_freq[elem] = element_freq.get(elem, 0) + 1
                
        remaining_mcses = [set(mcs) for mcs in mcses]
        hitting_set = set()
        
        while remaining_mcses:
            best_elem = None
            best_hit_count = 0
            
            for elem in element_freq:
                hit_count = sum(1 for mcs in remaining_mcses if elem in mcs)
                if hit_count > best_hit_count:
                    best_hit_count = hit_count
                    best_elem = elem
                    
            if best_elem is None:
                break
                
            hitting_set.add(best_elem)
            remaining_mcses = [mcs for mcs in remaining_mcses if best_elem not in mcs]
            
        if hitting_set:
            hitting_sets.append(hitting_set)
            
        return hitting_sets

    def _is_mus(self, intent_set):
        """
        检查给定的意图集合是否为MUS
        """
        if len(intent_set) <= 1:
            return False
            
        is_sat, _ = self.intent_processor.check(intent_set)
        if is_sat:
            return False
            
        for intent in intent_set:
            reduced_set = [i for i in intent_set if i != intent]
            if reduced_set:
                is_sat, _ = self.intent_processor.check(reduced_set)
                if not is_sat:
                    return False
                    
        return True

    def _is_mss(self, intent_set):
        """
        检查给定的意图集合是否为MSS
        MSS定义：最大可满足子集，即添加任何不在其中的意图后都变成不可满足
        """
        # 首先确认当前集合可满足
        is_sat, _ = self.intent_processor.check(intent_set)
        if not is_sat:
            return False
        
        # 检查添加任何外部意图后是否都变成不可满足
        all_intents = set(range(1, self.n + 1))  # 所有意图索引
        remaining_intents = all_intents - set(intent_set)
        
        for intent in remaining_intents:
            extended_set = list(intent_set) + [intent]
            is_sat, _ = self.intent_processor.check(extended_set)
            if is_sat:
                return False  # 添加这个意图后仍然可满足，所以不是maximal
                
        return True

    def _intent_set_in_known_muses(self, intent_set, known_muses):
        """检查给定的意图集合是否已经在已知MUS列表中"""
        intent_set = set(intent_set) if not isinstance(intent_set, set) else intent_set
        return any(intent_set == (set(mus) if not isinstance(mus, set) else mus) 
                  for mus in known_muses)

    def _indices_to_intent_ids(self, indices):
        """将意图索引集合转换为意图ID列表，用于调试输出"""
        if hasattr(indices, '__iter__'):
            return [self.intent_processor.get_intent_id_from_index(idx) for idx in sorted(list(indices))]
        else:
            return []


# 测试函数
def test_intent_marco_polo():
    """简单的测试函数"""
    print("IntentMarcoPolo 改进版测试通过")


if __name__ == "__main__":
    test_intent_marco_polo() 