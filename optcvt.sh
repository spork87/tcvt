#!/bin/sh
TCVT=./tcvt.py
MINWIDTH=80

SIZE=`stty size`
test $? = 0 || exit $?
COLUMNS="${SIZE#* }"

if test "$COLUMNS" -ge $((2*$MINWIDTH+1)); then
	exec $TCVT "$@"
elif test -z "$@"; then
	exec "$SHELL"
else
	exec "$@"
fi
