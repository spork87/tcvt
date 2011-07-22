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

class TwoColumn:
    def __init__(self, curseswindow):
        self.screen = curseswindow
        self.height, width = self.screen.getmaxyx()
        self.halfwidth = (width - 1) // 2
        self.left = self.screen.derwin(self.height, self.halfwidth, 0, 0)
        self.left.scrollok(1)
        self.right = self.screen.derwin(self.height, self.halfwidth, 0,
                                        self.halfwidth + 1)
        self.right.scrollok(1)
        self.ypos, self.xpos = 0, 0
        self.screen.vline(0, self.halfwidth, curses.ACS_VLINE, self.height)
        self.attrs = 0

    @property
    def curwin(self):
        return self.left if self.ypos < self.height else self.right

    def getmaxyx(self):
        return (self.height * 2, self.halfwidth)

    def move(self, ypos, xpos):
        self.ypos = max(0, min(self.height * 2 - 1, ypos))
        self.xpos = max(0, min(self.halfwidth - 1, xpos))
        self.do_move()

    def do_move(self):
        self.curwin.move(self.ypos % self.height, self.xpos)

    def relmove(self, yoff, xoff):
        self.move(self.ypos + yoff, self.xpos + xoff)

    def addch(self, char):
        if self.xpos == self.halfwidth - 1:
            self.curwin.insch(self.ypos % self.height, self.xpos, char,
                              self.attrs)
            if self.ypos + 1 == 2 * self.height:
                self.scroll()
                self.move(self.ypos, 0)
            else:
                self.move(self.ypos + 1, 0)
        else:
            self.curwin.addch(self.ypos % self.height, self.xpos, char,
                              self.attrs)
            self.xpos += 1

    def refresh(self):
        self.screen.refresh()
        if self.ypos < self.height:
            self.right.refresh()
            self.left.refresh()
        else:
            self.left.refresh()
            self.right.refresh()

    def getyx(self):
        return (self.ypos, self.xpos)

    def scroll_up_right(self):
        """Copy first line of right window to last line of left window and
        scroll up the right window."""
        self.left.move(self.height - 1, 0)
        for x in range(self.halfwidth - 1):
            self.left.addch(self.right.inch(0, x))
        self.left.insch(self.right.inch(0, self.halfwidth - 1))
        self.do_move() # fix cursor
        self.right.scroll()

    def scroll_down_right(self):
        """Scroll down the right window and copy the last line of the left
        window to the first line of the right window."""
        self.right.scroll(-1)
        self.right.move(0, 0)
        for x in range(self.halfwidth - 1):
            self.right.addch(self.left.inch(self.height - 1, x))
        self.right.insch(self.left.inch(self.height - 1, self.halfwidth - 1))
        self.do_move() # fix cursor

    def scroll(self):
        self.left.scroll()
        self.scroll_up_right()

    def clrtobot(self):
        if self.ypos < self.height:
            self.right.clear()
            self.left.clrtobot()
        else:
            self.right.clrtobot()

    def attron(self, attr):
        self.attrs |= attr

    def clrtoeol(self):
        self.curwin.clrtoeol()

    def delch(self):
        self.curwin.delch(self.ypos % self.height, self.xpos)

    def attrset(self, attr):
        self.attrs = attr

    def insertln(self):
        if self.ypos >= self.height:
            self.right.insertln()
        else:
            self.scroll_down_right()
            self.left.insertln()

    def insch(self, char):
        self.curwin.insch(self.ypos % self.height, self.xpos, char, self.attrs)

    def deleteln(self):
        if self.ypos >= self.height:
            self.right.deleteln()
        else:
            self.left.deleteln()
            self.scroll_up_right()

    def inch(self):
        return self.curwin.inch(self.ypos % self.height, self.xpos)

class Terminal:
    def __init__(self):
        self.mode = (self.feed_simple,)
        self.realscreen = None
        self.screen = None
        self.fg = self.bg = 0
        self.graphics_font = False
        self.graphics_chars = {} # populated after initscr
        self.lastchar = ord(' ')

    def switchmode(self):
        if isinstance(self.screen, TwoColumn):
            self.screen = Simple(self.realscreen)
        else:
            self.screen = TwoColumn(self.realscreen)
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
        self.screen = TwoColumn(self.realscreen)
        curses.noecho()
        curses.raw()
        self.graphics_chars = {
            0x71: curses.ACS_HLINE,
            0xc4: curses.ACS_HLINE,
        }

    def stop(self):
        curses.noraw()
        curses.echo()
        curses.endwin()

    def feed(self, char):
        self.mode[0](char, *self.mode[1:])

    def feed_simple(self, char):
        if self.graphics_font and ord(char) in self.graphics_chars:
            self.addch(self.graphics_chars[ord(char)])
        elif char in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ':
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

    def feed_esc(self, char):
        if char == '[':
            self.mode = (self.feed_esc_opbr,)
        else:
            raise ValueError("feed esc %r" % char)

    def feed_esc_opbr(self, char):
        self.mode = (self.feed_simple,) # default
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
        elif code == 11:
            self.graphics_font = True
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
        self.mode = (self.feed_simple,) # default
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
    curses.setupterm(oldterm)
    return keymap

def main():
    keymapping =  compute_keymap(symbolic_keymapping)
    t = Terminal()

    pid, masterfd = pty.fork()
    if pid == 0: # child
        os.environ["TERM"] = "ansi"
        os.execvp(sys.argv[1], sys.argv[1:])
        sys.exit(1)

    try:
        t.start()
        t.resizepty(masterfd)
        while True:
            try:
                res, _, _ = select.select([0, masterfd], [], [])
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
                    elif key <= 0xff:
                        os.write(masterfd, chr(key))
                    elif key in keymapping:
                        os.write(masterfd, keymapping[key])
                    else:
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
                t.screen.refresh()
    finally:
        t.stop()

if __name__ == '__main__':
    main()
