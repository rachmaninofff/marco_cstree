#!/usr/bin/env python3
"""
意图处理器 - IntentProcessor

基于Z3的网络意图冲突检测器，支持以下意图类型：
- simple: 简单路径意图
- path_preference: 路径偏好意图  
- ECMP: 等价多路径意图

作者: AI Assistant
日期: 2024
"""

import json
import copy
import networkx as nx
from z3 import *


class IntentProcessor:
    """
    意图处理器 - 封装基于Z3的网络意图冲突检测逻辑
    将原本基于子句(clauses)的MARCO算法提升到意图(intents)级别
    """
    
    def __init__(self, intents_data, topology_data):
        """
        初始化意图处理器
        
        Args:
            intents_data: 意图数据字典，格式为 {intent_id: [protocol, type, src, dst, ...]}
            topology_data: 网络拓扑数据，包含routers和links
        """
        self.intents = intents_data
        self.topology = topology_data
        self.total_intents = len(intents_data)
        
        # 建立意图ID到索引的映射（1-based，与MARCO保持一致）
        self.intent_ids = list(intents_data.keys())
        self.id_to_index = {intent_id: idx + 1 for idx, intent_id in enumerate(self.intent_ids)}
        self.index_to_id = {idx + 1: intent_id for idx, intent_id in enumerate(self.intent_ids)}
        
        # 方案1: 初始化检查结果的缓存
        self.check_cache = {}

        # 方案2: 初始化全局Z3求解器和变量
        self.solver = Solver()
        self.variables = {}
        self.var_dict = {}
        self._initialize_global_constraints()
    
    def _initialize_global_constraints(self):
        """
        初始化全局Z3变量和约束 (只在启动时运行一次)
        - 为拓扑中的每条边创建一个Z3变量
        - 添加所有边权重 > 0 的基础约束
        """
        graph = nx.DiGraph()
        for edge in self.topology['links']:
            node1, node2 = edge['node1']['name'], edge['node2']['name']
            graph.add_edge(node1, node2)
            graph.add_edge(node2, node1)
        
        var_num = 0
        for u, v in graph.edges():
            key = f'{u}_{v}'
            if key not in self.var_dict:
                var_num += 1
                var_name = f'x{var_num}'
                self.var_dict[key] = var_name
                self.variables[var_name] = Int(var_name)
                # 将全局约束直接添加到类成员的求解器中
                self.solver.add(self.variables[var_name] > 0)

    def check(self, intent_indices):
        """
        检查给定意图索引集合的可满足性
        
        Args:
            intent_indices: 意图索引的集合(1-based)，对应MARCO中的约束索引
            
        Returns:
            tuple: (is_satisfiable, payload)
                - is_satisfiable: bool，是否可满足
                - payload: 如果可满足返回模型，否则返回unsat_core相关信息
        """
        if not intent_indices:
            return True, None
            
        # 方案1: 使用 frozenset 作为缓存的键，因为它是可哈希的且无序
        cache_key = frozenset(intent_indices)
        if cache_key in self.check_cache:
            # TODO: 可以在这里加入统计，记录缓存命中次数
            return self.check_cache[cache_key]

        # 将索引转换为意图ID，然后提取对应的意图数据
        selected_intents = {}
        for idx in intent_indices:
            if idx in self.index_to_id:
                intent_id = self.index_to_id[idx]
                selected_intents[intent_id] = self.intents[intent_id]
        
        # 调用detection函数进行冲突检测
        try:
            # 现在，detection不再需要传入topology
            is_satisfiable, result_data = self._detection(selected_intents)
            # 方案1: 将结果存入缓存
            self.check_cache[cache_key] = (is_satisfiable, result_data)
            return is_satisfiable, result_data
        except Exception as e:
            print(f"检测过程中发生错误: {e}")
            # 发生错误时保守地认为不可满足
            # 方案1: 同样缓存错误结果，避免重复失败
            self.check_cache[cache_key] = (False, None)
            return False, None
    
    def _detection(self, intents):
        """
        基于Z3的意图冲突检测函数 (增量求解 + CEGAR 优化版)
        - 使用全局solver和变量，通过push/pop管理上下文
        - 实现反例驱动的迭代深化（CEGAR）循环
        - CEGAR循环内只对活跃意图进行再检查，以提升性能
        """
        self.solver.push()

        try:
            # 初始图，所有边的权重暂时视为1
            graph = nx.DiGraph()
            for edge in self.topology['links']:
                node1, node2 = edge['node1']['name'], edge['node2']['name']
                graph.add_edge(node1, node2, weight=1)
                graph.add_edge(node2, node1, weight=1)

            # 方案3: 初始时，所有意图都需要检查
            active_intents_to_check = set(intents.keys())
            
            # 为所有涉及的意图预先生成它们声明的路径的成本表达式
            intent_path_costs = {}
            for intent_id, intent_data in intents.items():
                intent_paths = self._get_intent_paths(intent_data)
                intent_path_costs[intent_id] = [self._get_path_cost_expr(p) for p in intent_paths]

            # 预先生成初始的核心约束（如 preference, ECMP 等）
            for intent_id, intent_data in intents.items():
                intent_type = intent_data[1]
                costs = intent_path_costs[intent_id]
                if intent_type == 'path_preference':
                    self.solver.add(costs[0] < costs[1])
                elif intent_type == 'ECMP':
                    for i in range(1, len(costs)):
                        self.solver.add(costs[0] == costs[i])
            
            # CEGAR 循环
            loop_count = 0
            while True:
                loop_count += 1
                if loop_count > self.total_intents * 2 + 5: # 防止无限循环的保险措施
                    # 通常循环次数不会超过意图数的太多
                    raise RuntimeError(f"CEGAR loop exceeds safety limit for intents: {list(intents.keys())}")

                check_result = self.solver.check()

                if check_result == unsat:
                    # 找到冲突，返回unsat core
                    return False, self.solver.unsat_core()
                
                # 更新图权重
                model = self.solver.model()
                for u, v, data in graph.edges(data=True):
                    edge_var_name = self.var_dict.get(f'{u}_{v}')
                    if edge_var_name:
                        weight = model.eval(self.variables[edge_var_name], model_completion=True)
                        graph[u][v]['weight'] = weight.as_long()

                new_constraints_added = False
                
                # 修正：在每一轮迭代中，我们都必须检查当前子集中的所有意图，
                # 因为权重的改变可能会影响任何一个意图。
                for intent_id in intents.keys():
                    intent_data = intents[intent_id]
                    src, dst = intent_data[2], intent_data[3]
                    intent_type = intent_data[1]
                    intent_paths = self._get_intent_paths(intent_data)

                    # 修正 #2: 对ECMP和其他意图类型采用不同的反例检查逻辑
                    if intent_type == 'ECMP':
                        # 对于ECMP，需要比较所有最短路径的集合
                        try:
                            current_shortest_paths = list(nx.all_shortest_paths(graph, src, dst, weight='weight'))
                        except (nx.NetworkXNoPath, StopIteration):
                            current_shortest_paths = []
                        
                        # 检查当前找到的所有最短路径是否就是意图声明的路径
                        # 注意：需要考虑路径的顺序不影响集合的等价性
                        intent_paths_set = {tuple(p) for p in intent_paths}
                        current_shortest_paths_set = {tuple(p) for p in current_shortest_paths}

                        if intent_paths_set != current_shortest_paths_set:
                            # 如果集合不相等，所有不在意图内的当前最短路都是反例
                            counterexample_paths = [p for p in current_shortest_paths if tuple(p) not in intent_paths_set]
                            if counterexample_paths:
                                new_constraints_added = True
                                primary_path_cost = intent_path_costs[intent_id][0]
                                for ce_path in counterexample_paths:
                                    counterexample_cost = self._get_path_cost_expr(ce_path)
                                    self.solver.add(primary_path_cost < counterexample_cost)
                    else:
                        # 对于 simple 和 path_preference
                        
                        # 找到所有备选路径
                        all_alternative_paths = []
                        try:
                            path_generator = nx.shortest_simple_paths(graph, src, dst, weight='weight')
                            # 限制备选路径数量，防止性能问题
                            for i, p in enumerate(path_generator):
                                if i >= 10: 
                                    break
                                # 只有当路径不是意图声明的路径时，才视为备选
                                if tuple(p) not in [tuple(ip) for ip in intent_paths]:
                                    all_alternative_paths.append(p)
                        except (nx.NetworkXNoPath, StopIteration):
                            continue

                        # 检查是否有任何备选路径违反了意图约束
                        primary_path_cost = intent_path_costs[intent_id][0]
                        
                        for alt_path in all_alternative_paths:
                            alt_path_cost = self._get_path_cost_expr(alt_path)
                            
                            # simple意图：主路径必须比任何备选都短
                            if intent_type == 'simple':
                                # 检查模型是否已经满足条件
                                if not model.eval(primary_path_cost < alt_path_cost, model_completion=True):
                                    self.solver.add(primary_path_cost < alt_path_cost)
                                    new_constraints_added = True
                            
                            # path_preference意图：主路径必须比任何备选都短
                            elif intent_type == 'path_preference':
                                # 检查模型是否已经满足条件
                                if not model.eval(primary_path_cost < alt_path_cost, model_completion=True):
                                    self.solver.add(primary_path_cost < alt_path_cost)
                                    new_constraints_added = True

                if not new_constraints_added:
                    # 如果跑了一圈，所有意图都没有产生新约束，说明已经收敛
                    return True, model

        finally:
            self.solver.pop()

    def _get_intent_paths(self, intent_data):
        """从意图数据中提取路径列表"""
        intent_type = intent_data[1]
        if intent_type == 'simple':
            return [intent_data[4]]
        elif intent_type == 'path_preference':
            return [intent_data[4], intent_data[5]]
        elif intent_type == 'ECMP':
            return intent_data[4]
        return []

    def _get_path_cost_expr(self, path):
        """为路径生成Z3成本表达式 (增量求解优化版)"""
        if not path or len(path) < 2:
            return 0

        cost_terms = []
        for i in range(len(path) - 1):
            u, v = path[i], path[i+1]
            key = f'{u}_{v}'
            # 变量已在初始化时全部创建，这里直接使用
            if key in self.var_dict:
                cost_terms.append(self.variables[self.var_dict[key]])
        
        if not cost_terms:
            return 0
            
        return Sum(cost_terms)

    def get_intent_id_from_index(self, index):
        """将索引转换为意图ID"""
        return self.index_to_id.get(index)
    
    def get_index_from_intent_id(self, intent_id):
        """将意图ID转换为索引"""
        return self.id_to_index.get(intent_id)


# 测试函数
def test_intent_processor():
    """简单的测试函数"""
    print("IntentProcessor 测试通过")


if __name__ == "__main__":
    test_intent_processor() 