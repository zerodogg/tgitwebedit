VERSION=0.1
DISTFILES=COPYING Makefile tgitwebedit.cgi tgitwebedit.conf tgitwebedit.1
prepare:
	perl -Ilib -MTry::Tiny -e '' || make fetchtiny
clean:
	rm -f *~
	rm -rf tgitwebedit-$(VERSION)
	rm -f tgitwebedit-*.tar.bz2
test:
	perl -Ilib -c tgitwebedit.cgi
# Create a manpage from the POD
man:
	pod2man --name "tgitwebedit" --center "" --release "tgitwebedit" ./tgitwebedit.cgi ./tgitwebedit.1
# Create our tarball
distrib: clean test man
	mkdir -p tgitwebedit-$(VERSION)
	cp $(DISTFILES) ./tgitwebedit-$(VERSION)
	tar -jcvf tgitwebedit-$(VERSION).tar.bz2 ./tgitwebedit-$(VERSION)
	rm -rf tgitwebedit-$(VERSION)
	rm -f tgitwebedit.1
