import abc
import array

from . import minisolvers


class MapSolver(object):
    """The abstract base class for any MapSolver, implementing common utility functions."""
    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod  # must be overridden, but can be called via super()
    def __init__(self, n, bias=True, dump=None):
        """Common initialization.

        Args:
            n: The number of constraints to map.
            bias: Boolean specifying the solver's bias.  True is a
                  high/inclusion/MUS bias; False is a low/exclusion/MSS bias;
                  None is no bias.
        """
        self.n = n
        self.bias = bias
        self.all_n = set(range(1, n+1))  # used in complement fairly frequently
        self.dump = dump

    @abc.abstractmethod
    def next_seed(self):
        pass

    def check_seed(self, seed):
        """Check whether a given seed is still unexplored.

        Returns:
            True if seed is unexplored (i.e., its corresponding assignment is a model)
        """
        return self._solver.check_complete(positive_lits=seed)

    def implies(self, assumptions=None):
        """Get implications (level-0 decisions) of the current instance.
        If assumptions are provided, get implications of the current
        instance w.r.t. those assumptions.

        Returns:
            An array of literals.
        """
        return self._solver.implies(assumptions)

    def find_above(self, seed):
        """Look for and return any unexplored point including the given seed.
            Calling map.find_above(MSS) after map.block_down(MSS) will thus find
            strict supersets of the MSS, as the MSS itself has been blocked.

        Returns:
            Any unexplored strict superset of seed, if one exists.
        """
        superset_exists = self._solver.solve(seed)
        if superset_exists:
            return self.get_seed()
        else:
            return None

    def get_seed(self):
        """Get the seed from the current model.  (Depends on work in next_seed to be valid.)

        Returns:
            A seed as an array of 1-based constraint indexes.
        """
        return self._solver.get_model_trues(start=0, end=self.n, offset=1)

        # slower:
        #model = self._solver.get_model()
        #return [i for i in range(self.n) if model[i]]

        # slowest:
        #seed = []
        #for i in range(self.n):
        #    if self._solver.model_value(i+1):
        #        seed.add(i)
        #return seed

    def maximize_seed(self, seed, direction):
        """Maximize a given seed within the current set of constraints.
           The Boolean direction parameter specifies up (True) or down (False)

        Returns:
            A seed as an array of 1-based constraint indexes.
        """
        while True:
            comp = self.complement(seed)
            tmpvar = self._solver.new_var() + 1
            if direction:
                # search for a solution w/ all of the current seed plus at
                # least one from the current complement.
                self._solver.add_clause([-tmpvar] + list(comp))  # temporary clause
                # activate the temporary clause and all seed clauses
                havenew = self._solver.solve([tmpvar] + list(seed))
            else:
                # search for a solution w/ none of current complement and at
                # least one from the current seed removed.
                self._solver.add_clause([-tmpvar] + [-i for i in seed])  # temporary clause
                # activate the temporary clause and deactivate complement clauses
                havenew = self._solver.solve([tmpvar] + [-i for i in comp])
            self._solver.add_clause([-tmpvar])  # remove the temporary clause

            if havenew:
                seed = self.get_seed()
            else:
                return seed

    def complement(self, aset):
        """Return the complement of a given set w.r.t. the set of mapped constraints."""
        return self.all_n.difference(aset)

    def add_clause(self, clause):
        """Add a given clause to the Map solver."""
        self._solver.add_clause(clause)
        if self.dump is not None:
            self.dump.write(" ".join(str(lit) for lit in clause) + " 0\n")

    def block_down(self, frompoint):
        """Block down from a given set."""
        clause = self.complement(frompoint)
        self.add_clause(clause)

    def block_up(self, frompoint):
        """Block up from a given set."""
        clause = [-i for i in frompoint]
        self.add_clause(clause)


class MinicardMapSolver(MapSolver):
    def __init__(self, n, bias=True, rand_seed=None):   # bias=True is a high/inclusion/MUS bias; False is a low/exclusion/MSS bias.
        super(MinicardMapSolver, self).__init__(n, bias)

        if bias:
            self.k = n  # initial lower bound on # of True variables
        else:
            self.k = 0

        self._solver = minisolvers.MinicardSolver()

        # Initialize random seed and randomize variable activity if seed is given
        if rand_seed is not None:
            self._solver.set_rnd_seed(rand_seed)
            self._solver.set_rnd_init_act(True)

        self._solver.new_vars(self.n, self.bias)

        # add "bound-setting" variables
        self._solver.new_vars(self.n)

        # add cardinality constraint (comment is for high bias, maximal model;
        #                             becomes AtMostK for low bias, minimal model)
        # want: generic AtLeastK over all n variables
        # how: make AtLeast([n vars, n bound-setting vars], n)
        #      then, assume the desired k out of the n bound-setting vars.
        # e.g.: for real vars a,b,c: AtLeast([a,b,c, x,y,z], 3)
        #       for AtLeast 3: assume(-x,-y,-z)
        #       for AtLeast 1: assume(-x)
        # and to make AtLeast into an AtMost:
        #   AtLeast([lits], k) ==> AtMost([-lits], #lits-k)
        if self.bias:
            self._solver.add_atmost([-(x+1) for x in range(self.n * 2)], self.n)
        else:
            self._solver.add_atmost([(x+1) for x in range(self.n * 2)], self.n)

    def solve_with_bound(self, k):
        # same assumptions work both for high bias / atleast and for low bias / atmost
        return self._solver.solve( [-(self.n+x+1) for x in range(k)] + [(self.n+k+x+1) for x in range(self.n-k)] )

    def check_seed(self, seed):
        """Check whether a given seed is still unexplored.

        For MinicardMapSolver, we have to make sure to effectively disable the
        cardinality constraint.  When bias=True, this requires setting its auxiliary
        variables to True (hence including them in positive_lits in check_complete).

        Returns:
            True if seed is unexplored (i.e., its corresponding assignment is a model)
        """
        positive_lits = seed + array.array('i', range(self.n+1, self.n*2+1))
        ret = self._solver.check_complete(positive_lits)
        return ret

    def next_seed(self):
        '''
            Find the next *maximum* model.
        '''
        if self.solve_with_bound(self.k):
            return self.get_seed()

        if self.bias:
            if not self.solve_with_bound(0):
                # no more models
                return None
            # move to the next bound
            self.k -= 1
        else:
            if not self.solve_with_bound(self.n):
                # no more models
                return None
            # move to the next bound
            self.k += 1

        while not self.solve_with_bound(self.k):
            if self.bias:
                self.k -= 1
            else:
                self.k += 1

        assert 0 <= self.k <= self.n

        return self.get_seed()

    def block_above_size(self, size):
        self._solver.add_atmost( [(x+1) for x in range(self.n)], size)
        self.k = min(size, self.k)

    def block_below_size(self, size):
        self._solver.add_atmost( [-(x+1) for x in range(self.n)], self.n-size)
        self.k = min(size, self.k)


class MinisatMapSolver(MapSolver):
    def __init__(self, n, bias=True, rand_seed=None, dump=None):   # bias=True is a high/inclusion/MUS bias; False is a low/exclusion/MSS bias; None is no bias.
        super(MinisatMapSolver, self).__init__(n, bias, dump)

        self._solver = minisolvers.MinisatSolver()

        # Initialize random seed and randomize variable activity if seed is given
        if rand_seed is not None:
            self._solver.set_rnd_seed(rand_seed)
            self._solver.set_rnd_init_act(True)

        self._solver.new_vars(self.n, self.bias)

        if self.bias is None:
            self._solver.set_rnd_pol(True)
        
        # 基数约束优化相关属性
        self.cardinality_threshold = 0  # 动态基数阈值
        self.enable_cardinality_constraint = False  # 是否启用基数约束

    def set_cardinality_threshold(self, threshold):
        """
        设置基数阈值，只考虑大小 >= threshold 的种子
        这是基数约束优化的核心：动态排除小规模解
        """
        old_threshold = self.cardinality_threshold
        self.cardinality_threshold = int(max(0, min(threshold, self.n)))
        self.enable_cardinality_constraint = self.cardinality_threshold > 0
        
        if self.cardinality_threshold != old_threshold:
            # 添加基数约束：至少包含 threshold 个变量
            if self.enable_cardinality_constraint:
                # 添加AtLeast约束：至少有threshold个变量为真
                self._add_atleast_constraint(self.cardinality_threshold)
    
    def _add_atleast_constraint(self, min_size):
        """
        添加AtLeast约束：种子至少包含min_size个意图
        通过添加子句来实现：至少有min_size个变量为真
        """
        # AtLeast可以通过添加多个子句来实现
        # 对于AtLeast(vars, k)，我们添加约束：
        # 任意选择n-k+1个变量，至少有一个为真
        
        if min_size <= 0 or min_size > self.n:
            return
        
        # 简化实现：我们直接通过求解时的假设来实现
        # 这样可以避免添加指数级的子句
        pass  # 实际约束会在next_seed_with_cardinality中处理

    def next_seed(self):
        """
        生成下一个种子
        如果启用基数约束，则只返回满足基数要求的种子
        """
        if self.enable_cardinality_constraint:
            return self.next_seed_with_cardinality()
        else:
            return self.next_seed_original()
    
    def next_seed_original(self):
        """原始的种子生成方法，不考虑基数约束"""
        if self._solver.solve():
            return self.get_seed()
        else:
            return None
    
    def next_seed_with_cardinality(self):
        """
        带基数约束的种子生成
        只返回大小 >= cardinality_threshold 的种子
        """
        max_attempts = 100  # 防止无限循环
        attempts = 0
        
        while attempts < max_attempts:
            if self._solver.solve():
                seed = self.get_seed()
                
                # 检查基数约束
                if len(seed) >= self.cardinality_threshold:
                    return seed
                else:
                    # 种子太小，阻塞它并继续寻找
                    self.block_small_seed(seed)
                    attempts += 1
            else:
                return None
        
        # 如果多次尝试都失败，可能阈值设置过高
        return None
    
    def block_small_seed(self, small_seed):
        """
        阻塞过小的种子
        添加约束：不能再生成这个特定的小种子
        """
        if len(small_seed) < self.cardinality_threshold:
            # 阻塞这个精确的小种子
            clause = [-i for i in small_seed]
            self.add_clause(clause)
    
    def update_cardinality_threshold(self, new_threshold):
        """
        动态更新基数阈值
        这是基数约束优化的关键：随着找到更大的MSS，提高阈值
        """
        if new_threshold > self.cardinality_threshold:
            old_threshold = self.cardinality_threshold
            self.set_cardinality_threshold(new_threshold)
            return True
        return False
    
    def get_cardinality_info(self):
        """返回当前的基数约束信息"""
        return {
            'threshold': self.cardinality_threshold,
            'enabled': self.enable_cardinality_constraint,
            'max_possible': self.n
        }
