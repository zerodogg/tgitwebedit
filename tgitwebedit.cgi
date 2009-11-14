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
use File::Basename qw(basename dirname);
use autouse 'Cwd' => qw(realpath);
use autouse 'HTML::Entities' => qw(encode_entities);

use constant { true => 1, false => 0 };

my $q;
my $reqHeader = false;
my $VERSION = '0.1';
my $instDir = dirname($0);
my $menuSlurp = false;
my %conf;

# Purpose: Load a configuration file
# Usage: LoadConfigFile(/FILE, \%ConfigHash, \%OptionRegexHash, OnlyValidOptions?);
#  OptionRegeXhash can be available for only a select few of the config options
#  or skipped completely (by replacing it by undef).
#  If OnlyValidOptions is true it will cause LoadConfigFile to skip options not in
#  the OptionRegexHash.
sub LoadConfigFile
{
	my ($File, $ConfigHash, $OptionRegex, $OnlyValidOptions) = @_;

	open(my $CONFIG, '<', "$File") or do {
		warn(sprintf('Unable to read the configuration settings from %s: %s', $File, $!));
		return(0);
	};
	while(<$CONFIG>) {
		next if m/^\s*(#.*)?$/;
		next if not m/=/;
		chomp;
		my $Option = $_;
		my $Value = $_;
		$Option =~ s/^\s*(\S+)\s*=.*/$1/;
		$Value =~ s/^\s*\S+\s*=\s*(.*)\s*/$1/;
		if($OnlyValidOptions) {
			unless(defined($OptionRegex->{$Option})) {
				warn("Unknown configuration option \"$Option\" (=$Value) in $File: Ignored.");
				next;
			}
		}
		unless(defined($Value)) {
			warn("Empty value for option $Option in $File");
		}
		if(defined($OptionRegex) and defined($OptionRegex->{$Option})) {
			my $MustMatch = $OptionRegex->{$Option};
			unless ($Value =~ /$MustMatch/) {
				warn("Invalid setting of $Option (=$Value) in the config file: Must match $OptionRegex->{Option}.");
				next;
			}
		}
		$ConfigHash->{$Option} = $Value;
	}
	close($CONFIG);
}

sub slurp
{
	my $file = shift;
	my $o = $/;
	undef $/;
	open(my $i,'<',$file) or return;
	my $r = <$i>;
	$/ = $o;
	close($i);
	return $r;
}

sub confVal
{
	my $val = shift;
	if(not keys %conf)
	{
		LoadConfigFile('./tgitwebedit.conf',\%conf);
		if(not $conf{restrictedPath} =~ /^\//)
		{
			$conf{restrictedPath} = realpath($conf{restrictedPath});
		}
		if(not $conf{restrictedPath})
		{
			error('restrictedPath config option is missing');
		}
	}
	return $conf{$val};
}

sub header
{
	my $title = shift;
	my $o;
	$o = $q->header();
	$o .= '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">'."\n";
	$o .= '<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en"><head>';
	$o .= '<title>TGitWebEdit';
	if ($title)
	{
		$o .= ' - '.$title;
	}
	$o .= '</title>';
	$o .= '<meta name="robots" content="noindex, nofollow" />';
	$o .= '<meta http-equiv="Content-Type" content="text/html charset=UTF-8" />';
	# YUI
	$o .= '<link rel="stylesheet" type="text/css" href="http://yui.yahooapis.com/2.8.0r4/build/assets/skins/sam/skin.css" />';
	$o .= '<script type="text/javascript" src="http://yui.yahooapis.com/2.8.0r4/build/yahoo-dom-event/yahoo-dom-event.js"></script>';
	$o .= '<script type="text/javascript" src="http://yui.yahooapis.com/2.8.0r4/build/element/element-min.js"></script>';
	$o .= '<script src="http://yui.yahooapis.com/2.8.0r4/build/container/container_core-min.js"></script>';
	$o .= '<script src="http://yui.yahooapis.com/2.8.0r4/build/editor/simpleeditor-min.js"></script>';
	# Scripts
	$o .= '<script type="text/javascript">function tglog(msg) {  if(typeof(msg) == "object") { msg = "Exception: "+msg.message }; if(console && console.log) { console.log(msg); } }</script>';
	$o .= '<script type="text/javascript">var $ = function (i) { return document.getElementById(i); };</script>';
	$o .= '<script type="text/javascript">var runToggleRTE = false; function onloadRunner () { if (runToggleRTE) { toggleRTE(); } };</script>';
	$o .= '</head><body class="yui-skin-sam" onload="onloadRunner();">';
	$o .= '<div id="header"><h3>TGitWebEdit</h3>';
	$o .= '<span id="menu">';
	if (not $menuSlurp and -e $instDir.'/custom_menu.html')
	{
		$menuSlurp = true;
		$o .= slurp($instDir.'/custom_menu.html') or error('Failed to slurp the menu: '.$!);
	}
	else
	{
		if (-e $instDir.'/custom_index.html')
		{
			$o .= '<a href="'.$q->url().'">Main page</a> - ';
		}
		$o .= '<a href="'.$q->url().'?type=file_list">File list</a>';
	}
	$o .= '<hr /><br /></div><div id="primaryContent">';
	$reqHeader = true;
	return $o;
}

sub footer
{
	my $o = '</div><div id="footer"><br /><br /><small>Generated by TGitWebEdit version '.$VERSION.'</small></div>';
	$o .= '</body></html>';
	return $o;
}

sub editFile
{
	my $file = $q->param('filePath');
	if(not defined $file or not length $file)
	{
		error('No filePath supplied');
	}
	$file = realpath(confVal('restrictedPath').'/'.$file);
	if(not defined $file or not length $file)
	{
		error('Illegal path');
	}
	my $c = '';
	my $canSave = true;
	if (-e $file)
	{
		if(-d $file)
		{
			error($file.': is a directory');
		}
		elsif(-x $file)
		{
			error($file.': is executable. Refusing to edit an executeable file.');
		}
		open(my $i,'<',$file);
		undef $/;
		$c = <$i>;
		close($i);
		if(not -w $file)
		{
			$canSave = false;
		}
	}
	print header('Editing '.basename($file));
	if(not $canSave)
	{
		print '<b>WARNING: </b>This file is not writeable, you will not be able to save any changes!<br /><br />';
	}
	print '<form name="editor" method="post" action="'.$q->url().'?type=file_save'.'">';
	print '<input type="hidden" name="type" value="file_save" />';
	print '<input type="hidden" name="filePath" value="'.relativeRestrictedPath($file).'" />';
	print textEditor($c,$file);
	print '<br />';
	if ($canSave)
	{
		print '<input type="submit" value="Save file" />&nbsp;';
	}
	# FIXME: Add some magic so that if the back fails, we still forward
	# to url()
	print '<a href="'.$q->url().'"><input type="button" value="Cancel and discard changes" onclick="window.history.back(); return false;"></a>';
	print '</form>';
	print footer();
}

sub saveFile
{
	my $content = $q->param('mainEditor');
	if(not defined $content)
	{
		error('No content submitted');
	}
	my $errc = '<br /><br />The data you submitted is included below so that you may save it some other way until you are able to fix this issue.<br /><textarea rows="5" cols="50">'.$content.'</textarea>';

	my $file = $q->param('filePath');
	if(not defined $file or not length $file)
	{
		error('saveFile(): no filePath!'.$errc);
	}
	$file = realpath(confVal('restrictedPath').'/'.$file);
	if(not defined $file or not length $file)
	{
		error('Illegal path'.$errc);
	}
	if (-e $file)
	{
		if(-d $file)
		{
			error($file.': is a directory'.$errc);
		}
		elsif(-x $file)
		{
			error($file.': is executable. Refusing to edit an executeable file.'.$errc);
		}
		elsif(not -w $file)
		{
			error($file.': is not writeable by tgitwebedit (running as UID '.$<.'). Data could not be saved.'.$errc);
		}
	}

	open(my $out,'>',$file) or error('Failed to open '.$file.' for writing: '.$!);
	print {$out} $content;
	close($out);

	if (confVal('enableGit'))
	{
		system('git','add',$file);
		system('git','commit','-m', 'Changes made by '.$q->remote_host());
	}

	print header();
	print 'The file was saved successfully';
	print footer();
}

sub textEditor
{
	my $content = shift;
	my $file = shift;
	my $o = ''; 
	$o .= '<script type="text/javascript">
var rteON = false;
var RTE = null;
function toggleRTE()
{
	if (rteON)
	{
		if(RTE)
		{
			RTE.saveHTML();
			RTE.destroy();
			RTE = null;
		}
		rteON = false;
		$("rtestatus").innerHTML = "on";
	}
	else
	{
		rteON = true;
		try
		{
			RTE = new YAHOO.widget.SimpleEditor("mainEditor", { handleSubmit: true });
		}
		catch(error)
		{
			tglog(error);
		}
		RTE.render();
		$("rtestatus").innerHTML = "off";
	}
}</script>';
	$o .= '<b>'.basename($file).'</b>:<br />';
	$o .= '<a href="#" onclick="try { toggleRTE(); } catch(e) {tglog(e);}; return false">Toggle graphical (HTML) editor <span id="rtestatus">on</span></a></a><br />';
	$o .= '<textarea name="mainEditor" id="mainEditor" cols="100" rows=30">'.$content.'</textarea>';
	if ($content  =~ /<\s*br\s*[^>]>/i)
	{
		$o .= '<script type="text/javascript">runToggleRTE = true;</script>';
	}
	return $o;
}

sub URL_fileSelector
{
	my $file = shift;
	$file = relativeRestrictedPath($file);
	my $p = $q->url().'?type=file_list&dirPath='.$file;
	return encode_entities($p);
}

sub URL_editFile
{
	my $file = shift;
	$file = relativeRestrictedPath($file);
	my $p = $q->url().'?type=file_edit&filePath='.$file;
	return encode_entities($p);
}

sub fileListing
{
	my $dir = shift;
	my $l = '<b>'.$dir.'</b>:<br />';
	$l .= '<table style="border:0px;">';
	my @dirs = sort(glob($dir.'/*'));
	if(not realpath($dir) eq realpath(confVal('restrictedPath')))
	{
		unshift(@dirs,{ url => URL_fileSelector($dir.'/../'), label => '[DIR]', name => '.. (one level up)' });
	}
	else
	{
		unshift(@dirs,{ url => '',label => '&nbsp;', name => '' });
	}
	foreach my $p (@dirs)
	{
		my ($label,$url,$name);
		if(ref($p))
		{
			$label = $p->{label};
			$url   = $p->{url};
			$name  = $p->{name};
		}
		else
		{
			my $b = basename($p);
			if (-d $p)
			{
				$label = '[DIR]';
				$url = URL_fileSelector($p);
			}
			else
			{
				$label = '[FILE]';
				if (not -x $p)
				{
					$url = URL_editFile($p);
				}
			}
			$name = $b;
		}
		$l .= '<tr><td>';
		$l .= $label;
		$l .= '</td><td>';
		if(defined $url and length $url)
		{
			$name = '<a href="'.$url.'">'.$name.'</a>';
		}
		$l .= $name;
		$l .= '</a></td></tr>';
	}
	$l .= '</table>';
	return $l;
}

sub fileSelector
{
	my $path = $q->param('dirPath');
	$path = defined $path ? safePath($path) : '.';

	$path = realpath(confVal('restrictedPath').'/'.$path);
	if(not defined $path or not length $path)
	{
		error('Illegal path');
	}
	elsif(not -e $path)
	{
		error($path.': does not exist');
	}
	elsif(not -d $path)
	{
		error($path.': is not a directory');
	}
	print header()."\n";
	print fileListing($path)."\n";
	print footer();
}

sub relativeRestrictedPath
{
	my $path = shift;
	$path = realpath($path);
	my $rpath = confVal('restrictedPath');
	$path =~ s/$rpath//;
	return $path;
}

sub safePath
{
	my $path = shift;
	$path =~ s/\.//g;
	return $path;
}

sub error
{
	my $e = shift;
	if(not $reqHeader)
	{
		print header('Error');
	}
	print '<b>Error: </b>';
	print $e;
	print footer();
	exit(1);
}

sub defaultPage
{
	if (-e $instDir.'/custom_index.html')
	{
		print header();
		my $cust = slurp($instDir.'/custom_index.html') or error('Failed to slupr the custom index: '.$!);
		print $cust;
		print footer();
	}
	else
	{
		fileSelector();
	}
}

sub main
{
	$q = CGI->new;
	my $type = $q->param('type');
	$type = defined $type ? $type : 'default';

	if   ($type eq 'default')
	{
		defaultPage();
	}
	elsif($type eq 'file_list')
	{
		fileSelector();
	}
	elsif($type eq 'file_edit')
	{
		editFile();
	}
	elsif($type eq 'file_save')
	{
		saveFile();
	}
	elsif(defined $type and length($type))
	{
		error('The type "'.$type.'" is unknown. Bailing out.');
	}
	else
	{
		error('No type= submitted');
	}
	if(not $reqHeader)
	{
		error('Internal error, no request headers sent at end of app.');
	}
}

try
{
	main();
}
catch
{
	my $e = $_;
	try
	{
		error('main() error: '.$e);
	}
	catch
	{
		die('Error when running main(): '.$e."\n\n".'Error during error() as well: '.$_);
	};

};

__END__

=head1 NAME

=head1 DESCRIPTION

=head1 CONFIGURATION

=head1 CUSTOMIZATION

tgitwebedit can have additional customizations applied, in addition to
what is already offered by the configuration options. You can create a
custom menu, or a custom entry page.

=head2 Custom menu

By default tgitwebedit will create its own menu. However, if you want to
replace it with a custom menu, just create I<custom_menu.html>

=head2 Custom entry page

The entry page is the page that is first showed when you enter tgitwebedit.
By default the root file list will be showed, however if you edit/create
I<custom_index.html> you can add any custom welcome page you want.

=head1 LICENSE AND COPYRIGHT
