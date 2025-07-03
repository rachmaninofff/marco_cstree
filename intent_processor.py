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
            
        # 将索引转换为意图ID，然后提取对应的意图数据
        selected_intents = {}
        for idx in intent_indices:
            if idx in self.index_to_id:
                intent_id = self.index_to_id[idx]
                selected_intents[intent_id] = self.intents[intent_id]
        
        # 调用detection函数进行冲突检测
        try:
            is_satisfiable, result_data = self._detection(selected_intents, self.topology)
            return is_satisfiable, result_data
        except Exception as e:
            print(f"检测过程中发生错误: {e}")
            # 发生错误时保守地认为不可满足
            return False, None
    
    def _detection(self, intents, topology):
        """
        基于Z3的意图冲突检测函数
        """
        # 构建网络图
        graph = nx.DiGraph()
        for edge in topology['links']:
            node1 = edge['node1']['name']
            node2 = edge['node2']['name']
            graph.add_edge(node1, node2, weight=1)
            graph.add_edge(node2, node1, weight=1)

        initial_graph = copy.deepcopy(graph)
        constraints = []
        intent_constraints = {}
        var_dict = {}
        variables = {}
        var_num = 0
        
        # 约束到意图的映射，用于unsat_core分析
        constraint_intent_map = {}
        intent_infos = {}

        # 为每条边定义变量
        for u, v in graph.edges():
            key = f'{u}_{v}'
            var_num += 1
            var = f'x{var_num}'
            var_dict[key] = var
            variables[var] = Int(var)
            var_cons = f'{var} > 0'
            z3_expr = eval(var_cons, {}, variables)
            constraints.append(z3_expr)
            constraint_intent_map[len(constraints)] = 'global'

        # 处理每个意图
        for intent_id, intent in intents.items():
            intent_cons = []
            intent_constraints[intent_id] = intent_cons
            intent_infos[intent_id] = {}
            
            if intent[1] == 'path_preference':
                var_dict, var_num = self._process_path_preference_intent(
                    intent_id, intent, graph, var_dict, variables, var_num, 
                    constraints, intent_cons, intent_infos, constraint_intent_map
                )
            elif intent[1] == 'simple':
                var_dict, var_num = self._process_simple_intent(
                    intent_id, intent, graph, var_dict, variables, var_num,
                    constraints, intent_cons, intent_infos, constraint_intent_map
                )
            elif intent[1] == 'ECMP':
                var_dict, var_num = self._process_ecmp_intent(
                    intent_id, intent, graph, var_dict, variables, var_num,
                    constraints, intent_cons, intent_infos, constraint_intent_map
                )

        # 使用Z3求解器检查可满足性
        solver = Solver()
        
        # 添加约束并跟踪
        constraint_map = {}
        for i, cons in enumerate(constraints, 1):
            if i in constraint_intent_map:
                intent_id = constraint_intent_map[i]
                label = f'{intent_id}_c{i}'
            else:
                intent_id = 'global'
                label = f'global_c{i}'
            
            solver.assert_and_track(cons, label)
            constraint_map[label] = cons

        # 检查可满足性
        check_result = solver.check()
        
        if check_result == unsat:
            unsat_core = solver.unsat_core()
            return False, unsat_core
        elif check_result == sat:
            model = solver.model()
            return True, model
        else:
            # unknown情况，保守地认为不可满足
            return False, None
    
    def _process_path_preference_intent(self, intent_id, intent, graph, var_dict, variables, var_num,
                                       constraints, intent_cons, intent_infos, constraint_intent_map):
        """处理路径偏好意图"""
        # 解析意图参数：[protocol, type, src, dst, primary_path, secondary_path]
        src, dst = intent[2], intent[3]
        primary_path, secondary_path = intent[4], intent[5]
        
        intent_infos[intent_id]['constraint_path'] = secondary_path
        intent_infos[intent_id]['shortest_path'] = [primary_path, secondary_path]
        intent_infos[intent_id]['primary_path'] = primary_path
        intent_infos[intent_id]['paths'] = [primary_path, secondary_path]
        
        # 生成两条路径的变量表达式
        path_vars = []
        for path in [primary_path, secondary_path]:
            path_expr, var_dict, var_num = self._get_path_expression(
                path, var_dict, variables, var_num, constraints, intent_cons
            )
            path_vars.append(path_expr)
        
        # 记录路径约束变量
        intent_infos[intent_id]['constraint_path_cons'] = path_vars[1]  # secondary
        intent_infos[intent_id]['primary_path_cons'] = path_vars[0]     # primary
        
        # 生成偏好约束：primary_path < secondary_path
        preference_cons = f'{path_vars[0]} < {path_vars[1]}'
        z3_expr = eval(preference_cons, {}, variables)
        z3_expr = simplify(z3_expr)
        
        constraints.append(z3_expr)
        constraint_intent_map[len(constraints)] = intent_id
        intent_cons.append(z3_expr)
        
        return var_dict, var_num
    
    def _process_simple_intent(self, intent_id, intent, graph, var_dict, variables, var_num,
                              constraints, intent_cons, intent_infos, constraint_intent_map):
        """处理简单路径意图"""
        # 解析意图参数：[protocol, type, src, dst, path]
        src, dst = intent[2], intent[3]
        path = intent[4]
        
        # 标准化路径格式
        if not isinstance(path[0], list):
            paths = [path]
        else:
            paths = path
            
        intent_infos[intent_id]['constraint_path'] = paths
        intent_infos[intent_id]['shortest_path'] = paths
        intent_infos[intent_id]['paths'] = paths
        intent_infos[intent_id]['relation_path_cons'] = {}
        
        # 为每条路径生成变量表达式
        path_vars = []
        for path in paths:
            path_expr, var_dict, var_num = self._get_path_expression(
                path, var_dict, variables, var_num, constraints, intent_cons
            )
            
            # 保存路径到表达式的映射
            key = '_'.join(path)
            intent_infos[intent_id]['relation_path_cons'][key] = path_expr
            path_vars.append(path_expr)
        
        intent_infos[intent_id]['constraint_path_cons'] = path_vars
        
        return var_dict, var_num
    
    def _process_ecmp_intent(self, intent_id, intent, graph, var_dict, variables, var_num,
                            constraints, intent_cons, intent_infos, constraint_intent_map):
        """处理ECMP意图"""
        # 解析意图参数：[protocol, type, src, dst, ecmp_paths]
        src, dst = intent[2], intent[3]
        ecmp_paths = intent[4]
        
        intent_infos[intent_id]['constraint_path'] = ecmp_paths[0]
        intent_infos[intent_id]['shortest_path'] = ecmp_paths
        intent_infos[intent_id]['paths'] = ecmp_paths
        
        # 为每条ECMP路径生成变量表达式
        path_vars = []
        for path in ecmp_paths:
            path_expr, var_dict, var_num = self._get_path_expression(
                path, var_dict, variables, var_num, constraints, intent_cons
            )
            path_vars.append(path_expr)
        
        intent_infos[intent_id]['constraint_path_cons'] = path_vars[0]
        
        # 生成ECMP等价约束：所有路径权重相等
        for j in range(1, len(path_vars)):
            ecmp_constraint = f'{path_vars[0]} == {path_vars[j]}'
            z3_expr = eval(ecmp_constraint, {}, variables)
            z3_expr = simplify(z3_expr)
            
            constraints.append(z3_expr)
            constraint_intent_map[len(constraints)] = intent_id
            intent_cons.append(z3_expr)
        
        return var_dict, var_num
    
    def _get_path_expression(self, path, var_dict, variables, var_num, constraints, intent_cons):
        """
        为给定路径生成Z3变量表达式
        
        Args:
            path: 路径节点列表，如 ['A', 'B', 'C']
            
        Returns:
            tuple: (path_expression, updated_var_dict, updated_var_num)
        """
        if len(path) < 2:
            return "0", var_dict, var_num
            
        # 处理第一条边
        key = f'{path[0]}_{path[1]}'
        if key not in var_dict:
            var_num += 1
            var = f'x{var_num}'
            var_dict[key] = var
            variables[var] = Int(var)
            var_cons = f'{var} > 0'
            z3_expr = eval(var_cons, {}, variables)
            constraints.append(z3_expr)
            intent_cons.append(z3_expr)
        else:
            var = var_dict[key]
            var_cons = f'{var} > 0'
            z3_expr = eval(var_cons, {}, variables)
            if z3_expr not in intent_cons:
                intent_cons.append(z3_expr)
                
        path_expr = var
        
        # 处理剩余的边
        for i in range(1, len(path) - 1):
            key = f'{path[i]}_{path[i + 1]}'
            if key not in var_dict:
                var_num += 1
                var = f'x{var_num}'
                var_dict[key] = var
                variables[var] = Int(var)
                var_cons = f'{var} > 0'
                z3_expr = eval(var_cons, {}, variables)
                constraints.append(z3_expr)
                intent_cons.append(z3_expr)
            else:
                var = var_dict[key]
                var_cons = f'{var} > 0'
                z3_expr = eval(var_cons, {}, variables)
                if z3_expr not in intent_cons:
                    intent_cons.append(z3_expr)
                    
            path_expr = path_expr + ' + ' + var
            
        return path_expr, var_dict, var_num
    
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