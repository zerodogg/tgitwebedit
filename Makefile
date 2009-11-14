prepare:
	perl -Ilib -MTry::Tiny -e '' || make fetchtiny
# Fetches Try::Tiny for those that need it
fetchtiny:
	mkdir -p lib/Try/
	cd lib/Try; wget http://cpansearch.perl.org/src/NUFFIN/Try-Tiny-0.02/lib/Try/Tiny.pm
