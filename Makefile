PREFIX ?= /usr/local
BINDIR ?= ${PREFIX}/bin
MANDIR ?= ${PREFIX}/share/man

install:build
	install -d "${DESTDIR}${BINDIR}"
	install -d "${DESTDIR}${MANDIR}/man1"
	install -m755 tcvt.py "${DESTDIR}${BINDIR}/tcvt"
	install -m755 optcvt.sh.transformed "${DESTDIR}${BINDIR}/optcvt"
	install -m644 tcvt.1.gz "${DESTDIR}${MANDIR}/man1/tcvt.1.gz"
	ln -s tcvt.1.gz "${DESTDIR}${MANDIR}/man1/optcvt.1.gz"
build:optcvt.sh.transformed tcvt.1.gz
clean:
	rm -f optcvt.sh.transformed tcvt.1.gz

optcvt.sh.transformed:optcvt.sh
	sed 's!^TCVT=.*!TCVT="${BINDIR}/tcvt"!' < $< > $@

%.gz:%
	gzip -9 < $< > $@

.PHONY:build install clean
