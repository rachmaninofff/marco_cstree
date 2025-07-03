# MARCO+CS-tree 网络意图冲突分析器 (重构和优化版)

基于MARCO算法和CS-tree方法的网络意图冲突分析工具，专门用于分析网络意图间的最小不可满足子集(MUS)和最大可满足子集(MSS)。本项目是基于一个初始原型的重构和优化版本，修复了核心算法的逻辑错误并显著提升了性能。

## 项目概述

本项目实现了一个专门针对网络意图冲突分析的MARCO+CS-tree算法，核心特性包括：

1.  **意图级别操作**: 将原本基于约束(clauses)的MARCO算法提升到意图(intents)级别。
2.  **CS-tree批量枚举**: 当发现不可满足种子时，使用CS-tree算法批量枚举所有MUS。
3.  **精确的冲突检测**: 采用反例驱动的迭代深化（CEGAR）模型，集成基于Z3的意图冲突检测逻辑，确保分析的正确性。
4.  **多种意图类型支持**: 支持`simple`、`path_preference`、`ECMP`三种意图类型。
5.  **高性能**: 通过结果缓存、Z3增量求解和优化的CEGAR循环，分析性能得到数量级提升。

## 文件结构

```
marco_cstree/
├── intent_processor.py      # 意图处理器，封装基于Z3的CEGAR冲突检测逻辑
├── intent_marco_polo.py     # 修改后的MARCO算法，支持CS-tree
├── intent_marco.py          # 主入口程序
├── mapsolvers.py            # MARCO的Map求解器，包含MinisatMapSolver
├── minisolvers.py           # pyminisolvers的Python接口
├── libminisat.so            # Minisat求解器动态库
├── libminicard.so           # Minicard求解器动态库 (未使用，为依赖完整性保留)
├── utils.py                 # 统计工具类
├── README.md                # 本文档
└── test/                    # 测试目录
    ├── run_test.py          # 组件测试脚本
    ├── run_12_intents_test.py # 12意图场景测试脚本
    └── test_data/           # 测试数据
        ├── intents_12.json # 12意图测试数据
        ├── topology.json    # 示例网络拓扑
```

## 核心组件

### 1. IntentProcessor (intent_processor.py)
- 封装基于Z3的网络意图冲突检测逻辑。
- **核心算法**: 采用**反例驱动的迭代深化(CEGAR)**模型。通过循环求解，不断从Z3模型中寻找反例（即不符合意图要求的最短路径），并将反例作为新约束加入求解器，直到系统收敛或发现冲突。
- **性能优化**:
  - **结果缓存**: 缓存已检查的意图子集的结果，避免在CS-tree中重复计算。
  - **增量求解**: 维护一个全局Z3求解器实例，利用`push/pop`管理上下文，极大提升了求解效率。

### 2. MinisatMapSolver (mapsolvers.py)
- MARCO算法的核心组件之一，作为"种子生成器"。
- 它使用一个真正的**SAT求解器(Minisat)**，通过添加阻塞子句来系统性、无重复地探索所有可能的意图组合，为主循环提供检查的种子。
- 已取代原版中基于启发式的`SimpleMapSolver`。

### 3. IntentMarcoPolo (intent_marco_polo.py)
- MARCO算法的主驱动逻辑，在"意图"层面进行操作。
- `enumerate()`: 主枚举循环，调用`MinisatMapSolver`生成种子，调用`IntentProcessor`检查种子。
- `cs_tree_shrink()`: 当发现不可满足的种子时，调用CS-tree算法批量枚举所有包含的MUS。

## 使用方法

### 基本用法

由于项目内部使用了相对导入，必须将其作为一个模块来运行。请使用 `python3 -m` 命令。

```bash
# 基本分析 (使用12个意图的数据集)
python3 -m marco_cstree.intent_marco marco_cstree/test/test_data/intents_12.json marco_cstree/test/test_data/topology.json

# 保存结果到文件
python3 -m marco_cstree.intent_marco <intents.json> <topology.json> --output results.json

# 指定分析偏向 (MUSes 或 MSSes)
python3 -m marco_cstree.intent_marco <intents.json> <topology.json> --bias MUSes
```

### 运行测试

```bash
# 运行12个意图的小规模集成测试
python3 -m marco_cstree.test.run_12_intents_test

# 运行原有的组件测试
python3 -m marco_cstree.test.run_test
```

## 算法原理

### MARCO算法
MARCO (MArco Reduction using COres) 是一个用于枚举MUS和MSS的算法：
1.  **生成种子**: 使用`MinisatMapSolver`生成一个尚未被探索过的意图子集。
2.  **检查种子**: 使用`IntentProcessor`检查该意图子集的可满足性。
3.  **扩展/收缩**: 如果可满足，扩展为MSS；如果不可满足，使用`cs_tree_shrink`收缩为一个或多个MUS。
4.  **阻塞**: 将发现的MSS或MUS作为阻塞子句添加到`MinisatMapSolver`中，以避免重复探索。
5.  循环直至所有组合均被探索。

### CS-tree批量枚举
当发现不可满足种子时，使用CS-tree算法批量枚举该种子中包含的所有MUS，通过递归和剪枝（可满足性剪枝、超集剪枝）来提高效率。

## 依赖要求

- Python 3.7+
- z3-solver
- networkx
- 项目已将`pyminisolvers`的编译后动态库(`libminisat.so`, `libminicard.so`)和接口文件直接包含在内，无需额外编译。

## 许可证

本项目仅供学术研究使用。

## 作者

AI Assistant (重构与优化) - 2024 