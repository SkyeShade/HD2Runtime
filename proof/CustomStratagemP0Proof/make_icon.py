"""Writes images/orbital_gas_barrage_icon.png, the proof's obviously custom development icon (docs/custom-images.md):
a red checkerboard crossed by a green X inside a green frame, in the game's icon mask convention (red and green on
black). Deterministic; run it only to regenerate the file."""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'scripts'))
import hd2_image  # noqa: E402

SIZE = 256


def pixel(x, y):
    frame = x < 14 or y < 14 or x >= SIZE - 14 or y >= SIZE - 14
    inner = 24 <= x < SIZE - 24 and 24 <= y < SIZE - 24
    checker = inner and ((x - 24) // 52 + (y - 24) // 52) % 2 == 0
    cross = inner and (abs(x - y) < 8 or abs(x + y - (SIZE - 1)) < 8)
    return (255 if checker else 0, 255 if frame or cross else 0, 0, 255)


if __name__ == '__main__':
    data = bytes(v for y in range(SIZE) for x in range(SIZE) for v in pixel(x, y))
    (HERE / 'images/orbital_gas_barrage_icon.png').write_bytes(hd2_image.write_png(SIZE, SIZE, data))
