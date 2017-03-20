#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import mutagen
import pprint
import argparse


parser = argparse.ArgumentParser(description='Create podcast from songs')
parser.add_argument('files', type=str, nargs='+',
                    help='music files to be added to podcast')

args = parser.parse_args()

for f in vars(args)['files']:
    audio = mutagen.File(f, easy=True)
    if 'covr' in audio:
        del audio['covr']
    elif u'APIC:' in audio:
        del audio['APIC:']
    pprint.pprint(audio)
