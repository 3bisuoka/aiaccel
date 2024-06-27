#!/usr/bin/env python
import argparse
import csv
import os
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import cocoex
import optuna
import pandas as pd

from aiaccel.hpo.samplers.nelder_mead_sampler import NelderMeadEmptyError, NelderMeadSampler


def _optimize_sequential(
        study: optuna.Study,
        func: Callable[[list[float]], float],
        search_space: dict[str, tuple[float, float]]
        ) -> float | None:
    try:
        trial = study.ask()
    except NelderMeadEmptyError:
        return None
    param = []
    for name, distribution in search_space.items():
        param.append(trial.suggest_float(name, *distribution))

    result = func(param)
    time.sleep(0.1)

    frozentrial = study.tell(trial, result)
    study._log_completed_trial(frozentrial)
    return result


def _optimize_sequential_wrapper(args: list[Any]) -> float | None:
    return _optimize_sequential(*args)


def optimize(
    study: optuna.Study,
    func: Callable[[list[float]], float],
    search_space: dict[str, tuple[float, float]],
    result_csv_name: str,
    num_trial: int = 1000,
    num_parallel: int = 10,
) -> None:
    csv_array: list[list[str | float]] = [["step", "value"]]

    with ThreadPoolExecutor(max_workers=num_parallel) as executor:
        for step in range(int(num_trial / num_parallel)):
            results = executor.map(
                _optimize_sequential_wrapper, [(study, func, search_space) for _ in range(num_parallel)]
                )
            for result in results:
                if result is not None:
                    csv_array.append([step, result])

    with open(result_csv_name, "w") as f:
        writer = csv.writer(f)
        writer.writerows(csv_array)


def create_optuna_result(
    study: optuna.Study,
    output_folder: str,
    problem: Any,
    optuna_seed: int
) -> None:
    study_df = study.trials_dataframe()
    result_dir = "optuna_csv/" + output_folder + f"/f{problem.id_function}/DM{problem.dimension:02}"
    os.makedirs(result_dir, exist_ok=True)
    study_df.to_csv(result_dir + f"/result_{problem.id}_{optuna_seed:03}.csv")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--func_id")
    parser.add_argument("--dim")
    args = parser.parse_args()

    func_id = int(args.func_id)
    dim = int(args.dim)

    ### input
    suite_name = "bbob"
    output_folder = f"optuna-neldermead-subTPE-mcTmvF-func_id{func_id}-dim{dim}"
    budget_multiplier = 200  # increase to 10, 100, ...

    ### prepare
    suite_options = f"function_indices: {func_id} dimensions: {dim}"
    print(suite_options)
    suite = cocoex.Suite(suite_name, "", suite_options)
    observer = cocoex.Observer(suite_name, "result_folder: " + output_folder)
    minimal_print = cocoex.utilities.MiniPrint()

    num_parallel = 10
    optuna_seed = 1

    # ### go
    for problem in suite:  # this loop will take several minutes or longer
        problem.observe_with(observer)  # generates the data for cocopp post-processing

        search_space = {}
        for i in range(problem.dimension):
            search_space[f"x{i}"] = (-5.0, 5.0)
        print(search_space)

        # NM+subTPE
        sub_sampler = optuna.samplers.TPESampler(seed=optuna_seed, consider_magic_clip=True, multivariate=False)
        study = optuna.create_study(
            sampler=NelderMeadSampler(
                search_space=search_space, seed=optuna_seed, block=False, sub_sampler=sub_sampler
            )
        )

        num_trial = budget_multiplier*problem.dimension
        step_csv_dir = "step_csv/" + output_folder + f"/f{problem.id_function}/DM{problem.dimension:02}/"
        os.makedirs(step_csv_dir, exist_ok=True)
        optimize(
            study, problem, search_space,
            step_csv_dir + f"result_{problem.id}_{optuna_seed:03}.csv", num_trial, num_parallel
            )

        create_optuna_result(study, output_folder, problem, optuna_seed)

        optuna_seed += 1

        minimal_print(problem, final=problem.index == len(suite) - 1)

    # result - f_opt
    for i, problem in enumerate(suite):
        coco_file_path = (
            "exdata/"
            + f"{output_folder}/"
            + f"data_f{problem.id_function}/bbobexp_f{problem.id_function}_DIM{problem.dimension}_i1.rdat"
            )

        with open(coco_file_path) as f:
            data = f.readlines()

        f_opt = float(data[i % 15].split(" ")[12][1:-1])
        print(f_opt)

        optuna_result_dir = "optuna_csv/" + output_folder + f"/f{problem.id_function}/DM{problem.dimension:02}/"
        optuna_seed = i + 1
        df = pd.read_csv(optuna_result_dir + f"result_{problem.id}_{optuna_seed:03}.csv")
        df["value - f_opt"] = df["value"] - f_opt

        print(df)
        df.to_csv(optuna_result_dir + f"result_{problem.id}_{optuna_seed:03}_fopt.csv")

        step_csv_dir = "step_csv/" + output_folder + f"/f{problem.id_function}/DM{problem.dimension:02}/"
        df = pd.read_csv(step_csv_dir + f"result_{problem.id}_{optuna_seed:03}.csv")
        df["value - f_opt"] = df["value"] - f_opt

        print(df)
        df.to_csv(step_csv_dir + f"result_{problem.id}_{optuna_seed:03}_fopt.csv")
