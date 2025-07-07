#!/usr/bin/env python3
"""
小规模测试脚本 - 仅使用前12个意图

用于快速调试和验证核心算法的正确性。
修改：启用基数约束优化，获得所有最大基数的MSS。
"""
import os
import sys
import time

# 假设此脚本在项目根目录下通过 python3 -m marco_cstree.test.run_12_intents_test 执行
from marco_cstree.intent_marco import IntentConflictAnalyzer

def main():
    """主测试函数"""
    print("=" * 50)
    print("运行小规模测试 (12个意图) - 基数约束优化版本")
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

    # 启用基数约束优化的配置
    config = {
        'bias': 'MUSes',
        'timeout': 600,       
        'max_results': 100,
        'verbose': True,     
        'maximize': False,
        'comms_ignore': False,
        'enable_cardinality_optimization': True,  # 启用基数约束优化
        'max_msses_per_cardinality': float('inf') # 不限制每个基数级别的MSS数量
    }

    print(f"配置: 基数约束优化已启用")
    print(f"目标: 获得所有最大基数的MSS，不检查相似度")
    
    start_time = time.time()
    
    # 创建分析器并执行分析
    analyzer = IntentConflictAnalyzer(
        intents_file=intents_file,
        topology_file=topology_file,
        config=config
    )
    
    results = analyzer.analyze()
    
    end_time = time.time()
    total_time = end_time - start_time
    
    print(f"\n分析完成！总耗时: {total_time:.2f} 秒")
    
    # 打印结果摘要
    print("\n" + "=" * 50)
    print("12个意图测试结果摘要 (基数约束优化)")
    print("=" * 50)
    
    muses = results.get('muses', [])
    msses = results.get('msses', [])
    
    print(f"找到 {len(muses)} 个MUS (最小不可满足子集)")
    print(f"找到 {len(msses)} 个MSS (最大可满足子集)")
    
    if msses:
        print(f"\nMSS大小分布:")
        mss_sizes = {}
        for mss in msses:
            size = len(mss)
            mss_sizes[size] = mss_sizes.get(size, 0) + 1
        for size, count in sorted(mss_sizes.items(), reverse=True):
            print(f"  大小 {size}: {count} 个MSS")
        
        max_mss_size = max(len(mss) for mss in msses)
        print(f"\n最大MSS大小: {max_mss_size}")
        
        # 显示所有最大基数的MSS
        max_msses = [mss for mss in msses if len(mss) == max_mss_size]
        print(f"最大基数MSS数量: {len(max_msses)}")
        
        print(f"\n所有最大基数({max_mss_size})的MSS:")
        for i, mss in enumerate(max_msses, 1):
            print(f"  MSS{i}: {sorted(mss)}")
    
    if muses:
        print(f"\nMUS大小分布:")
        mus_sizes = {}
        for mus in muses:
            size = len(mus)
            mus_sizes[size] = mus_sizes.get(size, 0) + 1
        for size, count in sorted(mus_sizes.items()):
            print(f"  大小 {size}: {count} 个MUS")
    
    print(f"\n性能指标:")
    print(f"  分析速度: {12 / total_time:.1f} 意图/秒")
    
    # 详细结果展示
    analyzer.print_detailed_results(results)
    
    print("\n12个意图基数约束优化测试完成！")

if __name__ == "__main__":
    main() 