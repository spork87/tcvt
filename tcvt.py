#!/usr/bin/python
#
# Tow Column Virtual Terminal.
#
# Copyright 2011 Helmut Grohne <helmut@subdivi.de>. All rights reserved.
# 
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
# 
#    1. Redistributions of source code must retain the above copyright notice,
#       this list of conditions and the following disclaimer.
# 
#    2. Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
# 
# THIS SOFTWARE IS PROVIDED BY HELMUT GROHNE ``AS IS'' AND ANY EXPRESS OR
# IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO
# EVENT SHALL HELMUT GROHNE OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA,
# OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE,
# EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
# 
# The views and conclusions contained in the software and documentation are
# those of the authors and should not be interpreted as representing official
# policies, either expressed or implied, of Helmut Grohne.

import pty
import sys
import os
import select
import fcntl
import termios
import struct
import curses
import errno
import time

def init_color_pairs():
    for bi, bc in enumerate((curses.COLOR_BLACK, curses.COLOR_RED,
                             curses.COLOR_GREEN, curses.COLOR_YELLOW,
                             curses.COLOR_BLUE, curses.COLOR_MAGENTA,
                             curses.COLOR_CYAN, curses.COLOR_WHITE)):
        for fi, fc in enumerate((curses.COLOR_WHITE, curses.COLOR_BLACK,
                                 curses.COLOR_RED, curses.COLOR_GREEN,
                                 curses.COLOR_YELLOW, curses.COLOR_BLUE,
                                 curses.COLOR_MAGENTA, curses.COLOR_CYAN)):
            if fi != 0 or bi != 0:
                curses.init_pair(fi*8+bi, fc, bc)

def get_color(fg=1, bg=0):
    return curses.color_pair(((fg + 1) % 8) * 8 + bg)

class Simple:
    def __init__(self, curseswindow):
        self.screen = curseswindow
        self.screen.scrollok(1)

    def getmaxyx(self):
        return self.screen.getmaxyx()

    def move(self, ypos, xpos):
        ym, xm = self.getmaxyx()
        self.screen.move(max(0, min(ym - 1, ypos)), max(0, min(xm - 1, xpos)))

    def relmove(self, yoff, xoff):
        y, x = self.getyx()
        self.move(y + yoff, x + xoff)

    def addch(self, char):
        self.screen.addch(char)

    def refresh(self):
        self.screen.refresh()

    def getyx(self):
        return self.screen.getyx()

    def scroll(self):
        self.screen.scroll()

    def clrtobot(self):
        self.screen.clrtobot()

    def attron(self, attr):
        self.screen.attron(attr)

    def clrtoeol(self):
        self.screen.clrtoeol()

    def delch(self):
        self.screen.delch()

    def attrset(self, attr):
        self.screen.attrset(attr)

    def insertln(self):
        self.screen.insertln()

    def insch(self, char):
        self.screen.insch(char)

    def deleteln(self):
        self.screen.deleteln()

    def inch(self):
        return self.screen.inch()

class Columns:
    def __init__(self, curseswindow, numcolumns=2):
        self.screen = curseswindow
        self.height, width = self.screen.getmaxyx()
        assert numcolumns > 1
        self.numcolumns = numcolumns
        self.columnwidth = (width - (numcolumns - 1)) // numcolumns
        assert self.columnwidth > 0
        self.windows = []
        for i in range(numcolumns):
            window = self.screen.derwin(self.height, self.columnwidth,
                                        0, i * (self.columnwidth + 1))
            window.scrollok(1)
            self.windows.append(window)
        self.ypos, self.xpos = 0, 0
        for i in range(1, numcolumns):
            self.screen.vline(0, i * (self.columnwidth + 1) - 1,
                              curses.ACS_VLINE, self.height)
        self.attrs = 0

    @property
    def curwin(self):
        return self.windows[self.ypos // self.height]

    @property
    def curypos(self):
        return self.ypos % self.height

    @property
    def curxpos(self):
        return self.xpos

    def getmaxyx(self):
        return (self.height * self.numcolumns, self.columnwidth)

    def move(self, ypos, xpos):
        height, width = self.getmaxyx()
        self.ypos = max(0, min(height - 1, ypos))
        self.xpos = max(0, min(width - 1, xpos))
        self.fix_cursor()

    def fix_cursor(self):
        self.curwin.move(self.curypos, self.curxpos)

    def relmove(self, yoff, xoff):
        self.move(self.ypos + yoff, self.xpos + xoff)

    def addch(self, char):
        if self.xpos == self.columnwidth - 1:
            self.curwin.insch(self.curypos, self.curxpos, char, self.attrs)
            if self.ypos + 1 == 2 * self.height:
                self.scroll()
                self.move(self.ypos, 0)
            else:
                self.move(self.ypos + 1, 0)
        else:
            self.curwin.addch(self.curypos, self.curxpos, char, self.attrs)
            self.xpos += 1

    def refresh(self):
        self.screen.refresh()
        for window in self.windows:
            if window is not self.curwin:
                window.refresh()
        self.curwin.refresh()

    def getyx(self):
        return (self.ypos, self.xpos)

    def scroll_up(self, index):
        """Copy first line of the window with given index to last line of the
        previous window and scroll up the given window."""
        assert index > 0
        previous = self.windows[index - 1]
        previous.move(self.height - 1, 0)
        for x in range(self.columnwidth - 1):
            previous.addch(self.windows[index].inch(0, x))
        previous.insch(self.windows[index].inch(0, self.columnwidth - 1))
        self.fix_cursor()
        self.windows[index].scroll()

    def scroll_down(self, index):
        """Scroll down the window with given index and copy the last line of
        the previous window to the first line of the given window."""
        assert index > 0
        current = self.windows[index]
        previous = self.windows[index - 1]
        current.scroll(-1)
        current.move(0, 0)
        for x in range(self.columnwidth - 1):
            current.addch(previous.inch(self.height - 1, x))
        current.insch(previous.inch(self.height - 1, self.columnwidth - 1))
        self.fix_cursor()

    def scroll(self):
        self.windows[0].scroll()
        for i in range(1, self.numcolumns):
            self.scroll_up(i)

    def clrtobot(self):
        index = self.ypos // self.height
        for i in range(index + 1, self.numcolumns):
            self.windows[i].clear()
        self.windows[index].clrtobot()

    def attron(self, attr):
        self.attrs |= attr

    def clrtoeol(self):
        self.curwin.clrtoeol()

    def delch(self):
        self.curwin.delch(self.curypos, self.curxpos)

    def attrset(self, attr):
        self.attrs = attr

    def insertln(self):
        index = self.ypos // self.height
        for i in reversed(range(index + 1, self.numcolumns)):
            self.scroll_down(i)
        self.curwin.insertln()

    def insch(self, char):
        self.curwin.insch(self.curypos, self.curxpos, char, self.attrs)

    def deleteln(self):
        index = self.ypos // self.height
        self.windows[index].deleteln()
        for i in range(index + 1, self.numcolumns):
            self.scroll_up(i)

    def inch(self):
        return self.curwin.inch(self.curypos, self.curxpos)

def acs_map():
    """call after curses.initscr"""
    # can this mapping be obtained from curses?
    return {
        'l': curses.ACS_ULCORNER,
        'm': curses.ACS_LLCORNER,
        'k': curses.ACS_URCORNER,
        'j': curses.ACS_LRCORNER,
        't': curses.ACS_LTEE,
        'u': curses.ACS_RTEE,
        'v': curses.ACS_BTEE,
        'w': curses.ACS_TTEE,
        'q': curses.ACS_HLINE,
        'x': curses.ACS_VLINE,
        'n': curses.ACS_PLUS,
        'o': curses.ACS_S1,
        's': curses.ACS_S9,
        '`': curses.ACS_DIAMOND,
        'a': curses.ACS_CKBOARD,
        'f': curses.ACS_DEGREE,
        'g': curses.ACS_PLMINUS,
        '~': curses.ACS_BULLET,
        ',': curses.ACS_LARROW,
        '+': curses.ACS_RARROW,
        '.': curses.ACS_DARROW,
        '-': curses.ACS_UARROW,
        'h': curses.ACS_BOARD,
        'i': curses.ACS_LANTERN,
        'p': curses.ACS_S3,
        'r': curses.ACS_S7,
        'y': curses.ACS_LEQUAL,
        'z': curses.ACS_GEQUAL,
        '{': curses.ACS_PI,
        '|': curses.ACS_NEQUAL,
        '}': curses.ACS_STERLING,
    }

def compose_dicts(dct1, dct2):
    result = {}
    for key, value in dct1.items():
        try:
            result[key] = dct2[value]
        except KeyError:
            pass
    return result

class Terminal:
    def __init__(self, acsc):
        self.mode = (self.feed_simple,)
        self.realscreen = None
        self.screen = None
        self.fg = self.bg = 0
        self.graphics_font = False
        self.graphics_chars = acsc # really initialized after
        self.lastchar = ord(' ')

    def switchmode(self):
        if isinstance(self.screen, Columns):
            self.screen = Simple(self.realscreen)
        else:
            self.screen = Columns(self.realscreen)
        self.screen.refresh()

    def resized(self):
        self.screen = Simple(self.realscreen)
        self.screen.refresh()

    def resizepty(self, ptyfd):
        ym, xm = self.screen.getmaxyx()
        fcntl.ioctl(ptyfd, termios.TIOCSWINSZ,
                    struct.pack("HHHH", ym, xm, 0, 0))

    def addch(self, char):
        self.lastchar = char
        self.screen.addch(char)

    def start(self):
        self.realscreen = curses.initscr()
        self.realscreen.nodelay(1)
        self.realscreen.keypad(1)
        curses.start_color()
        init_color_pairs()
        self.screen = Columns(self.realscreen)
        curses.noecho()
        curses.raw()
        self.graphics_chars = compose_dicts(self.graphics_chars, acs_map())

    def stop(self):
        curses.noraw()
        curses.echo()
        curses.endwin()

    def feed_reset(self):
        if self.graphics_font:
            self.mode = (self.feed_graphics,)
        else:
            self.mode = (self.feed_simple,)

    def feed(self, char):
        self.mode[0](char, *self.mode[1:])

    def feed_simple(self, char):
        if char in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ':
            self.addch(ord(char))
        elif char in '0123456789@:~$ .#!/_(),[]=-+*\'"|<>%&\\?;`^{}':
            self.addch(ord(char))
        elif char in '\xb4\xb6\xb7\xc3\xc4\xd6\xdc\xe4\xe9\xfc\xf6':
            self.addch(ord(char))
        elif char == '\r':
            self.screen.relmove(0, -9999)
        elif char == '\n':
            y, _ = self.screen.getyx()
            ym, _ = self.screen.getmaxyx()
            if y + 1 == ym:
                self.screen.scroll()
                self.screen.move(y, 0)
            else:
                self.screen.move(y+1, 0)
        elif char == '\x1b':
            self.mode = (self.feed_esc,)
        elif char == '\a':
            curses.beep()
        elif char == '\b':
            self.screen.relmove(0, -1)
        elif char == '\t':
            y, x = self.screen.getyx()
            _, xm = self.screen.getmaxyx()
            x = min(x + 8 - x % 8, xm - 1)
            self.screen.move(y, x)
        else:
            raise ValueError("feed %r" % char)

    def feed_graphics(self, char):
        if char == '\x1b':
            self.mode = (self.feed_esc,)
        elif char in self.graphics_chars:
            self.addch(self.graphics_chars[char])
        elif char == 'q': # some applications appear to use VT100 names?
            self.addch(curses.ACS_HLINE)
        else:
            raise ValueError("graphics %r" % char)

    def feed_esc(self, char):
        if char == '[':
            self.mode = (self.feed_esc_opbr,)
        else:
            raise ValueError("feed esc %r" % char)

    def feed_esc_opbr(self, char):
        self.feed_reset()
        if char == 'H':
            self.feed_esc_opbr_next('H', "0;0")
        elif char == 'J':
            self.screen.clrtobot()
        elif char == 'm':
            self.feed_esc_opbr_next('m', '0')
        elif char in '0123456789':
            self.mode = (self.feed_esc_opbr_next, char)
        elif char == 'K':
            self.screen.clrtoeol()
        elif char in 'ABCDLMP':
            self.feed_esc_opbr_next(char, '1')
        else:
            raise ValueError("feed esc [ %r" % char)

    def feed_color(self, code):
        if code == 0:
            self.fg = self.bg = 0
            self.screen.attrset(0)
        elif code == 1:
            self.screen.attron(curses.A_BOLD)
        elif code == 4:
            self.screen.attron(curses.A_UNDERLINE)
        elif code == 7:
            self.screen.attron(curses.A_REVERSE)
        elif code == 10:
            self.graphics_font = False
            self.feed_reset()
        elif code == 11:
            self.graphics_font = True
            self.feed_reset()
        elif 30 <= code <= 37:
            self.fg = code - 30
            self.screen.attron(get_color(self.fg, self.bg))
        elif code == 39:
            self.fg = 7
            self.screen.attron(get_color(self.fg, self.bg))
        elif 40 <= code <= 47:
            self.bg = code - 40
            self.screen.attron(get_color(self.fg, self.bg))
        elif code == 49:
            self.bg = 0
            self.screen.attron(get_color(self.fg, self.bg))
        else:
            raise ValueError("feed esc [ %r m" % code)

    def feed_esc_opbr_next(self, char, prev):
        self.feed_reset()
        if char in '0123456789;':
            self.mode = (self.feed_esc_opbr_next, prev + char)
        elif char == 'm':
            parts = prev.split(';')
            for p in parts:
                self.feed_color(int(p))
        elif char == 'H':
            parts = prev.split(';')
            if len(parts) != 2:
                raise ValueError("feed esc [ %r H" % parts)
            self.screen.move(*map((-1).__add__, map(int, parts)))
        elif prev == '2' and char == 'J':
            self.screen.move(0, 0)
            self.screen.clrtobot()
        elif char == 'C' and prev.isdigit():
            self.screen.relmove(0, int(prev))
        elif char == 'P' and prev.isdigit():
            for _ in range(int(prev)):
                self.screen.delch()
        elif char == '@' and prev.isdigit():
            for _ in range(int(prev)):
                self.screen.insch(ord(' '))
        elif char == 'A' and prev.isdigit():
            self.screen.relmove(-int(prev), 0)
        elif char == 'M' and prev.isdigit():
            for _ in range(int(prev)):
                self.screen.deleteln()
        elif char == 'L' and prev.isdigit():
            for _ in range(int(prev)):
                self.screen.insertln()
        elif char == 'D' and prev.isdigit():
            self.screen.relmove(0, -int(prev))
        elif char == 'd' and prev.isdigit():
            _, x = self.screen.getyx()
            self.screen.move(int(prev) - 1, x)
        elif char == 'B' and prev.isdigit():
            self.screen.relmove(int(prev), 0)
        elif char == 'b' and prev.isdigit():
            for _ in range(int(prev)):
                self.screen.addch(self.lastchar)
        elif char == 'G' and prev.isdigit():
            y, _ = self.screen.getyx()
            self.screen.move(y, int(prev) - 1)
        elif char == 'X' and prev.isdigit():
            for _ in range(int(prev)):
                self.screen.addch(ord(' '))
        elif char == 'K' and prev == '1':
            y, x = self.screen.getyx()
            self.screen.move(y, 0)
            for _ in range(x):
                self.screen.addch(ord(' '))
        else:
            raise ValueError("feed esc [ %r %r" % (prev, char))

symbolic_keymapping = {
    ord("\n"): "cr",
    curses.KEY_LEFT: "kcub1",
    curses.KEY_DOWN: "kcud1",
    curses.KEY_RIGHT: "kcuf1",
    curses.KEY_UP: "kcuu1",
    curses.KEY_HOME: "khome",
    curses.KEY_IC: "kich1",
    curses.KEY_BACKSPACE: "kbs",
    curses.KEY_PPAGE: "kpp",
    curses.KEY_NPAGE: "knp",
}

def compute_keymap(symbolic_map):
    oldterm = os.environ["TERM"]
    curses.setupterm("ansi")
    keymap = {}
    for key, value in symbolic_map.items():
        keymap[key] = (curses.tigetstr(value) or "").replace("\\E", "\x1b")
    acsc = curses.tigetstr("acsc")
    acsc = dict(zip(acsc[1::2], acsc[::2]))
    curses.setupterm(oldterm)
    return keymap, acsc

def set_cloexec(fd):
    flags = fcntl.fcntl(fd, fcntl.F_GETFD, 0)
    flags |= fcntl.FD_CLOEXEC
    fcntl.fcntl(fd, fcntl.F_SETFD, flags)

def main():
    keymapping, acsc = compute_keymap(symbolic_keymapping)
    t = Terminal(acsc)

    errpiper, errpipew = os.pipe()
    set_cloexec(errpipew)
    pid, masterfd = pty.fork()
    if pid == 0: # child
        os.close(errpiper)
        os.environ["TERM"] = "ansi"
        try:
            if len(sys.argv) < 2:
                os.execvp(os.environ["SHELL"], [os.environ["SHELL"]])
            else:
                os.execvp(sys.argv[1], sys.argv[1:])
        except OSError, err:
            os.write(errpipew, "exec failed: %s" % (err,))
        sys.exit(1)

    os.close(errpipew)
    data = os.read(errpiper, 1024)
    os.close(errpiper)
    if data:
        print(data)
        sys.exit(1)
    try:
        t.start()
        t.resizepty(masterfd)
        refreshpending = None
        while True:
            try:
                res, _, _ = select.select([0, masterfd], [], [],
                                          refreshpending and 0)
            except select.error, err:
                if err.args[0] == errno.EINTR:
                    t.resized()
                    t.resizepty(masterfd)
                    continue
                raise
            if 0 in res:
                while True:
                    key = t.realscreen.getch()
                    if key == -1:
                        break
                    if key == 0xb3:
                        t.switchmode()
                        t.resizepty(masterfd)
                    elif key in keymapping:
                        os.write(masterfd, keymapping[key])
                    elif key <= 0xff:
                        os.write(masterfd, chr(key))
                    else:
                        if "TCVT_DEVEL" in os.environ:
                            raise ValueError("getch returned %d" % key)
            elif masterfd in res:
                try:
                    data = os.read(masterfd, 1024)
                except OSError:
                    break
                if not data:
                    break
                for char in data:
                    t.feed(char)
                if refreshpending is None:
                    refreshpending = time.time() + 0.1
            elif refreshpending is not None:
                t.screen.refresh()
                refreshpending = None
            if refreshpending is not None and refreshpending < time.time():
                t.screen.refresh()
                refreshpending = None
    finally:
        t.stop()

if __name__ == '__main__':
    main()
