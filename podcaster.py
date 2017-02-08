#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import argparse
import mutagen
import pprint
import tempfile
import subprocess
import unicodedata
import datetime
from PIL import Image
import os
import math
import sys

PRESENT_TEMPLATE="ChapterTemplate.svg"
MISSING_ARTWORK="MissingArtworkMusic.png"
PODCAST_ARTWORK="PodcastArtwork.jpg"


class Podcast:
    def __init__ (self):
        self.audio = None
        self.chapterImagesInfo = """<?xml version="1.0" encoding="UTF-8" ?>
            <NHNTStream version="1.0" timeScale="1000"
            mediaType="vide" mediaSubType="jpeg" width="1920" height="1080"
            codecVendor="....">"""
        self.chapterInfo = """<?xml version="1.0" encoding="UTF-8" ?>
            <TextStream version="1.1">
                <TextStreamHeader><TextSampleDescription/>
                </TextStreamHeader>"""
        self.length = 0
        self.files=[]

    
    def chapterize(self):
        nhml=tempfile.mkstemp(suffix='.nhml', dir='.')
        os.write(nhml[0],self.chapterImagesInfo)
        os.write(nhml[0],"""</NHNTStream>""")
        os.close(nhml[0])
        
        chap=tempfile.mkstemp(suffix='.ttxt', dir='.')
        os.write(chap[0],self.chapterInfo)
        os.write(chap[0],"""</TextStream>""")
        os.close(chap[0])

        
        subprocess.call([
            "MP4Box", self.audio,
            "-add", "{file}:chap:name=Chapter Titles".format(file=chap[1]),
            "-add", "{file}:name=Chapter Images".format(file=nhml[1])
        ])
        
        os.remove(nhml[1])
        os.remove(chap[1])


    def tag(self):
        description=""
        title=""
        artist=""
        
        i=0
        for song in self.files:
            i+=1
            description += "{i:02}. {name}\n".format(
                i=i,
                name=self.songCompleteName(song)
            )
            
            if (title):
                title += " | ".encode('UTF-8')
            title += song['title'][0].encode('UTF-8')
        
            if (artist):
                artist += " | ".encode('UTF-8')
            artist += song['artist'][0].encode('UTF-8')
            
        subprocess.call([
            "mp4tags",
            "-H", "1",
            "-X", "clean",
            "-i", "podcast",
            "-E", "Podcast creator by Avi Alkalay",
            "-e", "Avi Alkalay",
            "-C", "Copyright by its holders",
            "-a", artist,
            "-s", title,
            "-l", description,
            self.audio
        ])

        subprocess.call([
            "mp4art",
            "-z",
            "--add", "{}/{}".format(os.path.dirname(sys.argv[0]),PODCAST_ARTWORK),
            self.audio
        ])


    def songImage(self,f):
    
        theArtwork = []
    
        if 'artwork' in f:
            # overwrite theArtwork tuple if file has artwork
            theArtwork=tempfile.mkstemp()
            os.write(theArtwork[0],f['artwork'])
            os.close(theArtwork[0])
        else:
            theArtwork.append(0)
            theArtwork.append("{}/{}".format(os.path.dirname(sys.argv[0]),MISSING_ARTWORK))
    
        with open("{}/{}".format(os.path.dirname(sys.argv[0]),PRESENT_TEMPLATE), 'r') as myfile:
            template=myfile.read()
    
        albumYear=""
        if 'date' in f:
            albumYear = " ({})".format(f['date'][0].encode('UTF-8'))
        
        template=template.format(
            NAME=f['title'][0].replace('&',"&amp;").encode('UTF-8'),
            ARTIST=f['artist'][0].replace('&',"&amp;").encode('UTF-8'),
            ALBUM=f['album'][0].replace('&',"&amp;").encode('UTF-8') + albumYear,
            COVER_ART_PATH=theArtwork[1]
        )

        theTemplate=tempfile.mkstemp(suffix='.svg')
        os.write(theTemplate[0],template)
        os.close(theTemplate[0])

        thePresentation=tempfile.mkstemp(suffix='.png')
        os.close(thePresentation[0])
    
        subprocess.call(["inkscape", "--without-gui", "--export-area-page", "-e",
            thePresentation[1], theTemplate[1]])
    
        os.remove(theTemplate[1])
        if (theArtwork[0] != 0):
            os.remove(theArtwork[1])

        thePresentationJPG=tempfile.mkstemp(suffix='.jpg', dir='.')
        os.close(thePresentationJPG[0])
        
        im = Image.open(thePresentation[1])
        im.save(thePresentationJPG[1])
        os.remove(thePresentation[1])

        f['image']=thePresentationJPG[1]    


    def concatAudioFiles(self):
        coder=[
            "-y",
            "-filter_complex",
            "concat=n={number_of_songs}:v=0:a=1 [out]".format(
                number_of_songs=len(self.files)
            ),
            "-map", "[out]",
            "-vn",
            "-c:a", "libfdk_aac", "-vbr", "4",
            "-map_metadata", "-1",
        ]

        params = []
    
        for f in self.files:
            params.append("-i")
            params.append(f['file'])

        subprocess.call(
            ["ffmpeg"] +
            params +
            coder +
            [self.audio]
        )


    def musicInfo(self,f):
        info = {}
        audio = mutagen.File(f, easy=True)

        #pprint.pprint(audio.info.length)

    
        info['theLength']=audio.info.length
        info.update(audio)
    
        # Now get only cover art
        audio = mutagen.File(f, easy=False)
    
        #pprint.pprint(audio)
    
        k = audio.keys()
        if 'covr' in k:
            info['artwork']=str(audio['covr'][0])
        elif 'APIC:thumbnail' in k:
            info['artwork']=audio['APIC:thumbnail'].data
    
        return info


    def clean(self):
        for f in self.files:
            os.remove(f['image'])


    def songCompleteName(self, song, html=False):
        albumYear=" ({})"
        template="{artist} » {album} » {title} ({l})"
        
        if (html):
            template="""
                <span class="song">
                    <span class="artist">{artist}</span>
                        <span class="separator"> » </span>
                    <span class="album">{album}</span>
                        <span class="separator"> » </span>
                    <span class="title">{title}</span>
                    <span class="duration">({l})</span>
                </span>"""
            albumYear=""" <span class="yearwrap">(<span class="year">{}</span>)</span>"""
        

        if 'date' in song:
            albumYear = albumYear.format(song['date'][0])
        else:
            albumYear = ""
        
        name=template.format(
            artist = song['artist'][0].encode('UTF-8'),
            album = song['album'][0].encode('UTF-8') + albumYear,
            title = song['title'][0].encode('UTF-8'),
            l = str(datetime.timedelta(seconds=math.floor(song['theLength'])))
        )
        
        if (html):
            name=name.replace('&',"&amp;")
        
        return name


    def ffmetadataChapter(self,song):
        # unused
        timeScale=1000000
        template="[CHAPTER]\nTIMEBASE=1/{scale}\nSTART={start}\nEND={end}\ntitle={title}\n"

        return template.format(
            scale=timeScale,
            start=int(timeScale*self.length),
            end=int(timeScale*self.length + song['theLength']),
            title=self.songCompleteName(song)
        )


    def timedTextChapter(self,song):
        timeScale=1000
        template="""<TextSample sampleTime="{time}" xml:space="preserve">{title}</TextSample>\n"""

        return template.format(
            time="0{:.11}".format(datetime.timedelta(seconds=self.length)),
            title=self.songCompleteName(song),
            i=len(self.files)
        )


    def add(self,name):
        f = {'file': name}
        f.update(self.musicInfo(name))
        
        self.songImage(f)
        self.chapterImagesInfo += """<NHNTSample DTS="{cursor}" mediaFile="{file}" isRAP="yes" />\n""".format(
            cursor=int(1000*self.length),
            file=f['image']
        )

        self.chapterInfo += self.timedTextChapter(f)
                
        self.length += f['theLength']
        
        self.files.append(f)

  
    def make(self,target):
        self.audio=target
        if (self.audio.endswith('.m4a') == False):
            self.audio+='.m4a'
        
        self.concatAudioFiles()
        self.chapterize()
        self.tag()
        self.clean()
        


parser = argparse.ArgumentParser(description='Create podcast from songs')

parser.add_argument('files', type=str, nargs='+',
                    help='music files to be added to podcast')

args = parser.parse_args()

p = Podcast()

for f in vars(args)['files']:
    p.add(f)

p.make('output.m4a')
