#!/usr/bin/env python
# -*- coding: UTF-8 -*-

########################################################################################
#
# Get a list of audio files (M4A, MP3, FLAC) and concatenate them all in a new AAC M4A
# extended podcast file.
#
# Tags and cover art will be used to generate chapters info and nice chapter images.
#
# See the main() function for some defaults
#
# Licensed as GPL 3
#
# Avi Alkalay <avi at unix dot sh>
# 2017-02-13
# Made in Brazil
#


import argparse
import mutagen
import pprint
import tempfile
import subprocess
import unicodedata
import datetime
import logging
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
            "-add", "{file}:name=Chapter Images".format(file=nhml[1]),
            "-delay", "1={}".format(self.introDuration)
        ])
        
        os.remove(nhml[1])
        os.remove(chap[1])


    def makeDescriptions(self):
        self.description=""
        self.artist=""
        tracks=""
        youtubeTracks=""
        composers=""
        albums=""
        
        i=0
        pos=self.introDuration/1000
        for song in self.files:
            i+=1
            name=self.songCompleteName(song)
            tracks += "{i:02}. {name}\n".format(
                i=i,
                name=name
            )

            youtubeTracks += "{i:02}. [{pos}] {name}\n".format(
                i=i,
                name=name,
                # http://stackoverflow.com/a/31946730/367824
                pos = "{:0>8}".format(datetime.timedelta(seconds=math.floor(pos)))
            )
            pos += song['theLength']
            
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
                
                albumArtist=""
                if 'performer'   in song: albumArtist=song['performer'][0]   # MP3
                if 'albumartist' in song: albumArtist=song['albumartist'][0] # MPEG-4
                
                albums += "{i:02}. {albumArtist} » {album}{year}\n".format(
                    i=i,
                    album=', '.join(song['album']).encode('UTF-8'),
                    albumArtist=albumArtist.encode('UTF-8'),
                    year=albumYear
                )
            
            if (self.title == None or self.title.endswith(" | ")):
                self.title += song['title'][0].encode('UTF-8')
                self.title += " | "
        
            if self.artist: self.artist += " | ".encode('UTF-8')
            self.artist += song['artist'][0].encode('UTF-8')
        
        template="{prefix}TRACK LIST\n{tracks}\n\nCOMPOSERS\n{composers}\n\nALBUMS\n{albums}{suffix}"
        
        self.description = template.format(
            tracks=tracks,
            composers=composers,
            albums=albums,
            prefix=self.descriptionPrefix,
            suffix=self.descriptionSuffix
        ) 
        
        self.youtubeDescription = template.format(
            tracks=youtubeTracks,
            composers=composers,
            albums=albums,
            prefix=self.descriptionPrefix,
            suffix=self.descriptionSuffix
        ) 
        
        if self.title.endswith(' | '):
            self.title = self.title[:-3]


    def tag(self):
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
            "-a", self.artist,
            "-s", self.title,
            "-A", self.podcast,
            "-l", self.description,
            "-m", self.description,
            self.output
        ])

        self.images['cover']=self.templateSVGtoJPG('podcast-artwork',1400,1400)

        subprocess.call([
            "mp4art",
            "-z",
            "--add", self.images['cover'],
            self.output
        ])


    def imagify(self):
        # Extract artwork from every audio file
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


        # build GPAC's NHML sequence of images for video
        cursor=0
        self.images = {}
        if self.introDuration > 0:
            logging.debug('About to make Intro image')

            data = {
                'TITLE': self.title
            }
            
            self.images['intro']=self.templateSVGtoJPG("intro", 1280, 720, data)

            self.chapterInfo += self.timedTextChapter(cursor, "Introduction")

            self.chapterImagesInfo += """<NHNTSample DTS="{cursor}" mediaFile="{file}" isRAP="yes" />\n""".format(
                cursor=int(1000*cursor),
                file=self.images['intro']
            )
            
            cursor += self.introDuration/1000
        
        
        for i in range(len(self.files)):
            logging.debug('About to make image for %s', self.files[i]['title'][0])

            data = {}
            
            albumYear=""
            if 'date' in self.files[i]:
                albumYear = " ({:.4})".format(self.files[i]['date'][0].encode('UTF-8'))
        
            if i > 0:
                data['PREV_VISIBILITY']="visible"
                data['PREV_NAME']=self.files[i-1]['title'][0].replace('&',"&amp;").encode('UTF-8')
                data['PREV_ARTIST']=self.files[i-1]['artist'][0].replace('&',"&amp;").encode('UTF-8')
                data['PREV_COVER_ART_PATH']=self.files[i-1]['artworkFile']
            else:
                data['PREV_VISIBILITY']="none"
                data['PREV_NAME']=data['PREV_ARTIST']=data['PREV_COVER_ART_PATH']="whatever"
            
            if i < len(self.files)-1:
                data['NEXT_VISIBILITY']="visible"
                data['NEXT_NAME']=self.files[i+1]['title'][0].replace('&',"&amp;").encode('UTF-8')
                data['NEXT_ARTIST']=self.files[i+1]['artist'][0].replace('&',"&amp;").encode('UTF-8')
                data['NEXT_COVER_ART_PATH']=self.files[i+1]['artworkFile']
            else:
                data['NEXT_VISIBILITY']="none"
                data['NEXT_NAME']=data['NEXT_ARTIST']=data['NEXT_COVER_ART_PATH']="whatever"

            data['NAME']=self.files[i]['title'][0].replace('&',"&amp;").encode('UTF-8')
            data['ARTIST']=self.files[i]['artist'][0].replace('&',"&amp;").encode('UTF-8')
            data['ALBUM']=self.files[i]['album'][0].replace('&',"&amp;").encode('UTF-8') + albumYear
            data['COVER_ART_PATH']=self.files[i]['artworkFile']

            data['COMPOSER']=""
            if 'composer' in self.files[i]:
                data['COMPOSER']=", ".join(self.files[i]['composer']).replace('&',"&amp;").encode('UTF-8')
        

            self.files[i]['image'] = self.templateSVGtoJPG("chapter", 1280, 720, data)

            self.chapterInfo += self.timedTextChapter(cursor, self.songCompleteName(self.files[i]))

            self.chapterImagesInfo += """<NHNTSample DTS="{cursor}" mediaFile="{file}" isRAP="yes" />\n""".format(
                cursor=int(1000*cursor),
                file=self.files[i]['image']
            )

            cursor += self.files[i]['theLength']
            
            i += 1  
            
        self.images['credits'] = self.templateSVGtoJPG("credits", 1280, 720)
        
        self.chapterInfo += self.timedTextChapter(cursor, "Credits")

        self.chapterImagesInfo += """<NHNTSample DTS="{cursor}" mediaFile="{file}" isRAP="yes" />\n""".format(
            cursor=int(1000*cursor),
            file=self.images['credits']
        )
        
        cursor += self.introDuration/1000

        self.images['end']     = self.templateSVGtoJPG("end", 1280, 720)

        self.chapterImagesInfo += """<NHNTSample DTS="{cursor}" mediaFile="{file}" isRAP="yes" />\n""".format(
            cursor=int(1000*cursor),
            file=self.images['end']
        )
        

    def templateSVGtoJPG(self, svgid, w, h, data={}):
        empty = ""
        theData = {
            'TITLE': empty,
            'ALBUM': empty,
            'ARTIST': empty,
            'COMPOSER': empty,
            'COVER_ART_PATH': empty,
            'NAME': empty,
            'NEXT_ARTIST': empty,
            'NEXT_COVER_ART_PATH': empty,
            'NEXT_NAME': empty,
            'NEXT_VISIBILITY': empty,
            'PREV_VISIBILITY': empty,
            'PREV_ARTIST': empty,
            'PREV_COVER_ART_PATH': empty,
            'PREV_NAME': empty
        }

        theData.update(data)

        logging.debug('templateSVGtoJPG: %s', str(theData))

#         pprint.pprint(theData)
#         return

        with open("{}/{}".format(os.path.dirname(sys.argv[0]),self.chapterTemplate), 'r') as myfile:
            template=myfile.read()    

        template = template.format(**theData)

        # SVG data is ready in memory, now write SVG file
        theTemplate = tempfile.mkstemp(suffix='.svg', dir='.')
        os.write(theTemplate[0],template)
        os.close(theTemplate[0])

        # Generate PNG from SVG
        thePresentation = tempfile.mkstemp(suffix='.png')
        os.close(thePresentation[0])

        subprocess.call([
            "inkscape", "--without-gui",
            "--export-id={}".format(svgid),
            "-w", str(w),
            "-h", str(h),
            "-e", thePresentation[1], theTemplate[1]]
        )

        os.remove(theTemplate[1])       # remove temporary SVG

        # Convert PNG to JPG
        thePresentationJPG=tempfile.mkstemp(suffix='.jpg', dir='.')
        os.close(thePresentationJPG[0])

        im = Image.open(thePresentation[1])
        im.save(thePresentationJPG[1])

        os.remove(thePresentation[1])   # remove temporary PNG
    
        return thePresentationJPG[1]


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


    def musicInfo(self, f):
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
    
#         pprint.pprint(info)
        return info


    def clean(self):
        for f in self.files:
            os.remove(f['image'])
            if (f['artworkFile'].endswith(self.missingArtwork)==False):
                os.remove(f['artworkFile'])
        for f in self.images:
            os.remove(self.images[f])


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
        
        l = str(datetime.timedelta(seconds=math.floor(song['theLength'])))
        if song['theLength'] < 60*60:
            if song['theLength'] < 10*60:
                l=l[-4:]
            else:
                l=l[-5:]
        
        name=template.format(
            artist = song['artist'][0].encode('UTF-8'),
            album = song['album'][0].encode('UTF-8'),
            title = song['title'][0].encode('UTF-8') + albumYear,
            l = l
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


    def timedTextChapter(self, seconds, title):
        timeScale=1000
        template="""<TextSample sampleTime="{time}" xml:space="preserve">{title}</TextSample>\n"""

        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        h = int(h)
        m = int(m)

        return template.format(
            time="{:02d}:{:02d}:{:06.3f}".format(h, m, s),
            title=title
        )


    def add(self, name):
        f = {'file': name}
        f.update(self.musicInfo(name))
        
#         pprint.pprint(f)
#         return
                        
        self.length += f['theLength']
        
        self.files.append(f)


    def toYouTube(self):
        yt = os.open(os.path.splitext(self.output)[0] + ".youtube.txt", os.O_CREAT | os.O_WRONLY)
        os.write(yt, self.youtubeDescription)
        os.close(yt)
        
  
    def make(self):
        # Compute output file name
        if (self.output == None):
            if self.podcast:                 self.output = self.podcast
            if self.output and self.episode: self.output += " - "                                
            if self.episode:                 self.output += '{:03d}'.format(self.episode)        
            if self.output and self.title:   self.output += " - "                                
            if self.title:                   self.output += self.title                           
            
        if self.output == None:                     self.output = "output"
        if self.output.endswith('.m4a') == False:   self.output += '.m4a'
        
        
        self.makeDescriptions()
        
        # Generate images for each audio file
        self.imagify()
        
        # Make the audio track
        self.concatAudioFiles()
        
        # Merge audio and chapters into one final M4A file
        self.chapterize()
        
        # Add rich podcast-like tags to the M4A
        self.tag()
        
        # Write HTML file
#         self.toHTML()
        
        self.toYouTube()
        
        # Remove temporary files
        self.clean()
        


def main():
    #logging.basicConfig(level=logging.DEBUG)

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

    parser.add_argument('-c', dest='chapterTemplate', default="artwork.svg",
        help='SVG file to be used as template for each chapter image')

    parser.add_argument('-m', dest='missingArtwork', default="MissingArtworkMusic.png",
        help="image to use in case audio file doesn't have embeded arwork")
    
    parser.add_argument('-a', dest='podcastArtwork', default="PodcastArtwork.jpg",
        help="image to embed as artwork in final M4A podcast file")
    
    parser.add_argument('--dp', dest='descriptionPrefix', default="",
        help="text for description, before track list")
    
    parser.add_argument('--ds', dest='descriptionSuffix', default="",
        help="text for description, after track list")

    parser.add_argument('--intro', dest='introDuration', type=int, default="3000",
        help="Duration in miliseconds for introduction image")

    parser.add_argument('f', type=str, nargs='+',
                        help='music files to be added to podcast')

    args = parser.parse_args(namespace=p)
    
    for f in p.f:
        p.add(f)

    p.make()


__name__ == '__main__' and main()

