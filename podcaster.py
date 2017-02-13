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


class Podcast:
    def __init__ (self):
        self.audio = None
        self.chapterImagesInfo = """<?xml version="1.0" encoding="UTF-8" ?>
            <NHNTStream version="1.0" timeScale="1000"
            mediaType="vide" mediaSubType="jpeg" width="1280" height="720"
            codecVendor="....">"""
        self.chapterInfo = """<?xml version="1.0" encoding="UTF-8" ?>
            <TextStream version="1.1">
                <TextStreamHeader><TextSampleDescription/>
                </TextStreamHeader>"""
        self.length = 0
        self.files = []

    
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
            "MP4Box", self.output,
            "-add", "{file}:chap:name=Chapter Titles".format(file=chap[1]),
            "-add", "{file}:name=Chapter Images".format(file=nhml[1])
        ])
        
        os.remove(nhml[1])
        os.remove(chap[1])


    def tag(self):
        description=""
        tracks=""
        composers=""
        albums=""
        artist=""
        
        i=0
        for song in self.files:
            i+=1
            tracks += "{i:02}. {name}\n".format(
                i=i,
                name=self.songCompleteName(song)
            )
            
            if 'composer' in song:
                composers += "{i:02}. {name}\n".format(
                    i=i,
                    name=', '.join(song['composer']).encode('UTF-8')
                )
            
            if ('album') in song:
                albumYear = " ({:.4})"
                if 'date' in song:
                    albumYear = albumYear.format(song['date'][0])
                else:
                    albumYear = ""
                
                albums += "{i:02}. {albumArtist} » {album}{year}\n".format(
                    i=i,
                    album=', '.join(song['album']).encode('UTF-8'),
                    albumArtist=song['albumartist'][0].encode('UTF-8'),
                    year=albumYear
                )
            
            if (self.title == None or self.title.endswith(" | ")):
                self.title += song['title'][0].encode('UTF-8')
                self.title += " | "
        
            if (artist):
                artist += " | ".encode('UTF-8')
            artist += song['artist'][0].encode('UTF-8')
        
        description = "{prefix}TRACK LIST\n{tracks}\n\nCOMPOSERS\n{composers}\n\nALBUMS\n{albums}{suffix}".format(
            tracks=tracks,
            composers=composers,
            albums=albums,
            prefix=self.descriptionPrefix,
            suffix=self.descriptionSuffix
        ) 
        
        if self.title.endswith(' | '):
            self.title = self.title[:-3]

        subprocess.call([
            "mp4tags",
            "-H", "1",
            "-X", "clean",
            "-i", "podcast",
            "-B", "1",
            "-M", str(self.episode),
            "-E", "Podcast creator by Avi Alkalay",
            "-e", "Avi Alkalay",
            "-C", "Copyright by its holders",
            "-a", artist,
            "-s", self.title,
            "-l", description,
            self.output
        ])

        subprocess.call([
            "mp4art",
            "-z",
            "--add", "{}/{}".format(os.path.dirname(sys.argv[0]),self.podcastArtwork),
            self.output
        ])


    def imagify(self):
        for i in range(len(self.files)):
            theArtwork = []
    
            if 'artwork' in self.files[i]:
                # overwrite theArtwork tuple if file has artwork
                theArtwork=tempfile.mkstemp()
                os.write(theArtwork[0],self.files[i]['artwork'])
                os.close(theArtwork[0])
                self.files[i]['artworkFile'] = theArtwork[1]
            else:
                self.files[i]['artworkFile'] = "{}/{}".format(
                    os.path.dirname(sys.argv[0]),
                    self.missingArtwork
                )


        cursor=0
        for i in range(len(self.files)):
            with open("{}/{}".format(os.path.dirname(sys.argv[0]),self.chapterTemplate), 'r') as myfile:
                template=myfile.read()
    
            albumYear=""
            if 'date' in self.files[i]:
                albumYear = " ({:.4})".format(self.files[i]['date'][0].encode('UTF-8'))
        
            composer=""
            if 'composer' in self.files[i]:
                composer=", ".join(self.files[i]['composer']).replace('&',"&amp;").encode('UTF-8')
        
            if i > 0:
                PREV_VISIBILITY="visible"
                PREV_NAME=self.files[i-1]['title'][0].replace('&',"&amp;").encode('UTF-8')
                PREV_ARTIST=self.files[i-1]['artist'][0].replace('&',"&amp;").encode('UTF-8')
                PREV_COVER_ART_PATH=self.files[i-1]['artworkFile']
            else:
                PREV_VISIBILITY="none"
                PREV_NAME=PREV_ARTIST=PREV_COVER_ART_PATH="whatever"
            
            if i < len(self.files)-1:
                NEXT_VISIBILITY="visible"
                NEXT_NAME=self.files[i+1]['title'][0].replace('&',"&amp;").encode('UTF-8')
                NEXT_ARTIST=self.files[i+1]['artist'][0].replace('&',"&amp;").encode('UTF-8')
                NEXT_COVER_ART_PATH=self.files[i+1]['artworkFile']
            else:
                NEXT_VISIBILITY="none"
                NEXT_NAME=NEXT_ARTIST=NEXT_COVER_ART_PATH="whatever"

            template=template.format(
                COMPOSER=composer,
                NAME=self.files[i]['title'][0].replace('&',"&amp;").encode('UTF-8'),
                ARTIST=self.files[i]['artist'][0].replace('&',"&amp;").encode('UTF-8'),
                ALBUM=self.files[i]['album'][0].replace('&',"&amp;").encode('UTF-8') + albumYear,
                COVER_ART_PATH=self.files[i]['artworkFile'],

                NEXT_VISIBILITY=NEXT_VISIBILITY,
                NEXT_NAME=NEXT_NAME,
                NEXT_ARTIST=NEXT_ARTIST,
                NEXT_COVER_ART_PATH=NEXT_COVER_ART_PATH,

                PREV_VISIBILITY=PREV_VISIBILITY,
                PREV_NAME=PREV_NAME,
                PREV_ARTIST=PREV_ARTIST,
                PREV_COVER_ART_PATH=PREV_COVER_ART_PATH
            )

            # SVG data is ready in memory, now write SVG file
            theTemplate=tempfile.mkstemp(suffix='.svg', dir='.')
            os.write(theTemplate[0],template)
            os.close(theTemplate[0])

            # Convert to PNG
            thePresentation=tempfile.mkstemp(suffix='.png')
            os.close(thePresentation[0])

            subprocess.call(["inkscape", "--without-gui", "--export-area-page",
                "-w", "1280",
                "-h", "720",
                "-e", thePresentation[1], theTemplate[1]])

            os.remove(theTemplate[1])

            # Convert to JPG
            thePresentationJPG=tempfile.mkstemp(suffix='.jpg', dir='.')
            os.close(thePresentationJPG[0])
    
            im = Image.open(thePresentation[1])
            im.save(thePresentationJPG[1])
            os.remove(thePresentation[1])

            self.files[i]['image']=thePresentationJPG[1]

            self.chapterImagesInfo += """<NHNTSample DTS="{cursor}" mediaFile="{file}" isRAP="yes" />\n""".format(
                cursor=int(1000*cursor),
                file=self.files[i]['image']
            )

            cursor+=self.files[i]['theLength']
            
            i += 1


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
            [self.output]
        )


    def musicInfo(self,f):
        info = {}
        audio = mutagen.File(f, easy=True)
    
        info['theLength']=audio.info.length
        info.update(audio)
    
        # Now get only cover art and composer
        audio = mutagen.File(f, easy=False)
        
        k = audio.keys()
        if '\xA9wrt' in k:
            info['composer']=audio['\xA9wrt']

        if 'covr' in k:
            info['artwork']=str(audio['covr'][0])
        elif u'APIC:' in k:
            info['artwork']=audio['APIC:'].data
    
        return info


    def clean(self):
        for f in self.files:
            os.remove(f['image'])
            if (f['artworkFile'].endswith(self.missingArtwork)==False):
                os.remove(f['artworkFile'])


    def songCompleteName(self, song, html=False):
        albumYear=" 【{:.4}】"
        template="{artist} » {title} ({l})"
        
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
            album = song['album'][0].encode('UTF-8'),
            title = song['title'][0].encode('UTF-8') + albumYear,
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


    def add(self, name):
        f = {'file': name}
        f.update(self.musicInfo(name))
        
#         pprint.pprint(f)
#         return
        
        self.chapterInfo += self.timedTextChapter(f)
                
        self.length += f['theLength']
        
        self.files.append(f)

  
    def make(self):
        if (self.output == None):
            if self.podcast:                 self.output = self.podcast
            if self.output and self.episode: self.output += " - "                                
            if self.episode:                 self.output += '{:03d}'.format(self.episode)        
            if self.output and self.title:   self.output += " - "                                
            if self.title:                   self.output += self.title                           
            
        if self.output == None:                     self.output = "output"
        if self.output.endswith('.m4a') == False:   self.output += '.m4a'
        
        self.imagify()
        self.concatAudioFiles()
        self.chapterize()
        self.tag()
        self.clean()
        


def main():
    p = Podcast()

    parser = argparse.ArgumentParser(
        description='Create extended podcast from well tagged audio files'
    )

    parser.add_argument('-p', dest='podcast',
        help='podcast global name')

    parser.add_argument('-t', dest='title',
        help='title for podcast')

    parser.add_argument('-i', dest='episode', type=int,
        help='episode number')

    parser.add_argument('-o', dest='output',
        help='output file name (defaults to "{podcast name} - {episode} - {title}.m4a)"')

    parser.add_argument('-c', dest='chapterTemplate', default="ChapterTemplate.svg",
        help='SVG file to be used as template for each chapter image')

    parser.add_argument('-m', dest='missingArtwork', default="MissingArtworkMusic.png",
        help="image to use in case audio file doesn't have embeded arwork")
    
    parser.add_argument('-a', dest='podcastArtwork', default="PodcastArtwork.jpg",
        help="image to embed as artwork in final M4A podcast file")
    
    parser.add_argument('--dp', dest='descriptionPrefix', default="",
        help="text for description, before track list")
    
    parser.add_argument('--ds', dest='descriptionSuffix', default="",
        help="text for description, after track list")

    parser.add_argument('f', type=str, nargs='+',
                        help='music files to be added to podcast')

    args = parser.parse_args(namespace=p)
    
#     pprint.pprint(vars(p))

    for f in p.f:
        p.add(f)

    p.make()


__name__ == '__main__' and main()

