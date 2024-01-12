import unittest
import optuna
import datetime

import numpy as np

from aiaccel.hpo.samplers.nelder_mead_sampler import NelderMeadSampler, NelderMeadState, Simplex


class TestSimplex(unittest.TestCase):
    def setUp(self):
        self.simplex = Simplex()
        self.vertices = np.array([[1.0, 2.0], [3.0, 4.0]])

    def test_add_vertices(self):
        self.simplex.add_vertices(self.vertices[0])
        self.assertTrue(np.array_equal(self.simplex.vertices, self.vertices[:1]))

        self.simplex.add_vertices(self.vertices[1])
        self.assertTrue(np.array_equal(self.simplex.vertices, self.vertices))

    def test_update_vertices(self):
        vertices2 = np.array([[1.0, 2.0], [5.0, 6.0]])
        self.simplex.add_vertices(self.vertices[0])
        self.simplex.add_vertices(self.vertices[1])

        self.simplex.update_vertices(1, vertices2[1])
        self.assertTrue(np.array_equal(self.simplex.vertices, vertices2))

    def test_num_of_vertices(self):
        self.simplex.add_vertices(self.vertices[0])
        self.assertEqual(self.simplex.num_of_vertices(), 1)

        self.simplex.add_vertices(self.vertices[1])
        self.assertEqual(self.simplex.num_of_vertices(), 2)


class TestSimplexOperation(unittest.TestCase):
    def setUp(self):
        self.simplex = Simplex()
        self.vertices = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
        self.values = np.array([5.0, 3.0, 7.0])
        for vertex, value in zip(self.vertices, self.values):
            self.simplex.add_vertices(vertex, value)

    def test_order_by(self):
        self.simplex.order_by()

        self.assertTrue(np.array_equal(self.simplex.vertices[0], self.vertices[1]))
        self.assertTrue(np.array_equal(self.simplex.values[0], self.values[1]))
        self.assertTrue(np.array_equal(self.simplex.vertices[1], self.vertices[0]))
        self.assertTrue(np.array_equal(self.simplex.values[1], self.values[0]))
        self.assertTrue(np.array_equal(self.simplex.vertices[2], self.vertices[2]))
        self.assertTrue(np.array_equal(self.simplex.values[2], self.values[2]))

    def test_calc_centroid(self):
        centroid_xs = np.array([2, 3])

        self.simplex.calc_centroid()
        self.assertTrue(np.array_equal(self.simplex.centroid, centroid_xs))

    def test_reflect(self):
        reflect_xs = np.array([-1.0, 0.0])

        self.simplex.calc_centroid()
        xr = self.simplex.reflect()
        self.assertTrue(np.array_equal(xr, reflect_xs))

    def test_expand(self):
        expand_xs = np.array([-4.0, -3.0])

        self.simplex.calc_centroid()
        xe = self.simplex.expand()
        self.assertTrue(np.array_equal(xe, expand_xs))

    def test_inside_contract(self):
        inside_contract_xs = np.array([3.5, 4.5])

        self.simplex.calc_centroid()
        xic = self.simplex.inside_contract()
        self.assertTrue(np.array_equal(xic, inside_contract_xs))

    def test_outside_contract(self):
        outside_contract_xs = np.array([0.5, 1.5])

        self.simplex.calc_centroid()
        xoc = self.simplex.outside_contract()
        self.assertTrue(np.array_equal(xoc, outside_contract_xs))

    def test_shrink(self):
        shrink_xs = np.array([[3.0, 4.0], [2.0, 3.0], [4.0, 5.0]])

        self.simplex.calc_centroid()
        xsh = self.simplex.shrink()
        self.assertTrue(np.array_equal(xsh, shrink_xs))
        self.assertTrue(np.array_equal(self.simplex.vertices[0], self.vertices[1]))
        self.assertTrue(np.array_equal(self.simplex.values[0], self.values[1]))
        self.assertEqual(len(self.simplex.vertices), 1)
        self.assertEqual(len(self.simplex.values), 1)


class TestNelderMeadSamplerOperation(unittest.TestCase):
    def setUp(self):
        search_space = {"x": [-5, 5], "y": [-5, 5]}
        self.sampler = NelderMeadSampler(search_space=search_space, seed=42)
        self.vertices = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
        self.values = np.array([5.0, 3.0, 7.0])
        for vertex, value in zip(self.vertices, self.values):
            self.sampler.simplex.add_vertices(vertex, value)
        self.sampler.simplex.calc_centroid()

    def test_after_initialize(self):
        self.sampler.after_initialize()

        self.assertEqual(self.sampler.state, NelderMeadState.Reflect)

    def test_reflect(self):
        reflect_xs = np.array([-1.0, 0.0])
        xr = self.sampler.reflect()

        self.assertTrue(np.array_equal(xr, reflect_xs))

    def test_after_reflect_to_reflect(self):
        # self.simplex.vertices[0] <= self.store.r < self.simplex.vertices[-2]
        reflect_xs = np.array([-1.0, 0.0])
        reflect_value = 4.0

        self.sampler.store.r = self.sampler.reflect()
        self.sampler.after_reflect(reflect_value)

        self.assertEqual(self.sampler.state, NelderMeadState.Reflect)
        vertex = self.sampler.simplex.vertices[-1]
        self.assertTrue(np.array_equal(vertex, reflect_xs))
        value = self.sampler.simplex.values[-1]
        self.assertTrue(np.array_equal(value, reflect_value))

    def test_after_reflect_to_expand(self):
        # self.store.r < self.simplex.vertices[0]
        objective = 2.0

        self.sampler.store.r = self.sampler.reflect()
        self.sampler.after_reflect(objective)

        self.assertEqual(self.sampler.state, NelderMeadState.Expand)

    def test_after_reflect_to_outside_contract(self):
        # self.simplex.vertices[-2] <= self.store.r < self.simplex.vertices[-1]
        objective = 6.0

        self.sampler.store.r = self.sampler.reflect()
        self.sampler.after_reflect(objective)

        self.assertEqual(self.sampler.state, NelderMeadState.OutsideContract)

    def test_after_reflect_to_inside_contract(self):
        # self.simplex.vertices[-1] <= self.store.r
        objective = 8.0

        self.sampler.store.r = self.sampler.reflect()
        self.sampler.after_reflect(objective)

        self.assertEqual(self.sampler.state, NelderMeadState.InsideContract)

    def test_expand(self):
        expand_xs = np.array([-4.0, -3.0])

        xe = self.sampler.expand()

        self.assertTrue(np.array_equal(xe, expand_xs))

    def test_after_expand_less_than_r(self):
        # self.store.e < self.store.r:
        reflect_value = 2.0
        expand_value = 1.0
        expand_xs = np.array([-4.0, -3.0])

        self.sampler.store.r = self.sampler.reflect()
        self.sampler.after_reflect(reflect_value)
        self.sampler.store.e = self.sampler.expand()
        self.sampler.after_expand(expand_value)

        self.assertEqual(self.sampler.state, NelderMeadState.Reflect)
        vertex = self.sampler.simplex.vertices[-1]
        self.assertTrue(np.array_equal(vertex, expand_xs))
        value = self.sampler.simplex.values[-1]
        self.assertTrue(np.array_equal(value, expand_value))

    def test_after_expand_more_than_r(self):
        # else (self.store.r <= self.store.e):
        reflect_value = 2.0
        expand_value = 3.0
        reflect_xs = np.array([-1.0, 0.0])

        self.sampler.store.r = self.sampler.reflect()
        self.sampler.after_reflect(reflect_value)
        self.sampler.store.e = self.sampler.expand()
        self.sampler.after_expand(expand_value)

        self.assertEqual(self.sampler.state, NelderMeadState.Reflect)
        vertex = self.sampler.simplex.vertices[-1]
        self.assertTrue(np.array_equal(vertex, reflect_xs))
        value = self.sampler.simplex.values[-1]
        self.assertTrue(np.array_equal(value, reflect_value))

    def test_inside_contract(self):
        inside_contract_xs = np.array([3.5, 4.5])

        xic = self.sampler.inside_contract()

        self.assertTrue(np.array_equal(xic, inside_contract_xs))

    def test_after_inside_contract_to_reflect(self):
        # self.store.ic < self.simplex.vertices[-1]
        reflect_value = 8.0
        inside_contract_value = 6.0
        inside_contract_xs = np.array([3.5, 4.5])

        self.sampler.store.r = self.sampler.reflect()
        self.sampler.after_reflect(reflect_value)
        self.sampler.store.ic = self.sampler.inside_contract()
        self.sampler.after_inside_contract(inside_contract_value)

        self.assertEqual(self.sampler.state, NelderMeadState.Reflect)
        vertex = self.sampler.simplex.vertices[-1]
        self.assertTrue(np.array_equal(vertex, inside_contract_xs))
        value = self.sampler.simplex.values[-1]
        self.assertTrue(np.array_equal(value, inside_contract_value))

    def test_after_inside_contract_to_shrink(self):
        # else (self.simplex.vertices[-1] <= self.store.ic)
        reflect_value = 8.0
        inside_contract_value = 8.0

        self.sampler.store.r = self.sampler.reflect()
        self.sampler.after_reflect(reflect_value)
        self.sampler.store.ic = self.sampler.inside_contract()
        self.sampler.after_inside_contract(inside_contract_value)

        self.assertEqual(self.sampler.state, NelderMeadState.Shrink)

    def test_outside_contract(self):
        outside_contract_xs = np.array([0.5, 1.5])

        xoc = self.sampler.outside_contract()
        self.assertTrue(np.array_equal(xoc, outside_contract_xs))

    def test_after_outside_contract_to_reflect(self):
        # self.store.oc <= self.store.r
        reflect_value = 6.0
        outside_contract_value = 5.0
        outside_contract_xs = np.array([0.5, 1.5])

        self.sampler.store.r = self.sampler.reflect()
        self.sampler.after_reflect(reflect_value)
        self.sampler.store.oc = self.sampler.outside_contract()
        self.sampler.after_outside_contract(outside_contract_value)

        self.assertEqual(self.sampler.state, NelderMeadState.Reflect)
        vertex = self.sampler.simplex.vertices[-1]
        self.assertTrue(np.array_equal(vertex, outside_contract_xs))
        value = self.sampler.simplex.values[-1]
        self.assertTrue(np.array_equal(value, outside_contract_value))

    def test_after_outside_contract_to_shrink(self):
        # else (self.store.r < self.store.oc)
        reflect_value = 6.0
        outside_contract_value = 7.0

        self.sampler.store.r = self.sampler.reflect()
        self.sampler.after_reflect(reflect_value)
        self.sampler.store.oc = self.sampler.outside_contract()
        self.sampler.after_outside_contract(outside_contract_value)

        self.assertEqual(self.sampler.state, NelderMeadState.Shrink)

    def test_shrink(self):
        shrink_xs = np.array([[3.0, 4.0], [2.0, 3.0], [4.0, 5.0]])
        min_value = self.sampler.simplex.values[0]

        xsh = self.sampler.shrink()
        self.assertTrue(np.array_equal(xsh, shrink_xs))
        vertex = self.sampler.simplex.vertices[0]
        self.assertTrue(np.array_equal(vertex, shrink_xs[0]))
        value = self.sampler.simplex.values[0]
        self.assertEqual(value, min_value)

    def test_aftter_shrink(self):
        self.sampler.after_shrink()

        self.assertEqual(self.sampler.state, NelderMeadState.Reflect)

    def test_is_within_range(self):
        # True
        coordinates = np.array([3.0, 4.0])
        self.assertTrue(self.sampler.is_within_range(coordinates))

        # False
        coordinates = np.array([-6.0, 4.0])
        self.assertFalse(self.sampler.is_within_range(coordinates))
        coordinates = np.array([6.0, 4.0])
        self.assertFalse(self.sampler.is_within_range(coordinates))
        coordinates = np.array([3.0, -6.0])
        self.assertFalse(self.sampler.is_within_range(coordinates))
        coordinates = np.array([3.0, 6.0])
        self.assertFalse(self.sampler.is_within_range(coordinates))

    def test_get_next_coordinates_initial(self):
        self.sampler.get_next_coordinates()
        self.assertTrue(np.array_equal(self.sampler.x, np.array([])))

    def test_get_next_coordinates_reflect(self):
        reflect_xs = np.array([-1.0, 0.0])

        self.sampler.state = NelderMeadState.Reflect
        self.sampler.get_next_coordinates()
        self.assertTrue(np.array_equal(self.sampler.x, reflect_xs))

    def test_get_next_coordinates_expand(self):
        expand_xs = np.array([-4.0, -3.0])

        self.sampler.state = NelderMeadState.Expand
        self.sampler.get_next_coordinates()
        self.assertTrue(np.array_equal(self.sampler.x, expand_xs))

    def test_get_next_coordinates_inside_contract(self):
        inside_contract_xs = np.array([3.5, 4.5])

        self.sampler.state = NelderMeadState.InsideContract
        self.sampler.get_next_coordinates()
        self.assertTrue(np.array_equal(self.sampler.x, inside_contract_xs))

    def test_get_next_coordinates_outside_contract(self):
        outside_contract_xs = np.array([0.5, 1.5])

        self.sampler.state = NelderMeadState.OutsideContract
        self.sampler.get_next_coordinates()
        self.assertTrue(np.array_equal(self.sampler.x, outside_contract_xs))

    def test_get_next_coordinates_shrink(self):
        shrink_xs = np.array([[2.0, 3.0], [4.0, 5.0]])

        self.sampler.state = NelderMeadState.Shrink
        self.sampler.get_next_coordinates()
        self.assertTrue(np.array_equal(self.sampler.x, shrink_xs[0]))
        self.assertTrue(np.array_equal(self.sampler.xs, shrink_xs))

    def test_get_next_coordinates_reflect_out_of_range(self):
        expand_xs = np.array([3.5, 4.5])

        self.sampler._search_space["x"] = [0.0, 5.0]
        self.sampler.state = NelderMeadState.Reflect
        self.sampler.get_next_coordinates()
        self.assertTrue(np.array_equal(self.sampler.x, expand_xs))

    def test_set_objective_initial(self):
        self.sampler.simplex = Simplex()
        initial_xs = [
            np.array([1.0, 2.0]),
            np.array([3.0, 4.0]),
            np.array([5.0, 6.0])
        ]
        initial_value = [5.0, 3.0, 7.0]

        self.sampler.set_objective(initial_xs[0], initial_value[0])
        self.assertEqual(self.sampler.state, NelderMeadState.Initial)
        vertex = self.sampler.simplex.vertices[0]
        self.assertTrue(np.array_equal(vertex, initial_xs[0]))
        value = self.sampler.simplex.values[0]
        self.assertTrue(np.array_equal(value, initial_value[0]))

        self.sampler.set_objective(initial_xs[1], initial_value[1])
        self.assertEqual(self.sampler.state, NelderMeadState.Initial)
        vertex = self.sampler.simplex.vertices[1]
        self.assertTrue(np.array_equal(vertex, initial_xs[1]))
        value = self.sampler.simplex.values[1]
        self.assertTrue(np.array_equal(value, initial_value[1]))

        self.sampler.set_objective(initial_xs[2], initial_value[2])
        self.assertEqual(self.sampler.state, NelderMeadState.Reflect)
        vertex = self.sampler.simplex.vertices[2]
        self.assertTrue(np.array_equal(vertex, initial_xs[2]))
        value = self.sampler.simplex.values[2]
        self.assertTrue(np.array_equal(value, initial_value[2]))

    def test_set_objective_reflect(self):
        reflect_xs = np.array([-1.0, 0.0])
        reflect_value = 4.0

        self.sampler.state = NelderMeadState.Reflect
        self.sampler.store.r = self.sampler.reflect()
        self.sampler.set_objective(reflect_xs, reflect_value)

        self.assertEqual(self.sampler.state, NelderMeadState.Reflect)
        vertex = self.sampler.simplex.vertices[-1]
        self.assertTrue(np.array_equal(vertex, reflect_xs))
        value = self.sampler.simplex.values[-1]
        self.assertTrue(np.array_equal(value, reflect_value))

    def test_set_objective_expand(self):
        reflect_value = 2.0
        expand_value = 1.0
        expand_xs = np.array([-4.0, -3.0])

        self.sampler.state = NelderMeadState.Expand
        self.sampler.store.r = self.sampler.reflect()
        self.sampler.after_reflect(reflect_value)
        self.sampler.store.e = self.sampler.expand()
        self.sampler.set_objective(expand_xs, expand_value)

        self.assertEqual(self.sampler.state, NelderMeadState.Reflect)
        vertex = self.sampler.simplex.vertices[-1]
        self.assertTrue(np.array_equal(vertex, expand_xs))
        value = self.sampler.simplex.values[-1]
        self.assertTrue(np.array_equal(value, expand_value))

    def test_set_objective_inside_contract(self):
        reflect_value = 8.0
        inside_contract_value = 6.0
        inside_contract_xs = np.array([3.5, 4.5])

        self.sampler.state = NelderMeadState.InsideContract
        self.sampler.store.r = self.sampler.reflect()
        self.sampler.after_reflect(reflect_value)
        self.sampler.store.ic = self.sampler.inside_contract()
        self.sampler.set_objective(inside_contract_xs, inside_contract_value)

        self.assertEqual(self.sampler.state, NelderMeadState.Reflect)
        vertex = self.sampler.simplex.vertices[-1]
        self.assertTrue(np.array_equal(vertex, inside_contract_xs))
        value = self.sampler.simplex.values[-1]
        self.assertTrue(np.array_equal(value, inside_contract_value))

    def test_set_objective_outside_contract(self):
        reflect_value = 6.0
        outside_contract_value = 5.0
        outside_contract_xs = np.array([0.5, 1.5])

        self.sampler.state = NelderMeadState.OutsideContract
        self.sampler.store.r = self.sampler.reflect()
        self.sampler.after_reflect(reflect_value)
        self.sampler.store.oc = self.sampler.outside_contract()
        self.sampler.set_objective(outside_contract_xs, outside_contract_value)

        self.assertEqual(self.sampler.state, NelderMeadState.Reflect)
        vertex = self.sampler.simplex.vertices[-1]
        self.assertTrue(np.array_equal(vertex, outside_contract_xs))
        value = self.sampler.simplex.values[-1]
        self.assertTrue(np.array_equal(value, outside_contract_value))

    def test_set_objective_shrink(self):
        shrink_xs = np.array([[2.0, 3.0], [4.0, 5.0]])
        shrink_value = [4.0, 6.0]
        self.sampler.state = NelderMeadState.Shrink
        self.sampler.xs = self.sampler.shrink()[1:]

        self.sampler.set_objective(shrink_xs[0], shrink_value[0])
        self.assertEqual(self.sampler.state, NelderMeadState.Shrink)
        vertex = self.sampler.simplex.vertices[1]
        self.assertTrue(np.array_equal(vertex, shrink_xs[0]))
        value = self.sampler.simplex.values[1]
        self.assertTrue(np.array_equal(value, shrink_value[0]))

        self.sampler.set_objective(shrink_xs[1], shrink_value[1])
        self.assertEqual(self.sampler.state, NelderMeadState.Reflect)
        vertex = self.sampler.simplex.vertices[2]
        self.assertTrue(np.array_equal(vertex, shrink_xs[1]))
        value = self.sampler.simplex.values[2]
        self.assertTrue(np.array_equal(value, shrink_value[1]))


class TestNelderMeadSampler(unittest.TestCase):
    def setUp(self):
        search_space = {"x": [-5, 5], "y": [-5, 5]}
        self.sampler = NelderMeadSampler(search_space=search_space, seed=42)

        self.study = optuna.create_study(sampler=self.sampler)
        self.state = optuna.trial.TrialState.COMPLETE
        self.param_distribution = optuna.distributions.FloatDistribution(-5, 5)
        self.trial = optuna.trial.FrozenTrial(
            number=0,
            state=self.state,
            value=[0.0],
            datetime_start=datetime.datetime.now(),
            datetime_complete=datetime.datetime.now(),
            params={"x": 0.0, "y": 1.0},
            distributions=self.param_distribution,
            user_attrs={},
            system_attrs={},
            intermediate_values={},
            trial_id=0,
        )

    def test_infer_relative_search_space(self):
        self.assertEqual(self.sampler.infer_relative_search_space(self.study, self.trial), {})

    def test_sample_relative(self):
        self.assertEqual(self.sampler.sample_relative(self.study, self.trial, self.param_distribution), {})

    def test_before_trial(self):
        self.sampler.before_trial(self.study, self.trial)
        self.assertTrue(np.array_equal(self.sampler.x, np.array([])))

    def test_sample_independent_initial(self):
        value = self.sampler.sample_independent(self.study, self.trial, "x", self.param_distribution)
        self.assertIsInstance(value, float)
        self.assertGreaterEqual(value, -5.0)
        self.assertLessEqual(value, 5.0)

        value = self.sampler.sample_independent(self.study, self.trial, "y", self.param_distribution)
        self.assertIsInstance(value, float)
        self.assertGreaterEqual(value, -5.0)
        self.assertLessEqual(value, 5.0)

    def test_sample_independent_reflect(self):
        self.vertices = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
        self.values = np.array([5.0, 3.0, 7.0])
        for vertex, value in zip(self.vertices, self.values):
            self.sampler.simplex.add_vertices(vertex, value)
        self.sampler.simplex.calc_centroid()
        self.sampler.state = NelderMeadState.Reflect
        self.sampler.before_trial(self.study, self.trial)

        reflect_xs = [-1.0, 0.0]
        value = self.sampler.sample_independent(self.study, self.trial, "x", self.param_distribution)
        self.assertEqual(value, reflect_xs[0])

        value = self.sampler.sample_independent(self.study, self.trial, "y", self.param_distribution)
        self.assertEqual(value, reflect_xs[1])

    def test_after_trial(self):
        values = [0.0]
        initial_xs = np.array([0.0, 1.0])
        self.sampler.after_trial(self.study, self.trial, self.state, values)

        self.assertEqual(self.sampler.state, NelderMeadState.Initial)
        vertex = self.sampler.simplex.vertices[0]
        self.assertTrue(np.array_equal(vertex, initial_xs))
        value = self.sampler.simplex.values[0]
        self.assertEqual(value, values[0])
