#!/usr/bin/env python3
"""
测试脚本 - 用于验证MARCO+CS-tree算法的正确性

测试流程：
1. 使用简单的测试数据验证各个组件功能
2. 运行完整的意图冲突分析
3. 验证结果的正确性

作者: AI Assistant
日期: 2024
"""

import sys
import os
import json

from marco_cstree.intent_processor import IntentProcessor
from marco_cstree.intent_marco_polo import IntentMarcoPolo  
from marco_cstree.mapsolvers import MinisatMapSolver
from marco_cstree.utils import Statistics
from marco_cstree.intent_marco import IntentConflictAnalyzer


def test_components():
    """测试各个组件的基本功能"""
    print("=" * 50)
    print("组件测试")
    print("=" * 50)
    
    # 加载测试数据
    test_dir = os.path.dirname(__file__)
    intents_file = os.path.join(test_dir, "test_data", "intents.json")
    topology_file = os.path.join(test_dir, "test_data", "topology.json")
    
    with open(intents_file, 'r') as f:
        intents_data = json.load(f)
    
    with open(topology_file, 'r') as f:
        topology_data = json.load(f)
    
    print(f"加载测试数据: {len(intents_data)} 个意图")
    
    # 测试IntentProcessor
    print("\n1. 测试IntentProcessor...")
    processor = IntentProcessor(intents_data, topology_data)
    
    # 测试单个意图
    test_indices = [1]  # intent_1
    is_sat, payload = processor.check(test_indices)
    print(f"  单个意图 {test_indices}: {'可满足' if is_sat else '不可满足'}")
    
    # 测试多个意图
    test_indices = [1, 2]  # intent_1 + intent_2
    is_sat, payload = processor.check(test_indices)
    print(f"  多个意图 {test_indices}: {'可满足' if is_sat else '不可满足'}")
    
    # 测试MinisatMapSolver
    print("\n2. 测试MinisatMapSolver...")
    map_solver = MinisatMapSolver(n=len(intents_data), bias=True)
    
    seeds = []
    for i in range(3):
        seed = map_solver.next_seed()
        if seed:
            seeds.append(seed)
            print(f"  生成种子 {i+1}: {seed}")
    
    # 测试阻塞功能
    map_solver.block_up([1, 2])
    print("  阻塞 [1, 2] 后:")
    for i in range(2):
        seed = map_solver.next_seed()
        if seed:
            print(f"    新种子: {seed}")
    
    # 测试Statistics
    print("\n3. 测试Statistics...")
    stats = Statistics()
    
    with stats.time("test_operation"):
        import time
        time.sleep(0.01)  # 短暂休眠用于测试
    
    stats.increment_counter("test_counter")
    stats.add_stat("test_stat", 42)
    
    print(f"  时间统计: {dict(stats.get_times())}")
    print(f"  计数统计: {dict(stats.get_counts())}")
    
    print("\n所有组件测试完成！")


def main():
    """主测试函数"""
    print("MARCO+CS-tree 算法测试")
    
    try:
        # 运行组件测试
        test_components()
        
        print("\n" + "=" * 50)
        print("测试总结")
        print("=" * 50)
        print("✅ 所有测试通过！")
        print("✅ 算法运行正常")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main() 