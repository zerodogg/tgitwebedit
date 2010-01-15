#!/usr/bin/perl
# tgitwebedit - A tiny web-based editor
# Copyright (C) Eskild Hustvedt 2009, 2010
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

use strict;
use warnings;
use CGI;
use IPC::Open3 qw(open3);
use File::Basename qw(basename dirname);
use autouse 'Cwd' => qw(realpath);

use constant { true => 1, false => 0 };

my $q;
my @warnings;
my $reqHeader = false;
my $VERSION = '0.1';
my $instDir = dirname($0);
my $menuSlurp = false;
my $defaultCharset = 'UTF-8';
my %conf;
my %sessionCache = (
	'hasModule' => {},
);

# Purpose: Load a configuration file
# Usage: LoadConfigFile(/FILE, \%ConfigHash, \%OptionRegexHash, OnlyValidOptions?);
#  OptionRegeXhash can be available for only a select few of the config options
#  or skipped completely (by replacing it by undef).
#  If OnlyValidOptions is true it will cause LoadConfigFile to skip options
#  not in the OptionRegexHash.
sub LoadConfigFile
{
	my ($File, $ConfigHash, $OptionRegex, $OnlyValidOptions) = @_;
	assert(@_);

	open(my $CONFIG, '<', "$File") or do
	{
		twarn(sprintf('Unable to read the configuration settings from %s: %s', $File, $!));
		return(0);
	};
	while(<$CONFIG>)
	{
		next if m/^\s*(#.*)?$/;
		next if not m/=/;
		chomp;
		my $Option = $_;
		my $Value = $_;
		$Option =~ s/^\s*(\S+)\s*=.*/$1/;
		$Value =~ s/^\s*\S+\s*=\s*(.*)\s*/$1/;
		if($OnlyValidOptions) {
			unless(defined($OptionRegex->{$Option}))
			{
				twarn("Unknown configuration option \"$Option\" (=$Value) in $File: Ignored.");
				next;
			}
		}
		unless(defined($Value))
		{
			twarn("Empty value for option $Option in $File");
		}
		if(defined($OptionRegex) and defined($OptionRegex->{$Option}))
		{
			my $MustMatch = $OptionRegex->{$Option};
			unless ($Value =~ /$MustMatch/)
			{
				twarn("Invalid setting of $Option (=$Value) in the config file: Must match $OptionRegex->{Option}.");
				next;
			}
		}
		$ConfigHash->{$Option} = $Value;
	}
	close($CONFIG);
}

# Purpose: Get the charset of a file
# Usage: getCharsetOf(path/to/file);
sub getCharsetOf
{
	my $path = shift;
	if (!InPath('file'))
	{
		twarn('The "file" utility is missing. Charset detection is not possible. Defaulting to '.$defaultCharset);
		return $defaultCharset;
	}
	if(not -e $path)
	{
		twarn('Tried to get charset of non-existing file: '.$path);
		return $defaultCharset;
	}
	my $pid = open3(my $in, my $out, my $err,'file','--mime',$path);
	if(not $pid)
	{
		twarn('Failed to open communication to "file": '.$!);
		return $defaultCharset;
	}
	my $info = <$out>;
	waitpid($pid,0);
	if (not $info =~ /charset/)
	{
		# If it has no charset, but has a something/something - we assume that
		# it is a binary file.
		if ($info =~ m{: \S+/\S+\s*$})
		{
			return 'binary';
		}
		elsif($info =~ /:\s+very\s+short\s+file\s+\(no\s+magic\)\s*$/i)
		{
			return $defaultCharset;
		}
		twarn('Failed to parse output from "file": \''.$info.'\' - defaulting to '.$defaultCharset.' (for '.$path.')');
		return $defaultCharset;
	}
	$info =~ s/\r?\n//g;
	$info =~ s/.*charset=(\S+).*/$1/;
	if(not length $info)
	{
		twarn('"file" did not return a usable charset, defaulting to '.$defaultCharset);
		return $defaultCharset;
	}
	$info =~ tr/a-z/A-Z/;

	# Perform replacements
	my %replace = (
		# US-ASCII can just as fine be UTF-8
		'US-ASCII' => 'UTF-8',
	);
	if ($replace{$info})
	{
		$info = $replace{$info};
	}
	return $info;
}

# Purpose: Assert a statment
# Usage: assert(some boolean, fatal?);
# If the boolean is false, twarn() will be called. If the boolean is true,
# nothing happens.
# If fatal is true, then error() will be called in place of twarn();
sub assert
{
	my($bool,$fatal) = @_;
	if ($bool)
	{
		return;
	}
	my @info = caller;
	my $message = 'failed at line '.$info[2].' in '.$info[1].' ('.$info[0].')';
	if ($fatal)
	{
		error('Essential assertion '.$message);
	}
	else
	{
		twarn('Assertion '.$message);
	}
}

# Purpose: Add a warning to be output on the page being generated
# Usage: twarn(message);
sub twarn
{
	my $msg = shift;
	push(@warnings,htmlEncode($msg));
}

# Purpose: Slurp a file
# Usage: slurp(path);
# 	Returns undef on failure, the contents of path on success.
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

# Purpose: Check for a file in path
# Usage: InPath(FILE)
sub InPath
{
	foreach (split /:/, $ENV{PATH}) { if (-x "$_/@_" and ! -d "$_/@_" ) {	return "$_/@_"; } } return false;
}

# Purpose: Check if a file should be ignored
# Usage: bool = ignoreFile(FILE);
sub ignoreFile
{
	my $name = shift;
	my @regexes;
	if (defined $sessionCache{ignores})
	{
		@regexes = @{$sessionCache{ignores}};
	}
	else
	{
		my $confVal = confVal('ignoreFiles');
		foreach my $entry (split(/,/,$confVal))
		{
			# Escape \
			$entry =~ s/\\/\\\\/g;
			# Escape metacharacters
			$entry =~ s/(\.|\$|\^|\+|\?|\(|\)|\{|\}|\|)/\\$1/g;
			# Turn * into .*
			$entry =~ s/\*/.*/g;
			push(@regexes, qr/^$entry$/);
		}
		$sessionCache{ignores} = \@regexes;
	}

	my @names = ($name);
	if(realpath($name) ne $name)
	{
		push(@names,realpath($name));
	}
	
	foreach my $fname (@names)
	{
		if (
			$fname eq realpath($instDir.'/tgitwebedit.conf')
				or
			$fname eq realpath($0)
			)
		{
			return true;
		}
		foreach my $ent (@regexes)
		{
			if ($fname =~ $ent)
			{
				return true;
			}
		}
	}
	return false;
}

# Purpose: Get the source code
# Usage: provideSource();
sub provideSource
{
	my $f = slurp($0) or error('Fatal: failed to read self');
	print $q->header(-type => 'text/plain');
	print $f;
	exit(0);
}

# Purpose: Encode HTML
# Usage: htmlEncode(string);
sub htmlEncode
{
	my $string = shift;
	if(not defined $sessionCache{'hasModule'}{'HTML::Entities'})
	{
		if(eval('use HTML::Entities qw(encode_entities);1;'))
		{
			$sessionCache{'hasModule'}{'HTML::Entities'} = true;
		}
		else
		{
			$sessionCache{'hasModule'}{'HTML::Entities'} = false;
		}
	}

	if ($sessionCache{'hasModule'}{'HTML::Entities'})
	{
		return encode_entities($string);
	}

	$string =~ s/&/&amp;/g;
	$string =~ s/"/&quot;/g;
	$string =~ s/</&lt;/g;
	$string =~ s/>/&gt;/g;
	return $string;
}

# Purpose: Retrieve a configuration value, automagically loading the
# 	conf file if needed
# Usage: val = confVal('name');
sub confVal
{
	my $val = shift;
	if(not keys %conf)
	{
		# Conf defaults
		%conf = (
			'restrictedPath' => '.',
			'enableGit' => 'true',
			'useApacheStock' => 'true',
			'ignoreFiles' => '*.pm,*.cgi',
		);
		if (-e './tgitwebedit.conf')
		{
			LoadConfigFile('./tgitwebedit.conf',\%conf);
		}
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

# Purpose: Return the header string (HTML as well as HTTP)
# Usage: headerString = header(TITLE?, CHARSET?);
sub header
{
	my $title = shift;
	my $charset = shift;
	if (not defined $charset)
	{
		$charset = $defaultCharset;
	}
	my $o;
	$o = $q->header(-charset => $charset);
	$o .= '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">'."\n";
	$o .= '<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en"><head>';
	$o .= '<title>TGitWebEdit';
	if ($title)
	{
		$o .= ' - '.$title;
	}
	$o .= '</title>';
	$o .= '<meta name="robots" content="noindex, nofollow" />';
	$o .= '<meta http-equiv="Content-Type" content="text/html charset='.$charset.'" />';
	# YUI
	$o .= '<link rel="stylesheet" type="text/css" href="http://yui.yahooapis.com/2.8.0r4/build/assets/skins/sam/skin.css" />';
	$o .= '<script type="text/javascript" src="http://yui.yahooapis.com/2.8.0r4/build/yahoo-dom-event/yahoo-dom-event.js"></script>';
	$o .= '<script type="text/javascript" src="http://yui.yahooapis.com/2.8.0r4/build/element/element-min.js"></script>';
	$o .= '<script type="text/javascript" src="http://yui.yahooapis.com/2.8.0r4/build/container/container_core-min.js"></script>';
	$o .= '<script type="text/javascript" src="http://yui.yahooapis.com/2.8.0r4/build/editor/simpleeditor-min.js"></script>';
	# Scripts
	$o .= '<script type="text/javascript">/* <![CDATA[ */ function tglog(msg) {  if(typeof(msg) == "object") { msg = "Exception: "+msg.message }; if(console && console.log) { console.log(msg); } } /* ]]> */</script>';
	$o .= '<script type="text/javascript">var $ = function (i) { return document.getElementById(i); };</script>';
	$o .= '<script type="text/javascript">var runToggleRTE = false; function onloadRunner () { if (runToggleRTE) { toggleRTE(); } };</script>';
	$o .= '</head><body class="yui-skin-sam" onload="onloadRunner();">';
	$o .= '<div id="header"><h3>TGitWebEdit</h3>'."\n";
	$o .= '<!-- You can retrieve the source for this instance of tgitwebedit by visiting: '.$q->url().'?type=source -->'."\n";
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
	$o .= '</span></div><hr /><div id="primaryContent"><br />';
	$reqHeader = true;
	return $o;
}

# Purpose: Return the footer HTML string
# Usage: footerString = footer();
sub footer
{
	my $o = '</div><div id="footer"><br /><br /><small>Generated by TGitWebEdit version '.$VERSION.'<br /><small>Licensed under the <a href="http://www.gnu.org/licenses/agpl.html">GNU AGPL version 3 or (at your option) any later version</a>. <a href="'.$q->url().'?type=source/tgitwebedit.cgi">Get the source.</a>.</small></small></div>';
	if (@warnings)
	{
		$o .= '<div id="warnings"><b>Warnings:</b><br />';
		$o .= join('<br />',@warnings);
		$o .= '</div>';
	}
	$o .= '</body></html>';
	return $o;
}

# Purpose: Output an edit page for the path supplied in the filePath param
# Usage: editFile(),
sub editFile
{
	my $file = $q->param('filePath');
	if (defined $q->param('dirPath'))
	{
		my $newFile = $q->param('filename');
		my $dirPath = $q->param('dirPath');

		if(not length $dirPath)
		{
			error('No dirPath supplied');
		}
		elsif(not length $newFile)
		{
			error('You need to enter a file name');
		}
		$file = $dirPath.'/'.$newFile;
	}

	if(not defined $file or not length $file)
	{
		error('No filePath supplied');
	}
	$file = fullSafePath($file);
	if ($file and $file eq realpath($instDir.'/tgitwebedit.conf'))
	{
		error('Editing the tgitwebedit.conf file is not permitted.');
	}
	elsif(not defined $file or not length $file or ignoreFile($file))
	{
		error('Illegal path');
	}
	my $c = '';
	my $canSave = true;
	my $charset = $defaultCharset;
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
		$charset = getCharsetOf($file);
		if ($charset eq 'binary')
		{
			error($file.': is a binary file. Refusing to edit.');
		}
		$c = slurp($file);
		error('Failed to read '.$file.': '.$!) if not defined $c;

		if(not -w $file)
		{
			$canSave = false;
		}
	}
	print header('Editing '.basename($file),$charset);
	if(not $canSave)
	{
		print '<b>WARNING: </b>This file is not writeable, you will not be able to save any changes!<br /><br />';
	}
	print '<form method="post" action="'.$q->url().'?type=file_save'.'">';
	print '<div>';
	print '<input type="hidden" name="type" value="file_save" />';
	print '<input type="hidden" name="file_charset" value="'.$charset.'" />';
	print '<input type="hidden" name="filePath" value="'.relativeRestrictedPath($file).'" />';
	print textEditor($c,$file);
	print '<br />';
	if ($canSave)
	{
		if (-e $file)
		{
			print '<input type="submit" value="Save file" />&nbsp;';
		}
		else
		{
			print '<input type="submit" value="Create and save file" />&nbsp;';
		}
	}
	print '<a href="'.$q->url().'"><input type="button" value="Cancel and discard changes" onclick="window.history.back(); if(window.history.length > 1) return false" /></a>';
	print '</div>';
	print '</form>';
	print footer();
}

# Purpose: Save POSTed data generated by an editFile() form
# Usage: saveFile();
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
		error('saveFile(): no filePath!'.$errc,true);
	}
	$file = realpath(confVal('restrictedPath').'/'.$file);
	if(not defined $file or not length $file or ignoreFile($file))
	{
		error('Illegal path'.$errc,true);
	}
	if (-e $file)
	{
		if(-d $file)
		{
			error($file.': is a directory'.$errc,true);
		}
		elsif(-x $file)
		{
			error($file.': is executable. Refusing to edit an executeable file.'.$errc,true);
		}
		elsif(not -w $file)
		{
			error($file.': is not writeable by tgitwebedit (running as UID '.$<.'). Data could not be saved.'.$errc,true);
		}
	}

	my $setMode = false;

	if(not -e $file)
	{
		$setMode = true;
	}

	open(my $out,'>',$file) or error('Failed to open '.$file.' for writing: '.$!.$errc,true);
	print {$out} $content;
	close($out);

	if ($setMode)
	{
		chmod(0644,$file);
	}

	print header();
	print 'The file was saved successfully';
	if (confVal('enableGit'))
	{
		print '<pre>';
		system('git','add',$file);
		system('git','commit','-m', 'Changes made by '.$q->remote_host());
		print '</pre>';
	}
	print footer();
}

# Purpose: Return the HTML needed for a text editor with the contents
# 	supplied.
# Usage: editorHTML = textEditor(content);
sub textEditor
{
	my $content = shift;
	my $file = shift;
	my $o = ''; 
	$o .= '<script type="text/javascript">
//<![CDATA[
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
} /* ]]> */</script>';
	$o .= '<b>'.htmlEncode(basename($file)).'</b>:<br />';
	$o .= '<a href="#" onclick="try { toggleRTE(); } catch(e) {tglog(e);}; return false">Toggle graphical (HTML) editor <span id="rtestatus">on</span></a><br />';
	$o .= '<textarea name="mainEditor" id="mainEditor" cols="100" rows="30">'.$content.'</textarea>';
	# The reason we check only for the limited selection of tags
	# below, rather than any XML/SGML-like tag is because some sites use
	# includes which are wrapped in <pre></pre>, and if we start editing
	# those includes in full html mode, things look quite awful.
	if ($content  =~ /<\s*(br|p)\s*[^>]+>/i and not 
			(
				$content =~ /<\?\s*php/ || $content =~ /<\s*script/
			)
		)
	{
		$o .= '<script type="text/javascript">runToggleRTE = true;</script>';
	}
	return $o;
}

# Purpose: Get the URL for a file selector page
# Usage: URL = URL_fileSelector(PATH);
sub URL_fileSelector
{
	my $file = shift;
	$file = relativeRestrictedPath($file);
	my $p = $q->url().'?type=file_list&dirPath='.$file;
	return htmlEncode($p);
}

# Purpose: Get the URL for a file editor page
# Usage: URL = URL_editFile(PATH);
sub URL_editFile
{
	my $file = shift;
	$file = relativeRestrictedPath($file);
	my $p = $q->url().'?type=file_edit&filePath='.$file;
	return htmlEncode($p);
}

# Purpose: Return HTML for listing the files in the directory supplied
# Usage: html = fileListing(path);
sub fileListing
{
	my $dir = shift;
	my $l = '<b>'.relativeRestrictedPath($dir).'</b>:<br />';
	if (-w $dir || 1)
	{
		$l .= '<span id="mkdir" style="display:none;"><form method="get" action="'.$q->url().'"><span>Directory name: <input type="text" name="dirname" /> <input type="submit" value="Create" /> <input type="hidden" name="type" value="mkdir" /><input type="hidden" name="dirPath" value="'.htmlEncode(relativeRestrictedPath($dir)).'" /></span></form></span>';
		$l .= '<span id="mkfile" style="display:none;"><form method="get" action="'.$q->url().'"><span>File name: <input type="text" name="filename" /> <input type="submit" value="Create" /> <input type="hidden" name="type" value="file_edit" /><input type="hidden" name="dirPath" value="'.htmlEncode(relativeRestrictedPath($dir)).'" /></span></form></span>';
		$l .= '<a id="mkdirP" href="#" onclick="$(\'mkdir\').style.display = \'block\'; $(\'mkdirP\').style.display = \'none\'; $(\'mkSep\').style.display = \'none\'; return false">New directory</a>';
		$l .= '<span id="mkSep"> || </span>';
		$l .= '<a id="mkfileP" href="#" onclick="$(\'mkfile\').style.display = \'block\'; $(\'mkfileP\').style.display = \'none\'; $(\'mkSep\').style.display = \'none\'; return false">New file</a>';
	}
	$l .= '<table style="border:0px;">';
	my @dirs = sort(glob($dir.'/*'));
	if(not realpath($dir) eq realpath(confVal('restrictedPath')))
	{
		unshift(@dirs,{ url => URL_fileSelector($dir.'/../'), label => '[UP]', name => '.. (one level up)' });
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
				my $ignore = ignoreFile($p);
				if (not -x $p and not getCharsetOf($p) eq 'binary' and not $ignore)
				{
					$url = URL_editFile($p);
				}
				elsif(-x $p)
				{
					$label = '[BINX]';
				}
				elsif(not $ignore)
				{
					$label = '[BIN]';
				}
			}
			$name = $b;
		}
		$l .= '<tr><td>';
		if (confVal('useApacheStock') && confVal('useApacheStock') eq 'true')
		{
			my %stockMap = (
				'[DIR]' => '<img src="/icons/folder.png" alt="[DIR]" />',
				'[UP]' => '<img src="/icons/back.png" alt="[UP]" />',
				'[FILE]' => '<img src="/icons/text.png" alt="[FILE]" />',
				'[BIN]' => '<img src="/icons/binary.png" alt="[BIN]" />',
				'[BINX]' => '<img src="/icons/unknown.png" alt="[BIN]" />',
			);
			if(defined $stockMap{$label})
			{
				$l .= $stockMap{$label};
			}
			else
			{
				$l .= $label;
			}
		}
		else
		{
			$l .= $label;
		}
		$l .= '</td><td>';
		if(defined $url and length $url)
		{
			$name = '<a href="'.$url.'">'.htmlEncode($name).'</a>';
		}
		$l .= $name;
		$l .= '</td></tr>';
	}
	$l .= '</table>';
	return $l;
}

# Purpose: Output a file selector for the directory supplied in the dirPath
# 	parameter, or the root of our restrictedPath.
# Usage: fileSelector();
sub fileSelector
{
	my $path = $q->param('dirPath');
	$path = fullSafePath($path);
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

# Purpose: Get the path to a file or dir that is relative to our restrictedPath
# Usage: path = relativeRestrictedPath(/full/path);
sub relativeRestrictedPath
{
	my $path = shift;
	$path = realpath($path);
	my $rpath = confVal('restrictedPath');
	$path =~ s/^$rpath//;
	if (not length $path or not $path =~ /[^\.]/)
	{
		return '/';
	}
	return $path;
}

# Purpose: Create a new directory
# Usage: createDirectory(dir);
sub createDirectory
{
	my $parentDir = $q->param('dirPath');
	error('dirPath missing') if not $parentDir or not length $parentDir;
	$parentDir = fullSafePath($parentDir);
	error('dirPath does not exist') if not -d $parentDir;

	my $dir = $q->param('dirname');
	error('You need to enter a directory name.') if not defined $dir or not length $dir;
	if ($dir =~ m{/})
	{
		error($dir.': can not contain /');
	}
	$dir = $parentDir.'/'.safePath($dir);
	if(-f $dir)
	{
		error($dir.': exists and is a file');
	}
	elsif(-d $dir)
	{
		error($dir.': exists and is a directory');
	}
	mkdir($dir) or error('Failed to create directory at '.$dir.': '.$!);
	print header()."\n";
	print 'Created directory: <i>'.htmlEncode($dir).'</i><br /><br />';
	print fileListing($dir)."\n";
	print footer();
}

# Purpose: Sanitize user file path input to avoid injections
# Usage: path = safePath('path');
sub safePath
{
	my $path = shift;
	$path =~ s/^\.+//g;
	$path =~ s{/\.+}{/}g;
	return $path;
}

# Purpose. Get a safe path relative to restrictedPath
# Usage: path = fullSafePath(path);
sub fullSafePath
{
	my $path = shift;
	$path = defined $path ? safePath($path) : '.';
	$path = realpath(confVal('restrictedPath').'/'.$path);
	return $path;
}

# Purpose: Sanitize user charset input to avoid injections
# Usage: charset = safeCharset('charset',alwaysReturn?);
sub safeCharset
{
	my $charset = shift;
	my $alwaysReturn = shift;
	if ($alwaysReturn)
	{
		$alwaysReturn = $defaultCharset;
	}
	else
	{
		$alwaysReturn = undef;
	}
	if (not $charset)
	{
		return $alwaysReturn;
	}
	$charset =~ s/.*([A-Za-z0-9-]+).*/$1/;
	if ($charset)
	{
		return $charset;
	}
	return $alwaysReturn;
}

# Purpose: Output an error page with the contents supplied and exit
# Usage: error('text'); 
sub error
{
	my $e = shift;
	my $noEncode = shift;
	if(not $reqHeader)
	{
		print header('Error');
	}
	print '<b>Error: </b>';
	if ($noEncode)
	{
		print $e;
	}
	else
	{
		print htmlEncode($e);
	}
	print footer();
	exit(1);
}

# Purpose: Output the default page, either a root dir listing, or custom_index.html
# Usage: defaultPage();
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

# Purpose: Main entry point
# Usage: main();
sub main
{
	$q = CGI->new;
	my $type = $q->param('type');
	$type = defined $type ? $type : 'default';

	if ($type eq 'source' || $type eq 'source/tgitwebedit.cgi')
	{
		provideSource();
	}

	if(not -e $instDir.'/.htaccess')
	{
		error($instDir.'/.htaccess: does not exist, refusing to continue.<br />tgitwebedit does not contain any authentication support, and you must therefore use HTTP auth. When .htaccess does not exist, tgitwebedit assumes no authentication is being used and refuses to work.');
	}

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
	elsif($type eq 'mkdir')
	{
		createDirectory();
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

# Run main() and perform some additional error handling in the process
my $r = eval
{
	main();
	1;
};
my $e = $@;
if (!$r)
{
	$r = eval
	{
		error('main() error: '.$e);
		1;
	};
	if (!$r)
	{
		die('Error when running main(): '.$e."\n\n".'Error during error() as well: '.$@);
	}
}

__END__

=head1 NAME

tgitwebedit - a simple web-based editor for static content that can use git
for revision control of changes.

=head1 DESCRIPTION

tgitwebedit is a simple web-based editor for static content that can use git
for revision control of changes. For lack of a better term it can be called
a single-file "CMS", althoguh it doesn't actually provide any means of serving
the content, or managing how something is served. It provides a simple web UI
for editing static files that can then be served through existing scripts,
or as completely static HTML pages.

=head1 INSTALLATION

Installation of tgitwebedit is completely straightforward. Follow
either the quick or full instructions below.

=head2 Quick instructions

	- Configure it by editing tgitwebedit.conf
	- Set up basic HTTP authentication for the current directory
		(tgitwebedit does no authentication on its own)
	- Upload to the web server, ensuring that tgitwebedit.cgi
		is executable, and any files it should edit is writable
		by the web server.
	- Optionally, create the git repository that should contain the
		data.

=head2 Full instructions

=over

=item B<Step 1> - Preparation

Decide if you want to use the configuration file (you probably do, though 
tgitwebedit will work fine without it, it'll just use some sane defaults).
If you don't, skip to step 3.

=item B<Step 2> - Configuration

Edit the tgitwebedit.conf file to suit your needs.

=item B<Step 3> - Securing

tgitwebedit does not contain any builtin authentication. Therefore
you will need to use basic http authentication. Now is the time
to configure this, ie. in your .htaccess and .htpasswd files.

=back

=head3 Instructions on setting up basic HTTP auth for apache:

Create a I<.htaccess> like so:

	AuthType Basic
	AuthName "tgitwebedit"
	AuthUserFile /path/on/webserver/to/.htpasswd
	Require user USER_FROM_HTPASSWD

Then create a htpasswd file using the apache htpasswd tool. Not all
distros put this into PATH, so you may need to use locate to find
out where it is.

	$ htpasswd .htpasswd USER

=over

=item B<Step 4> - Upload

Upload tgitwebdit.cgi (and tgitwebedit.conf if you use it), along with the
authentication files you created in step 3 to the directory you want tgitwebdit
to run from on your web server. Make sure tgitwebedit.cgi is executable by your
user, and that the files you want it to be able to edit is writable by
the user running the web-server.

If you want to use the git revision-control features as well, you need to
create the git repository that should contain the data (and ensure
that the git repository is writable by the web server). As long as the
directories containing the files tgitwebedit can edit is contained inside that
tree, tgitwebedit will start using it automatically.

That's it. tgitwebedit is now ready to be used.

=back

=head1 CONFIGURATION

The configuration for tgitwebedit is contained in the tgitwebedit.conf
file in the same directory as tgitwebedit.cgi. It should be fairly
straightforward to configure. The configuration file as it looks in a
default installation is included below.

=head2 Default configuration file

	# Configuration file for tgitwebedit

	# This is the path under which files can be edited.
	# The path can be relative to the directory containing tgitwebedit,
	# or it can be a fully qualified path. Relative paths are resolved during
	# runtime.
	restrictedPath=.

	# If this is set to any value OTHER than 0 then tgitwebedit will use
	# git for revision control of changes. Setting it to 0 disables this
	# feature.
	enableGit=true

	# If this is set to true then tgitwebedit will attempt to use apache
	# stock icons for directories and files.
	useApacheStock=true

	# This is a comma-separated list of filenames to ignore. * works
	# as a wildcard.
	ignoreFiles=*.pm,*.cgi

=head1 CUSTOMIZATION

tgitwebedit can have additional customizations applied, in addition to
what is already offered by the configuration options. You can create a
custom menu, or a custom entry page.

It is worth noting that you can not run any CGI script through these custom
incldues. Yes, it would be useful to be able to, but it would also open up
a bunch of other security considerations in the process. Therefore, if you
do need to run a CGI script inside these custom files, simply add an iframe
inside them that links to the CGI script that you want to run. This way you
can still run your CGI script without having to modify tgitwebedit.

=head2 Custom menu

By default tgitwebedit will create its own menu. However, if you want to
replace it with a custom menu, just create I<custom_menu.html>

=head2 Custom entry page

The entry page is the page that is first showed when you enter tgitwebedit.
By default the root file list will be showed, however if you edit/create
I<custom_index.html> you can add any custom welcome page you want.

=head1 LICENSE AND COPYRIGHT

Copyright (C) Eskild Hustvedt 2009

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
