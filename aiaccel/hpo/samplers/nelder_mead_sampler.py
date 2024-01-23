from __future__ import annotations

import dataclasses
import queue
from collections.abc import Generator
from typing import Any, Sequence

import numpy as np
import optuna
from optuna import distributions
from optuna._transform import _SearchSpaceTransform
from optuna.distributions import BaseDistribution
from optuna.samplers._lazy_random_state import LazyRandomState
from optuna.study import Study
from optuna.trial import FrozenTrial, TrialState


@dataclasses.dataclass
class Coef:
    r: float = 1.0
    ic: float = -0.5
    oc: float = 0.5
    e: float = 2.0
    s: float = 0.5


@dataclasses.dataclass
class Storage:
    r: np.ndarray[float, float] | None = None  # reflect
    e: np.ndarray[float, float] | None = None  # expand
    ic: np.ndarray[float, float] | None = None  # inside_contract
    oc: np.ndarray[float, float] | None = None  # outside_contract
    s: np.ndarray[float, float] | None = None  # shrink


@dataclasses.dataclass
class Vertex:
    coordinate: np.ndarray[float, float]
    value: float


class NelderMeadAlgorism:
    def __init__(self,
                 search_space: dict[str, list[float]],
                 coef: Coef,
                 seed: int | None = None) -> None:
        self.dimension: int = len(search_space)
        self._rng: LazyRandomState = LazyRandomState(seed)

        self._search_space = {}
        for param_name, param_distribution in sorted(search_space.items()):
            self._search_space[param_name] = list(param_distribution)

        self.vertices: np.ndarray[float, float] = np.array([])
        self.values: np.ndarray[float, float] = np.array([])
        self.coef: Coef = coef

        self.NumofInitialCreateTrial: int = 0

        self.storage: Storage = Storage()

        self.vertex_queue: queue.Queue[Vertex] = queue.Queue()

    def initial(self) -> Generator[np.ndarray[float, float], None, None]:
        for _ in range(self.dimension + 1):
            initial_param = []
            for param_name, param_distribution in self._search_space.items():
                search_space = {
                    param_name: optuna.distributions.FloatDistribution(param_distribution[0], param_distribution[1])
                    }
                trans = _SearchSpaceTransform(search_space)
                trans_params = self._rng.rng.uniform(trans.bounds[:, 0], trans.bounds[:, 1])
                initial_param.append(trans.untransform(trans_params)[param_name])
            self.NumofInitialCreateTrial += 1
            yield np.array(initial_param), self.dimension + 1 - self.NumofInitialCreateTrial
        temp = []
        for _ in range(self.dimension + 1):
            temp.append(self.vertex_queue.get())
        self.vertices = np.array([vertex.coordinate for vertex in temp])
        self.values = np.array([vertex.value for vertex in temp])

    def order_by(self) -> None:
        order = np.argsort(self.values)

        self.vertices = self.vertices[order]
        self.values = self.values[order]

    def centroid(self) -> None:
        self.storage = Storage()
        self.order_by()
        self.yc = self.vertices[:-1].mean(axis=0)

    def reflect(self) -> Generator[np.ndarray[float, float], None, None]:
        yr = self.yc + self.coef.r * (self.yc - self.vertices[-1])
        self.storage.r = yr
        yield from self.func(yr)

    def expand(self) -> Generator[np.ndarray[float, float], None, None]:
        ye = self.yc + self.coef.e * (self.yc - self.vertices[-1])
        self.storage.e = ye
        yield from self.func(ye)

    def inside_contract(self) -> Generator[np.ndarray[float, float], None, None]:
        yic = self.yc + self.coef.ic * (self.yc - self.vertices[-1])
        self.storage.ic = yic
        yield from self.func(yic)

    def outside_contract(self) -> Generator[np.ndarray[float, float], None, None]:
        yoc = self.yc + self.coef.oc * (self.yc - self.vertices[-1])
        self.storage.oc = yoc
        yield from self.func(yoc)

    def shrink(self) -> Generator[np.ndarray[float, float], None, None]:
        for i in range(1, len(self.vertices)):
            yield self.vertices[0] + self.coef.s * (self.vertices[i] - self.vertices[0]), 0
        for i in range(1, len(self.vertices)):
            vertex = self.vertex_queue.get()
            self.vertices[i] = vertex.coordinate
            self.values[i] = vertex.value

    def func(self, y: np.ndarray[float, float]) -> Generator[np.ndarray[float, float], None, None]:
        if self.is_within_range(y):
            yield y, 0
        else:
            self.vertex_queue.put(Vertex(y, np.inf))

    def is_within_range(self, coordinates: np.ndarray[float, float]) -> bool:
        return all(not (co < ss[0] or ss[1] < co) for ss, co in zip(self._search_space.values(), coordinates))

    def search(self) -> Generator[np.ndarray[float, float], None, None]:
        yield from self.initial()
        while True:

            self.centroid()
            yield from self.reflect()
            fr = self.vertex_queue.get().value

            if self.values[0] <= fr < self.values[-2]:

                self.vertices[-1] = self.storage.r
                self.values[-1] = fr

            elif fr < self.values[0]:

                yield from self.expand()
                fe = self.vertex_queue.get().value

                if fe < fr:
                    self.vertices[-1] = self.storage.e
                    self.values[-1] = fe

                else:
                    self.vertices[-1] = self.storage.r
                    self.values[-1] = fr

            elif self.values[-2] <= fr < self.values[-1]:

                yield from self.outside_contract()
                foc = self.vertex_queue.get().value

                if foc <= fr:
                    self.vertices[-1] = self.storage.oc
                    self.values[-1] = foc

                else:
                    self.shrink()

            elif self.values[-1] <= fr:

                yield from self.inside_contract()
                fic = self.vertex_queue.get().value

                if fic < self.values[-1]:
                    self.vertices[-1] = self.storage.ic
                    self.values[-1] = fic

                else:
                    yield from self.shrink()


class NelderMeadSampler(optuna.samplers.BaseSampler):
    def __init__(self,
                 search_space: dict[str, list[float]],
                 seed: int | None = None,
                 **coef: float
                 ) -> None:
        self.param_names = []  # パラメータの順序を記憶
        for param_name in sorted(search_space.keys()):
            self.param_names.append(param_name)

        self.NelderMead: NelderMeadAlgorism = NelderMeadAlgorism(search_space, Coef(**coef), seed)
        self.generator = self.NelderMead.search()
        self.ParallelLimit: int = len(search_space) + 1
        self.NumOfRunningTrial: int = 0

    def infer_relative_search_space(self, study: Study, trial: FrozenTrial) -> dict[str, BaseDistribution]:
        return {}

    def sample_relative(
        self, study: Study, trial: FrozenTrial, search_space: dict[str, BaseDistribution]
    ) -> dict[str, Any]:
        return {}

    def before_trial(self, study: Study, trial: FrozenTrial) -> None:
        if self.NumOfRunningTrial == 0 or self.ParallelLimit > 0:
            trial.user_attrs["Coordinate"], self.ParallelLimit = next(self.generator)
            trial.user_attrs["ParallelEnabled"] = self.ParallelLimit > 0
            self.NumOfRunningTrial += 1
        else:
            trial.user_attrs["Coordinate"] = None
            trial.user_attrs["ParallelEnabled"] = False

    def sample_independent(
        self,
        study: Study,
        trial: FrozenTrial,
        param_name: str,
        param_distribution: distributions.BaseDistribution,
    ) -> Any:
        if trial.user_attrs["Coordinate"] is None:
            raise ValueError('trial.user_attrs["Coordinate"] is None')
        param_index = self.param_names.index(param_name)
        param_value = trial.user_attrs["Coordinate"][param_index]

        return param_value

    def after_trial(
        self,
        study: Study,
        trial: FrozenTrial,
        state: TrialState,
        values: Sequence[float] | None,
    ) -> None:
        coordinate = np.array([trial.params[name] for name in self.param_names])
        if isinstance(values, list):
            self.NelderMead.vertex_queue.put(Vertex(coordinate, values[0]))
            self.NumOfRunningTrial -= 1
