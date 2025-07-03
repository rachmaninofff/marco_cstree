#!/usr/bin/env python3
"""
Utils - 统计和实用工具类

为MARCO+CS-tree算法提供统计信息收集和时间测量功能

作者: AI Assistant
日期: 2024
"""

import time
from collections import Counter, defaultdict
import threading
import types


def get_time():
    """获取当前时间"""
    return time.time()


class Statistics:
    """
    统计信息收集器
    
    支持时间测量、计数器和任意统计数据收集
    """
    
    def __init__(self):
        self._start = get_time()
        self._times = Counter()
        self._counts = Counter()
        self._stats = defaultdict(list)
        self._active_timers = {}   # dict: key=category, value=start time

    def time(self, category):
        """返回时间测量的上下文管理器"""
        return self.TimerContext(self, category)

    class TimerContext:
        """时间测量上下文管理器"""
        
        def __init__(self, stats, category):
            self._stats = stats
            self._category = category

        def __enter__(self):
            self._stats.start_time(self._category)

        def __exit__(self, ex_type, ex_value, traceback):
            self._stats.end_time(self._category)
            return False  # 不处理异常

    def increment_counter(self, category):
        """增加计数器"""
        self._counts[category] += 1

    def start_time(self, category):
        """开始计时"""
        assert category not in self._active_timers
        self.increment_counter(category)
        self._active_timers[category] = get_time()

    def end_time(self, category):
        """结束计时"""
        self.update_time(category)
        del self._active_timers[category]

    def update_time(self, category):
        """更新时间（用于正在运行的计时器）"""
        now = get_time()
        self._times[category] += now - self._active_timers[category]
        # 重置"开始时间"，因为之前的时间已经被计算了
        self._active_timers[category] = now

    def total_time(self):
        """获取总运行时间"""
        return get_time() - self._start

    def get_times(self):
        """获取所有时间统计"""
        self._times['total'] = self.total_time()
        for category in self._active_timers:
            # 如果有计时器正在运行，给它们加上到目前为止的时间
            self.update_time(category)
        return self._times

    def get_counts(self):
        """获取所有计数统计"""
        return self._counts

    def add_stat(self, name, value):
        """添加统计数据"""
        self._stats[name].append(value)

    def get_stats(self):
        """获取所有统计数据"""
        return self._stats

    def get_summary(self):
        """获取统计摘要"""
        times = self.get_times()
        counts = self.get_counts()
        
        summary = {
            'total_time': times.get('total', 0),
            'major_times': {
                'check': times.get('check', 0),
                'cs_tree_shrink': times.get('cs_tree_shrink', 0),
                'grow': times.get('grow', 0),
                'block': times.get('block', 0),
                'seed': times.get('seed', 0)
            },
            'major_counts': {
                'check': counts.get('check', 0),
                'cs_tree_shrink': counts.get('cs_tree_shrink', 0),
                'grow': counts.get('grow', 0),
                'seed': counts.get('seed', 0)
            },
            'all_times': dict(times),
            'all_counts': dict(counts),
            'all_stats': dict(self._stats)
        }
        
        return summary

    def print_summary(self):
        """打印统计摘要"""
        summary = self.get_summary()
        
        print("\n" + "=" * 50)
        print("统计摘要")
        print("=" * 50)
        
        print(f"总运行时间: {summary['total_time']:.3f} 秒")
        
        print("\n主要操作时间:")
        for name, time_val in summary['major_times'].items():
            count = summary['major_counts'].get(name, 0)
            if count > 0:
                avg_time = time_val / count
                print(f"  {name}: {time_val:.3f}s (调用{count}次, 平均{avg_time:.3f}s)")
        
        print("\n其他操作时间:")
        other_times = {k: v for k, v in summary['all_times'].items() 
                      if k not in summary['major_times'] and k != 'total'}
        for name, time_val in other_times.items():
            print(f"  {name}: {time_val:.3f}s")
        
        print("\n操作计数:")
        for name, count in summary['all_counts'].items():
            if name not in summary['major_counts']:
                print(f"  {name}: {count}")
        
        if summary['all_stats']:
            print("\n其他统计:")
            for name, values in summary['all_stats'].items():
                if isinstance(values, list) and values:
                    if all(isinstance(v, (int, float)) for v in values):
                        avg_val = sum(values) / len(values)
                        print(f"  {name}: {len(values)}个值, 平均{avg_val:.3f}")
                    else:
                        print(f"  {name}: {len(values)}个值")
        
        print("=" * 50)


def synchronize_class(sync_class):
    """
    让任何类变为线程安全（通过在每个方法调用时获取对象级锁）
    注意：这不会保护对非方法属性的访问
    
    基于: http://theorangeduck.com/page/synchronized-python
    """
    lock = threading.RLock()

    def decorator(func):
        def wrapper(*args, **kwargs):
            with lock:
                return func(*args, **kwargs)
        return wrapper

    orig_init = sync_class.__init__

    def __init__(self, *args, **kwargs):
        self.__lock__ = lock          # 不被此代码使用，但可能有用
        self.__synchronized__ = True  # 用于断言检查的标志
        orig_init(self, *args, **kwargs)

    sync_class.__init__ = __init__

    for key in dir(sync_class):
        val = getattr(sync_class, key)
        # 同步除__init__和__new__之外的所有方法
        if isinstance(val, (types.MethodType, types.FunctionType)) and key != '__init__' and key != '__new__':
            setattr(sync_class, key, decorator(val))

    return sync_class


# 测试函数
def test_statistics():
    """测试Statistics类的基本功能"""
    print("测试Statistics类...")
    
    stats = Statistics()
    
    # 测试时间测量
    with stats.time("test_operation"):
        time.sleep(0.1)
    
    # 测试计数器
    for i in range(5):
        stats.increment_counter("test_counter")
    
    # 测试统计数据
    for i in range(3):
        stats.add_stat("test_values", i * 10)
    
    # 打印结果
    print(f"Times: {dict(stats.get_times())}")
    print(f"Counts: {dict(stats.get_counts())}")
    print(f"Stats: {dict(stats.get_stats())}")
    
    stats.print_summary()
    print("Statistics 测试完成")


if __name__ == "__main__":
    test_statistics() 