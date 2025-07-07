import json
import copy
import networkx as nx
from z3 import *

def z3_satisfication(constraints): #, var_dict
    #solver = Solver()
    opt = Optimize()
    # print('z3_satisfication')
    #print('!!! add_constraints', constraints)

    # 添加约束到求解器
    id = 1
    # for cons in constraints:
    #     solver.assert_and_track(cons, f'c{id}')
    #     if id in [129, 166]:
    #         print(f'c{id}: {cons}')
    #     id += 1
    opt.add(constraints)

    # 检查不可行性
    if opt.check() == unsat:
        #print('unsatisfiable', solver.unsat_core())
        return False, None
    else:
        return True, opt.model()


def k_shortest_paths(G, source, target, k):
    #print('all_paths', list((nx.all_shortest_paths(G, source, target, weight='weight'))))
    #return list(islice(nx.shortest_simple_paths(G, source, target, weight='weight'), k))

    all_paths = []
    #print('!!!graph', G.edges(data=True))
    shortest_path_generator = nx.shortest_simple_paths(G, source, target, weight='weight')

    for path in shortest_path_generator:
        # print('path', path)
        # print('all_paths', all_paths)
        # Calculate the weight of the current path
        # for u, v in zip(path, path[1:]):
        #     print('u', u, v, G[u][v], G[u][v].get('weight', 1))
        path_weight = sum(G[u][v].get('weight', 1) for u, v in zip(path, path[1:]))

        # If we already have k paths, check if this path's weight matches the k-th path's weight
        if len(all_paths) >= k and path_weight > all_paths[-1][1]:
            break

        # Append the path and its weight
        all_paths.append((path, path_weight))

    # Extract only the paths from the (path, weight) tuples
    #print('all_paths', all_paths)
    k_paths = [p for p, w in all_paths]
    #print('k_paths', k_paths)
    return k_paths


def get_path_expr(paths, var_dict, var_num, variables, constraints, intent_cons):
    paths_var = []
    for path in paths:
        key = f'{path[0]}_{path[1]}'
        if key not in var_dict.keys():
            var_num += 1
            var = f'x{var_num}'
            var_dict[key] = var
            variables[var] = Int(var)
            var_cons = f'{var} > 0'
            z3_expr = eval(var_cons, {}, variables)  # 将变量名替换为 Z3 变量
            constraints.append(z3_expr)
            intent_cons.append(z3_expr)
        else:
            var = var_dict[key]
            var_cons = f'{var} > 0'
            z3_expr = eval(var_cons, {}, variables)  # 将变量名替换为 Z3 变量
            if z3_expr not in intent_cons:
                intent_cons.append(z3_expr)

        path_var = var

        for i in range(1, len(path) - 1):
            key = f'{path[i]}_{path[i + 1]}'
            if key not in var_dict.keys():
                var_num += 1
                var = f'x{var_num}'
                var_dict[key] = var
                variables[var] = Int(var)
                var_cons = f'{var} > 0'
                z3_expr = eval(var_cons, {}, variables)  # 将变量名替换为 Z3 变量
                constraints.append(z3_expr)
                intent_cons.append(z3_expr)
            else:
                var = var_dict[key]
                var_cons = f'{var} > 0'
                z3_expr = eval(var_cons, {}, variables)  # 将变量名替换为 Z3 变量
                if z3_expr not in intent_cons:
                    intent_cons.append(z3_expr)

            # print('var', var, path_var)
            path_var = path_var + ' + ' + var
        paths_var.append(path_var)
    return paths_var, var_dict, var_num, variables, constraints, intent_cons


def isexistPrefer(intents):
    prefer_intents = {}
    for intent_id, intent in intents.items():
        if intent[1] == 'path_preference':
            prefer_intents[intent_id] = intent
    return prefer_intents


def detection(intents, topology):
    graph = nx.DiGraph()
    for edge in topology['links']:
        node1 = edge['node1']['name']
        node2 = edge['node2']['name']
        # print('edge', edge, node1, node2)
        graph.add_edge(node1, node2, weight=1)
        graph.add_edge(node2, node1, weight=1)

    inital_graph = copy.deepcopy(graph)
    constraints = []
    intent_constraints = {}
    intent_cons_description = {}
    var_dict = {}
    variables = {}
    var_num = 0

    intent_infos = {}

    #define a var for each edge
    #print('initial edges', graph.edges)
    for u, v in graph.edges():
        key = f'{u}_{v}'
        var_num += 1
        var = f'x{var_num}'
        var_dict[key] = var
        variables[var] = Int(var)
        var_cons = f'{var} > 0'
        z3_expr = eval(var_cons, {}, variables)  # 将变量名替换为 Z3 变量
        constraints.append(z3_expr)

    #print('var_dict', var_dict)

    for intent_id, intent in intents.items():
        intent_cons = []
        intent_cons_dcp = []
        intent_infos[intent_id] = {}
        if intent[1] == 'path_preference':
            intent_infos[intent_id]['constrant_path'] = intent[5]
            intent_infos[intent_id]['shortest_path'] = [intent[4], intent[5]]
            intent_infos[intent_id]['primary_path'] = intent[4]
            paths = [intent[4], intent[5]]
            intent_infos[intent_id]['paths'] = paths
            path_vars = []
            for path in paths:
                key = f'{path[0]}_{path[1]}'
                if key not in var_dict.keys():
                    var_num += 1
                    var = f'x{var_num}'
                    var_dict[key] = var
                    variables[var] = Int(var)
                    var_cons = f'{var} > 0'
                    z3_expr = eval(var_cons, {}, variables)  # 将变量名替换为 Z3 变量
                    constraints.append(z3_expr)
                    intent_cons.append(z3_expr)
                else:
                    var = var_dict[key]
                    var_cons = f'{var} > 0'
                    z3_expr = eval(var_cons, {}, variables)  # 将变量名替换为 Z3 变量
                    if z3_expr not in intent_cons:
                        intent_cons.append(z3_expr)

                path_var = var

                for i in range(1, len(path)-1):
                    key = f'{path[i]}_{path[i+1]}'
                    if key not in var_dict.keys():
                        var_num += 1
                        var = f'x{var_num}'
                        var_dict[key] = var
                        variables[var] = Int(var)
                        var_cons = f'{var} > 0'
                        z3_expr = eval(var_cons, {}, variables)  # 将变量名替换为 Z3 变量
                        constraints.append(z3_expr)
                        intent_cons.append(z3_expr)
                    else:
                        var = var_dict[key]
                        var_cons = f'{var} > 0'
                        z3_expr = eval(var_cons, {}, variables)  # 将变量名替换为 Z3 变量
                        if z3_expr not in intent_cons:
                            intent_cons.append(z3_expr)

                    #print('var', var, path_var)
                    path_var = path_var + ' + ' + var
                #print('final path_var', path_var)
                path_vars.append(path_var)
            #print('path_vars', path_vars)
            intent_infos[intent_id]['constraint_path_cons'] = path_vars[1]
            intent_infos[intent_id]['primary_path_cons'] = path_vars[0]
            preference_cons = f'{path_vars[0]} < {path_vars[1]}'
            intent_cons_dcp.append(preference_cons)
            # intent_infos[f'intent{k}']['intent_cons'] = preference_cons
            #print('preference_cons', preference_cons)
            # print('vars', variables)
            z3_expr = eval(preference_cons, {}, variables)  # 将变量名替换为 Z3 变量
            # z3.set_param('pp.max_lines', 1000)
            z3_expr = simplify(z3_expr)
            #print('z3_expr', z3_expr)

            constraints.append(z3_expr)
            intent_cons.append(z3_expr)
            # con_id = len(constraints)
            # cons_pris[str(con_id)] = intent_pri[f'intent{k+1}']
            #cons_intent[str(con_id)] = k
        elif intent[1] == 'ECMP':
            intent_infos[intent_id]['constrant_path'] = intent[4][0]
            intent_infos[intent_id]['shortest_path'] = intent[4]
            paths = intent[4]
            intent_infos[intent_id]['paths'] = paths
            path_vars = []
            for path in paths:
                key = f'{path[0]}_{path[1]}'
                if key not in var_dict.keys():
                    var_num += 1
                    var = f'x{var_num}'
                    var_dict[key] = var
                    variables[var] = Int(var)
                    var_cons = f'{var} > 0'
                    z3_expr = eval(var_cons, {}, variables)  # 将变量名替换为 Z3 变量
                    constraints.append(z3_expr)
                    intent_cons.append(z3_expr)
                else:
                    var = var_dict[key]
                    var_cons = f'{var} > 0'
                    z3_expr = eval(var_cons, {}, variables)  # 将变量名替换为 Z3 变量
                    if z3_expr not in intent_cons:
                        intent_cons.append(z3_expr)

                path_var = var

                for i in range(1, len(path)-1):
                    key = f'{path[i]}_{path[i+1]}'
                    if key not in var_dict.keys():
                        var_num += 1
                        var = f'x{var_num}'
                        var_dict[key] = var
                        variables[var] = Int(var)
                        var_cons = f'{var} > 0'
                        z3_expr = eval(var_cons, {}, variables)  # 将变量名替换为 Z3 变量
                        constraints.append(z3_expr)
                        intent_cons.append(z3_expr)
                    else:
                        var = var_dict[key]
                        var_cons = f'{var} > 0'
                        z3_expr = eval(var_cons, {}, variables)  # 将变量名替换为 Z3 变量
                        if z3_expr not in intent_cons:
                            intent_cons.append(z3_expr)

                    #print('var', var, path_var)
                    path_var = path_var + ' + ' + var
                #print('final path_var', path_var)
                path_vars.append(path_var)
            #print('path_vars', path_vars)
            intent_infos[intent_id]['constraint_path_cons'] = path_vars[0]
            for j in range(1, len(path_vars)):
                ecmp_one = f'{path_vars[0]} == {path_vars[j]}'
                intent_cons_dcp.append(ecmp_one)
                z3_expr = eval(ecmp_one, {}, variables)  # 将变量名替换为 Z3 变量
                z3_expr = simplify(z3_expr)
                constraints.append(z3_expr)
                intent_cons.append(z3_expr)
        elif intent[1] == 'Any_path' or intent[1] == 'any_path' or intent[1] == 'simple':
            if not isinstance(intent[4][0], list):
                intent[4] = [intent[4]]

            intent_infos[intent_id]['constrant_path'] = intent[4]
            intent_infos[intent_id]['shortest_path'] = intent[4]

            paths = intent[4]
            intent_infos[intent_id]['paths'] = paths
            path_vars = []
            intent_infos[intent_id]['relation_path_cons'] = {}
            #print('paths', paths)
            for path in paths:
                key = f'{path[0]}_{path[1]}'
                #print('!!!key', key)
                if key not in var_dict.keys():
                    var_num += 1
                    var = f'x{var_num}'
                    var_dict[key] = var
                    variables[var] = Int(var)
                    var_cons = f'{var} > 0'
                    z3_expr = eval(var_cons, {}, variables)  # 将变量名替换为 Z3 变量
                    constraints.append(z3_expr)
                    intent_cons.append(z3_expr)
                else:
                    var = var_dict[key]
                    var_cons = f'{var} > 0'
                    z3_expr = eval(var_cons, {}, variables)  # 将变量名替换为 Z3 变量
                    if z3_expr not in intent_cons:
                        intent_cons.append(z3_expr)

                path_var = var

                for i in range(1, len(path)-1):
                    key = f'{path[i]}_{path[i+1]}'
                    if key not in var_dict.keys():
                        var_num += 1
                        var = f'x{var_num}'
                        var_dict[key] = var
                        variables[var] = Int(var)
                        var_cons = f'{var} > 0'
                        z3_expr = eval(var_cons, {}, variables)  # 将变量名替换为 Z3 变量
                        constraints.append(z3_expr)
                        intent_cons.append(z3_expr)
                    else:
                        var = var_dict[key]
                        var_cons = f'{var} > 0'
                        z3_expr = eval(var_cons, {}, variables)  # 将变量名替换为 Z3 变量
                        if z3_expr not in intent_cons:
                            intent_cons.append(z3_expr)

                    #print('var', var, path_var)
                    path_var = path_var + ' + ' + var
                #print('final path_var', path_var)
                key = '_'.join(path)
                intent_infos[intent_id]['relation_path_cons'][key] = path_var
                path_vars.append(path_var)
            #print('path_vars', path_vars)
            intent_infos[intent_id]['constraint_path_cons'] = path_vars
            # for j in range(1, len(path_vars)):
            #     ecmp_one = f'{path_vars[0]} = {path_vars[j]}'
            #     intent_cons_dcp.append(ecmp_one)
            #     z3_expr = eval(ecmp_one, {}, variables)  # 将变量名替换为 Z3 变量
            #
            #     constraints.append(z3_expr)
            #     intent_cons.append(z3_expr)

        intent_constraints[intent_id] = intent_cons
        intent_cons_description[intent_id] = intent_cons_dcp

    #print('constraints', constraints)
    #print('intent cons', intent_constraints)
    #print('cons_pri', cons_pris)
    check_result, model = z3_satisfication(constraints) #, var_dict
    #print('initial check', check_result)
    # print('initial info', intent_infos)
    #print('model', model)

    #如果初始检测就是False
    if not check_result:
        return False, intent_constraints

    #print('intent constraints', intent_constraints, intent_cons_description)

    #print('var_dict', var_dict)
    removed_constraints = []
    loop = 0
    while True:
        loop += 1
        print('loops', loop)
        # intent_current_paths = {}
        shortest_paths_dict = {}
        for intent_id, intent in intents.items():
            #print('intent_id', intent_id, sat_optimal_intentCom)
            src = intent[2]
            dst = intent[3]
            #shortest_path = nx.shortest_path(graph, src, dst, weight='weight')
            unsat_shortest_paths = []
            if intent[1] == 'path_preference':
                k_num = 2
                #print('src_des', src, dst)
                k_shortestPaths = k_shortest_paths(graph, src, dst, k_num)
                #print('k_shortestPaths', k_shortestPaths, intent_infos[intent_id]['shortest_path'])
                set1 = {frozenset(sublist) for sublist in k_shortestPaths}
                set2 = {frozenset(sublist) for sublist in intent_infos[intent_id]['shortest_path']}
                # print('set1', set1)
                # print('set2', set2)
                if set1 == set2:
                    # print('!!!equal')
                    # shortest_paths_dict[intent_id] = []
                    continue
                else:
                    intersection_paths = [sublist for sublist in k_shortestPaths if
                                          sublist in intent_infos[intent_id]['shortest_path']]
                    #print('intersection_paths', intersection_paths)
                    # temp1 = set1 - intersection_paths
                    # #temp1 = [list(item) for item in temp1]
                    # print('temp1', temp1)
                    unsat_k_paths = []
                    for item in k_shortestPaths:
                        if item not in intersection_paths:
                            unsat_k_paths.append(item)
                    expr_list1, var_dict, var_num, variables, constraints, intent_constraints[
                        intent_id] = get_path_expr(unsat_k_paths, var_dict, var_num, variables, constraints,
                                                   intent_constraints[intent_id])
                    # temp2 = set2 - intersection_paths
                    # print('temp2', temp2)
                    unsat_intent_paths = intent_infos[intent_id]['shortest_path']
                    # for item in intent_infos[intent_id]['shortest_path']:
                    #     if item not in intersection_paths:
                    #         unsat_intent_paths.append(item)
                    expr_list2, var_dict, var_num, variables, constraints, intent_constraints[
                        intent_id] = get_path_expr(unsat_intent_paths, var_dict, var_num, variables, constraints,
                                                   intent_constraints[intent_id])
                    # print('unsat_k_paths', unsat_k_paths, unsat_intent_paths)
                    for e1 in expr_list2:
                        for e2 in expr_list1:
                            cons = f'{e1} < {e2}'
                            z3_expr = eval(cons, {}, variables)
                            z3_expr = simplify(z3_expr)
                            #print('z3_expr', z3_expr)
                            constraints.append(z3_expr)
                            intent_constraints[intent_id].append(z3_expr)

                    shortest_paths_dict[intent_id] = unsat_k_paths

                    # is_subset = all(sublist in intent_infos[intent_id]['shortest_path'] for sublist in k_shortestPaths)
                    # if is_subset:
                    #     for short_p in shortest_paths:
                    #         intent_infos[intent_id]['shortest_path'].remove(short_p)

                shortest_paths = nx.all_shortest_paths(graph, src, dst, weight='weight')
                shortest_paths = list(shortest_paths)
                #print('shortest_paths', shortest_paths, intent_infos[intent_id]['shortest_path'])
                if len(shortest_paths) == 1 and shortest_paths[0] == intent_infos[intent_id]['shortest_path']:
                    # print('!!!equal')
                    continue
                else:
                    temp_short_paths = []
                    for short_p in shortest_paths:
                        if short_p == intent_infos[intent_id]['shortest_path']:
                            continue
                        temp_short_paths.append(short_p)
                    unsat_shortest_paths = temp_short_paths
                shortest_paths_dict[intent_id] = unsat_shortest_paths
            elif intent[1] == 'ECMP':
                shortest_paths = nx.all_shortest_paths(graph, src, dst, weight='weight')
                shortest_paths = list(shortest_paths)
                #print(f'{intent_id} shortest_paths', shortest_paths)
                #print(intent_infos[intent_id]['shortest_path'])
                is_subset = all(sublist in intent_infos[intent_id]['shortest_path'] for sublist in shortest_paths)
                #print('----------is_subset', is_subset)
                if is_subset:
                    # print('!!!equal')
                    continue
                else:
                    temp_short_paths = []
                    for short_p in shortest_paths:
                        if short_p not in intent_infos[intent_id]['shortest_path']:
                            temp_short_paths.append(short_p)
                    unsat_shortest_paths = temp_short_paths
                shortest_paths_dict[intent_id] = unsat_shortest_paths
            elif intent[1] == 'Any_path' or intent[1] == 'any_path' or intent[1] == 'simple':
                k_num = len(intent[4])
                #print('k_num', k_num)
                #print('!!!inputgraph', graph.edges(data=True))
                k_shortestPaths = k_shortest_paths(graph, src, dst, k_num)
                #print('k_shortestPaths', k_shortestPaths, intent_infos[intent_id]['shortest_path'])
                set1 = {frozenset(sublist) for sublist in k_shortestPaths}
                set2 = {frozenset(sublist) for sublist in intent_infos[intent_id]['shortest_path']}
                #print('set1', set1, set2)
                if set1 == set2:
                    #print('!!!equal')
                    #shortest_paths_dict[intent_id] = []
                    continue
                else:
                    intersection_paths = [sublist for sublist in k_shortestPaths if sublist in intent_infos[intent_id]['shortest_path']]
                    #print('intersection_paths', intersection_paths)
                    # temp1 = set1 - intersection_paths
                    # #temp1 = [list(item) for item in temp1]
                    # print('temp1', temp1)
                    unsat_k_paths = []
                    for item in k_shortestPaths:
                        if item not in intersection_paths:
                            unsat_k_paths.append(item)
                    expr_list1, var_dict, var_num, variables, constraints, intent_constraints[intent_id] = get_path_expr(unsat_k_paths, var_dict, var_num, variables, constraints, intent_constraints[intent_id])
                    # temp2 = set2 - intersection_paths
                    # print('temp2', temp2)
                    unsat_intent_paths = intent_infos[intent_id]['shortest_path']
                    # for item in intent_infos[intent_id]['shortest_path']:
                    #     if item not in intersection_paths:
                    #         unsat_intent_paths.append(item)
                    expr_list2, var_dict, var_num, variables, constraints, intent_constraints[intent_id] = get_path_expr(unsat_intent_paths, var_dict, var_num, variables, constraints, intent_constraints[intent_id])
                    #print('unsat_k_paths', unsat_k_paths, unsat_intent_paths)
                    for e1 in expr_list2:
                        for e2 in expr_list1:
                            cons = f'{e1} < {e2}'
                            z3_expr = eval(cons, {}, variables)
                            z3_expr = simplify(z3_expr)
                            #print('z3_expr', z3_expr)
                            constraints.append(z3_expr)
                            intent_constraints[intent_id].append(z3_expr)

                    shortest_paths_dict[intent_id] = unsat_k_paths
            if intent[1] == 'ECMP':
                for shortest_path in unsat_shortest_paths:
                    key = f'{shortest_path[0]}_{shortest_path[1]}'
                    if key not in var_dict.keys():
                        var_num += 1
                        var = f'x{var_num}'
                        var_dict[key] = var
                        variables[var] = Int(var)
                        var_cons = f'{var} > 0'
                        z3_expr = eval(var_cons, {}, variables)  # 将变量名替换为 Z3 变量
                        constraints.append(z3_expr)
                        intent_constraints[intent_id].append(z3_expr)
                    else:
                        var = var_dict[key]
                        var_cons = f'{var} > 0'
                        z3_expr = eval(var_cons, {}, variables)  # 将变量名替换为 Z3 变量
                        if z3_expr not in intent_constraints[intent_id]:
                            intent_constraints[intent_id].append(z3_expr)
                    path_var = var
                    for i in range(1, len(shortest_path) - 1):
                        key = f'{shortest_path[i]}_{shortest_path[i + 1]}'
                        if key not in var_dict.keys():
                            var_num += 1
                            var = f'x{var_num}'
                            var_dict[key] = var
                            variables[var] = Int(var)
                            var_cons = f'{var} > 0'
                            z3_expr = eval(var_cons, {}, variables)  # 将变量名替换为 Z3 变量
                            constraints.append(z3_expr)
                            intent_constraints[intent_id].append(z3_expr)
                        else:
                            var = var_dict[key]
                            var_cons = f'{var} > 0'
                            z3_expr = eval(var_cons, {}, variables)  # 将变量名替换为 Z3 变量
                            if z3_expr not in intent_constraints[intent_id]:
                                intent_constraints[intent_id].append(z3_expr)
                        # print('var', var, path_var)
                        path_var = path_var + ' + ' + var
                    #print('path_var', path_var)
                    if intent[1] == 'path_preference':
                        satisfied_path_var = intent_infos[intent_id]['constraint_path_cons']
                        # intent_paths[f'intent{k}']['constraint']
                        cons = f'{satisfied_path_var} < {path_var}'
                        z3_expr = eval(cons, {}, variables)
                        z3_expr = simplify(z3_expr)
                        intent_constraints[intent_id].append(z3_expr)
                        intent_cons_description[intent_id].append(cons)
                        constraints.append(z3_expr)
                        if shortest_path == intent_infos[intent_id]['primary_path']:
                            removed_constraints.append(z3_expr)
                    elif intent[1] == 'ECMP':
                        satisfied_path_var = intent_infos[intent_id]['constraint_path_cons']
                        # intent_paths[f'intent{k}']['constraint']
                        cons = f'{satisfied_path_var} < {path_var}'
                        z3_expr = eval(cons, {}, variables)
                        z3_expr = simplify(z3_expr)
                        intent_constraints[intent_id].append(z3_expr)
                        intent_cons_description[intent_id].append(cons)
                        constraints.append(z3_expr)

                    # elif intent[1] == 'Any_path':
                    #     for satisfied_path_var in intent_infos[intent_id]['constraint_path_cons']:
                    #         cons = f'{satisfied_path_var} < {path_var}'
                    #         z3_expr = eval(cons, {}, variables)
                    #         z3_expr = simplify(z3_expr)
                    #         print('z3_expr', z3_expr)
                    #         intent_constraints[intent_id].append(z3_expr)
                    #         intent_cons_description[intent_id].append(cons)
                    #         constraints.append(z3_expr)

        if len(shortest_paths_dict.keys()) == 0:
            prefer_intents = isexistPrefer(intents)
            #print('!!!prefer_intents', prefer_intents)

            if len(prefer_intents.keys()) == 0:
                return True, intent_constraints
            else:
                #print('before preference constraints', constraints)
                negated_constraints = []
                for intent_id, intent in prefer_intents.items():
                    #print('intent_infos', intent_infos)
                    primary_cons = intent_infos[intent_id]['primary_path_cons']
                    secondary_cons = intent_infos[intent_id]['constraint_path_cons']
                    preference_cons = f'{primary_cons} < {secondary_cons}'
                    z3_expr = eval(preference_cons, {}, variables)
                    # z3.set_param('pp.max_lines', 1000)
                    z3_expr = simplify(z3_expr)
                    #print('z3_expr', z3_expr)

                    negated_constraint = (Not(z3_expr))
                    simply_negated_constraint = simplify(negated_constraint)
                    #print('negative ', Not(z3_expr))
                    constraints.append(z3_expr)
                    # if Not(z3_expr) in constraints:
                    #     constraints.remove(Not(z3_expr))

                    intent_constraints[intent_id].append(z3_expr)

                temp_cons = []
                for cons in constraints:
                    if cons in removed_constraints:
                        continue
                    else:
                        temp_cons.append(cons)
                constraints = temp_cons

                # print('removed_constraints', removed_constraints)
                #print('after preference constraints', constraints)

                check_result, model = z3_satisfication(constraints)
                #print('!!!prefer check', check_result)

                if not check_result:
                    return False, intent_constraints
                else:
                    #print('var_dict', var_dict)
                    return True, intent_constraints


        #print('number of constraints', len(constraints))
        check_result, model = z3_satisfication(constraints) #, var_dict
        #print('check_result', check_result)
        if check_result:
            tmp_graph = copy.deepcopy(inital_graph)
            #update graph
            # print('update graph', model)
            # print('var_dict', var_dict)
            modified_edge_num = 0
            for x in model:
                weight = model[x]
                #print('weight', weight, type(weight))
                #print('variables', variables)
                edge = ''
                #print('!!!var_dict', var_dict)
                for key, value in var_dict.items():
                    # print('value', type(value), type(x), type(key))
                    #print(key, str(x))
                    if value == str(x):
                        #print('equal', value, x, key)
                        edge = key
                        break
                #edge = [key for key, value in variables.items() if value == x]
                if edge == '':
                    continue
                nodes = edge.split('_')
                # print('nodes', nodes[0], nodes[1])
                # print('all nodes', tmp_graph.edges)
                tmp_graph[nodes[0]][nodes[1]]['weight'] = weight.as_long()
                if weight.as_long() != 1:
                    modified_edge_num += 1
                #tmp_graph[nodes[1]][nodes[0]]['weight'] = weight.as_long()
                #print('var', x, 'edge', edge, 'weight', weight)
            graph = tmp_graph

        else:
            return False, intent_constraints


with open('./intents_100_40.json', 'r') as f:
    intents = json.load(f)

with open("./topology.json", 'r') as f:
    topo = json.load(f)

result, cons = detection(intents, topo)
print('!!!result', result)
print('cons', cons)