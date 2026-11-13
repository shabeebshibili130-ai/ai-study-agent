# Computer Science: Data Structures, Algorithms & Artificial Intelligence

## 1. Asymptotic Complexity (Big-O Notation)
- **Time Hierarchy**: $O(1) < O(\log n) < O(n) < O(n \log n) < O(n^2) < O(2^n) < O(n!)$.
- **Master Theorem for Divide & Conquer**: $T(n) = aT(n/b) + f(n)$.
  - If $f(n) = O(n^c)$ where $c < \log_b a \implies T(n) = \Theta(n^{\log_b a})$.
  - If $f(n) = \Theta(n^{\log_b a} \log^k n) \implies T(n) = \Theta(n^{\log_b a} \log^{k+1} n)$.

## 2. Core Data Structures
- **Arrays & Dynamic Arrays**: $O(1)$ random access, amortized $O(1)$ append.
- **Linked Lists**: $O(1)$ insertion/deletion at pointers, $O(n)$ search.
- **Hash Tables**: $O(1)$ average lookup/insert/delete via hash function with collision resolution (chaining or open addressing).
- **Binary Search Trees (BST) & AVL/Red-Black**: Self-balancing trees guarantee $O(\log n)$ operations.
- **Heaps & Priority Queues**: Complete binary tree satisfying heap invariant. $O(\log n)$ push/pop, $O(1)$ peek, $O(n)$ heapify.
- **Graphs**: Represented via adjacency lists or matrices. BFS (shortest path unweighted, $O(V+E)$), DFS (topological sort, connected components, $O(V+E)$).

## 3. Essential Algorithms
- **Sorting**:
  - QuickSort: Average $O(n \log n)$, in-place partition.
  - MergeSort: Guaranteed $O(n \log n)$, stable, requires $O(n)$ auxiliary space.
- **Graph Algorithms**:
  - Dijkstra's Algorithm: Shortest path with non-negative weights using min-heap ($O((V+E)\log V)$).
  - Bellman-Ford: Handles negative weights and detects negative cycles ($O(VE)$).
  - Kruskal & Prim: Minimum Spanning Trees (MST) using Disjoint Set Union ($O(E \log V)$).
- **Dynamic Programming (DP)**:
  - Overlapping subproblems + optimal substructure.
  - Classic problems: 0/1 Knapsack, Longest Common Subsequence (LCS), Edit Distance, Matrix Chain Multiplication.

## 4. Artificial Intelligence & Machine Learning
- **Supervised vs. Unsupervised vs. Reinforcement Learning**:
  - Supervised: Regression (MSE loss), Classification (Cross-entropy loss).
  - Unsupervised: Clustering (k-Means, DBSCAN), Dimensionality Reduction (PCA, t-SNE).
  - Reinforcement: Agent, environment, policy $\pi(a|s)$, Q-learning $Q(s, a) \leftarrow Q(s, a) + \alpha [r + \gamma \max_{a'} Q(s', a') - Q(s, a)]$.
- **Deep Learning & Neural Networks**:
  - Feedforward networks, Backpropagation via Chain Rule: $\frac{\partial L}{\partial w} = \frac{\partial L}{\partial y} \cdot \frac{\partial y}{\partial z} \cdot \frac{\partial z}{\partial w}$.
  - Convolutional Neural Networks (CNNs) for spatial computer vision (Conv, Pooling, Flatten, Dense).
  - Transformer Architecture: Multi-head Scaled Dot-Product Self-Attention:
    $$\text{Attention}(Q, K, V) = \text{softmax}\left(\frac{QK^T}{\sqrt{d_k}}\right)V$$
  - Large Language Models (LLMs): Autoregressive next-token prediction, pretraining, instruction fine-tuning, and RLHF.
