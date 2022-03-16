import hashlib
import os
import time
import warnings
import xmlrpc.client

import bencodepy

__author__ = 'Braden Baird <bradenbdev@gmail.com>'
__version__ = '0.1.2'


def nested_get(dic, keys):
    for key in keys:
        dic = dic[key]
    return dic


def nested_set(dic, keys, value):
    for key in keys[:-1]:
        dic = dic.setdefault(key, {})
    dic[keys[-1]] = value


def calc_chunks(length, bsize):
    div = int(length / bsize)
    return div + 1 if length % bsize else div


def calc_info_hash(info):
    """
    Calculates a torrent's info hash.
    :param info: The 'info' section of a torrent. Use bencode on the torrent to get this.
    :return str: The info hash of the torrent.
    """
    return hashlib.sha1(bencodepy.bencode(info)).hexdigest()


class FastTorrent:
    CHUNK_HASH_SIZE = 20

    def __init__(self, tor_file, current_dl_loc, new_dl_loc=None):
        """
        Initializes the object.
        :param str tor_file: Path to source torrent file that you want fast-resumed.
        :param str current_dl_loc: Path where the torrent was downloaded to.
        """
        self.tor_file = tor_file
        self.current_dl_loc = current_dl_loc
        self.new_dl_loc = new_dl_loc

        self.num_chunks = 0
        self.chunk_size = 0
        self.chunk_size = 0
        self.total_tor_size = 0
        self.has_saved_file = False
        self.fr_file_loc = None  # Fast resume file location; the path of new torrent file when save_to_file is called
        self.has_resumed = False
        self.tor_data = None

        self._load_file()

        self.info_hash = calc_info_hash(self.get_tor_data_val('info'))

    def _load_file(self):
        """Loads torrent file data into a dict."""
        if not os.path.exists(self.tor_file):
            raise RuntimeError('Torrent file was not found. Please pass the path to a valid torrent file.')

        with open(self.tor_file, 'rb') as f:
            self.tor_data = bencodepy.bdecode(f.read())
            if not self.get_tor_data_val('info'):
                raise RuntimeError('Invalid torrent data.')

    def get_tor_data_val(self, *keys):
        """
        Returns value from torrent data located at *keys. You can pass as many keys as you want.
        Here's an example of what this does:

            # Normally, without using get_tor_data_val, one might do:
            FastTorrent.tor_data['key1']['key2']
            # With get_tor_data_val, simply use:
            get_tor_data_val('key1', 'key2')

        :param str keys: The keys that lead to the value you want to access. Keys are encoded automatically,
        so pass these as strings.
        :return: The value retrieved from self.tor_data using the keys provided.
        """
        encoded_keys = [k.encode() for k in keys]
        return nested_get(self.tor_data, encoded_keys)

    def set_tor_data_val(self, *keys, value):
        """
        Identical to get_tor_data_val, but with an additional parameter to set a torrent data value.
        :param value: Value to set tor_data value to. Note that value must be a keyword arg.
        :param str keys: The keys that lead to the value you want to access. Keys are encoded automatically,
        so pass these as strings.
        :return: The value retrieved from self.tor_data using the keys provided.
        """
        encoded_keys = [k.encode() for k in keys]
        nested_set(self.tor_data, encoded_keys, value)

    def tor_data_val_exists(self, *keys):
        """Returns True if specified keys are in self.tor_data, False if otherwise."""
        try:
            _ = self.get_tor_data_val(*keys)
            return True
        except KeyError:
            return False

    def calc_file_chunks(self, offset, size):
        return calc_chunks(offset + size, self.chunk_size) - calc_chunks(offset + 1, self.chunk_size) + 1

    @property
    def tor_is_multi_file(self):
        """Is True if torrent has multiple files, False if otherwise."""
        return self.tor_data_val_exists('info', 'files')

    @property
    def dl_files_path(self):
        """The path where this torrent's files (should) have been downloaded."""
        path = os.path.expandvars(self.current_dl_loc)
        path = os.path.expanduser(path)
        return os.path.join(path, self.get_tor_data_val('info', 'name').decode())

    @property
    def dl_base_path(self):
        """
        The BASE path for this torrent's files. If it's a multi-file torrent,
        this will be <download directory/torrent name>. If it's a single-file torrent,
        it will be <download directory/file name>
        """
        return self.dl_files_path if self.tor_is_multi_file else os.path.dirname(self.dl_files_path)

    def check_download_locations(self):
        """
        Checks download location for files and makes sure that they're complete. Raises RuntimeError if files are
        incomplete or not present. If download location exists, updates the torrent data with a
        ['rtorrent']['directory'] entry.
        :return: None
        """
        if not os.path.exists(self.dl_files_path):
            raise RuntimeError(f'Torrent download was not found at download location {self.dl_files_path}.')

        if self.tor_is_multi_file:
            if len(os.listdir(self.dl_files_path)) == 0:
                raise RuntimeError("Base path for torrent is empty. Can't resume a torrent that hasn't started yet!")

    def get_downloaded_files(self):
        """
        Returns list of files that should be in the download location. Also checks the download locations to
        ensure that they exist. Will raise a RuntimeError if something is wrong with the download location or the
        files.
        :return: None
        """
        self.check_download_locations()
        if not self.tor_data_val_exists('info', 'piece length'):
            raise RuntimeError('Invalid torrent: No piece length key found.')

        self.chunk_size = self.get_tor_data_val('info', 'piece length')
        files = []
        if self.tor_is_multi_file:
            for file in self.get_tor_data_val('info', 'files'):
                files.append(file[b'path'][0].decode())
                self.total_tor_size += file[b'length']
        else:
            files = [self.get_tor_data_val('info', 'name').decode()]
            self.total_tor_size = self.get_tor_data_val('info', 'length')

        self.num_chunks = calc_chunks(self.total_tor_size, self.chunk_size)
        if self.num_chunks * self.CHUNK_HASH_SIZE != len(self.get_tor_data_val('info', 'pieces')):
            raise RuntimeError('Inconsistent chunks hash information!')
        return files

    def do_resume(self):
        """
        Creates and populates torrent's resume data. Will check all download locations and files to ensure they're
        done before doing so.
        :return: None
        """
        files = self.get_downloaded_files()
        data_dir = self.dl_base_path

        on_disk_size = 0  # on-disk data size counter
        block_offset = 0  # block offset

        self.set_tor_data_val('libtorrent_resume', 'files', value=[])
        for idx, file in enumerate(files):
            file_path = os.path.join(data_dir, file)
            if not os.path.isfile(file_path):
                raise RuntimeError("Something is wrong with the torrent's files. They either don't exist, or are not "
                                   "normal files.")

            file_size = os.path.getsize(file_path)
            tor_len = self.get_tor_data_val('info', 'files')[idx][b'length'] if self.tor_is_multi_file else \
                self.get_tor_data_val('info', 'length')

            if tor_len != file_size:
                raise RuntimeError("One of the torrent files does not match its expected size. Aborting.")

            mtime = int(os.path.getmtime(file_path))
            completed = self.calc_file_chunks(block_offset, file_size) if file_size else 0

            # Add libtorrent resume data to torrent
            self.get_tor_data_val('libtorrent_resume', 'files').insert(idx, {
                b'priority': 0,
                b'mtime': mtime,
                b'completed': completed
            })

            on_disk_size += file_size
            block_offset += tor_len

        # Resume failed if on_disk_size = 0 (no files to resume) or on_disk_size doesn't match sum of all files in
        # torrent
        if on_disk_size != self.total_tor_size or on_disk_size == 0:
            raise RuntimeError("File size verification failed. Files are missing.")

        # Set vars in torrent
        rtorrent_vals = {
            b'state': 1,  # started
            b'state_changed': int(time.time()),
            b'state_counter': 1,
            b'chunks_wanted': 0,
            b'chunks_done': self.num_chunks,
            b'complete': 1,
            b'hashing': 0,
            b'directory': self.new_dl_loc.encode() if self.new_dl_loc else self.dl_base_path.encode(),
            b'timestamp.finished': 0,
            b'timestamp.started': int(time.time()),
        }
        libtorrent_resume_vals = {
            b'bitfield': self.num_chunks,
            b'uncertain_pieces.timestamp': int(time.time())
        }

        self.set_tor_data_val('rtorrent', value=rtorrent_vals)
        self.get_tor_data_val('libtorrent_resume').update(libtorrent_resume_vals)

        self.has_resumed = True

    def save_to_file(self, dest=None):
        """
        Saves torrent data to file.
        :param str dest: Path where file should be saved. If not provided, will output to current directory as
        *torrent name*_fast.torrent
        :return: None
        """
        encoded_tor_data = bencodepy.bencode(self.tor_data)
        if dest is None:
            no_ext = os.path.splitext(self.tor_file)[0]
            filename = f'{os.path.basename(no_ext)}_fast.torrent'
            dest = os.path.join(os.path.dirname(self.tor_file), filename)

        with open(dest, 'wb') as f:
            f.write(encoded_tor_data)

        self.has_saved_file = True
        self.fr_file_loc = dest

    def add_to_rtorrent(self, server_url, custom_ratio=None):
        """
        Add fast resume torrent to rtorrent via xml rpc.
        :param str server_url: URL of the xml rpc server.
        :param float custom_ratio: Ratio to set in torrent's custom_ratio field.
        :return: None
        """
        if not self.has_resumed:
            warnings.warn('add_to_rtorrent was called before calling do_resume. Doing this will add the torrent to '
                          'rtorrent without fast resuming it.')

        encoded_tor_data = bencodepy.bencode(self.tor_data)

        server = xmlrpc.client.Server(server_url)
        server.load.raw_start('', xmlrpc.client.Binary(encoded_tor_data),
                              f'd.directory.set="{self.new_dl_loc or self.dl_base_path}"', 'd.priority.set=2')
        if custom_ratio is not None:
            server.d.custom.set(self.info_hash, 'custom_ratio', str(float(custom_ratio)))


def rfr(tor_file, current_dl_loc, new_dl_loc=None, dest=None):
    """
    Wrapper for FastTorrent class.
    :param tor_file: Path to torrent file that you want to fast resume.
    :param current_dl_loc: Path where the torrent was downloaded to.
    :param new_dl_loc: New download location to set in the fast resume torrent.
    :param dest: Path to write fast resume torrent to.
    :return:
    """
    tor = FastTorrent(tor_file, current_dl_loc, new_dl_loc)
    tor.do_resume()
    tor.save_to_file(dest)
