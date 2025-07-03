#!/usr/bin/env python3
"""
小规模测试脚本 - 仅使用前12个意图

用于快速调试和验证核心算法的正确性。
"""
import os
import sys
import time
import json

# 假设此脚本在项目根目录下通过 python3 -m marco_cstree.test.run_12_intents_test 执行
from marco_cstree.intent_marco import IntentConflictAnalyzer

def main():
    """主测试函数"""
    print("=" * 50)
    print("运行小规模测试 (12个意图)")
    print("=" * 50)
    
    # 构造测试文件路径
    script_dir = os.path.dirname(__file__)
    intent_file_path = os.path.join(script_dir, 'test_data', 'intents_20.json')
    topology_file_path = os.path.join(script_dir, 'test_data', 'topology.json')

    # 加载意图和拓扑数据
    try:
        intents_data = []
        topology_data = {}
        with open(intent_file_path, 'r') as f:
            intents_data = json.load(f)
        with open(topology_file_path, 'r') as f:
            topology_data = json.load(f)
    except FileNotFoundError:
        print(f"错误: 意图或拓扑文件未找到。请检查路径:\n- {intent_file_path}\n- {topology_file_path}")
        return

    print(f"成功加载 {len(intents_data)} 个意图")
    print(f"成功加载网络拓扑，包含 {len(topology_data['routers'])} 个路由器，{len(topology_data['links'])} 条链路\n")

    # 使用默认配置，但关闭详细输出以保持结果清晰
    config = {
        'bias': 'MUSes',
        'timeout': 600,       # 延长超时
        'max_results': 100,
        'verbose': True,     # 开启verbose以便观察
        'maximize': False,
        'comms_ignore': False
    }

    start_time = time.time()
    # 创建分析器并执行分析
    analyzer = IntentConflictAnalyzer(
        intents_file=intent_file_path,
        topology_file=topology_file_path,
        config=config
    )
    
    results = analyzer.analyze()
    analyzer.print_detailed_results(results)
    
    # 打印统计摘要
    print("\n==================================================")
    print("统计摘要")
    print("==================================================")
    end_time = time.time()
    total_time = end_time - start_time
    print(f"总运行时间: {total_time:.3f} 秒\n")
    
    print("主要操作时间:")
    for key, val in analyzer.stats.stats.items():
        if key.startswith('time.'):
            name = key.split('.')[1]
            total = val.sum()
            count = val.count()
            avg = total / count if count > 0 else 0
            print(f"  {name}: {total:.3f}s (调用{count}次, 平均{avg:.3f}s)")

    print("\n其他操作时间:")
    for key, val in analyzer.stats.stats.items():
        if not key.startswith('time.'):
            name = key.split('.')[1] if '.' in key else key
            print(f"  {name}: {val.sum():.3f}s")
    
    print("\n操作计数:")
    for key, val in analyzer.stats.counters.items():
        print(f"  {key}: {val}")
    print("==================================================")

    print("\n小规模测试完成！")

if __name__ == "__main__":
    main() 