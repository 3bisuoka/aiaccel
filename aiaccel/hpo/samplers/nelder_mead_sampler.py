from __future__ import annotations

import queue
import warnings
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
    vertices: np.ndarray
    values: np.ndarray

    def __init__(
        self,
        search_space: dict[str, tuple[float, float]],
        coeff: NelderMeadCoefficient | None = None,
        rng: np.random.RandomState | None = None,
        block: bool = True,
        timeout: int | None = None
    ) -> None:
        self._search_space = search_space
        self.coeff = coeff if coeff is not None else NelderMeadCoefficient()

        self.dimension = len(search_space)

        self.value_queue: queue.Queue[float] = queue.Queue()
        self._rng = rng if rng is not None else np.random.RandomState()

        self.block = block
        self.timeout = timeout

        self.generator = iter(self._generator())

    def get_vertex(self) -> np.ndarray:
        return next(self.generator)

    def put_value(self, value: float) -> None:
        self.value_queue.put(value)

    def _waiting_for_float(self) -> Generator[None, None, float]:
        result = yield from self._waiting_for_list(1)
        return result[0]

    def _waiting_for_list(self, num_waiting: int) -> Generator[None, None, list[float]]:
        results: list[float] = []
        while len(results) < num_waiting:
            try:
                results.append(self.value_queue.get(self.block, self.timeout))
            except queue.Empty:
                yield None

        return results

    def _generator(self) -> Generator[np.ndarray, None, None]:
        # initialization
        lows, highs = zip(*self._search_space.values())
        self.vertices = self._rng.uniform(lows, highs, (self.dimension + 1, self.dimension))
        self.values = np.empty(self.dimension + 1)

        yield from self.vertices
        self.values[:] = yield from self._waiting_for_list(len(self.vertices))

        # main loop
        shrink_requied = False
        while True:
            # sort self.vertices by their self.values
            order = np.argsort(self.values)
            self.vertices, self.values = self.vertices[order], self.values[order]

            # reflect
            yc = self.vertices[:-1].mean(axis=0)
            yield (yr := yc + self.coeff.r * (yc - self.vertices[-1]))
            fr = yield from self._waiting_for_float()

            if self.values[0] <= fr < self.values[-2]:
                self.vertices[-1], self.values[-1] = yr, fr
            elif fr < self.values[0]:  # expand
                yield (ye := yc + self.coeff.e * (yc - self.vertices[-1]))
                fe = yield from self._waiting_for_float()

                self.vertices[-1], self.values[-1] = (ye, fe) if fe < fr else (yr, fr)
            elif self.values[-2] <= fr < self.values[-1]:  # outside contract
                yield (yoc := yc + self.coeff.oc * (yc - self.vertices[-1]))
                foc = yield from self._waiting_for_float()

                if foc <= fr:
                    self.vertices[-1], self.values[-1] = yoc, foc
                else:
                    shrink_requied = True
            elif self.values[-1] <= fr:  # inside contract
                yield (yic := yc + self.coeff.ic * (yc - self.vertices[-1]))
                fic = yield from self._waiting_for_float()

                if fic < self.values[-1]:
                    self.vertices[-1], self.values[-1] = yic, fic
                else:
                    shrink_requied = True

            # shrink
            if shrink_requied:
                self.vertices = self.vertices[0] + self.coeff.s * (self.vertices - self.vertices[0])
                yield from self.vertices[1:]
                self.values[1:] = yield from self._waiting_for_list(len(self.vertices[1:]))

                shrink_requied = False


class NelderMeadSampler(optuna.samplers.BaseSampler):
    def __init__(
        self,
        search_space: dict[str, tuple[float, float]],
        seed: int | None = None,
        coeff: NelderMeadCoefficient | None = None,
    ) -> None:
        self._search_space = search_space

        self.nm = NelderMeadAlgorism(
            search_space=self._search_space,
            coeff=coeff,
            rng=np.random.RandomState(seed),
            block=False,
            timeout=None
            )

        self.running_trial_id: list[int] = []
        self.result_stack: dict[int, float] = {}

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
        # TODO: support parallel execution
        # TODO: support study.enqueue_trial()
        # TODO: system_attrs is deprecated.
        if "fixed_params" in trial.system_attrs:
            raise RuntimeError("NelderMeadSampler does not support enqueue_trial.")

        trial.set_user_attr("params", self._get_params())
        self.running_trial_id.append(trial._trial_id)

    def _get_params(self) -> np.ndarray:
        while True:
            params = self.nm.get_vertex()

            if params is None:
                raise RuntimeError("No more parallel calls to ask() are possible.")

            if all(low < x < high for x, (low, high) in zip(params, self._search_space.values())):
                break
            else:
                self.nm.put_value(np.inf)
        return params

    def sample_independent(
        self,
        study: Study,
        trial: FrozenTrial,
        param_name: str,
        param_distribution: BaseDistribution,
    ) -> Any:
        if trial.user_attrs["params"] is None:
            raise ValueError('trial.user_attrs["params"] is None')
        if param_name not in self._search_space:
            raise ValueError(f"The parameter name, {param_name}, is not found in the given search_space.")

        param_index = list(self._search_space.keys()).index(param_name)
        param_value = trial.user_attrs["params"][param_index]

        contains = param_distribution._contains(param_distribution.to_internal_repr(param_value))
        if not contains:
            warnings.warn(
                f"The value `{param_value}` is out of range of the parameter `{param_name}`. "
                f"The value will be used but the actual distribution is: `{param_distribution}`.", stacklevel=2)
        return param_value

    def after_trial(
        self,
        study: Study,
        trial: FrozenTrial,
        state: TrialState,
        values: Sequence[float] | None,
    ) -> None:
        if isinstance(values, list):
            self.stack[trial._trial_id] = values[0]

            if len(self.running_trial_id) == len(self.stack):
                for trial_id in self.running_trial_id:
                    self.nm.put_value(self.stack[trial_id])
                self.running_trial_id = []
                self.stack = {}
