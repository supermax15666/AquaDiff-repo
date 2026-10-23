from __future__ import annotations

from typing import Any, Callable

from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel, WhiteKernel
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, PolynomialFeatures, StandardScaler
from sklearn.svm import SVR


NUMERIC_FEATURES = ["temperature_K", "concentration_mol_L"]
SYSTEM_FEATURE = ["system"]
RANDOM_STATE = 20260814


def _feature_columns(pooled: bool) -> ColumnTransformer:
    transformers = []
    if pooled:
        transformers.append(
            (
                "sys",
                OneHotEncoder(sparse_output=False, handle_unknown="ignore"),
                [0],
            )
        )
        transformers.append(("num", "passthrough", [1, 2]))
    else:
        transformers.append(("num", "passthrough", [0, 1]))
    return ColumnTransformer(transformers, remainder="drop")


def _build_polynomial_ridge(pooled: bool) -> Pipeline:
    return Pipeline(
        [
            ("features", _feature_columns(pooled)),
            ("poly", PolynomialFeatures(degree=2, include_bias=False)),
            ("ridge", Ridge(alpha=1.0)),
        ]
    )


def _build_rbf_svr(pooled: bool) -> Pipeline:
    return Pipeline(
        [
            ("features", _feature_columns(pooled)),
            ("scaler", StandardScaler()),
            ("svr", SVR(kernel="rbf", C=1.0, epsilon=0.1, gamma="scale")),
        ]
    )


def _build_random_forest(pooled: bool) -> Pipeline:
    return Pipeline(
        [
            ("features", _feature_columns(pooled)),
            (
                "forest",
                RandomForestRegressor(
                    n_estimators=300,
                    min_samples_leaf=2,
                    random_state=RANDOM_STATE,
                    # n_jobs=1：单线程建树，避免受限环境（如无命名管道的沙箱）下
                    # joblib 线程池失败；RF 结果与并行度无关，逐位复现不受影响。
                    n_jobs=1,
                ),
            ),
        ]
    )


def _build_gradient_boosting(pooled: bool) -> Pipeline:
    return Pipeline(
        [
            ("features", _feature_columns(pooled)),
            (
                "boosting",
                GradientBoostingRegressor(
                    n_estimators=300,
                    learning_rate=0.05,
                    max_depth=3,
                    random_state=RANDOM_STATE,
                ),
            ),
        ]
    )


def _build_gaussian_process(pooled: bool) -> Pipeline:
    kernel = ConstantKernel(1.0) * RBF(
        length_scale=1.0, length_scale_bounds=(1e-2, 1e3)
    ) + WhiteKernel(noise_level=1e-3, noise_level_bounds=(1e-6, 1e1))
    return Pipeline(
        [
            ("features", _feature_columns(pooled)),
            ("scaler", StandardScaler()),
            (
                "gpr",
                GaussianProcessRegressor(
                    kernel=kernel,
                    normalize_y=True,
                    n_restarts_optimizer=0,
                    random_state=RANDOM_STATE,
                ),
            ),
        ]
    )


def _build_dummy_median(pooled: bool) -> Pipeline:
    return Pipeline(
        [
            ("features", _feature_columns(pooled)),
            ("dummy", DummyRegressor(strategy="median")),
        ]
    )


ModelBuilder = Callable[[bool], Pipeline]

MODEL_SPECS: dict[str, dict[str, Any]] = {
    "polynomial_ridge": {
        "display_name": "Polynomial Ridge",
        "description": "Quadratic polynomial features (T, c, T^2, Tc, c^2) with L2 Ridge(alpha=1.0).",
        "build": _build_polynomial_ridge,
    },
    "rbf_svr": {
        "display_name": "RBF-SVR",
        "description": "Support Vector Regression with RBF kernel, standardized features, C=1.0, epsilon=0.1.",
        "build": _build_rbf_svr,
    },
    "random_forest": {
        "display_name": "Random Forest",
        "description": "300 trees, min_samples_leaf=2, fixed random_state, deterministic.",
        "build": _build_random_forest,
    },
    "gradient_boosting": {
        "display_name": "Gradient Boosting",
        "description": "300 boosting stages, learning_rate=0.05, max_depth=3, fixed random_state.",
        "build": _build_gradient_boosting,
    },
    "gaussian_process": {
        "display_name": "Gaussian Process Regression",
        "description": "Constant*RBF + White noise kernel, normalized targets, zero optimizer restarts for determinism.",
        "build": _build_gaussian_process,
    },
    "dummy_median": {
        "display_name": "Mean/Median Dummy",
        "description": "Median-of-training-target baseline; the lower-bound reference.",
        "build": _build_dummy_median,
    },
}


def build_model(model_key: str, *, pooled: bool) -> Pipeline:
    if model_key not in MODEL_SPECS:
        raise ValueError(f"Unknown model key: {model_key!r}")
    return MODEL_SPECS[model_key]["build"](pooled)
