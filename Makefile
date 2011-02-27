PREFIX ?= /usr/local
BINDIR ?= ${PREFIX}/bin

install:tcvt.py optcvt.sh.transformed
	install -m755 tcvt.py "${DESTDIR}${BINDIR}/tcvt"
	install -m755 optcvt.sh.transformed "${DESTDIR}${BINDIR}/optcvt"
build:optcvt.sh.transformed
clean:
	rm -f optcvt.sh.transformed

optcvt.sh.transformed:optcvt.sh
	sed 's!^TCVT=.*!TCVT="${BINDIR}/tcvt"!' < $< > $@

.PHONY:build install clean
