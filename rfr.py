import os

import bencode

CHUNK_HASH_SIZE = 20
num_chunks = 0
chunk_size = 0
tsize = 0


def load_file(tfile):
    with open(tfile, 'rb') as f:
        return bencode.bdecode(f.read())


def torrent_check(tdata, base):
    if not tdata.get(b'info'):
        raise RuntimeError('Invalid torrent data.')

    chkpath = base
    path = chk_basedir(chkpath, tdata)
    tdata[b'rtorrent'] = {}
    tdata[b'rtorrent'][b'directory'] = path.encode()


def chk_basedir(path, tdata):
    base_path = os.path.join(path, tdata[b'info'][b'name'].decode())
    if not os.path.exists(base_path):
        raise RuntimeError('Base path was not found.')

    if is_multi(tdata):
        if len(os.listdir(base_path)) == 0:
            raise RuntimeError("Base path for torrent is empty. Can't resume a torrent that hasn't started yet!")
        path = os.path.join(path, tdata[b'info'][b'name'].decode())

    return path


def is_multi(tdata):
    """Returns True if torrent has multiple files, False if otherwise"""
    try:
        _ = tdata[b'info'][b'files']
        return True
    except KeyError:
        return False


def chunks(length, bsize):
    div = int(length / bsize)
    return div + 1 if length % bsize else div


def getfiles(tdata):
    global chunk_size, tsize, num_chunks
    try:
        chunk_size = tdata[b'info'][b'piece length']
    except KeyError:
        raise RuntimeError('Invalid torrent: No piece length key found.')

    files = []
    tsize = 0
    if is_multi(tdata):
        for f in tdata[b'info'][b'files']:
            files.append(f[b'path'][0].decode())
            tsize += f[b'length']
    else:
        files = [tdata[b'info'][b'name'].decode()]
        tsize = tdata[b'info'][b'length']

    num_chunks = chunks(tsize, chunk_size)
    if num_chunks * CHUNK_HASH_SIZE != len(tdata[b'info'][b'pieces']):
        raise RuntimeError('Inconsistent chunks hash information!')
    return files


def filechunks(offset, size):
    return chunks(offset + size, chunk_size) - chunks(offset + 1, chunk_size) + 1


def resume(tdata):
    files = getfiles(tdata)
    d = tdata[b'rtorrent'][b'directory'].decode()

    ondisksize = 0  # on-disk data size counter
    boffset = 0  # block offset
    missing = 0  # chunks missing

    for idx, f in enumerate(files):
        full_path = os.path.join(d, f)
        if not os.path.isfile(full_path):
            raise RuntimeError("Something is wrong with the torrent's files. They either don't exist, or are not "
                               "normal files.")

        fstat = os.path.getsize(full_path)
        trnt_length = tdata[b'info'][b'files'][idx][b'length'] if is_multi(tdata) else tdata[b'info'][b'length']

        if trnt_length != fstat:
            raise RuntimeError("One of the torrent files does not match its expected size. Aborting.")

        mtime = int(os.path.getmtime(full_path))
        completed = filechunks(boffset, fstat) if fstat else 0

        # Add libtorrent resume data to torrent
        tdata[b'libtorrent_resume'] = {}
        tdata[b'libtorrent_resume'][b'files'] = []
        tdata[b'libtorrent_resume'][b'files'].insert(idx, {
            b'mtime': mtime,
            b'completed': completed
        })

        ondisksize += fstat
        boffset += trnt_length

    # Resume failed if ondisksize = 0 (no files to resume) or ondisksize doesn't match sum of all files in torrent
    if ondisksize != tsize or ondisksize == 0:
        raise RuntimeError("File size verification failed. Files are missing.")

    print('Resume summary for torrent %s: %d missing.' % (tdata[b'info'][b'name'], missing))

    # Set vars in torrent
    tdata[b'rtorrent'][b'chunks_wanted'] = missing
    tdata[b'rtorrent'][b'chunks_done'] = num_chunks - missing
    tdata[b'rtorrent'][b'complete'] = 0 if missing else 1
    if not missing:
        tdata[b'libtorrent_resume'][b'bitfield'] = num_chunks


def savetofile(tdata, dest):
    encoded_tdata = bencode.bencode(tdata)
    with open(dest, 'wb') as f:
        f.write(encoded_tdata)


def rfr(tfile, base, dest):
    if not os.path.exists(tfile):
        raise RuntimeError('Torrent file was not found. Please pass the path to a valid torrent file.')

    # Process torrent
    torrent = load_file(tfile)
    torrent_check(torrent, base)
    resume(torrent)

    # Write torrent to file
    savetofile(torrent, dest)
    print('Done!')


if __name__ == '__main__':
    rfr('test-multi.torrent', '/Users/bradenbaird/Downloads', 'test-multi-fast.torrent')

    rfr('test.torrent', '/Users/bradenbaird/Downloads', 'test-fast.torrent')
