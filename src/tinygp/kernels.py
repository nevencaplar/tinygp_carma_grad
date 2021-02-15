# -*- coding: utf-8 -*-

__all__ = [
    "metric",
    "diagonal_metric",
    "dense_metric",
    "cholesky_metric",
    "Sum",
    "Product",
    "Constant",
    "DotProduct",
    "Polynomial",
    "Linear",
    "Exp",
    "ExpSquared",
    "Matern32",
    "Matern52",
    "Cosine",
    "RationalQuadratic",
]

from typing import Callable, Union

from functools import partial

import jax
import jax.numpy as jnp
from jax.scipy import linalg

from .functional import compose


Metric = Callable[[jnp.ndarray], jnp.ndarray]


def metric(r: jnp.ndarray) -> jnp.ndarray:
    return jnp.sum(jnp.square(r))


def diagonal_metric(ell: jnp.ndarray) -> Metric:
    return partial(jnp.multiply, 1.0 / ell)


def dense_metric(cov: jnp.ndarray, *, lower: bool = True) -> Metric:
    chol = linalg.cholesky(cov, lower=lower)
    return cholesky_metric(chol, lower=lower)


def cholesky_metric(chol: jnp.ndarray, *, lower: bool = True) -> Metric:
    solve = partial(linalg.solve_triangular, chol, lower=lower)
    return compose(metric, solve)


class Kernel:
    def __call__(self, X1: jnp.ndarray, X2: jnp.ndarray) -> jnp.ndarray:
        raise NotImplementedError()

    def evaluate_diag(self, X: jnp.ndarray) -> jnp.ndarray:
        return jax.vmap(self)(X, X)

    def evaluate(self, X1: jnp.ndarray, X2: jnp.ndarray) -> jnp.ndarray:
        return jax.vmap(lambda _X1: jax.vmap(lambda _X2: self(_X1, _X2))(X2))(
            X1
        )

    def __add__(self, other: Union["Kernel", jnp.ndarray]) -> "Kernel":
        if isinstance(other, Kernel):
            return Sum(self, other)
        return Sum(self, Constant(other))

    def __radd__(self, other: Union["Kernel", jnp.ndarray]) -> "Kernel":
        if isinstance(other, Kernel):
            return Sum(other, self)
        return Sum(Constant(other), self)

    def __mul__(self, other: Union["Kernel", jnp.ndarray]) -> "Kernel":
        if isinstance(other, Kernel):
            return Product(self, other)
        return Product(self, Constant(other))

    def __rmul__(self, other: Union["Kernel", jnp.ndarray]) -> "Kernel":
        if isinstance(other, Kernel):
            return Product(other, self)
        return Product(Constant(other), self)


class Sum(Kernel):
    def __init__(self, kernel1: Kernel, kernel2: Kernel):
        self.kernel1 = kernel1
        self.kernel2 = kernel2

    def __call__(self, X1: jnp.ndarray, X2: jnp.ndarray) -> jnp.ndarray:
        return self.kernel1(X1, X2) + self.kernel2(X1, X2)


class Product(Kernel):
    def __init__(self, kernel1: Kernel, kernel2: Kernel):
        self.kernel1 = kernel1
        self.kernel2 = kernel2

    def __call__(self, X1: jnp.ndarray, X2: jnp.ndarray) -> jnp.ndarray:
        return self.kernel1(X1, X2) * self.kernel2(X1, X2)


class Constant(Kernel):
    def __init__(self, value: jnp.ndarray):
        self.value = jnp.asarray(value)

    def __call__(self, X1: jnp.ndarray, X2: jnp.ndarray) -> jnp.ndarray:
        return self.value


class DotProduct(Kernel):
    def __call__(self, X1: jnp.ndarray, X2: jnp.ndarray) -> jnp.ndarray:
        return X1 @ X2


class Polynomial(Kernel):
    def __init__(self, *, order: int, sigma: jnp.ndarray):
        self.order = int(order)
        self.sigma2 = jnp.asarray(sigma) ** 2

    def __call__(self, X1: jnp.ndarray, X2: jnp.ndarray) -> jnp.ndarray:
        return (X1 @ X2 + self.sigma2) ** self.order


class Linear(Kernel):
    def __init__(self, *, order: int, sigma: jnp.ndarray):
        self.order = int(order)
        self.sigma2 = jnp.asarray(sigma) ** 2

    def __call__(self, X1: jnp.ndarray, X2: jnp.ndarray) -> jnp.ndarray:
        return (X1 @ X2 / self.sigma2) ** self.order


class MetricKernel(Kernel):
    def __init__(self, metric: Union[Metric, jnp.ndarray]):
        if callable(metric):
            self.metric = metric
        else:
            self.metric = diagonal_metric(metric)

    def evaluate_radial(self, r2: jnp.ndarray) -> jnp.ndarray:
        raise NotImplementedError()

    def __call__(self, X1: jnp.ndarray, X2: jnp.ndarray) -> jnp.ndarray:
        return self.evaluate_radial(self.metric(X1 - X2))


class Exp(MetricKernel):
    def evaluate_radial(self, r2: jnp.ndarray) -> jnp.ndarray:
        return jnp.exp(-jnp.sqrt(r2))


class ExpSquared(MetricKernel):
    def evaluate_radial(self, r2: jnp.ndarray) -> jnp.ndarray:
        return jnp.exp(-0.5 * r2)


class Matern32(MetricKernel):
    def evaluate_radial(self, r2: jnp.ndarray) -> jnp.ndarray:
        arg = jnp.sqrt(3.0 * r2)
        return (1.0 + arg) * jnp.exp(-arg)


class Matern52(MetricKernel):
    def evaluate_radial(self, r2: jnp.ndarray) -> jnp.ndarray:
        arg1 = 5.0 * r2
        arg2 = jnp.sqrt(arg1)
        return (1.0 + arg2 + arg1 / 3.0) * jnp.exp(-arg2)


class Cosine(MetricKernel):
    def evaluate_radial(self, r2: jnp.ndarray) -> jnp.ndarray:
        return jnp.cos(2 * jnp.pi * jnp.sqrt(r2))


class RationalQuadratic(MetricKernel):
    def __init__(self, metric: Metric, *, alpha: jnp.ndarray):
        self.alpha = jnp.asarray(alpha)
        super().__init__(metric)

    def evaluate_radial(self, r2: jnp.ndarray) -> jnp.ndarray:
        return (1.0 - 0.5 * r2 / self.alpha) ** self.alpha
