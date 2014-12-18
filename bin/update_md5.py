#coding: UTF-8
__author__ = 'yangchenxing'

import argparse
import hashlib
import itertools
import os
import sys


def parse_args():
    parser = argparse.ArgumentParser('捷酷MD5文件更新工具')
    parser.add_argument('files', metavar='FILE', nargs='+', help='需要更新的文件或者目录')
    return parser.parse_args()


def update_md5(file):
    if os.path.isdir(file):
        dirpath, dirnames, filenames = os.walk(file)
        for filename in itertools.chain(filenames, dirnames):
            update_md5(os.path.join(dirpath, filename))
    else:
        with open(file, 'rb') as f:
            md5 = hashlib.md5()
            while 1:
                content = f.read(1024)
                if content:
                    md5.update(content)
                else:
                    break
        md5_file = file + '.md5'
        with open(file + '.md5', 'wb') as f:
            f.write('%s  %s\n' % (md5.hexdigest(), md5_file))


def main():
    args = parse_args()
    for file in args.files:
        if not os.path.exists(file):
            print >>sys.stderr, '文件或目录不存在: %s' % (file,)
        else:
            update_md5(file)


if __name__ == '__main__':
    main()