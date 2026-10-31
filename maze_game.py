"""A ten-level pygame maze game with encrypted top-score persistence."""

from __future__ import annotations

import math
import os
import json
import random
import sys
import time
import ctypes
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

try:
    import pygame
except ModuleNotFoundError:
    pygame = None

PROJECT_DIR = Path(__file__).resolve().parent
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", PROJECT_DIR))
DATA_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else PROJECT_DIR
WIDTH, HEIGHT = 900, 650
# Keep the larger cell size evenly divisible by the three-times finer grid.
CELL = 48
SUBDIVISIONS = 3
SUBCELL = CELL // SUBDIVISIONS
MAX_LIVES = 3
TOTAL_LEVELS = 10
SCORE_DECAY_SECONDS = 20.0
MOVE_INTERVAL_SECONDS = 0.16
PLAYER_SPEED = SUBCELL / MOVE_INTERVAL_SECONDS * 1.5
HARD_MODE_SPEED_MULTIPLIER = 2.0
HARD_MODE_SCORE_MULTIPLIER = 1.2
WALL_COYOTE_SECONDS = 0.05
SCORE_FILE = DATA_DIR / ".scores.dat"
INFINITE_SCORE_FILE = DATA_DIR / ".infinite_scores.dat"
KEY_FILE = DATA_DIR / ".scores.key"
SOUNDS_DIR = RESOURCE_DIR / "Sounds"
SOUND_EFFECTS_DIR = RESOURCE_DIR / "Sound Effects"
LIFE_LOSS_SOUND = SOUND_EFFECTS_DIR / "Life Loss.mp3"
GOAL_REACHED_SOUND = SOUND_EFFECTS_DIR / "Goal Reached.wav"
INFINITE_START_TRACK = SOUNDS_DIR / "Infinite start.mp3"
CONTROLS_FILE = DATA_DIR / "controls.json"
FILE_ATTRIBUTE_HIDDEN = 0x2


def hide_file(path: Path) -> None:
    """Mark a generated data file hidden on Windows."""
    if os.name != "nt" or not path.exists():
        return
    attributes = ctypes.windll.kernel32.GetFileAttributesW(str(path))
    if attributes == 0xFFFFFFFF:
        raise OSError(f"Could not read file attributes: {path}")
    if not ctypes.windll.kernel32.SetFileAttributesW(
        str(path), attributes | FILE_ATTRIBUTE_HIDDEN
    ):
        raise OSError(f"Could not hide file: {path}")

DEFAULT_BINDINGS = {
    "up": ["w", "up"],
    "down": ["s", "down"],
    "left": ["a", "left"],
    "right": ["d", "right"],
    "pause": ["p", ""],
    "confirm": ["return", "space"],
    "back": ["escape", "m"],
    "quit": ["escape", ""],
    "restart": ["r", ""],
    "credits": ["c", ""],
}


def assign_binding(
    bindings: dict[str, list[str]], action: str, slot: int, key_name: str
) -> None:
    """Assign a key to one slot and remove it from every other slot."""
    normalized_key = key_name.lower()
    for other_action, keys in bindings.items():
        for other_slot in range(len(keys)):
            if (
                other_action != action or other_slot != slot
            ) and keys[other_slot] == normalized_key:
                keys[other_slot] = ""
    bindings[action][slot] = normalized_key


LEVELS = (
    (
        "###############",
        "#S#       #   #",
        "# # ##### # # #",
        "# #     #   # #",
        "# ##### ##### #",
        "#     #       #",
        "##### # ##### #",
        "#     # #     #",
        "# ##### # ### #",
        "#       #   #E#",
        "###############",
    ),
    (
        "################",
        "#S    #        #",
        "##### # ###### #",
        "#     #      # #",
        "# ###### ### # #",
        "#        #   # #",
        "# ###### # ### #",
        "# #      #     #",
        "# # ########## #",
        "# #          E #",
        "################",
    ),
    (
        "###############",
        "#S#     #     #",
        "# # ### # ### #",
        "#   #   #   # #",
        "### # ####### #",
        "#   #         #",
        "# ####### ### #",
        "#       # #   #",
        "####### # # # #",
        "#       #   #E#",
        "###############",
    ),
    (
        "###############",
        "#S      #     #",
        "####### # ### #",
        "#       # #   #",
        "# ####### # ###",
        "# #       #   #",
        "# # ######### #",
        "# #         # #",
        "# ######### # #",
        "#           #E#",
        "###############",
    ),
    (
        "###############",
        "#S#         # #",
        "# # ####### # #",
        "# #       # # #",
        "# ####### # # #",
        "#       # #   #",
        "####### # ### #",
        "#     # #     #",
        "# ### # #######",
        "#   #       E #",
        "###############",
    ),
    (
        "###############",
        "#S      #     #",
        "# ##### # ### #",
        "#     # #   # #",
        "##### # ### # #",
        "#     #     # #",
        "# ########### #",
        "# #           #",
        "# # ######### #",
        "# #         E #",
        "###############",
    ),
    (
        "###############",
        "#S#           #",
        "# # ######### #",
        "# #       #   #",
        "# ####### # ###",
        "#       # #   #",
        "####### # ### #",
        "#     # #     #",
        "# ### # #######",
        "#   #       E #",
        "###############",
    ),
    (
        "###############",
        "#S    #       #",
        "##### # ##### #",
        "#     #     # #",
        "# ######### # #",
        "# #       # # #",
        "# # ##### # # #",
        "# #     #   # #",
        "# ### # ##### #",
        "#     #     E #",
        "###############",
    ),
    (
        "###############",
        "#S#           #",
        "# # ######### #",
        "# # #       # #",
        "# # # ##### # #",
        "#   # #   #   #",
        "##### # # #####",
        "#     # #     #",
        "# ### # ##### #",
        "#   #       E #",
        "###############",
    ),
    (
        "###############",
        "#S      #     #",
        "####### # ### #",
        "#       # #   #",
        "# ####### # ###",
        "#       # #   #",
        "# ##### # ### #",
        "#     # #     #",
        "##### # #######",
        "#     #      E#",
        "###############",
    ),
)


def generate_infinite_level(level_number: int, seed: Optional[int] = None) -> tuple[str, ...]:
    """Create a perfect maze for an infinite-mode level."""
    width, height = 15, 11
    grid = [["#" for _ in range(width)] for _ in range(height)]
    randomizer = random.Random(level_number if seed is None else seed)
    stack = [(1, 1)]
    grid[1][1] = " "
    while stack:
        column, row = stack[-1]
        choices = []
        for dx, dy in ((2, 0), (-2, 0), (0, 2), (0, -2)):
            next_column, next_row = column + dx, row + dy
            if 1 <= next_column < width - 1 and 1 <= next_row < height - 1:
                if grid[next_row][next_column] == "#":
                    choices.append((next_column, next_row, dx, dy))
        if not choices:
            stack.pop()
            continue
        next_column, next_row, dx, dy = randomizer.choice(choices)
        grid[row + dy // 2][column + dx // 2] = " "
        grid[next_row][next_column] = " "
        stack.append((next_column, next_row))
    grid[1][1] = "S"
    grid[height - 2][width - 2] = "E"
    return tuple("".join(row) for row in grid)


@dataclass
class Maze:
    """Parsed level geometry and its player and goal positions."""

    rows: tuple[str, ...]
    start: tuple[int, int]
    goal: tuple[int, int]

    @classmethod
    def from_rows(cls, rows: tuple[str, ...]) -> "Maze":
        start = goal = (0, 0)
        for row, line in enumerate(rows):
            for column, cell in enumerate(line):
                if cell == "S":
                    start = (column, row)
                elif cell == "E":
                    goal = (column, row)
        return cls(rows, start, goal)

    def is_wall(self, column: int, row: int) -> bool:
        return (
            row < 0
            or row >= len(self.rows)
            or column < 0
            or column >= len(self.rows[row])
            or self.rows[row][column] == "#"
        )

    def is_subcell_wall(self, column: int, row: int) -> bool:
        """Check a position on the three-times finer movement grid."""
        return self.is_wall(column // SUBDIVISIONS, row // SUBDIVISIONS)

    def is_goal_subcell(self, column: int, row: int) -> bool:
        """Return whether a fine-grid position is inside the 3x3 goal."""
        return (column // SUBDIVISIONS, row // SUBDIVISIONS) == self.goal


class ScoreStore:
    """Read and write the top ten scores using Fernet authenticated encryption."""

    def __init__(self, score_file: Path = SCORE_FILE, key_file: Path = KEY_FILE):
        self.score_file = score_file
        self.key_file = key_file

    def _fernet(self) -> Fernet:
        if not self.key_file.exists():
            self.key_file.write_bytes(Fernet.generate_key())
            hide_file(self.key_file)
        return Fernet(self.key_file.read_bytes())

    def load(self) -> list[int]:
        if not self.score_file.exists():
            return []
        try:
            data = self._fernet().decrypt(self.score_file.read_bytes()).decode()
            return sorted(
                (int(value) for value in data.split(",") if value and int(value) > 0),
                reverse=True,
            )[:10]
        except (InvalidToken, OSError, ValueError):
            return []

    def add(self, score: int) -> list[int]:
        scores = self.load()
        if score > 0:
            scores.append(score)
        scores = sorted(scores, reverse=True)[:10]
        encrypted = self._fernet().encrypt(",".join(map(str, scores)).encode())
        self.score_file.write_bytes(encrypted)
        hide_file(self.score_file)
        return scores


class InfiniteScoreStore:
    """Read and write infinite-run score and level records securely."""

    def __init__(self, score_file: Path = INFINITE_SCORE_FILE, key_file: Path = KEY_FILE):
        self.score_file = score_file
        self.key_file = key_file

    def _fernet(self) -> Fernet:
        if not self.key_file.exists():
            self.key_file.write_bytes(Fernet.generate_key())
            hide_file(self.key_file)
        return Fernet(self.key_file.read_bytes())

    def load(self) -> list[tuple[int, int]]:
        if not self.score_file.exists():
            return []
        try:
            data = self._fernet().decrypt(self.score_file.read_bytes()).decode()
            records = (
                (int(score), int(levels))
                for value in data.split(",")
                if value
                for score, levels in [value.split(":")]
            )
            return sorted(
                (
                    record for record in records
                    if record[0] > 0 and record[1] > 0
                ),
                key=lambda record: (record[1], record[0]),
                reverse=True,
            )[:10]
        except (InvalidToken, OSError, ValueError):
            return []

    def add(self, score: int, levels: int) -> list[tuple[int, int]]:
        records = self.load()
        if score > 0 and levels > 0:
            records.append((score, levels))
        records = sorted(
            records,
            key=lambda record: (record[1], record[0]),
            reverse=True,
        )[:10]
        data = ",".join(f"{score}:{levels}" for score, levels in records).encode()
        self.score_file.write_bytes(self._fernet().encrypt(data))
        hide_file(self.score_file)
        return records


def level_score(seconds: float) -> int:
    """Return a rapidly decaying score that is always positive."""
    return max(1, round(1000 * math.exp(-max(0.0, seconds) / SCORE_DECAY_SECONDS)))


def infinite_speed_multiplier(level_number: int) -> float:
    """Return the piecewise infinite-mode speed multiplier."""
    level = max(1, level_number)
    if level <= 20:
        return 3.0 ** ((level - 1) / 19.0)
    if level <= 40:
        return 3.0 + 2.0 * math.sqrt((level - 20) / 20.0)
    return 5.0


class MazeGame:
    """Owns the game state, input, rendering, and screen transitions."""

    def __init__(self) -> None:
        if pygame is None:
            raise RuntimeError("pygame is required to run the game; install requirements.txt first")
        pygame.init()
        pygame.mixer.init()
        self.life_loss_sound = pygame.mixer.Sound(str(LIFE_LOSS_SOUND))
        self.goal_reached_sound = pygame.mixer.Sound(str(GOAL_REACHED_SOUND))
        self.life_loss_sound.set_volume(0.7)
        self.goal_reached_sound.set_volume(0.7)
        pygame.display.set_caption("Pygame Maze")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 32)
        self.large_font = pygame.font.Font(None, 68)
        self.small_font = pygame.font.Font(None, 24)
        self.store = ScoreStore()
        self.high_scores = self.store.load()
        self.infinite_store = InfiniteScoreStore()
        self.infinite_scores = self.infinite_store.load()
        self.state = "home"
        self.menu_option = 0
        self.hard_mode = False
        self.infinite_mode = False
        self.player_speed = PLAYER_SPEED
        self.level_index = 0
        self.lives = MAX_LIVES
        self.total_score = 0
        self.player = (0.0, 0.0)
        self.level_started = 0.0
        self.frame_seconds = 0.0
        self.momentum: Optional[tuple[int, int]] = None
        self.pending_wall_hit_at: Optional[float] = None
        self.death_background: Optional[pygame.Surface] = None
        self.message = ""
        self.current_music: Optional[Path] = None
        self.infinite_playlist: list[Path] = []
        self.pause_option = 0
        self.death_option = 0
        self.menu_rects: dict[str, list[pygame.Rect]] = {}
        self.paused_at: Optional[float] = None
        self.audio_focus_lost = False
        self.focus_paused = False
        self.bindings = self.load_bindings()
        self.binding_action: Optional[str] = None
        self.binding_slot = 0
        self.control_rects: list[tuple[str, int, pygame.Rect]] = []
        self.reset_controls_rect: Optional[pygame.Rect] = None
        self.controls_back_rect: Optional[pygame.Rect] = None
        self.infinite_level_rows: Optional[tuple[str, ...]] = None
        self.generated_level_signatures: set[tuple[str, ...]] = set()
        self.visited_cells: set[tuple[int, int]] = set()
        self.bonus_cell: Optional[tuple[int, int]] = None
        self.hazard_cells: list[tuple[int, int]] = []
        self.bonus_collected = False
        self.reset_level()

    def load_bindings(self) -> dict[str, list[str]]:
        """Load saved key names, falling back safely to the default layout."""
        try:
            data = json.loads(CONTROLS_FILE.read_text(encoding="utf-8"))
            return {
                action: [
                    str(data.get(action, DEFAULT_BINDINGS[action])[slot]).lower()
                    if slot < len(data.get(action, DEFAULT_BINDINGS[action]))
                    else ""
                    for slot in range(2)
                ]
                for action in DEFAULT_BINDINGS
            }
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return {action: keys[:] for action, keys in DEFAULT_BINDINGS.items()}

    def save_bindings(self) -> None:
        CONTROLS_FILE.write_text(json.dumps(self.bindings, indent=2), encoding="utf-8")

    def reset_bindings(self) -> None:
        self.bindings = {action: keys[:] for action, keys in DEFAULT_BINDINGS.items()}
        self.save_bindings()

    def key_matches(self, action: str, key: int) -> bool:
        pressed = pygame.key.name(key).lower()
        return pressed in self.bindings[action]

    def begin_binding(self, action: str, slot: int) -> None:
        self.binding_action = action
        self.binding_slot = slot

    def capture_binding(self, key: int) -> None:
        if self.binding_action is None:
            return
        assign_binding(
            self.bindings,
            self.binding_action,
            self.binding_slot,
            pygame.key.name(key),
        )
        self.save_bindings()
        self.binding_action = None

    def update_music(self) -> None:
        """Play the track associated with the current screen without restarting it."""
        if self.state == "paused" or self.audio_focus_lost:
            return
        if self.state == "playing" and self.infinite_mode:
            if self.current_music is None:
                self.play_music(INFINITE_START_TRACK, loops=0)
                return
            if pygame.mixer.music.get_busy():
                return
            if not self.infinite_playlist:
                self.infinite_playlist = [
                    path
                    for path in SOUNDS_DIR.glob("*.mp3")
                    if path != INFINITE_START_TRACK
                ]
                random.shuffle(self.infinite_playlist)
            self.play_music(self.infinite_playlist.pop(), loops=0)
            return
        tracks = {
            "home": SOUNDS_DIR / "Title Theme.mp3",
            "playing": SOUNDS_DIR / "Levels.mp3",
            "win": SOUNDS_DIR / "Win Theme.mp3",
            "death": SOUNDS_DIR / "Death Theme.mp3",
        }
        track = tracks.get(self.state, tracks["home"])
        if track == self.current_music:
            return
        self.play_music(track)

    def play_music(self, track: Path, loops: int = -1) -> None:
        """Load and play a verified soundtrack file."""
        if not track.exists():
            raise FileNotFoundError(f"Music file not found: {track}")
        pygame.mixer.music.load(str(track))
        pygame.mixer.music.play(loops)
        self.current_music = track

    def play_sound_effect(self, sound: pygame.mixer.Sound) -> None:
        """Play a short sound effect without interrupting the soundtrack."""
        if not self.audio_focus_lost:
            sound.play()

    def reset_level(self, reset_score_timer: bool = True) -> None:
        maze = self.current_maze()
        speed_ramp = (
            infinite_speed_multiplier(self.level_index + 1)
            if self.infinite_mode
            else 1.0
        )
        self.player_speed = PLAYER_SPEED * speed_ramp
        if self.hard_mode:
            self.player_speed *= HARD_MODE_SPEED_MULTIPLIER
        self.player = (
            float(maze.start[0] * CELL + SUBCELL),
            float(maze.start[1] * CELL + SUBCELL),
        )
        self.visited_cells = {maze.start}
        self.bonus_collected = False
        self.hazard_cells = []
        self.bonus_cell = self.choose_bonus_cell(maze) if self.infinite_mode else None
        self.pending_wall_hit_at = None
        if reset_score_timer:
            self.level_started = time.monotonic()

    def current_level_score(self) -> int:
        """Return the score currently available for completing this level."""
        score = level_score(time.monotonic() - self.level_started)
        multiplier = HARD_MODE_SCORE_MULTIPLIER if self.hard_mode else 1.0
        if self.bonus_collected:
            multiplier *= 3.0
        return round(score * multiplier)

    def start_game(self, hard_mode: bool = False, infinite_mode: bool = False) -> None:
        self.level_index = 0
        self.lives = MAX_LIVES
        self.total_score = 0
        self.hard_mode = hard_mode
        self.infinite_mode = infinite_mode
        self.infinite_playlist = []
        self.reset_infinite_generation()
        self.paused_at = None
        pygame.mixer.music.stop()
        self.current_music = None
        self.momentum = None
        self.pending_wall_hit_at = None
        self.message = ""
        self.reset_level()
        self.state = "playing"

    def reset_infinite_generation(self) -> None:
        """Discard all generated mazes so a restarted run starts fresh."""
        self.infinite_level_rows = None
        self.generated_level_signatures = set()

    def pause_game(self) -> None:
        """Freeze gameplay and its timers until the pause menu is dismissed."""
        if self.state != "playing":
            return
        self.state = "paused"
        self.pause_option = 0
        self.paused_at = time.monotonic()
        pygame.mixer.pause()
        pygame.mixer.music.pause()

    def resume_game(self) -> None:
        """Resume gameplay while preserving the score and collision timers."""
        if self.state != "paused" or self.paused_at is None:
            return
        paused_duration = time.monotonic() - self.paused_at
        self.level_started += paused_duration
        if self.pending_wall_hit_at is not None:
            self.pending_wall_hit_at += paused_duration
        self.paused_at = None
        self.state = "playing"
        self.audio_focus_lost = False
        pygame.mixer.unpause()
        pygame.mixer.music.unpause()

    def return_to_menu(self) -> None:
        """Leave the current run and return to the title menu."""
        pygame.mixer.music.stop()
        self.current_music = None
        self.momentum = None
        self.paused_at = None
        self.state = "home"
        self.menu_option = 0

    def resume_audio(self) -> None:
        """Resume audio after the game window regains focus."""
        if not self.audio_focus_lost:
            return
        self.audio_focus_lost = False
        pygame.mixer.unpause()
        pygame.mixer.music.unpause()

    def draw_option_boxes(self, state: str, options: tuple[str, ...], y: int, selected: int) -> None:
        """Draw selectable menu boxes and retain their hit areas for mouse input."""
        boxes = []
        width, height = 520, 36
        for index, option in enumerate(options):
            rect = pygame.Rect(WIDTH // 2 - width // 2, y + index * 45, width, height)
            boxes.append(rect)
            hovered = rect.collidepoint(pygame.mouse.get_pos())
            active = index == selected or hovered
            fill = (35, 75, 92) if active else (24, 38, 57)
            border = (120, 230, 140) if active else (65, 90, 115)
            pygame.draw.rect(self.screen, fill, rect)
            pygame.draw.rect(self.screen, border, rect, 2)
            self.text(option, rect.center, (120, 230, 140) if active else (190, 200, 210), self.small_font)
        self.menu_rects[state] = boxes

    def draw_controls_editor(self) -> None:
        """Render the two-slot key binding editor."""
        self.control_rects = []
        self.reset_controls_rect = pygame.Rect(190, 555, 240, 38)
        self.controls_back_rect = pygame.Rect(470, 555, 240, 38)
        labels = {
            "up": "Move up",
            "down": "Move down",
            "left": "Move left",
            "right": "Move right",
            "pause": "Pause",
            "confirm": "Confirm / select",
            "back": "Back / main menu",
            "quit": "Quit",
            "restart": "Restart",
            "credits": "Credits",
        }
        for index, (action, label) in enumerate(labels.items()):
            y = 112 + index * 43
            self.text(label, (210, y + 17), font=self.small_font)
            for slot in range(2):
                rect = pygame.Rect(355 + slot * 145, y, 125, 34)
                self.control_rects.append((action, slot, rect))
                hovered = rect.collidepoint(pygame.mouse.get_pos())
                active = self.binding_action == action and self.binding_slot == slot
                fill = (35, 75, 92) if hovered or active else (24, 38, 57)
                border = (255, 215, 90) if active else (120, 230, 140) if hovered else (65, 90, 115)
                pygame.draw.rect(self.screen, fill, rect)
                pygame.draw.rect(self.screen, border, rect, 2)
                key_name = self.bindings[action][slot] or "blank"
                self.text(key_name.upper(), rect.center, font=self.small_font)
        for rect, label in (
            (self.reset_controls_rect, "RESET DEFAULTS"),
            (self.controls_back_rect, "BACK"),
        ):
            hovered = rect.collidepoint(pygame.mouse.get_pos())
            pygame.draw.rect(self.screen, (35, 75, 92) if hovered else (24, 38, 57), rect)
            pygame.draw.rect(self.screen, (120, 230, 140) if hovered else (65, 90, 115), rect, 2)
            self.text(label, rect.center, font=self.small_font)
        if self.binding_action is not None:
            self.text("Press a key to bind it, or ESC to cancel",
                      (WIDTH // 2, 105), (255, 215, 90), self.small_font)

    def activate_menu_option(self, state: str, option: int) -> bool:
        """Apply a clicked menu selection."""
        if state == "home":
            self.menu_option = option
            if option == 3:
                self.state = "leaderboards"
            elif option == 4:
                self.state = "controls"
            elif option == 5:
                return False
            else:
                self.start_game(hard_mode=option == 1, infinite_mode=option == 2)
        elif state == "paused":
            self.pause_option = option
            if option == 0:
                self.resume_game()
            elif option == 1:
                self.return_to_menu()
            else:
                return False
        elif state == "win":
            if option == 0:
                self.start_game(hard_mode=self.hard_mode, infinite_mode=self.infinite_mode)
            elif option == 1:
                self.state = "home"
                self.menu_option = 0
            elif option == 2:
                self.state = "credits"
            else:
                return False
        elif state == "death":
            if option == 0:
                self.start_game(hard_mode=self.hard_mode, infinite_mode=self.infinite_mode)
            elif option == 1:
                self.state = "home"
                self.menu_option = 0
            else:
                return False
        return True

    def current_maze(self) -> Maze:
        """Return the selected fixed or procedurally generated level."""
        if self.infinite_mode:
            if self.infinite_level_rows is None:
                randomizer = random.Random()
                while True:
                    rows = generate_infinite_level(
                        self.level_index + 1,
                        seed=randomizer.randrange(1 << 30),
                    )
                    if rows not in self.generated_level_signatures:
                        self.infinite_level_rows = rows
                        self.generated_level_signatures.add(rows)
                        break
        else:
            rows = LEVELS[self.level_index]
        rows = self.infinite_level_rows if self.infinite_mode else rows
        return Maze.from_rows(rows)

    def maze_origin(self, maze: Maze) -> tuple[int, int]:
        """Return the top-left pixel position that centers the current maze."""
        maze_width = len(maze.rows[0]) * CELL
        maze_height = len(maze.rows) * CELL
        return (WIDTH - maze_width) // 2, (HEIGHT - maze_height) // 2 + 35

    def find_path(
        self,
        maze: Maze,
        start: tuple[int, int],
        goal: tuple[int, int],
    ) -> list[tuple[int, int]]:
        """Find an open-cell path, or return an empty path when none exists."""
        queue = deque([start])
        previous: dict[tuple[int, int], Optional[tuple[int, int]]] = {start: None}
        while queue:
            cell = queue.popleft()
            if cell == goal:
                path = []
                while cell is not None:
                    path.append(cell)
                    cell = previous[cell]
                return list(reversed(path))
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                next_cell = (cell[0] + dx, cell[1] + dy)
                if next_cell not in previous and not maze.is_wall(*next_cell):
                    previous[next_cell] = cell
                    queue.append(next_cell)
        return []

    def choose_bonus_cell(self, maze: Maze) -> Optional[tuple[int, int]]:
        """Choose a reachable, unvisited cell well away from the goal."""
        candidates = [
            (column, row)
            for row, line in enumerate(maze.rows)
            for column, cell in enumerate(line)
            if cell != "#"
            and (column, row) not in self.visited_cells
            and abs(column - maze.goal[0]) + abs(row - maze.goal[1]) >= 4
            and (column, row) != maze.goal
        ]
        reachable = set(self.find_path(maze, maze.start, maze.goal))
        candidates = [cell for cell in candidates if cell in reachable]
        if not candidates:
            return None
        return random.Random(self.level_index + 1001).choice(candidates)

    def cell_from_position(self, position: tuple[float, float]) -> tuple[int, int]:
        """Convert the player's local maze position to its containing cell."""
        return (int((position[0] + SUBCELL / 2) // CELL), int((position[1] + SUBCELL / 2) // CELL))

    def collect_bonus(self, maze: Maze) -> None:
        """Activate the level bonus and place separated hazards off a safe route."""
        if self.bonus_collected:
            return
        self.bonus_collected = True
        current_cell = self.cell_from_position(self.player)
        safe_path = set(self.find_path(maze, current_cell, maze.goal))
        candidates = [
            (column, row)
            for row, line in enumerate(maze.rows)
            for column, cell in enumerate(line)
            if cell != "#"
            and (column, row) not in safe_path
            and (column, row) != maze.goal
            and (column, row) != current_cell
        ]
        randomizer = random.Random((self.level_index + 1) * 7919)
        randomizer.shuffle(candidates)
        for candidate in candidates:
            if all(
                abs(candidate[0] - hazard[0]) + abs(candidate[1] - hazard[1]) >= 3
                for hazard in self.hazard_cells
            ):
                self.hazard_cells.append(candidate)
                if len(self.hazard_cells) == 3:
                    break

    def try_move(self, dx: float, dy: float) -> None:
        maze = self.current_maze()
        maze_left, maze_top = self.maze_origin(maze)
        target = (
            self.player[0] + dx * self.player_speed * self.frame_seconds,
            self.player[1] + dy * self.player_speed * self.frame_seconds,
        )
        player_rect = pygame.Rect(
            round(maze_left + target[0]),
            round(maze_top + target[1]),
            SUBCELL,
            SUBCELL,
        )
        if self.collides_with_wall(maze, player_rect):
            self.momentum = None
            if self.pending_wall_hit_at is None:
                self.pending_wall_hit_at = time.monotonic() + WALL_COYOTE_SECONDS
            return
        self.player = target
        self.visited_cells.add(self.cell_from_position(self.player))
        if self.bonus_cell == self.cell_from_position(self.player):
            self.collect_bonus(maze)
        goal_rect = pygame.Rect(
            maze_left + maze.goal[0] * CELL,
            maze_top + maze.goal[1] * CELL,
            CELL,
            CELL,
        )
        if player_rect.colliderect(goal_rect):
            self.play_sound_effect(self.goal_reached_sound)
            self.total_score += self.current_level_score()
            self.level_index += 1
            self.lives = min(MAX_LIVES, self.lives + 1)
            self.momentum = None
            if not self.infinite_mode and self.level_index == TOTAL_LEVELS:
                self.high_scores = self.store.add(self.total_score)
                self.state = "win"
            else:
                self.message = ""
                if self.infinite_mode:
                    self.infinite_level_rows = None
                self.reset_level()

        hazard_size = max(1, SUBCELL // 2)
        for hazard in self.hazard_cells:
            hazard_rect = pygame.Rect(
                maze_left + hazard[0] * CELL + (CELL - hazard_size) // 2,
                maze_top + hazard[1] * CELL + (CELL - hazard_size) // 2,
                hazard_size,
                hazard_size,
            )
            if player_rect.colliderect(hazard_rect):
                self.momentum = None
                self.pending_wall_hit_at = time.monotonic()
                return

    def collides_with_wall(self, maze: Maze, player_rect: pygame.Rect) -> bool:
        """Return whether the player rectangle overlaps any wall cell."""
        maze_left, maze_top = self.maze_origin(maze)
        for row, line in enumerate(maze.rows):
            for column, cell in enumerate(line):
                if cell == "#":
                    wall_rect = pygame.Rect(
                        maze_left + column * CELL,
                        maze_top + row * CELL,
                        CELL,
                        CELL,
                    )
                    if player_rect.colliderect(wall_rect):
                        return True
        return False

    def set_momentum(self, direction: tuple[int, int]) -> None:
        """Set a single-direction movement vector."""
        if self.momentum != direction:
            self.pending_wall_hit_at = None
            self.momentum = direction

    def resolve_pending_wall_hit(self) -> None:
        """Apply a wall collision after the brief correction window expires."""
        if self.pending_wall_hit_at is None or time.monotonic() < self.pending_wall_hit_at:
            return
        self.pending_wall_hit_at = None
        self.lives -= 1
        self.play_sound_effect(self.life_loss_sound)
        if self.lives <= 0:
            if self.infinite_mode:
                self.infinite_scores = self.infinite_store.add(self.total_score, self.level_index)
            self.draw_maze()
            self.death_background = self.screen.copy()
            self.death_option = 0
            self.state = "death"
        else:
            self.message = "Ouch! You lost a life."
            self.reset_level(reset_score_timer=False)

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.QUIT:
            return False
        if event.type == pygame.WINDOWFOCUSLOST:
            self.audio_focus_lost = True
            self.momentum = None
            pygame.mixer.pause()
            pygame.mixer.music.pause()
            if self.state == "playing":
                self.focus_paused = True
                self.pause_game()
            return True
        if event.type == pygame.WINDOWFOCUSGAINED:
            if self.focus_paused:
                self.focus_paused = False
                self.resume_game()
            elif self.state == "paused":
                self.audio_focus_lost = False
            else:
                self.resume_audio()
            return True
        if event.type == pygame.MOUSEMOTION:
            for index, rect in enumerate(self.menu_rects.get(self.state, [])):
                if rect.collidepoint(event.pos):
                    if self.state == "home":
                        self.menu_option = index
                    elif self.state == "paused":
                        self.pause_option = index
                    elif self.state == "death":
                        self.death_option = index
                    break
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.focus_paused:
                self.focus_paused = False
                self.resume_game()
            elif self.state == "paused":
                self.audio_focus_lost = False
            else:
                self.resume_audio()
            if self.state == "controls":
                for action, slot, rect in self.control_rects:
                    if rect.collidepoint(event.pos):
                        self.begin_binding(action, slot)
                        return True
                if self.reset_controls_rect and self.reset_controls_rect.collidepoint(event.pos):
                    self.reset_bindings()
                    return True
                if self.controls_back_rect and self.controls_back_rect.collidepoint(event.pos):
                    self.state = "home"
                    return True
            for index, rect in enumerate(self.menu_rects.get(self.state, [])):
                if rect.collidepoint(event.pos):
                    return self.activate_menu_option(self.state, index)
            return True
        if event.type != pygame.KEYDOWN:
            return True
        if self.state == "controls" and self.binding_action is not None:
            if event.key == pygame.K_ESCAPE:
                self.binding_action = None
            else:
                self.capture_binding(event.key)
            return True
        if self.state == "home":
            if self.key_matches("up", event.key) or self.key_matches("down", event.key):
                offset = -1 if self.key_matches("up", event.key) else 1
                self.menu_option = (self.menu_option + offset) % 6
            elif self.key_matches("confirm", event.key):
                if self.menu_option == 3:
                    self.state = "leaderboards"
                elif self.menu_option == 4:
                    self.state = "controls"
                elif self.menu_option == 5:
                    return False
                else:
                    self.start_game(
                        hard_mode=self.menu_option == 1,
                        infinite_mode=self.menu_option == 2,
                    )
            elif self.key_matches("credits", event.key):
                self.state = "credits"
            elif self.key_matches("back", event.key) or self.key_matches("quit", event.key):
                return False
        elif self.state == "playing":
            if self.key_matches("pause", event.key):
                self.pause_game()
                return True
            moves = {
                "left": (-1, 0), "right": (1, 0),
                "up": (0, -1), "down": (0, 1),
            }
            for action, direction in moves.items():
                if self.key_matches(action, event.key):
                    self.set_momentum(direction)
                    break
        elif self.state == "paused":
            if self.key_matches("up", event.key) or self.key_matches("down", event.key):
                offset = -1 if self.key_matches("up", event.key) else 1
                self.pause_option = (self.pause_option + offset) % 3
            elif self.key_matches("confirm", event.key):
                if self.pause_option == 0:
                    self.resume_game()
                elif self.pause_option == 1:
                    self.return_to_menu()
                else:
                    return False
            elif self.key_matches("pause", event.key):
                self.resume_game()
            elif self.key_matches("back", event.key):
                self.resume_game()
        elif self.state in ("win", "death"):
            if self.state == "death" and (
                self.key_matches("up", event.key) or self.key_matches("down", event.key)
            ):
                offset = -1 if self.key_matches("up", event.key) else 1
                self.death_option = (self.death_option + offset) % 3
            elif self.state == "death" and self.key_matches("confirm", event.key):
                if self.death_option == 0:
                    self.start_game(
                        hard_mode=self.hard_mode,
                        infinite_mode=self.infinite_mode,
                    )
                elif self.death_option == 1:
                    self.state = "home"
                    self.menu_option = 0
                    self.momentum = None
                else:
                    return False
            elif self.key_matches("confirm", event.key) or self.key_matches("restart", event.key):
                self.start_game(
                    hard_mode=self.hard_mode,
                    infinite_mode=self.infinite_mode,
                )
            elif self.key_matches("back", event.key):
                self.state = "home"
                self.menu_option = 0
                self.momentum = None
            elif self.key_matches("credits", event.key) and self.state == "win":
                self.state = "credits"
            elif self.key_matches("quit", event.key):
                return False
        elif self.state == "credits" and (
            self.key_matches("back", event.key) or self.key_matches("confirm", event.key)
        ):
            self.state = "home"
        elif self.state == "leaderboards" and (
            self.key_matches("back", event.key) or self.key_matches("confirm", event.key)
        ):
            self.state = "home"
        elif self.state == "controls" and (
            self.key_matches("back", event.key) or self.key_matches("confirm", event.key)
        ):
            self.state = "home"
        return True

    def text(self, value: str, position: tuple[int, int], color=(235, 235, 235), font=None) -> None:
        surface = (font or self.font).render(value, True, color)
        self.screen.blit(surface, surface.get_rect(center=position))

    def draw_scores(self, x: int, y: int, title: str = "TOP 10 SCORES") -> None:
        self.text(title, (x, y), (255, 215, 90))
        if not self.high_scores:
            self.text("No scores yet", (x, y + 34), (170, 170, 170), self.small_font)
        for index, score in enumerate(self.high_scores):
            self.text(f"{index + 1:>2}. {score:>6}", (x, y + 35 + index * 25), font=self.small_font)

    def draw_infinite_scores(self, x: int, y: int) -> None:
        self.text("INFINITE LEADERBOARD", (x, y), (255, 215, 90))
        if not self.infinite_scores:
            self.text("No runs yet", (x, y + 34), (170, 170, 170), self.small_font)
        for index, (score, levels) in enumerate(self.infinite_scores):
            self.text(
                f"{index + 1:>2}. {score:>6} pts  L{levels:>3}",
                (x, y + 35 + index * 25),
                font=self.small_font,
            )

    def draw_heart(self, center: tuple[int, int], filled: bool) -> None:
        """Draw a heart icon without relying on a font's heart glyph."""
        x, y = center
        color = (245, 100, 100) if filled else (115, 75, 85)
        left_circle = (x - 6, y - 3)
        right_circle = (x + 6, y - 3)
        point = (x, y + 10)
        pygame.draw.circle(self.screen, color, left_circle, 7, 0 if filled else 2)
        pygame.draw.circle(self.screen, color, right_circle, 7, 0 if filled else 2)
        pygame.draw.polygon(
            self.screen,
            color,
            ((x - 12, y - 2), (x + 12, y - 2), point),
            0 if filled else 2,
        )

    def draw_home_background(self) -> None:
        """Draw a low-resolution pixel-art maze pattern behind the title."""
        self.screen.fill((12, 16, 28))
        pattern = (
            "111111111111111111111111111111",
            "100000001111000000001111000001",
            "101111101001011111101001011101",
            "101000101001010000101001010001",
            "101011101111011110101111011101",
            "101010000000010010100000010001",
            "101011111111110011111111011101",
            "100000000000000000000000000001",
            "111011111011111111101111101111",
            "100010001000000100001000100001",
            "101110101111110111111010111101",
            "100000100000000000001000000001",
            "111111111111111111111111111111",
        )
        block = 28
        left = (WIDTH - len(pattern[0]) * block) // 2
        top = 170
        for row, line in enumerate(pattern):
            for column, cell in enumerate(line):
                if cell == "1":
                    color = (25, 45, 70) if (row + column) % 3 else (30, 58, 84)
                    pygame.draw.rect(
                        self.screen,
                        color,
                        (left + column * block, top + row * block, block, block),
                    )
        for column, color in ((3, (65, 150, 210)), (15, (235, 65, 75)), (26, (70, 205, 105))):
            pygame.draw.rect(
                self.screen,
                color,
                (left + column * block + 7, top + 7 * block + 7, block - 14, block - 14),
            )

    def draw_wall_texture(self, rect: pygame.Rect, row: int, column: int) -> None:
        """Fill a wall with a subtle, repeating pixel-art texture."""
        base = (25, 45, 70) if (row + column) % 3 else (30, 58, 84)
        shadow = (18, 35, 57)
        highlight = (39, 70, 96)
        pygame.draw.rect(self.screen, base, rect)
        tile = 12
        for texture_row in range(0, rect.height, tile):
            for texture_column in range(0, rect.width, tile):
                palette_index = (
                    row * 3 + column * 5 + texture_row // tile + texture_column // tile
                ) % 4
                if palette_index == 0:
                    color = shadow
                elif palette_index == 1:
                    color = highlight
                else:
                    color = base
                pygame.draw.rect(
                    self.screen,
                    color,
                    (rect.left + texture_column, rect.top + texture_row, tile, tile),
                )
        pygame.draw.rect(self.screen, (12, 24, 40), rect, 2)

    def draw(self) -> None:
        if self.state == "home":
            self.screen.fill((18, 22, 32))
            self.text("MAZE RUNNER", (WIDTH // 2, 72), (230, 70, 70), self.large_font)
            self.text("Reach the green goal. Avoid the walls.", (WIDTH // 2, 145))
            options = (
                "NORMAL MODE",
                "HARD MODE",
                "INFINITE MODE",
                "VIEW LEADERBOARDS",
                "VIEW CONTROLS",
                "QUIT",
            )
            self.draw_option_boxes("home", options, 185, self.menu_option)
        elif self.state == "playing":
            self.screen.fill((18, 22, 32))
            self.draw_maze()
        elif self.state == "paused":
            self.screen.fill((18, 22, 32))
            self.draw_maze()
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((5, 8, 15, 195))
            self.screen.blit(overlay, (0, 0))
            self.text("PAUSED", (WIDTH // 2, 125), (255, 215, 90), self.large_font)
            options = ("RETURN TO GAME", "RETURN TO MAIN MENU", "QUIT")
            self.draw_option_boxes("paused", options, 215, self.pause_option)
        elif self.state == "win":
            self.screen.fill((18, 22, 32))
            self.text("YOU WIN!", (WIDTH // 2, 75), (120, 240, 150), self.large_font)
            self.text(f"Final score: {self.total_score}", (WIDTH // 2, 145))
            self.draw_option_boxes("win", ("RESTART", "MAIN MENU", "CREDITS", "QUIT"), 190, 0)
            self.draw_scores(WIDTH // 2, 390)
        elif self.state == "death":
            if self.death_background is not None:
                self.screen.blit(self.death_background, (0, 0))
                overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                overlay.fill((5, 8, 15, 185))
                self.screen.blit(overlay, (0, 0))
            else:
                self.screen.fill((18, 22, 32))
            self.text("GAME OVER", (WIDTH // 2, 120), (240, 90, 90), self.large_font)
            self.text("You ran out of lives.", (WIDTH // 2, 190))
            if self.infinite_mode:
                self.text(f"Score: {self.total_score}   Levels reached: {self.level_index}", (WIDTH // 2, 235))
                restart_y = 285
            else:
                restart_y = 250
            self.draw_option_boxes("death", ("RESTART", "MAIN MENU", "QUIT"),
                                   restart_y - 20, self.death_option)
            if self.infinite_mode:
                self.draw_infinite_scores(WIDTH // 2, restart_y + 135)
            else:
                self.draw_scores(WIDTH // 2, restart_y + 135)
        elif self.state == "leaderboards":
            self.screen.fill((18, 22, 32))
            self.text("LEADERBOARDS", (WIDTH // 2, 65), (255, 215, 90), self.large_font)
            self.draw_scores(WIDTH // 4, 140, "NORMAL LEADERBOARD")
            self.draw_infinite_scores(WIDTH * 3 // 4, 140)
            self.text("Press ESC or ENTER to return", (WIDTH // 2, HEIGHT - 45), font=self.small_font)
        elif self.state == "controls":
            self.screen.fill((18, 22, 32))
            self.text("CONTROLS", (WIDTH // 2, 65), (255, 215, 90), self.large_font)
            self.text("Click a key box, then press the key to bind it", (WIDTH // 2, 100),
                      (170, 170, 180), self.small_font)
            self.draw_controls_editor()
        else:
            self.screen.fill((18, 22, 32))
            self.text("CREDITS", (WIDTH // 2, 110), (255, 215, 90), self.large_font)
            self.text("Pygame Maze", (WIDTH // 2, 205))
            self.text("Built with Python and pygame", (WIDTH // 2, 245), font=self.small_font)
            self.text("Press ESC or ENTER to return", (WIDTH // 2, 320), font=self.small_font)
        pygame.display.flip()

    def draw_maze(self) -> None:
        maze = self.current_maze()
        maze_left, maze_top = self.maze_origin(maze)
        level_label = (
            f"INFINITE LEVEL {self.level_index + 1}"
            if self.infinite_mode
            else f"LEVEL {self.level_index + 1}/{TOTAL_LEVELS}"
        )
        self.text(level_label, (140, 35), (255, 215, 90))
        self.text("LIVES:", (385, 35), (245, 100, 100))
        for life_index in range(MAX_LIVES):
            self.draw_heart((445 + life_index * 30, 35), life_index < self.lives)
        self.text(f"LEVEL SCORE: {self.current_level_score()}", (650, 35), font=self.small_font)
        if self.infinite_mode and self.bonus_collected:
            self.text("3x BONUS ACTIVE", (650, 58), (120, 210, 255), self.small_font)
        self.text(f"TOTAL: {self.total_score}", (835, 35), font=self.small_font)
        for row, line in enumerate(maze.rows):
            for column, cell in enumerate(line):
                rect = pygame.Rect(maze_left + column * CELL, maze_top + row * CELL, CELL, CELL)
                if cell == "#":
                    self.draw_wall_texture(rect, row, column)
                elif cell == "E":
                    pygame.draw.rect(self.screen, (70, 210, 105), rect.inflate(-8, -8))
        if self.infinite_mode:
            if self.bonus_cell is not None and not self.bonus_collected:
                bonus_rect = pygame.Rect(
                    maze_left + self.bonus_cell[0] * CELL + (CELL - SUBCELL) // 2,
                    maze_top + self.bonus_cell[1] * CELL + (CELL - SUBCELL) // 2,
                    SUBCELL,
                    SUBCELL,
                )
                pygame.draw.circle(self.screen, (115, 215, 255), bonus_rect.center, SUBCELL // 2)
            if self.hazard_cells and (pygame.time.get_ticks() // 180) % 2 == 0:
                hazard_size = max(1, SUBCELL // 2)
                for hazard in self.hazard_cells:
                    hazard_rect = pygame.Rect(
                        maze_left + hazard[0] * CELL + (CELL - hazard_size) // 2,
                        maze_top + hazard[1] * CELL + (CELL - hazard_size) // 2,
                        hazard_size,
                        hazard_size,
                    )
                    pygame.draw.circle(self.screen, (255, 95, 190), hazard_rect.center, hazard_size // 2)
        player_rect = pygame.Rect(
            round(maze_left + self.player[0]),
            round(maze_top + self.player[1]),
            SUBCELL,
            SUBCELL,
        )
        pygame.draw.rect(self.screen, (235, 55, 60), player_rect)
        if self.message:
            self.text(self.message, (WIDTH // 2, HEIGHT - 25), (255, 180, 90), self.small_font)

    def run(self) -> None:
        running = True
        while running:
            for event in pygame.event.get():
                running = self.handle_event(event) and running
            if running and self.state == "playing":
                self.resolve_pending_wall_hit()
            self.frame_seconds = self.clock.tick(60) / 1000.0
            if running and self.state == "playing" and self.momentum is not None:
                self.try_move(*self.momentum)
            if running:
                self.update_music()
            self.draw()
        pygame.quit()


def main() -> None:
    MazeGame().run()


if __name__ == "__main__":
    main()
