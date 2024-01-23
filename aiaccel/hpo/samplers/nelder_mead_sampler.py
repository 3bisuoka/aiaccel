from __future__ import annotations

import itertools
import queue
from collections.abc import Generator
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np
import optuna
from optuna.distributions import BaseDistribution
from optuna.study import Study
from optuna.trial import FrozenTrial, TrialState


@dataclass
class NelderMeadCoefficient:
    r: float = 1.0
    ic: float = -0.5
    oc: float = 0.5
    e: float = 2.0
    s: float = 0.5


class NelderMeadAlgorism:
    def __init__(
        self,
        search_space: dict[str, list[float]],
        coeff: NelderMeadCoefficient | None,
        seed: int | None = None,
        num_iterations: int | None = None,
    ) -> None:
        self._search_space = search_space
        self.coeff = coeff if coeff is not None else NelderMeadCoefficient()
        self.num_iterations = num_iterations

        self.dimension = len(search_space)

        self.vertex_queue: queue.Queue[float] = queue.Queue()
        np.random.seed(seed)

    def __iter__(self) -> Generator[np.ndarray[float, float], None, None]:
        # initialization
        lows, highs = zip(*self._search_space.values())
        vertices = np.random.uniform(lows, highs, (self.dimension + 1, self.dimension))

        yield from iter(vertices)
        values = np.array([self.vertex_queue.get() for _ in range(len(vertices))])

        # main loop
        shrink_requied = False
        for _ in range(self.num_iterations) if self.num_iterations is not None else itertools.count():
            # sort vertices by their values
            order = np.argsort(values)
            vertices, values = vertices[order], values[order]

            # reflect
            yc = vertices[:-1].mean(axis=0)
            yield (yr := yc + self.coeff.r * (yc - vertices[-1]))

            fr = self.vertex_queue.get()

            if values[0] <= fr < values[-2]:
                vertices[-1], values[-1] = yr, fr
            elif fr < values[0]:  # expand
                yield (ye := yc + self.coeff.e * (yc - vertices[-1]))
                fe = self.vertex_queue.get()

                vertices[-1], values[-1] = (ye, fe) if fe < fr else (yr, fr)
            elif values[-2] <= fr < values[-1]:  # outside contract
                yield (yoc := yc + self.coeff.oc * (yc - vertices[-1]))
                foc = self.vertex_queue.get()

                if foc <= fr:
                    vertices[-1], values[-1] = yoc, foc
                else:
                    shrink_requied = True
            elif values[-1] <= fr:  # inside contract
                yield (yic := yc + self.coeff.ic * (yc - vertices[-1]))
                fic = self.vertex_queue.get()

                if fic < values[-1]:
                    vertices[-1], values[-1] = yic, fic
                else:
                    shrink_requied = True

            # shrink
            if shrink_requied:
                vertices[1:] = [vertices[0] + self.coeff.s * (v - vertices[0]) for v in vertices[1:]]
                yield from iter(vertices[1:])

                values[1:] = [self.vertex_queue.get() for _ in range(len(vertices) - 1)]

                shrink_requied = False


class NelderMeadSampler(optuna.samplers.BaseSampler):
    def __init__(
        self,
        search_space: dict[str, list[float]],
        seed: int | None = None,
        num_iterations: int | None = None,
        coeff: NelderMeadCoefficient | None = None,
    ) -> None:
        self.param_names = []  # パラメータの順序を記憶
        self._search_space = {}
        for param_name, param_distribution in sorted(search_space.items()):
            self.param_names.append(param_name)
            self._search_space[param_name] = list(param_distribution)

        self.nm = NelderMeadAlgorism(self._search_space, coeff, seed, num_iterations)
        self.nm_generator = iter(self.nm)
        self.num_running_trial = 0

        self.stack: dict[int, float] = {}

    def is_within_range(self, coordinates: np.ndarray[float, float]) -> bool:
        return all(low < x < high for x, (low, high) in zip(coordinates, self._search_space.values()))

    def infer_relative_search_space(self, study: Study, trial: FrozenTrial) -> dict[str, BaseDistribution]:
        return {}

    def sample_relative(
        self,
        study: Study,
        trial: FrozenTrial,
        search_space: dict[str, BaseDistribution],
    ) -> dict[str, Any]:
        return {}

    def before_trial(self, study: Study, trial: FrozenTrial) -> None:
        if self.num_running_trial == 0:
            trial.user_attrs["Coordinate"] = next(self.nm_generator)
            if self.is_within_range(trial.user_attrs["Coordinate"]):
                self.num_running_trial += 1
            else:
                self.nm.vertex_queue.put(np.inf)
                self.before_trial(study, trial)
        else:
            trial.user_attrs["Coordinate"] = None

    def sample_independent(
        self,
        study: Study,
        trial: FrozenTrial,
        param_name: str,
        param_distribution: BaseDistribution,
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
        if isinstance(values, list):
            self.num_running_trial -= 1
            self.stack[trial._trial_id] = values[0]
            if self.num_running_trial == 0:
                for value in [item[1] for item in sorted(self.stack.items())]:
                    self.nm.vertex_queue.put(value)
                self.stack = {}
