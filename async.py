import asyncio
import curses
import textwrap
import os
from itertools import cycle, islice, chain
from os.path import isfile, join
from random import choice, randint, randrange
from statistics import median

import obstacles
from constants import GARBAGE_DIR, STARS_AMOUNT, STAR_CHARS, TIC_TIMEOUT, TIC_PER_YEAR
from curses_tools import draw_frame, get_frame_size, read_controls
from explosion import explode
from game_scenario import PHRASES, get_garbage_delay_tics
from physics import update_speed


loop = asyncio.get_event_loop()
garbages = {}
year = 1957


async def show_year(canvas):
    global year
    while True:
        frame = f'{year}: {PHRASES.get(year, "")}'
        draw_frame(canvas, 1, 1, frame)
        await asyncio.sleep(TIC_TIMEOUT*TIC_PER_YEAR)
        draw_frame(canvas, 1, 1, frame, negative=True)
        year += 1


async def show_gameover(canvas):
    frame = '''\
                  _____                         ____                 
                 / ____|                       / __ \                
                | |  __  __ _ _ __ ___   ___  | |  | |_   _____ _ __ 
                | | |_ |/ _` | '_ ` _ \ / _ \ | |  | \ \ / / _ \ '__|
                | |__| | (_| | | | | | |  __/ | |__| |\ V /  __/ |   
                 \_____|\__,_|_| |_| |_|\___|  \____/  \_/ \___|_|   
            '''
    frame  = textwrap.dedent(frame)
    canvas_rows, canvas_cols = canvas.getmaxyx()
    frame_rows, frame_cols = get_frame_size(frame)
    while True:
        draw_frame(canvas, (canvas_rows-frame_rows)//2,
                (canvas_cols-frame_cols)//2, frame)
        await asyncio.sleep(TIC_TIMEOUT)


async def fire(canvas, start_row, start_column, rows_speed=-0.3,
               columns_speed=0, ticks=1):
    """Display animation of gun shot, direction and speed can be specified."""

    row, column = start_row, start_column
    row += rows_speed
    column += columns_speed

    symbol = '-' if columns_speed else '|'

    rows, columns = canvas.getmaxyx()
    max_row, max_column = rows - 1, columns - 1

    curses.beep()

    while 0 < round(row) < max_row and 0 < round(column) < max_column:
        for obstacle in garbages.values():
            if obstacle.has_collision(row, column):
                obstacle.status = 0
                return
        canvas.addstr(round(row), round(column), symbol)
        await asyncio.sleep(TIC_TIMEOUT*ticks)
        canvas.addstr(round(row), round(column), ' ')
        row += rows_speed
        column += columns_speed


async def fly_garbage(canvas, garbage, garbage_frame, speed=0.5):
    """Animate garbage, flying from top to bottom.
    Сolumn position will stay same, as specified on start."""
    rows_number, columns_number = canvas.getmaxyx()

    column = garbage.column
    column = max(column, 0)
    column = min(column, columns_number - 1)

    row = garbage.row

    while row < rows_number - 1:
        if not garbage.status:
            garbages.pop(garbage.uid, None)
            center_row = garbage.row + garbage.rows_size % 2
            center_column = garbage.column + garbage.columns_size % 2
            await explode(canvas, center_row, center_column)
            return
        draw_frame(canvas, row, column, garbage_frame)
        canvas.refresh()
        await asyncio.sleep(TIC_TIMEOUT)
        draw_frame(canvas, row, column, garbage_frame, negative=True)
        row += speed
        garbage.row = row


def check_bounds(canvas, row, col, frame):
    num_row, num_col = canvas.getmaxyx()
    height, width = get_frame_size(frame)
    row = median([1, row, num_row-height-1])
    col = median([1, col, num_col-width-1])
    return row, col


async def animate_spaceship(canvas, start_row, start_col, frames, ticks):
    total_ticks = 0
    last_frame = ''
    row = start_row
    col = start_col
    new_row = row
    new_col = col
    row_speed = 0
    column_speed = 0
    for frame in cycle(frames):
        rows_direction, cols_direction, space_pressed = read_controls(canvas)
        if space_pressed and  year > 2019:
            loop.create_task(fire(canvas, row, col+2))
        row_speed, column_speed = update_speed(row_speed, column_speed,
                                               rows_direction, cols_direction,)
        new_row, new_col = check_bounds(
                canvas, row+row_speed,
                col+column_speed, frame, )
        if not total_ticks % ticks:
            draw_frame(canvas, round(row), round(col), last_frame,
                       negative=True, )
            frame_rows, frame_cols = get_frame_size(frame)
            for obstacle in garbages.values():
                if obstacle.has_collision(new_row, new_col,
                                          frame_rows, frame_cols):
                    loop.create_task(show_gameover(canvas))
                    return
            draw_frame(canvas, round(new_row), round(new_col), frame, )
            row = new_row
            col = new_col
        last_frame = frame
        canvas.refresh()
        await asyncio.sleep(TIC_TIMEOUT*ticks)


async def blink(canvas, row, col, symbol='*'):
    animation = [(curses.A_DIM, 20), (curses.A_NORMAL, 3),
                 (curses.A_BOLD, 5), (curses.A_NORMAL, 3), ]
    start_step = randrange(len(animation))
    animation_head = islice(animation, start_step, None)
    animation_tail = islice(animation, start_step)
    animation = cycle(chain(animation_head, animation_tail))

    for attr, ticks in animation:
        canvas.addstr(row, col, symbol, attr)
        await asyncio.sleep(TIC_TIMEOUT*ticks)


async def fill_orbit_with_garbage (canvas, garbage_frames, ticks=1):
    garbage_uid = 0
    while True:
        delay = get_garbage_delay_tics(year)
        if not delay:
            await asyncio.sleep(TIC_TIMEOUT*TIC_PER_YEAR)
            continue
        frame = choice(garbage_frames)
        frame_rows, frame_cols = get_frame_size(frame)
        _, canvas_cols = canvas.getmaxyx()
        garbage_col = randint(1, canvas_cols-frame_cols-1)
        garbage = obstacles.Obstacle(1, garbage_col, frame_rows, frame_cols,
                                     garbage_uid)
        garbages[garbage_uid] = garbage
        garbage_uid += 1
        loop.create_task(fly_garbage(canvas, garbage, frame, speed=0.5))
        await asyncio.sleep(TIC_TIMEOUT*delay)


def create_starset(max_row, max_col, num, symbols=['*']):
    return [(randint(1,max_row-2), randint(1, max_col-2), choice(symbols)) for
            _ in range(num)]

def create_garbageset():
    garbage_frames = []
    files = [join(GARBAGE_DIR, f) for f in os.listdir(GARBAGE_DIR)
             if isfile(join(GARBAGE_DIR, f))]
    for filepath in files:
        with open(filepath, "r") as garbage_file:
            garbage_frames.append(garbage_file.read())
    return garbage_frames


def draw(canvas):
    curses.curs_set(False)
    canvas.nodelay(True)
    canvas.border()
    canvas.refresh()
    (max_row, max_col) = canvas.getmaxyx()
    center_row = max_row // 2
    center_col = max_col // 2

    with open("files/rocket_frame_1.txt", 'r') as my_file:
        rocket_frame_1 = my_file.read()
    with open("files/rocket_frame_2.txt", 'r') as my_file:
        rocket_frame_2 = my_file.read()
    garbage_frames = create_garbageset()

    stars = create_starset(max_row, max_col, STARS_AMOUNT, STAR_CHARS)
    for row, col, symbol in stars:
        loop.create_task(blink(canvas, row, col, symbol))
    loop.create_task(animate_spaceship(canvas, center_row, center_col, 
                        [rocket_frame_1, rocket_frame_2, ], ticks=2))
    loop.create_task(fill_orbit_with_garbage (canvas, garbage_frames, ticks=3))
    loop.create_task(show_year(canvas))
    loop.run_forever()

if __name__ == '__main__':
    curses.update_lines_cols()
    curses.wrapper(draw)
