#!/usr/bin/env python3
"""
大规模测试脚本 - 使用 intents_100_40.json (40个意图)

测试改进的MARCO算法在较大规模意图集合上的性能和正确性。
修改：启用基数约束优化，专注于获得所有最大基数的MSS，避免组合爆炸。
"""
import os
import sys
import time

# 假设此脚本在项目根目录下通过 python3 -m marco_cstree.test.run_100_40_test 执行
from marco_cstree.intent_marco import IntentConflictAnalyzer

def main():
    """主测试函数"""
    print("=" * 70)
    print("运行大规模测试 (40个意图) - 基数约束优化版本")
    print("=" * 70)
    
    # 获取测试数据文件路径
    intents_file = "marco_cstree/test/test_data/intents_100_40.json"
    topology_file = "marco_cstree/test/test_data/topology.json"
    
    # 检查文件是否存在
    if not os.path.exists(intents_file):
        print(f"错误: 意图文件不存在: {intents_file}")
        sys.exit(1)
    
    if not os.path.exists(topology_file):
        print(f"错误: 拓扑文件不存在: {topology_file}")
        sys.exit(1)

    # 配置参数：启用基数约束优化以处理大规模问题
    config = {
        'bias': 'MUSes',
        'timeout': 1800,      # 30分钟超时
        'max_results': 10000, # 大幅增加最大结果数以容纳所有最大基数MSS
        'verbose': True,      # 保持详细输出以观察进度
        'maximize': False,
        'comms_ignore': False,
        'enable_cardinality_optimization': True,  # 启用基数约束优化
        'max_msses_per_cardinality': float('inf') # 不限制每个基数级别的MSS数量
    }

    print(f"数据集: {intents_file}")
    print(f"配置: 基数约束优化已启用")
    print(f"目标: 获得所有最大基数的MSS，避免组合爆炸")
    print(f"最大结果数: {config['max_results']}")
    print(f"超时设置: {config['timeout']}秒")
    print(f"开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    start_time = time.time()
    
    # 创建分析器并执行分析
    try:
        analyzer = IntentConflictAnalyzer(
            intents_file=intents_file,
            topology_file=topology_file,
            config=config
        )
        
        print(f"\n成功加载 {analyzer.intent_processor.total_intents} 个意图")
        print("🚀 开始大规模冲突分析 (基数约束优化模式)...")
        
        results = analyzer.analyze()
        
        end_time = time.time()
        total_time = end_time - start_time
        
        print(f"\n✅ 分析完成！总耗时: {total_time:.2f} 秒")
        
        # 打印结果摘要
        print("\n" + "=" * 70)
        print("40个意图大规模测试结果摘要 (基数约束优化)")
        print("=" * 70)
        
        muses = results.get('muses', [])
        msses = results.get('msses', [])
        
        print(f"🔍 找到 {len(muses)} 个MUS (最小不可满足子集)")
        print(f"🎯 找到 {len(msses)} 个MSS (最大可满足子集)")
        
        if muses:
            print(f"\n📊 MUS大小分布:")
            mus_sizes = {}
            for mus in muses:
                size = len(mus)
                mus_sizes[size] = mus_sizes.get(size, 0) + 1
            for size, count in sorted(mus_sizes.items()):
                print(f"  大小 {size}: {count} 个MUS")
            
            min_mus_size = min(len(mus) for mus in muses)
            max_mus_size = max(len(mus) for mus in muses)
            avg_mus_size = sum(len(mus) for mus in muses) / len(muses)
            print(f"  MUS大小范围: {min_mus_size} - {max_mus_size}, 平均: {avg_mus_size:.1f}")
        
        if msses:
            print(f"\n🎯 MSS大小分布:")
            mss_sizes = {}
            for mss in msses:
                size = len(mss)
                mss_sizes[size] = mss_sizes.get(size, 0) + 1
            for size, count in sorted(mss_sizes.items(), reverse=True):
                print(f"  大小 {size}: {count} 个MSS")
            
            max_mss_size = max(len(mss) for mss in msses)
            print(f"\n🏆 最大MSS大小: {max_mss_size}")
            
            # 显示所有最大基数的MSS
            max_msses = [mss for mss in msses if len(mss) == max_mss_size]
            print(f"🏆 最大基数MSS数量: {len(max_msses)}")
            
            # 如果最大基数MSS数量不太多，显示它们
            if len(max_msses) <= 10:
                print(f"\n所有最大基数({max_mss_size})的MSS:")
                for i, mss in enumerate(max_msses, 1):
                    print(f"  MSS{i}: {sorted(mss)}")
            else:
                print(f"\n注意: 发现 {len(max_msses)} 个最大基数MSS，仅显示前5个:")
                for i, mss in enumerate(max_msses[:5], 1):
                    print(f"  MSS{i}: {sorted(mss)}")
                print(f"  ... 还有 {len(max_msses) - 5} 个最大基数MSS")
            
            # 基数约束优化效果分析
            min_mss_size = min(len(mss) for mss in msses)
            avg_mss_size = sum(len(mss) for mss in msses) / len(msses)
            print(f"\n📈 基数约束优化效果:")
            print(f"  MSS大小范围: {min_mss_size} - {max_mss_size}")
            print(f"  平均MSS大小: {avg_mss_size:.1f}")
            print(f"  基数集中度: {len(max_msses)/len(msses)*100:.1f}% 的MSS达到最大基数")
        
        # 性能分析
        print(f"\n⚡ 性能指标:")
        print(f"  总分析时间: {total_time:.2f}秒")
        print(f"  分析速度: {40 / total_time:.1f} 意图/秒")
        if muses:
            print(f"  每个MUS发现时间: {total_time/len(muses):.3f}秒")
        if msses:
            print(f"  每个MSS发现时间: {total_time/len(msses):.3f}秒")
        
        # 与传统方法的对比估算
        if msses:
            estimated_traditional_msses = 2 ** (40 - len(muses[0]) if muses else 35)
            reduction_factor = estimated_traditional_msses / len(msses)
            print(f"\n🎯 基数约束优化收益:")
            print(f"  传统方法估算MSS数量: {estimated_traditional_msses:,}")
            print(f"  优化后实际MSS数量: {len(msses):,}")
            print(f"  复杂度降低倍数: {reduction_factor:,.0f}x")
        
        # 时间统计（如果可用）
        if hasattr(analyzer, 'stats'):
            times = analyzer.stats.get_times()
            counts = analyzer.stats.get_counts()
            
            print(f"\n🔍 详细时间分析:")
            for key, time_val in times.items():
                if key in ['check', 'divide_conquer_shrink', 'block_down', 'seed'] and time_val > 0.1:
                    count = counts.get(key, 0)
                    if count > 0:
                        avg_time = time_val / count
                        print(f"  {key}: {time_val:.2f}s (调用{count}次, 平均{avg_time:.3f}s)")
        
        # 根据结果数量决定是否显示详细信息
        if len(muses) <= 50 and len(msses) <= 20:
            print(f"\n" + "=" * 70)
            print("详细结果")
            print("=" * 70)
            analyzer.print_detailed_results(results)
        else:
            print(f"\n💡 由于找到 {len(muses)} 个MUS和 {len(msses)} 个MSS，仅显示摘要信息。")
            print("如需详细结果，请适当调整配置参数。")
        
    except Exception as e:
        print(f"❌ 分析过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    print("\n" + "=" * 70)
    print("🎉 40个意图大规模基数约束优化测试完成！")
    print("=" * 70)

if __name__ == "__main__":
    main() 