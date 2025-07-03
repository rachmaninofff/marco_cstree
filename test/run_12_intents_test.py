#!/usr/bin/env python3
"""
小规模测试脚本 - 仅使用前12个意图

用于快速调试和验证核心算法的正确性。
"""
import os
import sys

# 假设此脚本在项目根目录下通过 python3 -m marco_cstree.test.run_12_intents_test 执行
from marco_cstree.intent_marco import IntentConflictAnalyzer

def main():
    """主测试函数"""
    print("=" * 50)
    print("运行小规模测试 (12个意图)")
    print("=" * 50)
    
    # 获取测试数据文件路径
    # 注意：路径是相对于项目根目录
    intents_file = "marco_cstree/test/test_data/intents_12.json"
    topology_file = "marco_cstree/test/test_data/topology.json"
    
    # 检查文件是否存在
    if not os.path.exists(intents_file):
        print(f"错误: 意图文件不存在: {intents_file}")
        sys.exit(1)
    
    if not os.path.exists(topology_file):
        print(f"错误: 拓扑文件不存在: {topology_file}")
        sys.exit(1)

    # 使用默认配置，但关闭详细输出以保持结果清晰
    config = {
        'bias': 'MUSes',
        'timeout': 600,       # 延长超时
        'max_results': 100,
        'verbose': True,     # 开启verbose以便观察
        'maximize': False,
        'comms_ignore': False
    }

    # 创建分析器并执行分析
    analyzer = IntentConflictAnalyzer(
        intents_file=intents_file,
        topology_file=topology_file,
        config=config
    )
    
    results = analyzer.analyze()
    analyzer.print_detailed_results(results)
    
    print("\n小规模测试完成！")

if __name__ == "__main__":
    main() 