CC ?= cc
CFLAGS ?= -O2 -g
CFLAGS += -std=c11 -Wall -Wextra -Wpedantic -Werror -Wno-deprecated-declarations
CPPFLAGS += $(shell cups-config --cflags)
LDLIBS += $(shell cups-config --image --libs)
PREFIX ?= /usr
CUPS_SERVERBIN ?= $(shell cups-config --serverbin)
PPDDIR ?= $(PREFIX)/share/ppd/ctp800bd

.PHONY: all test install uninstall clean
all: build/rastertoctp800bd

build:
	mkdir -p $@

build/rastertoctp800bd: src/rastertoctp800bd.c | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) $< -o $@ $(LDLIBS)

build/mkraster: tests/mkraster.c | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) $< -o $@ $(LDLIBS)

test: all build/mkraster
	cupstestppd -W filters ppd/ctp800bd.ppd
	python3 -m unittest discover -s tests -v

install: all
	install -Dm755 build/rastertoctp800bd $(DESTDIR)$(CUPS_SERVERBIN)/filter/rastertoctp800bd
	install -Dm644 ppd/ctp800bd.ppd $(DESTDIR)$(PPDDIR)/ctp800bd.ppd
	install -Dm755 scripts/ctp800bd $(DESTDIR)$(PREFIX)/bin/ctp800bd

uninstall:
	rm -f $(DESTDIR)$(CUPS_SERVERBIN)/filter/rastertoctp800bd $(DESTDIR)$(PPDDIR)/ctp800bd.ppd $(DESTDIR)$(PREFIX)/bin/ctp800bd

clean:
	rm -rf build
