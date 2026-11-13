# Mathematics: Calculus, Linear Algebra & Probability

## 1. Single & Multivariable Calculus
- **Fundamental Theorem of Calculus (FTC)**:
  $$\frac{d}{dx} \int_a^x f(t)\, dt = f(x) \quad \text{and} \quad \int_a^b f'(x)\, dx = f(b) - f(a)$$
- **Taylor Series Expansion**:
  $$f(x) = \sum_{n=0}^{\infty} \frac{f^{(n)}(a)}{n!}(x - a)^n = f(a) + f'(a)(x-a) + \frac{f''(a)}{2!}(x-a)^2 + \dots$$
- **Multivariable Optimization**:
  - Gradient Vector: $\nabla f = \left[\frac{\partial f}{\partial x_1}, \frac{\partial f}{\partial x_2}, \dots, \frac{\partial f}{\partial x_n}\right]^T$.
  - Hessian Matrix ($H$): Second-order partial derivatives. If $\nabla f = 0$ and $H$ is positive definite $\implies$ local minimum.
  - Lagrange Multipliers for constrained optimization: $\nabla f(x) = \lambda \nabla g(x)$ subject to $g(x) = 0$.

## 2. Linear Algebra
- **Vector Spaces & Subspaces**: Linear independence, span, basis, dimension.
- **Rank-Nullity Theorem**: For matrix $A \in \mathbb{R}^{m \times n}$:
  $$\text{rank}(A) + \text{nullity}(A) = n$$
- **Eigenvalues & Eigenvectors**:
  $$A\vec{v} = \lambda\vec{v} \iff \det(A - \lambda I) = 0$$
- **Matrix Decompositions**:
  - Eigendecomposition: $A = Q\Lambda Q^{-1}$ (for diagonalizable matrices).
  - Singular Value Decomposition (SVD): $A = U\Sigma V^T$ for any rectangular matrix. Foundational for PCA and compression.

## 3. Probability & Statistics
- **Conditional Probability & Bayes' Theorem**:
  $$P(A|B) = \frac{P(B|A)P(A)}{P(B)} = \frac{P(B|A)P(A)}{\sum_i P(B|A_i)P(A_i)}$$
- **Random Variables & Expectations**:
  - Expected Value: $\mathbb{E}[X] = \int x f(x) dx$ (continuous) or $\sum x P(X=x)$ (discrete).
  - Variance: $\text{Var}(X) = \mathbb{E}[(X - \mu)^2] = \mathbb{E}[X^2] - (\mathbb{E}[X])^2$.
- **Central Limit Theorem (CLT)**: The sum (or average) of a large number of independent and identically distributed (i.i.d.) random variables approaches a normal distribution:
  $$\bar{X}_n \xrightarrow{d} \mathcal{N}\left(\mu, \frac{\sigma^2}{n}\right) \quad \text{as } n \to \infty$$
