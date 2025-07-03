#!/usr/bin/env python3
"""
SimpleMapSolver - 简化版本的MapSolver

避免复杂的SAT求解器依赖，使用启发式方法生成种子
专门为意图冲突分析设计

作者: AI Assistant
日期: 2024
"""

import random
import itertools
from collections import deque


class SimpleMapSolver:
    """
    简化版本的MapSolver
    使用简单的启发式方法生成种子，而不依赖复杂的SAT求解器
    """
    
    def __init__(self, n, bias=True, dump=None):
        """
        初始化简化的Map求解器
        
        Args:
            n: 约束总数（在我们的情况下是意图总数）
            bias: True表示偏向MUS，False表示偏向MSS
            dump: 转储文件（暂不使用）
        """
        self.n = n
        self.bias = bias
        self.all_n = set(range(1, n + 1))
        self.dump = dump
        
        # 被阻塞的上方向和下方向的集合
        self.blocked_up = []      # 存储被阻塞的不可满足集合（MUS及其超集被阻塞）
        self.blocked_down = []    # 存储被阻塞的可满足集合（MSS及其子集被阻塞）
        
        # 种子生成状态
        self._seed_exhausted = False
        # 修改策略：总是从小的子集开始，无论bias设置如何
        self._current_size = 2  # 从2个意图的组合开始
        self._size_attempts = 0
        self._max_attempts_per_size = min(50, max(5, n))
        
    def next_seed(self):
        """获取下一个种子"""
        max_retries = 1000  # 防止无限循环
        
        for _ in range(max_retries):
            # 如果当前大小的尝试次数已经用完，切换到下一个大小
            if self._size_attempts >= self._max_attempts_per_size:
                self._current_size += 1
                if self._current_size > self.n:
                    return None
                        
                self._size_attempts = 0
                
            # 生成候选种子
            if self._current_size >= self.n:
                seed = list(self.all_n)
            elif self._current_size <= 0:
                return None
            else:
                seed = self._generate_random_subset(self._current_size)
                
            self._size_attempts += 1
            
            # 检查是否被阻塞
            if not self._is_blocked(seed):
                return seed
                
        return None
    
    def _generate_random_subset(self, size):
        """生成指定大小的随机子集"""
        if size >= self.n:
            return list(self.all_n)
        if size <= 0:
            return []
            
        # 使用不同的随机策略提高多样性
        strategy = random.choice(['random', 'sequential', 'reverse'])
        
        if strategy == 'random':
            return sorted(random.sample(list(self.all_n), size))
        elif strategy == 'sequential':
            start = random.randint(1, max(1, self.n - size + 1))
            return list(range(start, start + size))
        else:  # reverse
            end = random.randint(size, self.n)
            return list(range(end - size + 1, end + 1))
    
    def _is_blocked(self, seed):
        """检查种子是否被阻塞"""
        seed_set = set(seed)
        
        # 检查是否被上方向阻塞（即是否是某个被阻塞的不可满足集合的超集）
        for blocked_set in self.blocked_up:
            if set(blocked_set).issubset(seed_set):
                return True
                
        # 检查是否被下方向阻塞（即是否是某个被阻塞的可满足集合的子集）
        for blocked_set in self.blocked_down:
            if seed_set.issubset(set(blocked_set)):
                return True
                
        return False
    
    def block_up(self, frompoint):
        """
        向上阻塞：阻塞包含frompoint的所有超集
        用于阻塞MUS及其超集
        """
        self.blocked_up.append(list(frompoint))
        # 清理冗余的阻塞集合
        self._cleanup_blocked_up()
    
    def block_down(self, frompoint):
        """
        向下阻塞：阻塞包含在frompoint中的所有子集
        用于阻塞MSS及其子集
        """
        self.blocked_down.append(list(frompoint))
        # 清理冗余的阻塞集合
        self._cleanup_blocked_down()
    
    def _cleanup_blocked_up(self):
        """清理冗余的向上阻塞集合（保留最小的）"""
        if len(self.blocked_up) <= 1:
            return
            
        # 移除被其他集合包含的集合
        cleaned = []
        for i, set1 in enumerate(self.blocked_up):
            is_redundant = False
            for j, set2 in enumerate(self.blocked_up):
                if i != j and set(set2).issubset(set(set1)):
                    is_redundant = True
                    break
            if not is_redundant:
                cleaned.append(set1)
        self.blocked_up = cleaned
    
    def _cleanup_blocked_down(self):
        """清理冗余的向下阻塞集合（保留最大的）"""
        if len(self.blocked_down) <= 1:
            return
            
        # 移除包含其他集合的集合
        cleaned = []
        for i, set1 in enumerate(self.blocked_down):
            is_redundant = False
            for j, set2 in enumerate(self.blocked_down):
                if i != j and set(set1).issubset(set(set2)):
                    is_redundant = True
                    break
            if not is_redundant:
                cleaned.append(set1)
        self.blocked_down = cleaned
    
    def complement(self, aset):
        """返回给定集合相对于全集的补集"""
        return self.all_n.difference(set(aset))
    
    def get_stats(self):
        """获取统计信息"""
        return {
            'blocked_up_count': len(self.blocked_up),
            'blocked_down_count': len(self.blocked_down),
            'total_constraints': self.n,
            'current_size': self._current_size,
            'size_attempts': self._size_attempts
        }
    
    def reset(self):
        """重置求解器状态"""
        self.blocked_up = []
        self.blocked_down = []
        self._current_size = self.n if self.bias else 1
        self._size_attempts = 0
        self._seed_exhausted = False


# 测试函数
def test_simple_map_solver():
    """测试SimpleMapSolver的基本功能"""
    print("测试SimpleMapSolver...")
    
    # 测试基本种子生成
    solver = SimpleMapSolver(n=5, bias=True)
    
    seeds = []
    for _ in range(10):
        seed = solver.next_seed()
        if seed is None:
            break
        seeds.append(seed)
        print(f"生成种子: {seed}")
    
    print(f"共生成 {len(seeds)} 个种子")
    
    # 测试阻塞功能
    solver.block_up([1, 2])  # 阻塞包含{1,2}的所有超集
    solver.block_down([3, 4, 5])  # 阻塞{3,4,5}的所有子集
    
    print("\n阻塞后生成种子:")
    for _ in range(5):
        seed = solver.next_seed()
        if seed is None:
            break
        print(f"阻塞后种子: {seed}")
    
    print(f"统计信息: {solver.get_stats()}")
    print("SimpleMapSolver 测试完成")


if __name__ == "__main__":
    test_simple_map_solver() 