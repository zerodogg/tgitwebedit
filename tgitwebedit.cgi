#!/usr/bin/perl
# A tiny web-based editor
# Copyright (C) Eskild Hustvedt 2009
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

use strict;
use warnings;
use CGI;
use FindBin;
use lib "$FindBin::RealBin/lib/";
use Try::Tiny;

use constant { true => 1, false => 0 };

my $q;
my $reqHeader = false;

sub header
{
	my $o;
	$o = $q->header()."\n";
	$o .= '<html><head></head><body>';
	$reqHeader = true;
	return $o;
}

sub footer
{
	my $o = '</body></html>';
	return $o;
}

sub editFile
{
}

sub saveFile
{
}

sub RTE
{
}

sub fileSelector
{
}

sub safePath
{
}

sub error
{
	my $e = shift;
	print header('Error');
	print $e;
	print footer();
	exit(1);
}

sub main
{
	$q = CGI->new;
	my $type = $q->param('type');
	$type = defined $type ? $type : 'file_list';

	if ($type eq 'file_list')
	{
		fileSelector();
	}
	else
	{
		error('Unknown type= submitted');
	}
	if(not $reqHeader)
	{
		error('Internal error, no request headers sent at end of app.');
	}
}

main();
