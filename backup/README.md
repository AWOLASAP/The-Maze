# Pygame Maze

This program is a ten-level pygame maze game. Move the red block to the green
goal, avoid the walls, and complete all levels before losing three lives.

## Run

```text
pip install -r requirements.txt
python maze_game.py
```

Scores are stored in encrypted `scores.dat` data. A local `scores.key` file is
created on first run and should be kept with the game data.

Short life-loss and goal-reached sound effects are stored in the `Sound Effects`
folder separately from the background music.

## Controls

- Arrow keys or WASD: move freely with continuous momentum; press a direction to turn
- P: pause during gameplay; losing window focus also pauses
- Infinite Mode: collect the blue bonus for a 3x level-score multiplier; avoid the flashing pink hazards
- Enter/Space: select a menu option
- Escape: return to the title screen from credits
