## Rtorrent fast resume

Python module that adds fast resume data to torrent files to be used by rtorrent.

### Description

This adds fast resume data to torrent files, allowing rtorrent to skip hash checking when a torrent is added. Based
on [rtorrent_fast_resume](https://github.com/rakshasa/rtorrent/blob/master/doc/rtorrent_fast_resume.pl)
and [rfr.pl](https://raw.githubusercontent.com/liaralabs/kb-scripts/master/deluge-to-rtorrent/rfr.pl).

### Installation

`pip install rfr`

### Usage

Here's a quick example of how to use this:

```
import rfr

tor = rfr.FastTorrent('path_to_original.torrent', 'path_to_downloaded_files')

# Call tor.do_resume() when you're ready to generate the fast resume data
tor.do_resume()

# Before outputting the torrent, you can adjust some of the torrent's params
# using:
tor.set_tor_data_val('rtorrent', 'directory', value='whatever you want')

# After calling tor.do_resume(), you can either save the resulting torrent to a file
# or upload straight to rtorrent via xml rpc
tor.save_to_file(dest)
tor.add_to_rtorrent(rtorrent_xmlrpc_url)
```
