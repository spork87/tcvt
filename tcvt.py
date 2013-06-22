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
import optparse

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

class BadWidth(Exception):
    pass

class Columns:
    def __init__(self, curseswindow, numcolumns=2):
        self.screen = curseswindow
        self.height, width = self.screen.getmaxyx()
        if numcolumns < 1:
            raise BadWidth("need at least two columns")
        self.numcolumns = numcolumns
        self.columnwidth = (width - (numcolumns - 1)) // numcolumns
        if self.columnwidth <= 0:
            raise BadWidth("resulting column width too small")
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
        ord(b'l'): curses.ACS_ULCORNER,
        ord(b'm'): curses.ACS_LLCORNER,
        ord(b'k'): curses.ACS_URCORNER,
        ord(b'j'): curses.ACS_LRCORNER,
        ord(b't'): curses.ACS_LTEE,
        ord(b'u'): curses.ACS_RTEE,
        ord(b'v'): curses.ACS_BTEE,
        ord(b'w'): curses.ACS_TTEE,
        ord(b'q'): curses.ACS_HLINE,
        ord(b'x'): curses.ACS_VLINE,
        ord(b'n'): curses.ACS_PLUS,
        ord(b'o'): curses.ACS_S1,
        ord(b's'): curses.ACS_S9,
        ord(b'`'): curses.ACS_DIAMOND,
        ord(b'a'): curses.ACS_CKBOARD,
        ord(b'f'): curses.ACS_DEGREE,
        ord(b'g'): curses.ACS_PLMINUS,
        ord(b'~'): curses.ACS_BULLET,
        ord(b','): curses.ACS_LARROW,
        ord(b'+'): curses.ACS_RARROW,
        ord(b'.'): curses.ACS_DARROW,
        ord(b'-'): curses.ACS_UARROW,
        ord(b'h'): curses.ACS_BOARD,
        ord(b'i'): curses.ACS_LANTERN,
        ord(b'p'): curses.ACS_S3,
        ord(b'r'): curses.ACS_S7,
        ord(b'y'): curses.ACS_LEQUAL,
        ord(b'z'): curses.ACS_GEQUAL,
        ord(b'{'): curses.ACS_PI,
        ord(b'|'): curses.ACS_NEQUAL,
        ord(b'}'): curses.ACS_STERLING,
    }

def compose_dicts(dct1, dct2):
    result = {}
    for key, value in dct1.items():
        try:
            result[key] = dct2[value]
        except KeyError:
            pass
    return result

simple_characters = bytearray(
        b'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ' +
        b'0123456789@:~$ .#!/_(),[]=-+*\'"|<>%&\\?;`^{}' +
        b'\xb4\xb6\xb7\xc3\xc4\xd6\xdc\xe4\xe9\xfc\xf6')

class Terminal:
    def __init__(self, acsc, columns):
        self.mode = (self.feed_simple,)
        self.realscreen = None
        self.screen = None
        self.fg = self.bg = 0
        self.graphics_font = False
        self.graphics_chars = acsc # really initialized after
        self.lastchar = ord(b' ')
        self.columns = columns

    def switchmode(self):
        if isinstance(self.screen, Columns):
            self.screen = Simple(self.realscreen)
        else:
            self.screen = Columns(self.realscreen, self.columns)
        self.screen.refresh()

    def resized(self):
        # The refresh call causes curses to notice the new dimensions.
        self.realscreen.refresh()
        self.realscreen.clear()
        try:
            self.screen = Columns(self.realscreen, self.columns)
        except BadWidth:
            self.screen = Simple(self.realscreen)

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
        self.screen = Columns(self.realscreen, self.columns)
        curses.noecho()
        curses.raw()
        self.graphics_chars = compose_dicts(self.graphics_chars, acs_map())

    def stop(self):
        curses.noraw()
        curses.echo()
        curses.endwin()

    def do_bel(self):
        curses.beep()

    def do_blink(self):
        self.screen.attron(curses.A_BLINK)

    def do_bold(self):
        self.screen.attron(curses.A_BOLD)

    def do_cr(self):
        self.screen.relmove(0, -9999)

    def do_cub(self, n):
        self.screen.relmove(0, -n)

    def do_cub1(self):
        self.do_cub(1)

    def do_cud(self, n):
        self.screen.relmove(n, 0)

    def do_cud1(self):
        self.do_cud(1)

    def do_cuf(self, n):
        self.screen.relmove(0, n)

    def do_cuf1(self):
        self.do_cuf(1)

    def do_cuu(self, n):
        self.screen.relmove(-n, 0)

    def do_cuu1(self):
        self.do_cuu(1)

    def do_dch(self, n):
        for _ in range(n):
            self.screen.delch()

    def do_dch1(self):
        self.do_dch(1)

    def do_dl(self, n):
        for _ in range(n):
            self.screen.deleteln()

    def do_dl1(self):
        self.do_dl(1)

    def do_ech(self, n):
        for _ in range(n):
            self.screen.addch(ord(b' '))

    def do_ed(self):
        self.screen.clrtobot()

    def do_el(self):
        self.screen.clrtoeol()

    def do_el1(self):
        y, x = self.screen.getyx()
        self.screen.move(y, 0)
        for _ in range(x):
            self.screen.addch(ord(b' '))

    def do_home(self):
        self.screen.move(0, 0)

    def do_hpa(self, n):
        y, _ = self.screen.getyx()
        self.screen.move(y, n)

    def do_ht(self):
        y, x = self.screen.getyx()
        _, xm = self.screen.getmaxyx()
        x = min(x + 8 - x % 8, xm - 1)
        self.screen.move(y, x)

    def do_ich(self, n):
        for _ in range(n):
            self.screen.insch(ord(b' '))

    def do_il(self, n):
        for _ in range(n):
            self.screen.insertln()

    def do_il1(self):
        self.do_il(1)

    def do_ind(self):
        y, _ = self.screen.getyx()
        ym, _ = self.screen.getmaxyx()
        if y + 1 == ym:
            self.screen.scroll()
            self.screen.move(y, 0)
        else:
            self.screen.move(y+1, 0)

    def do_invis(self):
        self.screen.attron(curses.A_INVIS)

    def do_smul(self):
        self.screen.attron(curses.A_UNDERLINE)

    def do_vpa(self, n):
        _, x = self.screen.getyx()
        self.screen.move(n, x)

    def feed_reset(self):
        if self.graphics_font:
            self.mode = (self.feed_graphics,)
        else:
            self.mode = (self.feed_simple,)

    def feed(self, char):
        self.mode[0](char, *self.mode[1:])

    def feed_simple(self, char):
        func = {
                ord('\a'): self.do_bel,
                ord('\n'): self.do_ind,
                ord('\r'): self.do_cr,
                ord('\t'): self.do_ht,
            }.get(char)
        if func:
            func()
        elif char in simple_characters:
            self.addch(char)
        elif char == 0x1b:
            self.mode = (self.feed_esc,)
        elif char == ord(b'\b'):
            self.screen.relmove(0, -1)
        else:
            raise ValueError("feed %r" % char)

    def feed_graphics(self, char):
        if char == 0x1b:
            self.mode = (self.feed_esc,)
        elif char in self.graphics_chars:
            self.addch(self.graphics_chars[char])
        elif char == ord(b'q'):  # some applications appear to use VT100 names?
            self.addch(curses.ACS_HLINE)
        else:
            raise ValueError("graphics %r" % char)

    def feed_esc(self, char):
        if char == ord(b'['):
            self.mode = (self.feed_esc_opbr,)
        else:
            raise ValueError("feed esc %r" % char)

    def feed_esc_opbr(self, char):
        self.feed_reset()
        func = {
                ord('A'): self.do_cuu1,
                ord('B'): self.do_cud1,
                ord('C'): self.do_cuf1,
                ord('D'): self.do_cub1,
                ord('H'): self.do_home,
                ord('J'): self.do_ed,
                ord('L'): self.do_il1,
                ord('M'): self.do_dl1,
                ord('K'): self.do_el,
                ord('P'): self.do_dch1,
            }.get(char)
        if func:
            func()
        elif char == ord(b'm'):
            self.feed_esc_opbr_next(char, bytearray(b'0'))
        elif char in bytearray(b'0123456789'):
            self.mode = (self.feed_esc_opbr_next, bytearray((char,)))
        else:
            raise ValueError("feed esc [ %r" % char)

    def feed_color(self, code):
        func = {
                1: self.do_bold,
                4: self.do_smul,
                5: self.do_blink,
                8: self.do_invis,
            }.get(code)
        if func:
            func()
        elif code == 0:
            self.fg = self.bg = 0
            self.screen.attrset(0)
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
        func = {
                ord('A'): self.do_cuu,
                ord('B'): self.do_cud,
                ord('C'): self.do_cuf,
                ord('D'): self.do_cub,
                ord('L'): self.do_il,
                ord('M'): self.do_dl,
                ord('P'): self.do_dch,
                ord('X'): self.do_ech,
                ord('@'): self.do_ich,
            }.get(char)
        if func and prev.isdigit():
            func(int(prev))
        elif char in bytearray(b'0123456789;'):
            self.mode = (self.feed_esc_opbr_next, prev + bytearray((char,)))
        elif char == ord(b'm'):
            parts = prev.split(b';')
            for p in parts:
                self.feed_color(int(p))
        elif char == ord(b'H'):
            parts = prev.split(b';')
            if len(parts) != 2:
                raise ValueError("feed esc [ %r H" % parts)
            self.screen.move(*map((-1).__add__, map(int, parts)))
        elif prev == bytearray(b'2') and char == ord(b'J'):
            self.screen.move(0, 0)
            self.screen.clrtobot()
        elif char == ord(b'd') and prev.isdigit():
            self.do_vpa(int(prev) - 1)
        elif char == ord(b'b') and prev.isdigit():
            for _ in range(int(prev)):
                self.screen.addch(self.lastchar)
        elif char == ord(b'G') and prev.isdigit():
            self.do_hpa(int(prev) - 1)
        elif char == ord(b'K') and prev == b'1':
            self.do_el1()
        else:
            raise ValueError("feed esc [ %r %r" % (prev, char))

symbolic_keymapping = {
    ord(b"\n"): "cr",
    curses.KEY_LEFT: "kcub1",
    curses.KEY_DOWN: "kcud1",
    curses.KEY_RIGHT: "kcuf1",
    curses.KEY_UP: "kcuu1",
    curses.KEY_HOME: "khome",
    curses.KEY_IC: "kich1",
    curses.KEY_BACKSPACE: "kbs",
    curses.KEY_PPAGE: "kpp",
    curses.KEY_NPAGE: "knp",
    curses.KEY_F1: "kf1",
    curses.KEY_F2: "kf2",
    curses.KEY_F3: "kf3",
    curses.KEY_F4: "kf4",
    curses.KEY_F5: "kf5",
    curses.KEY_F6: "kf6",
    curses.KEY_F7: "kf7",
    curses.KEY_F8: "kf8",
    curses.KEY_F9: "kf9",
}

def compute_keymap(symbolic_map):
    oldterm = os.environ["TERM"]
    curses.setupterm("ansi")
    keymap = {}
    for key, value in symbolic_map.items():
        keymap[key] = (curses.tigetstr(value) or b"").replace(b"\\E", b"\x1b")
    acsc = curses.tigetstr("acsc")
    acsc = bytearray(acsc)
    acsc = dict(zip(acsc[1::2], acsc[::2]))
    curses.setupterm(oldterm)
    return keymap, acsc

def set_cloexec(fd):
    flags = fcntl.fcntl(fd, fcntl.F_GETFD, 0)
    flags |= fcntl.FD_CLOEXEC
    fcntl.fcntl(fd, fcntl.F_SETFD, flags)

def main():
    parser = optparse.OptionParser()
    parser.disable_interspersed_args()
    parser.add_option("-c", "--columns", dest="columns", metavar="N",
                      type="int", default=2, help="number of columns")
    options, args = parser.parse_args()
    keymapping, acsc = compute_keymap(symbolic_keymapping)
    t = Terminal(acsc, options.columns)

    errpiper, errpipew = os.pipe()
    set_cloexec(errpipew)
    pid, masterfd = pty.fork()
    if pid == 0: # child
        os.close(errpiper)
        os.environ["TERM"] = "ansi"
        try:
            if len(args) < 1:
                os.execvp(os.environ["SHELL"], [os.environ["SHELL"]])
            else:
                os.execvp(args[0], args)
        except OSError as err:
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
            except select.error as err:
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
                        os.write(masterfd, struct.pack("B", key))
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
                for char in bytearray(data):
                    if "TCVT_DEVEL" in os.environ:
                        t.feed(char)
                    else:
                        try:
                            t.feed(char)
                        except ValueError:
                            t.feed_reset()
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
