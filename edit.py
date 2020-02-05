#!/usr/bin/env python3

import fileinput
import argparse
import re
from contextlib import contextmanager
import io
import os
import sys

SEP="---"

# cribbed from https://www.zopatista.com/python/2013/11/26/inplace-file-rewriting/
# no copyright but I'm assuming it's kinda not a big deal; if you want I will
# rewrite it to be a little different.
@contextmanager
def inplace(filename, mode='r', buffering=-1, encoding=None, errors=None,
            newline=None, backup_extension=None):
    """Allow for a file to be replaced with new content.

    yields a tuple of (readable, writable) file objects, where writable
    replaces readable.

    If an exception occurs, the old file is restored, removing the
    written data.

    mode should *not* use 'w', 'a' or '+'; only read-only-modes are supported.

    """

    # move existing file to backup, create new file with same permissions
    # borrowed extensively from the fileinput module
    if set(mode).intersection('wa+'):
        raise ValueError('Only read-only file modes can be used')

    backupfilename = filename + (backup_extension or os.extsep + 'bak')
    try:
        os.unlink(backupfilename)
    except os.error:
        pass
    os.rename(filename, backupfilename)
    readable = io.open(backupfilename, mode, buffering=buffering,
                       encoding=encoding, errors=errors, newline=newline)
    try:
        perm = os.fstat(readable.fileno()).st_mode
    except OSError:
        writable = open(filename, 'w' + mode.replace('r', ''),
                        buffering=buffering, encoding=encoding, errors=errors,
                        newline=newline)
    else:
        os_mode = os.O_CREAT | os.O_WRONLY | os.O_TRUNC
        if hasattr(os, 'O_BINARY'):
            os_mode |= os.O_BINARY
        fd = os.open(filename, os_mode, perm)
        writable = io.open(fd, "w" + mode.replace('r', ''), buffering=buffering,
                           encoding=encoding, errors=errors, newline=newline)
        try:
            if hasattr(os, 'chmod'):
                os.chmod(filename, perm)
        except OSError:
            pass
    try:
        yield readable, writable
    except Exception:
        # move backup back
        try:
            os.unlink(filename)
        except os.error:
            pass
        os.rename(backupfilename, filename)
        raise
    finally:
        readable.close()
        writable.close()
        try:
            os.unlink(backupfilename)
        except os.error:
            pass

def flush_block(outfh, keep, lines):
    if keep:
        outfh.write(SEP)
        outfh.write("\n")
        for k in lines:
            outfh.write(k)
            outfh.write("\n")

def drop_blocks(fname, pat):
    lines = []
    keep = True
    with inplace(fname) as (infh, outfh):
        for line in infh:
            line = line.rstrip('\n')
            if line.startswith(SEP):
                flush_block(outfh, keep, lines)
                lines = []
                keep = True
            else:
                lines.append(line)
                if pat.search(line):
                    keep = False
        if len(lines) > 0:
            flush_block(outfh, keep, lines)

def show_blocks(fname, pat):
    lines = []
    keep = False
    for line in fileinput.input(fname):
        line = line.rstrip('\n')
        if line.startswith(SEP):
            flush_block(sys.stdout, keep, lines)
            lines = []
            keep = False
        else:
            lines.append(line)
            if pat.search(line):
                keep = True
    if len(lines) > 0:
        flush_block(sys.stdout, keep, lines)


def main():
    parser = argparse.ArgumentParser("show and/or delete text-blocks from a file of '---' separated blocks")
    parser.add_argument('--show', type=str)
    parser.add_argument('--delete', type=str)
    parser.add_argument('--file', type=str, action='append')
    args = parser.parse_args()
    if args.show and args.delete:
        print("can only pass one of --show or --delete")
        exit(1)
    if not args.show and not args.delete:
        print("must pass one of --show or --delete")
        exit(1)
    if args.show:
        pat = re.compile(args.show, re.IGNORECASE)
        for f in args.file:
            show_blocks(f, pat)
    if args.delete:
        pat = re.compile(args.delete, re.IGNORECASE)
        for f in args.file:
            drop_blocks(f, pat)


if __name__ == '__main__':
    main()
