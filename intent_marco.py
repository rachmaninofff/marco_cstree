#!/usr/bin/env python3
"""
IntentMarco - 基于MARCO+CS-tree的网络意图冲突分析器

这是主入口程序，整合了：
1. IntentProcessor - 基于Z3的意图冲突检测
2. IntentMarcoPolo - 修改后的MARCO算法，支持CS-tree批量MUS枚举
3. MinisatMapSolver - 基于SAT的种子生成器
"""

import sys
import json
import argparse
import os
from datetime import datetime

from .intent_processor import IntentProcessor
from .intent_marco_polo import IntentMarcoPolo
from .mapsolvers import MinisatMapSolver
from .utils import Statistics


class IntentConflictAnalyzer:
    """
    网络意图冲突分析器
    
    核心功能：
    1. 加载意图数据和网络拓扑
    2. 基于MARCO+CS-tree算法分析意图冲突
    3. 生成详细的分析报告
    """
    
    def __init__(self, intents_file, topology_file, config=None):
        """
        初始化分析器
        
        Args:
            intents_file: 意图数据文件路径
            topology_file: 网络拓扑文件路径 
            config: 配置参数字典
        """
        self.intents_file = intents_file
        self.topology_file = topology_file
        self.config = config or self._default_config()
        
        # 加载数据
        self.intents_data = self._load_intents(intents_file)
        self.topology_data = self._load_topology(topology_file)
        
        # 初始化组件
        self.intent_processor = IntentProcessor(self.intents_data, self.topology_data)
        self.map_solver = MinisatMapSolver(
            n=len(self.intents_data),
            bias=(self.config['bias'] == 'MUSes')
        )
        self.stats = Statistics()
        
        # 分析结果
        self.all_muses = []
        self.all_msses = []
        
    def _default_config(self):
        """默认配置参数"""
        return {
            'bias': 'MUSes',        # 'MUSes' 或 'MSSes'
            'maximize': False,       # 是否最大化
            'verbose': True,         # 详细输出
            'timeout': 300,          # 超时时间（秒）
            'max_results': 100,      # 最大结果数量
            'comms_ignore': False    # 忽略通信（多进程相关）
        }
    
    def _load_intents(self, filepath):
        """加载意图数据"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(f"成功加载 {len(data)} 个意图")
            return data
        except Exception as e:
            print(f"加载意图文件失败: {e}")
            sys.exit(1)
    
    def _load_topology(self, filepath):
        """加载网络拓扑数据"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(f"成功加载网络拓扑，包含 {len(data.get('routers', []))} 个路由器，{len(data.get('links', []))} 条链路")
            return data
        except Exception as e:
            print(f"加载拓扑文件失败: {e}")
            sys.exit(1)
    
    def analyze(self):
        """
        执行意图冲突分析
        
        Returns:
            dict: 分析结果，包含MUS、MSS列表和统计信息
        """
        print("\n" + "=" * 50)
        print("开始意图冲突分析")
        print("=" * 50)
        
        # 创建IntentMarcoPolo实例
        marco_polo = IntentMarcoPolo(
            intent_processor=self.intent_processor,
            map_solver=self.map_solver,
            stats=self.stats,
            config=self.config
        )
        
        # 执行枚举
        result_count = 0
        start_time = datetime.now()
        
        try:
            for result_type, result_set in marco_polo.enumerate():
                result_count += 1
                
                if result_type == 'U':  # MUS
                    self.all_muses.append(result_set)
                    intent_ids = [self.intent_processor.get_intent_id_from_index(idx) for idx in result_set]
                    if self.config['verbose']:
                        print(f"找到MUS #{len(self.all_muses)}: {intent_ids}")
                        
                elif result_type == 'S':  # MSS
                    self.all_msses.append(result_set)
                    intent_ids = [self.intent_processor.get_intent_id_from_index(idx) for idx in result_set]
                    if self.config['verbose']:
                        print(f"找到MSS #{len(self.all_msses)}: {intent_ids}")
                
                # 检查停止条件
                if result_count >= self.config['max_results']:
                    print(f"达到最大结果数量限制 ({self.config['max_results']})，停止分析")
                    break
                
                elapsed = (datetime.now() - start_time).total_seconds()
                if elapsed > self.config['timeout']:
                    print(f"达到超时限制 ({self.config['timeout']}秒)，停止分析")
                    break
                    
        except KeyboardInterrupt:
            print("\n用户中断分析")
        except Exception as e:
            print(f"\n分析过程中发生错误: {e}")
            
        print(f"\n分析完成，找到 {len(self.all_muses)} 个MUS 和 {len(self.all_msses)} 个MSS")
        
        return self._generate_results()
    
    def _generate_results(self):
        """生成分析结果"""
        results = {
            'analysis_info': {
                'total_intents': len(self.intents_data),
                'intents_file': self.intents_file,
                'topology_file': self.topology_file,
                'analysis_time': datetime.now().isoformat(),
                'config': self.config
            },
            'muses': [],
            'msses': [],
            'statistics': self.stats.get_summary()
        }
        
        # 转换MUS到意图ID格式
        for mus_indices in self.all_muses:
            mus_intent_ids = [self.intent_processor.get_intent_id_from_index(idx) for idx in mus_indices]
            mus_details = {intent_id: self.intents_data[intent_id] for intent_id in mus_intent_ids}
            results['muses'].append({
                'intent_ids': mus_intent_ids,
                'intent_details': mus_details,
                'size': len(mus_intent_ids)
            })
        
        # 转换MSS到意图ID格式
        for mss_indices in self.all_msses:
            mss_intent_ids = [self.intent_processor.get_intent_id_from_index(idx) for idx in mss_indices]
            mss_details = {intent_id: self.intents_data[intent_id] for intent_id in mss_intent_ids}
            results['msses'].append({
                'intent_ids': mss_intent_ids,
                'intent_details': mss_details,
                'size': len(mss_intent_ids)
            })
        
        return results
    
    def print_detailed_results(self, results):
        """打印详细的分析结果"""
        print("\n" + "=" * 50)
        print("详细分析结果")
        print("=" * 50)
        
        # 基本信息
        info = results['analysis_info']
        print(f"分析意图数量: {info['total_intents']}")
        print(f"意图文件: {info['intents_file']}")
        print(f"拓扑文件: {info['topology_file']}")
        print(f"分析时间: {info['analysis_time']}")
        
        # MUS结果
        print(f"\n找到 {len(results['muses'])} 个最小不可满足子集(MUS):")
        for i, mus in enumerate(results['muses'], 1):
            print(f"\nMUS #{i} (大小: {mus['size']}):")
            print(f"  意图ID: {mus['intent_ids']}")
            for intent_id in mus['intent_ids']:
                intent_data = mus['intent_details'][intent_id]
                print(f"    {intent_id}: {intent_data}")
        
        # MSS结果 
        print(f"\n找到 {len(results['msses'])} 个最大可满足子集(MSS):")
        for i, mss in enumerate(results['msses'], 1):
            print(f"\nMSS #{i} (大小: {mss['size']}):")
            print(f"  意图ID: {mss['intent_ids']}")
            # MSS通常很大，只显示数量
        
        # 统计信息
        self.stats.print_summary()
    
    def save_results(self, results, output_file):
        """保存结果到文件"""
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print(f"\n结果已保存到: {output_file}")
        except Exception as e:
            print(f"保存结果失败: {e}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='基于MARCO+CS-tree的网络意图冲突分析器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python intent_marco.py intents.json topology.json
  python intent_marco.py intents.json topology.json --bias MSSes
  python intent_marco.py intents.json topology.json --output results.json --verbose
        """
    )
    
    parser.add_argument('intents_file', help='意图数据文件路径(JSON格式)')
    parser.add_argument('topology_file', help='网络拓扑文件路径(JSON格式)')
    parser.add_argument('--bias', choices=['MUSes', 'MSSes'], default='MUSes',
                       help='分析偏向: MUSes(默认) 或 MSSes')
    parser.add_argument('--timeout', type=int, default=300,
                       help='超时时间（秒），默认300')
    parser.add_argument('--max-results', type=int, default=100,
                       help='最大结果数量，默认100')
    parser.add_argument('--output', '-o', help='输出文件路径(JSON格式)')
    parser.add_argument('--verbose', '-v', action='store_true', default=True,
                       help='详细输出（默认开启）')
    parser.add_argument('--quiet', '-q', action='store_true',
                       help='静默模式，覆盖verbose设置')
    
    args = parser.parse_args()
    
    # 检查文件是否存在
    if not os.path.exists(args.intents_file):
        print(f"错误: 意图文件不存在: {args.intents_file}")
        sys.exit(1)
    
    if not os.path.exists(args.topology_file):
        print(f"错误: 拓扑文件不存在: {args.topology_file}")
        sys.exit(1)
    
    # 配置参数
    config = {
        'bias': args.bias,
        'timeout': args.timeout,
        'max_results': args.max_results,
        'verbose': args.verbose and not args.quiet,
        'maximize': False,
        'comms_ignore': False
    }
    
    # 创建分析器并执行分析
    analyzer = IntentConflictAnalyzer(
        intents_file=args.intents_file,
        topology_file=args.topology_file,
        config=config
    )
    
    results = analyzer.analyze()
    analyzer.print_detailed_results(results)
    
    # 保存结果
    if args.output:
        analyzer.save_results(results, args.output)
    
    print("\n分析完成！")


if __name__ == "__main__":
    main() 