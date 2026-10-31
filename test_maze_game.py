"""Unit tests for score decay, maze parsing, movement, and encrypted scores."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from maze_game import (
    DEFAULT_BINDINGS,
    InfiniteScoreStore,
    Maze,
    ScoreStore,
    assign_binding,
    generate_infinite_level,
    infinite_speed_multiplier,
    level_score,
)


class MazeGameTests(unittest.TestCase):
    def test_default_quit_binding_is_escape_only(self):
        """Quit defaults to Escape without a Q binding."""
        self.assertEqual(DEFAULT_BINDINGS["quit"], ["escape", ""])

    def test_assign_binding_unbinds_existing_duplicate(self):
        """A key can belong to only one control slot."""
        bindings = {
            "up": ["w", "up"],
            "pause": ["p", ""],
            "quit": ["q", ""],
        }

        assign_binding(bindings, "pause", 1, "w")

        self.assertEqual(bindings["pause"], ["p", "w"])
        self.assertEqual(bindings["up"], ["", "up"])

    def test_score_decays_with_time(self):
        """A faster level completion earns more points."""
        self.assertGreater(level_score(1), level_score(20))
        self.assertGreater(level_score(20), level_score(120))
        self.assertGreater(level_score(20), 300)

    def test_infinite_speed_uses_two_piecewise_curves(self):
        """Infinite speed reaches 3x at level 20 and 5x at level 40."""
        self.assertAlmostEqual(infinite_speed_multiplier(1), 1.0)
        self.assertAlmostEqual(infinite_speed_multiplier(20), 3.0)
        self.assertAlmostEqual(infinite_speed_multiplier(40), 5.0)
        self.assertEqual(infinite_speed_multiplier(100), 5.0)

    def test_maze_finds_start_goal_and_walls(self):
        """The parser locates both endpoints and blocks wall cells."""
        maze = Maze.from_rows(("#####", "#S E#", "#####"))
        self.assertEqual(maze.start, (1, 1))
        self.assertEqual(maze.goal, (3, 1))
        self.assertTrue(maze.is_wall(0, 1))
        self.assertFalse(maze.is_wall(2, 1))
        self.assertTrue(maze.is_subcell_wall(0, 3))
        self.assertFalse(maze.is_subcell_wall(7, 4))
        self.assertTrue(maze.is_goal_subcell(9, 4))

    def test_infinite_levels_are_valid_and_repeatable(self):
        """Infinite-mode mazes have endpoints and are deterministic by level."""
        first = generate_infinite_level(1)
        self.assertEqual(first, generate_infinite_level(1))
        maze = Maze.from_rows(first)
        self.assertEqual(maze.start, (1, 1))
        self.assertEqual(maze.goal, (13, 9))
        self.assertFalse(maze.is_wall(*maze.start))
        self.assertFalse(maze.is_wall(*maze.goal))

    def test_infinite_generation_can_be_reset_for_a_new_run(self):
        """A new run starts without retaining generated maze history."""
        first = generate_infinite_level(1, seed=10)
        second = generate_infinite_level(1, seed=20)
        self.assertNotEqual(first, second)

    def test_score_store_keeps_encrypted_top_ten(self):
        """Scores are capped at ten and the on-disk bytes are not plain text."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = ScoreStore(root / "scores.dat", root / "scores.key")
            for score in range(12):
                store.add(score)
            self.assertEqual(store.load(), list(range(11, 1, -1)))
            self.assertNotIn(b"11,10", (root / "scores.dat").read_bytes())

    def test_invalid_score_file_is_safe(self):
        """A tampered ciphertext does not crash the game or create fake scores."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scores.dat").write_bytes(b"not encrypted")
            store = ScoreStore(root / "scores.dat", root / "scores.key")
            self.assertEqual(store.load(), [])

    def test_infinite_score_store_ranks_levels_then_score(self):
        """Infinite records keep both metrics and rank deeper runs first."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = InfiniteScoreStore(root / "infinite.dat", root / "key")
            store.add(900, 4)
            store.add(700, 5)
            store.add(1000, 4)
            store.add(0, 0)
            self.assertEqual(store.load(), [(700, 5), (1000, 4), (900, 4)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
