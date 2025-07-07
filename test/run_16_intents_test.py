#!/usr/bin/env python3
"""
中等规模测试脚本 - 使用前16个意图

测试基数约束优化在中等规模下的效果。
修改：启用基数约束优化，获得所有最大基数的MSS。
"""
import os
import sys
import time
import json

# 假设此脚本在项目根目录下通过 python3 -m marco_cstree.test.run_16_intents_test 执行
from marco_cstree.intent_marco import IntentConflictAnalyzer

def main():
    """主测试函数"""
    print("=" * 60)
    print("运行中等规模测试 (16个意图) - 基数约束优化版本")
    print("=" * 60)
    
    # 构造测试文件路径
    script_dir = os.path.dirname(__file__)
    intent_file_path = os.path.join(script_dir, 'test_data', 'intents_16.json')
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

    # 启用基数约束优化的配置
    config = {
        'bias': 'MUSes',
        'timeout': 600,       
        'max_results': 1000,  # 增加最大结果数以容纳所有最大基数MSS
        'verbose': True,     
        'maximize': False,
        'comms_ignore': False,
        'enable_cardinality_optimization': True,  # 启用基数约束优化
        'max_msses_per_cardinality': float('inf') # 不限制每个基数级别的MSS数量
    }

    print(f"配置: 基数约束优化已启用")
    print(f"目标: 获得所有最大基数的MSS，不检查相似度")
    print(f"最大结果数: {config['max_results']}")

    start_time = time.time()
    # 创建分析器并执行分析
    analyzer = IntentConflictAnalyzer(
        intents_file=intent_file_path,
        topology_file=topology_file_path,
        config=config
    )
    
    results = analyzer.analyze()
    
    # 打印统计摘要
    print("\n==================================================")
    print("16个意图测试结果摘要 (基数约束优化)")
    print("==================================================")
    end_time = time.time()
    total_time = end_time - start_time
    print(f"总运行时间: {total_time:.3f} 秒\n")
    
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
        print(f"\n🎯 最大MSS大小: {max_mss_size}")
        
        # 显示所有最大基数的MSS
        max_msses = [mss for mss in msses if len(mss) == max_mss_size]
        print(f"🎯 最大基数MSS数量: {len(max_msses)}")
        
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
    
    # 获取时间统计
    times = analyzer.stats.get_times()
    counts = analyzer.stats.get_counts()
    
    print("\n🔍 主要操作时间:")
    for key, time_val in times.items():
        if key in ['check', 'divide_conquer_shrink', 'block_down', 'block_batch', 'seed']:
            count = counts.get(key, 0)
            if count > 0:
                avg_time = time_val / count
                print(f"  {key}: {time_val:.3f}s (调用{count}次, 平均{avg_time:.3f}s)")

    print(f"\n🎯 MUS/MSS 详细时间分析:")
    # MUS相关时间
    mus_time = times.get('divide_conquer_shrink', 0)
    mus_count = counts.get('divide_conquer_shrink', 0)
    print(f"  MUS发现时间: {mus_time:.3f}s (分而治之调用{mus_count}次)")
    
    # MSS相关时间 (主循环中的SAT种子处理)
    total_check_time = times.get('check', 0)
    total_checks = counts.get('check', 0)
    mss_count = counts.get('block_down', 0)  # MSS数量
    
    # 估算MSS处理时间 (总检查时间 - MUS分治时间)
    estimated_mss_time = max(0, total_check_time - mus_time)
    print(f"  MSS发现时间: {estimated_mss_time:.3f}s (主循环SAT种子处理)")
    print(f"  MSS数量: {mss_count}")

    print(f"\n📊 性能指标:")
    print(f"  分析速度: {16 / total_time:.1f} 意图/秒")
    print(f"  每个MUS平均时间: {mus_time/len(muses):.3f}s" if muses else "  无MUS发现")
    print(f"  每个MSS平均时间: {estimated_mss_time/len(msses):.3f}s" if msses else "  无MSS发现")

    print("\n其他操作时间:")
    other_times = {k: v for k, v in times.items() 
                  if k not in ['check', 'divide_conquer_shrink', 'block_down', 'block_batch', 'seed', 'total']}
    for key, time_val in other_times.items():
        print(f"  {key}: {time_val:.3f}s")
    
    print("\n操作计数:")
    for key, count in counts.items():
        print(f"  {key}: {count}")

    # 详细结果展示（如果不太多的话）
    if len(muses) <= 20 and len(msses) <= 20:
        print("\n" + "=" * 60)
        print("详细结果")
        print("=" * 60)
        analyzer.print_detailed_results(results)
    else:
        print(f"\n注意: 由于找到 {len(muses)} 个MUS和 {len(msses)} 个MSS，仅显示摘要信息。")

    print("==================================================")
    print("\n16个意图基数约束优化测试完成！")

if __name__ == "__main__":
    main() 