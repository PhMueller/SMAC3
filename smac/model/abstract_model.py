from __future__ import annotations
from abc import ABC, abstractmethod

from typing import Any, TypeVar

import copy
import warnings

import numpy as np
from sklearn.decomposition import PCA
from sklearn.exceptions import NotFittedError
from sklearn.preprocessing import MinMaxScaler

from ConfigSpace import ConfigurationSpace
from smac.constants import VERY_SMALL_NUMBER
from smac.utils.logging import get_logger
from smac.model.utils import get_types

__copyright__ = "Copyright 2022, automl.org"
__license__ = "3-clause BSD"


logger = get_logger(__name__)


Self = TypeVar("Self", bound="AbstractModel")


class AbstractModel(ABC):
    """Abstract implementation of the EPM API.

    **Note:** The input dimensionality of Y for training and the output dimensions
    of all predictions (also called ``n_objectives``) depends on the concrete
    implementation of this abstract class.

    Parameters
    ----------
    configspace : ConfigurationSpace
        Configuration space to tune for.
    types : List[int]
        Specifies the number of categorical values of an input dimension where
        the i-th entry corresponds to the i-th input dimension. Let's say we
        have 2 dimension where the first dimension consists of 3 different
        categorical choices and the second dimension is continuous than we
        have to pass [3, 0]. Note that we count starting from 0.
    bounds : List[Tuple[float, float]]
        bounds of input dimensions: (lower, uppper) for continuous dims; (n_cat, np.nan) for categorical dims
    seed : int
        The seed that is passed to the model library.
    instance_features : np.ndarray (I, K)
        Contains the K dimensional instance features
        of the I different instances
    pca_components : float
        Number of components to keep when using PCA to reduce
        dimensionality of instance features. Requires to
        set n_feats (> pca_dims).

    Attributes
    ----------
    instance_features : np.ndarray(I, K)
        Contains the K dimensional instance features
        of the I different instances
    pca : sklearn.decomposition.PCA
        Object to perform PCA
    pca_components : float
        Number of components to keep or None
    n_feats : int
        Number of instance features
    n_params : int
        Number of parameters in a configuration (only available after train has
        been called)
    scaler : sklearn.preprocessing.MinMaxScaler
        Object to scale data to be withing [0, 1]
    var_threshold : float
        Lower bound vor variance. If estimated variance < var_threshold, the set
        to var_threshold
    types : list
        If set, contains a list with feature types (cat,const) of input vector
    """

    def __init__(
        self,
        configspace: ConfigurationSpace,
        instance_features: dict[str, list[int | float]] | None = None,
        pca_components: int | None = 7,
        seed: int = 0,
    ) -> None:
        self.configspace = configspace
        self.seed = seed
        self.rng = np.random.RandomState(self.seed)
        self.instance_features = instance_features
        self.pca_components = pca_components

        n_features = 0
        if self.instance_features is not None:
            for v in self.instance_features.values():
                if n_features == 0:
                    n_features = len(v)
                else:
                    if len(v) != n_features:
                        raise RuntimeError("Instances must have the same number of features.")

        self.n_features = n_features
        self.n_params = len(self.configspace.get_hyperparameters())

        self.pca = PCA(n_components=self.pca_components)
        self.scaler = MinMaxScaler()
        self._apply_pca = False

        # Never use a lower variance than this
        self.var_threshold = VERY_SMALL_NUMBER
        self.types, self.bounds = get_types(configspace, instance_features)
        # Initial types array which is used to reset the type array at every call to train()
        self._initial_types = copy.deepcopy(self.types)

    def get_meta(self) -> dict[str, Any]:
        """Returns the meta data of the created object."""
        return {
            "name": self.__class__.__name__,
            "types": self.types,
            "bounds": self.bounds,
            "pca_components": self.pca_components,
        }

    def train(self: Self, X: np.ndarray, Y: np.ndarray) -> Self:
        """Trains the EPM on X and Y.

        Parameters
        ----------
        X : np.ndarray [n_samples, n_features (config + instance features)]
            Input data points.
        Y : np.ndarray [n_samples, n_objectives]
            The corresponding target values. n_objectives must match the
            number of target names specified in the constructor.

        Returns
        -------
        self : BaseEPM
        """
        if len(X.shape) != 2:
            raise ValueError("Expected 2d array, got %dd array!" % len(X.shape))
        if X.shape[1] != self.n_params + self.n_features:
            raise ValueError("Feature mismatch: X should have %d features, but has %d" % (self.n_params, X.shape[1]))
        if X.shape[0] != Y.shape[0]:
            raise ValueError("X.shape[0] ({}) != y.shape[0] ({})".format(X.shape[0], Y.shape[0]))

        # reduce dimensionality of features of larger than PCA_DIM
        if self.pca_components and X.shape[0] > self.pca.n_components and self.n_features >= self.pca_components:
            X_feats = X[:, -self.n_features :]
            # scale features
            X_feats = self.scaler.fit_transform(X_feats)
            X_feats = np.nan_to_num(X_feats)  # if features with max == min
            # PCA
            X_feats = self.pca.fit_transform(X_feats)
            X = np.hstack((X[:, : self.n_params], X_feats))
            if hasattr(self, "types"):
                # for RF, adapt types list
                # if X_feats.shape[0] < self.pca, X_feats.shape[1] ==
                # X_feats.shape[0]
                self.types = np.array(
                    np.hstack((self.types[: self.n_params], np.zeros(X_feats.shape[1]))),
                    dtype=np.uint,
                )  # type: ignore
            self._apply_pca = True
        else:
            self._apply_pca = False
            if hasattr(self, "types"):
                self.types = copy.deepcopy(self._initial_types)

        return self._train(X, Y)

    @abstractmethod
    def _train(self: Self, X: np.ndarray, Y: np.ndarray) -> Self:
        """Trains the random forest on X and y.

        Parameters
        ----------
        X : np.ndarray [n_samples, n_features (config + instance features)]
            Input data points.
        Y : np.ndarray [n_samples, n_objectives]
            The corresponding target values. n_objectives must match the
            number of target names specified in the constructor.

        Returns
        -------
        self
        """
        ...

    def predict(
        self, X: np.ndarray, cov_return_type: str | None = "diagonal_cov"
    ) -> tuple[np.ndarray, np.ndarray | None]:
        """Predict means and variances for given X.

        Parameters
        ----------
        X : np.ndarray of shape = [n_samples, n_features (config + instance features)]
            Training samples
        cov_return_type: Optional[str]
            Specifies what to return along with the mean. (Applies to only Gaussian Process for now)
            Can take 4 values: [None, diagonal_std, diagonal_cov, full_cov]
            * None - only mean is returned
            * diagonal_std - standard deviation at test points is returned
            * diagonal_cov - diagonal of the covariance matrix is returned
            * full_cov - whole covariance matrix between the test points is returned

        Returns
        -------
        means : np.ndarray of shape = [n_samples, n_objectives]
            Predictive mean
        vars : None or np.ndarray of shape = [n_samples, n_objectives] or [n_samples, n_samples]
            Predictive variance or standard deviation
        """
        if len(X.shape) != 2:
            raise ValueError("Expected 2d array, got %dd array!" % len(X.shape))
        if X.shape[1] != self.n_params + self.n_features:
            raise ValueError(
                "Rows in X should have %d entries but have %d!" % (self.n_params + self.n_features, X.shape[1])
            )

        if self._apply_pca:
            try:
                X_feats = X[:, -self.n_features :]
                X_feats = self.scaler.transform(X_feats)
                X_feats = self.pca.transform(X_feats)
                X = np.hstack((X[:, : self.n_params], X_feats))
            except NotFittedError:
                pass  # PCA not fitted if only one training sample

        if X.shape[1] != len(self.types):
            raise ValueError("Rows in X should have %d entries but have %d!" % (len(self.types), X.shape[1]))

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", "Predicted variances smaller than 0. Setting those variances to 0.")
            mean, var = self._predict(X, cov_return_type)

        if len(mean.shape) == 1:
            mean = mean.reshape((-1, 1))
        if var is not None and len(var.shape) == 1:
            var = var.reshape((-1, 1))

        return mean, var

    def _predict(
        self, X: np.ndarray, cov_return_type: str | None = "diagonal_cov"
    ) -> tuple[np.ndarray, np.ndarray | None]:
        """Predict means and variances for given X.

        Parameters
        ----------
        X : np.ndarray
            [n_samples, n_features (config + instance features)]
        cov_return_type: Optional[str]
            Specifies what to return along with the mean. Refer ``predict()`` for more information.

        Returns
        -------
        means : np.ndarray of shape = [n_samples, n_objectives]
            Predictive mean
        vars : None or np.ndarray of shape = [n_samples, n_objectives] or [n_samples, n_samples]
            Predictive variance or standard deviation
        """
        raise NotImplementedError()

    def predict_marginalized_over_instances(self, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Predict mean and variance marginalized over all instances.

        Returns the predictive mean and variance marginalised over all
        instances for a set of configurations.

        Parameters
        ----------
        X : np.ndarray
            [n_samples, n_features (config)]

        Returns
        -------
        means : np.ndarray of shape = [n_samples, 1]
            Predictive mean
        vars : np.ndarray  of shape = [n_samples, 1]
            Predictive variance
        """
        if len(X.shape) != 2:
            raise ValueError("Expected 2d array, got %dd array!" % len(X.shape))
        if X.shape[1] != len(self.bounds):
            raise ValueError("Rows in X should have %d entries but have %d!" % (len(self.bounds), X.shape[1]))

        if self.instance_features is None:
            mean, var = self.predict(X)
            assert var is not None

            var[var < self.var_threshold] = self.var_threshold
            var[np.isnan(var)] = self.var_threshold

            return mean, var
        else:
            n_instances = self.scen

            mean = np.zeros(X.shape[0])
            var = np.zeros(X.shape[0])
            for i, x in enumerate(X):
                X_ = np.hstack((np.tile(x, (n_instances, 1)), self.instance_features))
                means, vars = self.predict(X_)
                assert vars is not None  # please mypy
                # VAR[1/n (X_1 + ... + X_n)] =
                # 1/n^2 * ( VAR(X_1) + ... + VAR(X_n))
                # for independent X_1 ... X_n
                var_x = np.sum(vars) / (len(vars) ** 2)
                if var_x < self.var_threshold:
                    var_x = self.var_threshold

                var[i] = var_x
                mean[i] = np.mean(means)

            if len(mean.shape) == 1:
                mean = mean.reshape((-1, 1))
            if len(var.shape) == 1:
                var = var.reshape((-1, 1))

            return mean, var

    def get_configspace(self) -> ConfigurationSpace:
        """
        Retrieves the ConfigurationSpace used for the model.

        Returns
        -------
            self.configspace: The ConfigurationSpace of the model
        """
        return self.configspace