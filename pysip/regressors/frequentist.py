"""Frequentist regressor"""
from typing import Tuple, Union

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from ..filters.kalman_qr import KalmanQR, BayesianFilter
from ..statespace.base import StateSpace
from ..utils.statistics import ttest
from .base import BaseRegressor


class FreqRegressor(BaseRegressor):
    """Frequentist Regressor

    Args:
        ss: StateSpace()
        bayesian_filter: BayesianFilter()
        time_scale: Time series frequency, e.g. 's': seconds, 'D': days, etc.
            Works only for pandas.DataFrame with DateTime index
    """

    def __init__(
        self,
        ss: StateSpace,
        bayesian_filter: BayesianFilter = KalmanQR,
        time_scale: str = "s",
    ):
        super().__init__(ss, bayesian_filter, time_scale, False, True)

    def fit(
        self,
        df: pd.DataFrame,
        outputs: Union[str, list],
        inputs: Union[str, list] = None,
        options: dict = None,
    ) -> Union[pd.DataFrame, pd.DataFrame, dict]:
        if options is None:
            options = {}
        else:
            options = dict(options)

        options.setdefault("disp", True)
        options.setdefault("gtol", 1e-4)

        init = options.pop("init", "fixed")
        hpd = options.pop("hpd", 0.95)
        self.parameters.eta = self.parameters.init_parameters(1, init, hpd)
        data = self.ss.prepare_data(df, inputs, outputs)

        results = minimize(
            fun=self._eval_log_posterior,
            x0=self.parameters.eta_free,
            args=data,
            method="BFGS",
            jac="3-point",
            options=options,
        )

        # inverse jacobian of the transform eta = f(theta)
        inv_jac = np.diag(1.0 / np.array(self.parameters.eta_jacobian))

        # covariance matrix in the constrained space (e.g. theta)
        cov_theta = inv_jac @ results.hess_inv @ inv_jac

        # standard deviation of the constrained parameters
        sig_theta = np.sqrt(np.diag(cov_theta)) * self.parameters.scale
        inv_sig_theta = np.diag(1.0 / np.sqrt(np.diag(cov_theta)))

        # correlation matrix of the constrained parameters
        corr_matrix = inv_sig_theta @ cov_theta @ inv_sig_theta
        pd.set_option("display.float_format", "{:.3e}".format)
        df = pd.DataFrame(
            data=np.vstack(
                [
                    self.parameters.theta_free,
                    sig_theta,
                    ttest(self.parameters.theta_free, sig_theta, data[2].shape[1]),
                    np.abs(results.jac),
                    np.abs(self.parameters.d_penalty),
                ]
            ).T,
            columns=["θ", "σ(θ)", "pvalue", "|g(η)|", "|dpen(θ)|"],
            index=self.parameters.names_free,
        )
        df_corr = pd.DataFrame(
            data=corr_matrix,
            index=self.parameters.names_free,
            columns=self.parameters.names_free,
        )

        self.summary_ = df
        self.corr_ = df_corr
        self.results_ = results

        return df, df_corr, results

    def eval_residuals(
        self,
        df: pd.DataFrame,
        outputs: Union[str, list],
        inputs: Union[str, list] = None,
        x0: np.ndarray = None,
        P0: np.ndarray = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Compute the standardized residuals

        Args:
            df: Data
            outputs: Outputs name(s)
            inputs: Inputs name(s)
            x0: Initial state mean
            P0: Initial state deviation

        Returns:
            2-element tuple containing
                - **res**: Standardized residuals
                - **res_std**: Residuals deviations
        """

        dt, u, u1, y, *_ = self._prepare_data(df, inputs, outputs, None)
        ssm, index = self.ss.get_discrete_ssm(dt)
        res, res_std = self.filter.filtering(ssm, index, u, u1, y)[2:]

        return res.squeeze(), res_std.squeeze()

    def estimate_states(
        self,
        df: pd.DataFrame,
        outputs: list,
        inputs: list = None,
        x0: np.ndarray = None,
        P0: np.ndarray = None,
        smooth: bool = False,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Estimate the state filtered/smoothed distribution

        Args:
            df: Data
            inputs: Inputs names
            outputs: Outputs names
            x0: Initial state mean
            P0: Initial state deviation
            smooth: Use smoother

        Returns:
            2-element tuple containing
                - state mean
                - state covariance
        """

        dt, u, u1, y, *_ = self._prepare_data(df, inputs, outputs, None)
        return self._estimate_states(dt, u, u1, y, x0, P0, smooth)

    def eval_log_likelihood(
        self,
        df: pd.DataFrame,
        outputs: Union[str, list],
        inputs: Union[str, list] = None,
    ) -> Union[float, np.ndarray]:
        """Evaluate the negative log-likelihood

        Args:
            df: Data
            outputs: Outputs name(s)
            inputs: Inputs name(s)
            pointwise: Evaluate the log-likelihood pointwise

        Returns:
            Negative log-likelihood or predictive density evaluated point-wise
        """

        dt, u, u1, y = self._prepare_data(df, inputs, outputs)
        return self._eval_log_likelihood(dt, u, u1, y)

    def predict(
        self,
        df: pd.DataFrame,
        outputs: Union[str, list] = None,
        inputs: Union[str, list] = None,
        tnew: Union[np.ndarray, pd.Series] = None,
        x0: np.ndarray = None,
        P0: np.ndarray = None,
        smooth: bool = False,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """State-space model output prediction

        Args:
            df: Data
            outputs: Outputs name(s)
            inputs: Inputs name(s)
            tnew: New time instants
            x0: Initial state mean
            P0: Initial state deviation
            smooth: Use smoother

        Returns:
            2-element tuple containing
                - **y_mean**: Output mean
                - **y_std**: Output deviation
        """

        if self.ss.ny > 1:
            raise NotImplementedError

        dt, u, u1, y, index_back = self._prepare_data(df, inputs, outputs, tnew)
        x, P = self._estimate_states(dt, u, u1, y, x0, P0, smooth)

        # keep only the part corresponding to `tnew`
        if tnew is not None:
            x = x[index_back, :, :]
            P = P[index_back, :, :]
            x = x[-tnew.shape[0] :, :, :]
            P = P[-tnew.shape[0] :, :, :]

        y_mean = self.ss.C @ x
        y_std = np.sqrt(self.ss.C @ P @ self.ss.C.T) + self.ss.R

        return np.squeeze(y_mean), np.squeeze(y_std)
