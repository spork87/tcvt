#!/bin/sh
TCVT=./tcvt.py
MINWIDTH=80

SIZE=`stty size` || exit $?
COLUMNS="${SIZE#* }"
panes=$((COLUMNS / (MINWIDTH + 1)))

if test $panes -ge 2; then
	exec $TCVT -c$panes "$@"
elif test -z "$@"; then
	exec "$SHELL"
else
	exec "$@"
fi
