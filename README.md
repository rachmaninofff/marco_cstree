# MARCO+CS-tree 网络意图冲突分析器

基于MARCO算法和CS-tree方法的网络意图冲突分析工具，专门用于分析网络意图间的最小不可满足子集(MUS)和最大可满足子集(MSS)。

## 项目概述

本项目实现了一个专门针对网络意图冲突分析的MARCO+CS-tree算法，核心特性包括：

1. **意图级别操作**: 将原本基于约束(clauses)的MARCO算法提升到意图(intents)级别
2. **CS-tree批量枚举**: 当发现不可满足种子时，使用CS-tree算法批量枚举所有MUS
3. **Z3冲突检测**: 集成基于Z3的网络意图冲突检测逻辑
4. **多种意图类型支持**: 支持simple、path_preference、ECMP三种意图类型

## 文件结构

```
marco_cstree/
├── intent_processor.py      # 意图处理器，封装Z3冲突检测逻辑
├── intent_marco_polo.py     # 修改后的MARCO算法，支持CS-tree
├── simple_map_solver.py     # 简化的Map求解器，用于种子生成
├── utils.py                 # 统计工具类
├── intent_marco.py          # 主入口程序
├── README.md               # 本文档
└── test/                   # 测试目录
    ├── run_test.py         # 测试脚本
    └── test_data/          # 测试数据
        ├── intents.json    # 示例意图数据
        └── topology.json   # 示例网络拓扑
```

## 核心组件

### 1. IntentProcessor (intent_processor.py)
- 封装基于Z3的网络意图冲突检测逻辑
- 支持三种意图类型：simple、path_preference、ECMP
- 提供意图ID与索引的映射功能
- 核心方法：`check(intent_indices)` - 检查意图集合的可满足性

### 2. IntentMarcoPolo (intent_marco_polo.py)
- 修改后的MARCO算法，支持意图级别操作
- 实现CS-tree批量MUS枚举算法
- 核心方法：
  - `enumerate()` - 主枚举循环
  - `cs_tree_shrink()` - CS-tree批量MUS枚举
  - `_recursive_cs_tree()` - CS-tree递归实现

### 3. SimpleMapSolver (simple_map_solver.py)
- 简化版本的MapSolver，避免复杂的SAT求解器依赖
- 使用启发式方法生成种子
- 支持种子阻塞和清理功能

### 4. Statistics (utils.py)
- 统计信息收集器
- 支持时间测量、计数器和任意统计数据收集
- 提供详细的性能分析报告

## 使用方法

### 基本用法

```bash
# 基本分析
python intent_marco.py intents.json topology.json

# 指定分析偏向
python intent_marco.py intents.json topology.json --bias MUSes

# 保存结果到文件
python intent_marco.py intents.json topology.json --output results.json

# 设置超时和最大结果数
python intent_marco.py intents.json topology.json --timeout 300 --max-results 50
```

### 输入文件格式

#### 意图数据格式 (intents.json)
```json
{
  "intent_1": ["ospf", "simple", "R1", "R3", ["R1", "R2", "R3"]],
  "intent_2": ["ospf", "path_preference", "R1", "R3", ["R1", "R2", "R3"], ["R1", "R4", "R3"]],
  "intent_3": ["ospf", "ECMP", "R1", "R4", [["R1", "R2", "R4"], ["R1", "R3", "R4"]]]
}
```

意图格式说明：
- `simple`: `[protocol, type, src, dst, path]`
- `path_preference`: `[protocol, type, src, dst, primary_path, secondary_path]`
- `ECMP`: `[protocol, type, src, dst, ecmp_paths_list]`

#### 拓扑数据格式 (topology.json)
```json
{
  "routers": [
    {"name": "R1", "type": "router"},
    {"name": "R2", "type": "router"}
  ],
  "links": [
    {
      "node1": {"name": "R1"},
      "node2": {"name": "R2"},
      "weight": 1,
      "capacity": 100
    }
  ]
}
```

### 运行测试

```bash
# 运行组件测试
cd test
python run_test.py
```

## 算法原理

### MARCO算法
MARCO (MArco Reduction using COres) 是一个用于枚举MUS和MSS的算法：
1. 生成种子（约束子集）
2. 检查种子的可满足性
3. 如果可满足，扩展为MSS；如果不可满足，收缩为MUS
4. 阻塞已发现的结果，继续探索

### CS-tree批量枚举
当发现不可满足种子时，使用CS-tree算法批量枚举该种子中包含的所有MUS：
1. 递归构建搜索树
2. 使用可满足性剪枝和超集剪枝优化
3. 一次性返回所有MUS，提高效率

### 意图级别适配
- 将原本基于约束的操作提升到意图级别
- 使用IntentProcessor封装Z3冲突检测逻辑
- 建立意图ID与索引的映射关系

## 性能特点

- **批量枚举**: CS-tree能够一次性枚举多个MUS，减少冗余计算
- **智能剪枝**: 实现可满足性剪枝和超集剪枝，提高搜索效率
- **领域适配**: 专门针对网络意图冲突问题优化
- **统计分析**: 提供详细的性能统计和分析报告

## 依赖要求

- Python 3.7+
- z3-solver
- networkx
- 其他标准库

## 许可证

本项目仅供学术研究使用。

## 作者

AI Assistant - 2024 