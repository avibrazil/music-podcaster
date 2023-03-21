#!/usr/bin/env python3
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

#
# Cheat sheet for dependencies...
#
# Python libs:
# dnf install python3-mutagen python3-unidecode
# pip install python-wordpress-xmlrpc
#
# External programs:
# dnf install inkscape gpac ffmpeg libmp4v2
#
# External repo:
# git clone https://github.com/tokland/youtube-upload
#
# Dependencies for external repos:
# dnf install python2-google-api-client
# dnf install python3-google-api-client
#


import argparse
import mutagen
import pprint
import tempfile
import html
import subprocess
import json
import unicodedata
from unidecode import unidecode
import re
import datetime
from datetime import timezone
from dateutil.parser import parse
from dateutil import tz
import logging
from PIL import Image
import os
from shutil import copyfile
import math
import sys
from string import Template
import jinja2



from wordpress_xmlrpc import Client, WordPressPost, WordPressTerm
from wordpress_xmlrpc.methods import media, posts, taxonomies
from wordpress_xmlrpc.compat import xmlrpc_client



class Podcast:
    #### Constants

    formats=dict(
        audio=dict(
            extension='mp4',
            mimetype='audio/mp4',
        ),
        video=dict(
            extension='mp4',
            mimetype='video/mp4',
        )
    )
    
    artwork={
        'DEFAULT': dict(
            width=1280,
            height=720
        ),
        'episode': dict(
            width=2000,
            height=2000
        ),
    }


    #### Methods for orchestration

    def __init__ (self, logger=logging.DEBUG):
        self.ytupload = "/home/aviram/src/youtube-upload/bin/youtube-upload"
        self.audio = None
        self.length = 0
        self.files = []
        self.artists = []
        self.chapterImagesInfo = """<?xml version="1.0" encoding="UTF-8" ?>
            <NHNTStream version="1.0" timeScale="1000"
            mediaType="vide" mediaSubType="jpeg" width="1280" height="720"
            codecVendor="....">"""
        self.chapterInfo = """<?xml version="1.0" encoding="UTF-8" ?>
            <TextStream version="1.1">
                <TextStreamHeader><TextSampleDescription/>
                </TextStreamHeader>"""

        self.targetEncoding = 'UTF-8'
        
        self.templateProcessor = jinja2.Environment(
            loader=jinja2.FileSystemLoader(
                searchpath=['./','../'],
                followlinks=True
            )
        )

        logging.basicConfig()
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logger)

        self.logger.info("Get media info...")

    def make(self):
        self.missingArtworkFullPath="{}/{}".format(
            os.path.dirname(sys.argv[0]),
            self.missingArtwork
        )

        if (self.date != None):
            self.date = parse(self.date).replace(tzinfo = tz.tzlocal()).astimezone(tz.tzutc())

        # Compute output file name
        if (self.output == None):
            if self.podcast:                 self.output = self.podcast
            if self.output and self.episode: self.output += "-"
            if self.episode:                 self.output += '{:04d}'.format(int(self.episode))
            if self.output and self.title:   self.output += "-"
            if self.title:                   self.output += self.safeFileName(self.title)
            if self.output:
                self.output = self.output.replace(" ","_")

        fileExtension='.' + self.formats[self.mediaFormat]['extension']

        if self.output == None:              self.output = "output"
        if not self.output.endswith(fileExtension): self.output += fileExtension

        self.sampleOutput  = self.output.replace(fileExtension, '.sample' + fileExtension)
        self.teaser        = self.output.replace(fileExtension, '.jpg')
        self.youtubeOutput = self.output.replace(fileExtension, '.youtube.mp4')

#         if not self.logger.isEnabledFor(logging.DEBUG):
        # Generate images for each audio file
        self.imagify()

        # Generate image for social media
        self.visualTeaser()

        # Make the audio track
        self.concatAudioFiles()

#         self.makeDescriptions()

        # Merge audio and chapters into one final M4A media file
        self.extendedPodcast()

        # Write HTML file with full description
        #self.toHTML()

        # Write textual description optimized for YouTube
        if self.youtubeID == None and self.ytCred:
            self.toYouTube()
        else:
            # youtubeID probably already set by --youtube-id THE_ID
            pass

        self.toWordPress()

        # Remove temporary files
        self.clean()

    def clean(self):
        try:
            for f in self.files:
                if 'image' in f:
                    os.remove(f['image'])
                if 'artworkFile' in f and not f['artworkFile'].endswith(self.missingArtwork):
                    os.remove(f['artworkFile'])
        except AttributeError:
            pass

        try:
            for f in self.images:
                os.remove(self.images[f])
        except AttributeError:
            pass

    #### End of methods for orchestration




    #### Methods for gathering data
    
    def musicInfo(self, f):
        """
        Use mutagen to extract various media file tags, including cover art, and store it
        in a comprehensive dict.
        """
        info = {}
        audio = mutagen.File(f, easy=True)
    
        info['theLength']=audio.info.length
        info.update(audio)
    
        # Now get only cover art and composer
        audio = mutagen.File(f, easy=False)
        
        k = audio.keys()
        
        currtag=u'\xa9wrt'
        if currtag in k:
            info['composer']=audio[currtag]
            
        currtag='----:com.apple.iTunes:writer'
        if currtag in k:
            info['composer']=[]
            for i in range(len(audio[currtag])):
                info['composer'].append(audio[currtag][i].decode('UTF-8'))
                
        currtag=u'TXXX:Writer'
        if currtag in k:
            # Handle multiple artists on MP3
            info['composer']=audio[currtag].text[0].split("/")
            if 'composer' in info:
                info['composer'] = info['composer'][0].split("/")

        currtag='----:com.apple.iTunes:MusicBrainz Release Track Id'
        if currtag in k:
            info['musicbrainz_releasetrackid']=[]
            for i in range(len(audio[currtag])):
                info['musicbrainz_releasetrackid'].append(audio[currtag][i].decode('UTF-8'))

        currtag=u'TXXX:MusicBrainz Release Track Id'
        if currtag in k:
            info['musicbrainz_releasetrackid']=audio[currtag].text

        currtag='----:com.apple.iTunes:MusicBrainz Work Id'
        if currtag in k:
            info['musicbrainz_workid']=[]
            for i in range(len(audio[currtag])):
                info['musicbrainz_workid'].append(audio[currtag][i].decode('UTF-8'))

        currtag='----:com.apple.iTunes:WORK'
        if currtag in k:
            info['work']=[]
            for i in range(len(audio[currtag])):
                info['work'].append(audio[currtag][i].decode('UTF-8'))

        currtag='----:com.apple.iTunes:ARTISTS'
        if currtag in k:
            info['artists']=[]
            for i in range(len(audio[currtag])):
                info['artists'].append(audio[currtag][i].decode('UTF-8'))

        currtag=u'TXXX:Artists'
        if currtag in k:
            # Handle multiple artists on MP3
            info['artists']=audio[currtag].text[0].split("/")
            if 'musicbrainz_artistid' in info:
                info['musicbrainz_artistid'] = info['musicbrainz_artistid'][0].split("/")

#         if self.logger.isEnabledFor(logging.DEBUG):
#             # delete artwork for better debugging
#             if 'covr' in k:
#                 del audio['covr']
#             elif u'APIC:' in k:
#                 del audio['APIC:']
#         else:
            # if not debug mode, process cover art
        if 'covr' in k:
            info['artwork']=audio['covr'][0]
        elif u'APIC:' in k:
            info['artwork']=audio['APIC:'].data

        self.logger.debug('file: %s', json.dumps({k: info[k] for k in info.keys() if k not in ('artwork')}))
    
        return info

    def add(self, name):
        f = {'file': name}
        f.update(self.musicInfo(name))
        
        self.length += f['theLength']
        
        # Prepare list of artists for excerpt and MP4 tag
        if 'artists' in f:
            for a in range(len(f['artists'])):
                self.artists.append(f['artists'][a])
        else:
            self.artists.append(f['artist'][0])
        
        self.files.append(f)
    
    #### End of methods for gathering data




    #### Methods for content generation and manipulation
    
    def safeFileName(self, s):
        safe = s
        safe = safe.replace('•','-')
        safe = safe.replace('|','-')
        safe = safe.replace('/','-')
        safe = safe.replace('\\','-')
        safe = safe.replace("""'""","")
        safe = safe.replace("""“""","")
        safe = safe.replace("""”""","")
        safe = safe.replace("""‘""","")
        safe = safe.replace("""’""","")
        safe = safe.replace("""«""","")
        safe = safe.replace("""»""","")
        safe = safe.replace("""#""","")
        return unidecode(safe)
    
    def removeHTML(self, s):
        # Remove HTML
        transformed = re.sub(r'<[^>]+>','', s)
        
        # Remove WordPress shortcodes
        transformed = re.sub(r'\[iframe[^\]]+\]','', transformed)
        
        return transformed

    def templateSVGtoJPG(self, svgid, w, h, data={}):
        empty = ""
        theData = {
            'TITLE': empty,
            'NO': empty,
            'EPISODEURL': empty,
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

        self.logger.debug('templateSVGtoJPG: %s', str(theData))

#         pprint.pprint(theData)
#         return

#       chapTemplate="{}/{}".format(os.path.dirname(sys.argv[0]),self.chapterTemplate)
        chapTemplate=self.podcastArtwork
        with open(chapTemplate, 'r') as myfile:
            template=myfile.read()    

        template = template.format(**theData)
        
        # self.logger.debug('Template data sample: ...{}...'.format(template[1000:1200]))

        # SVG data is ready in memory, now write SVG file
        theTemplate = tempfile.NamedTemporaryFile(
            suffix='.{}.svg'.format(svgid),
            dir='.',
            encoding=self.targetEncoding,
            mode='w+',
            delete=False
        )
        theTemplate.write(template)
        theTemplate.close()

        # Generate PNG from SVG
        thePresentation = tempfile.mkstemp(suffix='.png')
        os.close(thePresentation[0])

        FNULL = open(os.devnull, 'w+')

        inkscapeCall=[
            "inkscape",
            "--export-id={}".format(svgid),
            "-w", str(w),
            "-h", str(h),
            "-o", thePresentation[1],
            theTemplate.name
        ]

        self.logger.debug('Call Inkscape as: %s', str(inkscapeCall))

        subprocess.call(
            inkscapeCall,
            stdin=FNULL,
            stdout=FNULL,
            stderr=FNULL
        )
        
        FNULL.close()

        os.remove(theTemplate.name)       # remove temporary SVG

        # Convert PNG to JPG
        thePresentationJPG=tempfile.mkstemp(suffix='.jpg', dir='.')
        os.close(thePresentationJPG[0])

        im = Image.open(thePresentation[1]).convert(mode='RGB')
        im.save(thePresentationJPG[1], quality=85, optimize=True)

        os.remove(thePresentation[1])   # remove temporary PNG
    
        return thePresentationJPG[1]


    def prettySongLength(self,seconds,template="{minutes}:{seconds}"):
        """
        Convert a song duration in seconds, such as 325.432, into human friendly format
        as 5:25 or 5m25s.
        """
        
        minutes=math.floor(seconds//60)
        sec=math.floor(seconds%60)
        
        return template.format(minutes=minutes,seconds=sec)     


    def songCompleteName(self, song):
        albumYear=" ({:.4})"
        template="{artist} ♬ {title} [{l}]"

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
            artist = song['artist'][0],
            album = song['album'][0],
            title = song['title'][0] + albumYear,
            l = l
        )

        return name

    def imagify(self):
        self.logger.info("Create images for each podcast chapter...")

        # Extract artwork from every audio file
        for i in range(len(self.files)):
            theArtwork = []

            if 'artwork' in self.files[i]:
                # overwrite theArtwork tuple if file has artwork
                theArtwork=tempfile.mkstemp(dir='.',suffix=".jpg")
                os.write(theArtwork[0], self.files[i]['artwork'])
                os.close(theArtwork[0])
                self.files[i]['artworkFile'] = theArtwork[1]
            else:
                self.files[i]['artworkFile'] = self.missingArtworkFullPath


        data = {
            'TITLE': self.title,
            'EPISODEURL': self.getWordPressURL() + self.getSlug(),
            'NO': self.episode
        }

        # Episode cover picture to be used in media file Wordpress thumbnail
        self.images = {}
        self.images['cover']=self.templateSVGtoJPG(
            'episode',
            self.artwork['episode']['width'],
            self.artwork['episode']['height'],
            data
        )

        # build GPAC's NHML sequence of images for video
        cursor=0 # milliseconds
        if self.introDuration > 0:
            self.logger.debug('About to make Intro image')

            self.images['intro']=self.templateSVGtoJPG(
                "intro",
                self.artwork['DEFAULT']['width'],
                self.artwork['DEFAULT']['height'],
                data
            )

            self.chapterInfo += self.timedTextChapter(cursor/1000, "Introduction")

            self.chapterImagesInfo += """<NHNTSample DTS="{cursor}" mediaFile="{file}" isRAP="yes" />\n""".format(
                cursor=int(cursor),
                file=self.images['intro']
            )

            cursor += self.introDuration


        for i in range(len(self.files)):
            self.logger.debug('About to make image for %s', self.files[i]['title'][0])

            data = {}

            albumYear=""
            if 'date' in self.files[i]:
                albumYear = " ({:.4})".format(self.files[i]['date'][0])

            if i > 0:
                data['PREV_VISIBILITY']="visible"
                data['PREV_NAME']=self.files[i-1]['title'][0].replace('&',"&#38;")
                data['PREV_ARTIST']=self.files[i-1]['artist'][0].replace('&',"&#38;")
                data['PREV_COVER_ART_PATH']=self.files[i-1]['artworkFile']
            else:
                data['PREV_VISIBILITY']="none"
                data['PREV_NAME']=data['PREV_ARTIST']=data['PREV_COVER_ART_PATH']="whatever"

            if i < len(self.files)-1:
                data['NEXT_VISIBILITY']="visible"
                data['NEXT_NAME']=self.files[i+1]['title'][0].replace('&',"&#38;")
                data['NEXT_ARTIST']=self.files[i+1]['artist'][0].replace('&',"&#38;")
                data['NEXT_COVER_ART_PATH']=self.files[i+1]['artworkFile']
            else:
                data['NEXT_VISIBILITY']="none"
                data['NEXT_NAME']=data['NEXT_ARTIST']=data['NEXT_COVER_ART_PATH']="whatever"

            data['NAME']=self.files[i]['title'][0].replace('&',"&#38;")
            data['ARTIST']=self.files[i]['artist'][0].replace('&',"&#38;")
            data['ALBUM']=self.files[i]['album'][0].replace('&',"&#38;") + albumYear
            data['COVER_ART_PATH']=self.files[i]['artworkFile']

            data['COMPOSER']=""
            if 'composer' in self.files[i]:
                data['COMPOSER']=", ".join(self.files[i]['composer']).replace('&',"&#38;")


            self.files[i]['image'] = self.templateSVGtoJPG(
                "chapter",
                self.artwork['DEFAULT']['width'],
                self.artwork['DEFAULT']['height'],
                data
            )

            self.chapterInfo += self.timedTextChapter(cursor/1000, self.songCompleteName(self.files[i]))

            self.chapterImagesInfo += """<NHNTSample DTS="{cursor}" mediaFile="{file}" isRAP="yes" />\n""".format(
                cursor=cursor,
                file=self.files[i]['image']
            )

            cursor += 1000 * self.files[i]['theLength']
            i += 1

        # Add image for credits...
        self.images['credits'] = self.templateSVGtoJPG(
            "credits",
            self.artwork['DEFAULT']['width'],
            self.artwork['DEFAULT']['height'],
            data
        )

        self.chapterInfo += self.timedTextChapter(cursor/1000, "Credits")

        self.chapterImagesInfo += """<NHNTSample DTS="{cursor}" mediaFile="{file}" isRAP="yes" />\n""".format(
            cursor=cursor,
            file=self.images['credits']
        )

        cursor += self.introDuration


        self.images['end']     = self.templateSVGtoJPG(
            "end",
            self.artwork['DEFAULT']['width'],
            self.artwork['DEFAULT']['height'],
            data
        )

        self.chapterInfo += self.timedTextChapter(cursor/1000, None)

        self.chapterImagesInfo += """<NHNTSample DTS="{cursor}" duration="{dur}" mediaFile="{file}" isRAP="yes" />\n""".format(
            cursor=cursor,
            file=self.images['end'],
            dur=1000
        )
        
        self.chapterInfo += """</TextStream>\n"""
        self.chapterImagesInfo += """</NHNTStream>\n"""



    def visualTeaser(self):
        # Use the Intro image as social media teaser
        copyfile(self.images['cover'],self.teaser)



    def visualTeaserGIF(self):
        imageList = []
        
        masterHeight = 1080
        masterWidth  = 0
        
        # Open all images
        for i in range(len(self.files)):
            if 'artwork' in self.files[i] and self.files[i]['artworkFile'] == self.missingArtworkFullPath:
                currentImage = Image.open(self.files[i]['artworkFile'])
                masterWidth += currentImage.size[0] * masterHeight/float(currentImage.size[1])
                imageList.append(currentImage)
        
        masterImage=Image.new('RGB', (2*masterWidth,masterHeight))

        # Concatenate resized images in a single long image
        xOffset=0
        for currentImage in imageList:
            newWidth=currentImage.size[0] * masterHeight/float(currentImage.size[1])
            masterImage.paste(
                currentImage.resize((newWidth, masterHeight), Image.ANTIALIAS),
                (xOffset,0)
            )
            xOffset += newWidth

        masterImage.paste(masterImage, (xOffset,0))
        
        teaserIndex = 0
        for x in range(xOffset-1920,80):
            masterImage.crop((
                x,      0,
                x+1920, 1080
            )).save("teaser-")



    def makeDescriptions(self):
        
#       templateProcessor.filters['formatArtistsHTML']=self.secureFileName


        self.logger.debug("Load HTML page template from " + self.descriptionHTML)

        self.textDescription =     templateProcessor.get_template(self.description).render(dataset=self)
        self.htmlDescription =     templateProcessor.get_template(self.descriptionHTML).render(dataset=self)
        self.textExcerpt =         templateProcessor.get_template(self.excerpt).render(dataset=self)
        self.youtubeDescription = ""
        
        self.logger.debug(self.excerpt)



    def concatSampleAudioFiles(self):
        coder=[
            "-y",
            "-filter_complex",
            "concat=n={number_of_songs}:v=0:a=1 [out]".format(
                number_of_songs=len(self.files)
            ),
            "-map", "[out]",
            "-vn",
            "-c:a", "libfdk_aac", "-vbr", "3",
            "-map_metadata", "-1",
        ]


        params = []
    
        for f in self.files:
            params.append("-ss")
            params.append(f['theLength']/2000-3)
            params.append("-t")
            params.append("00:00:05")
            params.append("-i")
            params.append(f['file'])

        subprocess.call(
            ["ffmpeg"] +
            params +
            coder +
            [self.output]
        )

    def concatAudioFiles(self):
        self.logger.info("Build audio track as concatenation of input files...")
    
        ffmpegCompressor = "aac"
        coder=[
            "-y",
            "-filter_complex",
            "concat=n={number_of_songs}:v=0:a=1 [out]".format(
                number_of_songs = len(self.files)
            ),
            "-map", "[out]",
            "-vn",
#            "-c:a", "libfdk_aac", "-vbr", "4",  # best option
            "-c:a", "aac", "-b:a", "160k",       # use if libfdk_aac not avaialble in ffmpeg
            "-map_metadata", "-1",
        ]

        params = []
    
        for f in self.files:
            params.append("-i")
            params.append(f['file'])

#         # Add hardcoded silence (introDuration + 1000 ms) to the end of audio so audio
#         # remains until the end of credit images.
#         params.append("-f")
#         params.append("lavfi")
#         params.append("-t")
#         params.append(str(datetime.timedelta(seconds=self.introDuration/1000 + 1)))
#         params.append("-i")
#         params.append("anullsrc=channel_layout=2:sample_rate=44100")

        FNULL = open(os.devnull, 'w+')
        subprocess.call(
            ["ffmpeg"] +
            params +
            coder +
            [self.output],
            stdin=FNULL,
            stdout=FNULL,
            stderr=FNULL
        )
        
        FNULL.close()

    def ffmetadataChapter(self,song):
        # unused, obsolete
        timeScale=1000000
        template="[CHAPTER]\nTIMEBASE=1/{scale}\nSTART={start}\nEND={end}\ntitle={title}\n"

        return template.format(
            scale=timeScale,
            start=int(timeScale*self.length),
            end=int(timeScale*self.length + song['theLength']),
            title=self.songCompleteName(song)
        )

    def timedTextChapter(self, seconds, title):
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        h = int(h)
        m = int(m)

        template="""<TextSample sampleTime="{time}" xml:space="preserve">{title}</TextSample>\n"""
        
        return template.format(
            time="{:02d}:{:02d}:{:06.3f}".format(h, m, s),
            title=title
        )

    def extendedPodcast(self):
        self.logger.info("Tag for extended podcast...")
        
        nhml = tempfile.NamedTemporaryFile(suffix='.nhml', dir='.', encoding=self.targetEncoding, mode='w+t', delete=False)
        nhml.write(self.chapterImagesInfo)
        nhml.close()
        
        chap = tempfile.NamedTemporaryFile(suffix='.ttxt', dir='.', encoding=self.targetEncoding, mode='w+t', delete=False)
        chap.write(self.chapterInfo)
        chap.close()

        # Mux everything together
        subprocess.call([
            "MP4Box",
            # audio file (generated on concatAudioFiles())
            self.output,
            # images and NHML index (generated on imagify())
            "-add", "{file}:name=Chapter Images".format(file=nhml.name),
            # chapter points (generated on imagify())
            "-add", "{file}:chap:name=Chapter Titles".format(file=chap.name),
            # add a delay to track 1 (audio) to compensate the cover image
            "-delay", "1={}".format(self.introDuration)
        ])
        
        os.remove(nhml.name)
        os.remove(chap.name)
        
        if not self.nhml:
            self.logger.info("Converting optimal NHML media into a 2 frames per second video...")
            fps2 = tempfile.NamedTemporaryFile(
                suffix     = '.' + self.formats[self.mediaFormat]['extension'],
                dir        = '.',
                encoding   = self.targetEncoding,
                mode       = 'w+t',
                delete     = False
            )
            
            FNULL = open(os.devnull, 'w+')
            subprocess.call(
                [
                    "ffmpeg", "-y",
                    "-i", self.output,
                    "-c:v", "libx264", "-tune", "stillimage", "-vf", "fps=2", # video filters
                    "-c:a", "copy", # audio processing: just copy source
                    fps2.name
                ],
                stdin=FNULL,
                stdout=FNULL,
                stderr=FNULL
            )

            FNULL.close()
        
            os.replace(fps2.name, self.output)
            
        description=self.templateProcessor.get_template(self.description).render(dataset=self)

        # Properly tag it
        subprocess.call([
            "mp4tags",
            "-H", "1",
            "-X", "clean",
            "-i", "podcast",
            "-B", "1",
            "-M", str(self.episode),
            "-E", "https://github.com/avibrazil/music-podcaster",
            "-e", "Avi Alkalay using https://github.com/avibrazil/music-podcaster",
            "-C", "Copyright by its holders",
            "-a", ' | '.join(self.artists),
            "-s", self.title,
            "-A", self.podcast,
            "-l", description,
            "-m", description,
            self.output
        ])

        # Add cover art
        subprocess.call([
            "mp4art",
            "-z",
            "--add", self.images['cover'],
            self.output
        ])
        
        self.byteSize = os.path.getsize(self.output)


    def youtubefy(self):
        # YouTube has problems with extended podcasts. Re-encode video for submission.
        
        self.logger.info("Optimizing media for YouTube...")
        
#         FNULL = open(os.devnull, 'w+')
#         subprocess.call(
#             [
#                 "ffmpeg", "-y",
#                 "-i", self.output,
#                 "-c:v", "libx264", "-tune", "stillimage", "-vf", "fps=2", # video filters
#                 "-c:a", "copy", # audio processing: just copy source
#                 self.youtubeOutput
#             ],
#             stdin=FNULL,
#             stdout=FNULL,
#             stderr=FNULL
#         )
# 
#         FNULL.close()


    #### End of methods for content generation and manipulation




    #### Methods for publishing (text, YouTube, WordPress)

    def wpAddTerm(self, slug, name):
        term = None
        for t in self.wpCategories:
            if t.slug == slug:
                term = t
                break
        
        self.logger.debug('Operating on %s (%s)', name, slug)
        
        if term:
            self.logger.debug('Using existing term %s', term.name)
        else:
            term = WordPressTerm()
            term.taxonomy = 'post_tag'
            term.name = name
            term.slug = slug
            term.id = self.wp.call(taxonomies.NewTerm(term))
            
            self.wpCategories.append(term)

            self.logger.debug('Creating term %s', term.name)
                    
        return term

    def getSlug(self):
        if not hasattr(self,'slug'):
           self.slug='e{:04d}'.format(int(self.episode))

        return self.slug
    
    def getWordPressURL(self):
        url = self.wordpress.replace('xmlrpc.php', '')
        # self.logger.debug('WordPress URL:  %s', url)

        return url


    def handleWordpressSubstitutions(self,text):
        if hasattr(self,'wordpressSubstitutions') and isinstance(self.wordpressSubstitutions,list):
            if not hasattr(self,'_wordpressSubstitutions'):
                # prepare and wuote target strings
                self._wordpressSubstitutions=[
                    (x[0],html.escape(x[1]))
                    for x in self.wordpressSubstitutions
                ]
            
            t=text
            for sub in self._wordpressSubstitutions:
                t=t.replace(sub[0],sub[1])
            
            return t
        return text
            

    def toWordPress(self):
        self.wp = Client(self.wordpress, self.wordpressUser, self.wordpressPass)
        
        self.wpCategories = self.wp.call(taxonomies.GetTerms('post_tag'))



        # Upload podcast media
        self.metamedia = dict(
            title     = '{i:04d} {title}'.format(i=int(self.episode), title=self.title),
            name      =  self.output,
            type      =  self.formats[self.mediaFormat]['mimetype'],
            overwrite = 1
        )

        with open(self.output, 'rb') as themedia:
            # XML-RPC is a weak protocol to send such a big file, so send only 10 bytes
            # just to get the media URL. Then send the real file by SCP later.
            # metamedia['bits'] = xmlrpc_client.Binary(themedia.read())    
            self.metamedia['bits'] = xmlrpc_client.Binary(bytearray(10)) #dummy placeholder

        self.logger.info('Upload media to WordPress...')
        self.metamedia.update(self.wp.call(media.UploadFile(self.metamedia)))

        # self.logger.info(metamedia)

        subprocess.call([
            "scp",
            self.output,
            os.path.join(self.serverFolder, os.path.basename(self.metamedia['url']))
        ])
        
        # Upload post thumbnail
        self.metathumb = dict(
            title     = self.handleWordpressSubstitutions(
                '{i:04d} {title}'.format(i=int(self.episode), title=self.title)
            ),
            name      = self.teaser,
            type      = 'image/jpeg',  # mimetype
            overwrite = 1
        )

        with open(self.teaser, 'rb') as thethumb:
            self.metathumb['bits'] = xmlrpc_client.Binary(thethumb.read())

        self.logger.info('Upload thumb to WordPress...')
        self.metathumb.update(self.wp.call(media.UploadFile(self.metathumb)))



        # Create post for WordPress
        self.logger.info('Create WordPress post...')
        post = WordPressPost()
        post.title = self.handleWordpressSubstitutions(
            '{title}'.format(i=int(self.episode), title=self.title)
        )
        if self.date:
            post.date = self.date
#             theyear = self.date.year()
#         else:
#             theyear = datetime.datetime.now().year
        post.slug = self.getSlug()
        post.comment_status = 'open'
        post.content = self.handleWordpressSubstitutions(
            self.templateProcessor.get_template(self.descriptionHTML).render(dataset=self)
        )
        post.thumbnail = self.metathumb['id']
        post.custom_fields = []
        post.excerpt = self.templateProcessor.get_template(self.excerpt).render(dataset=self)
        post.custom_fields.append(dict(
            key = 'enclosure',
            value = """{url}\n{bytesize}\n{mimetype}\na:2:{{s:8:"duration";s:8:"{duration}";s:10:"episode_no";s:4:"{episode}";}}""".format(
                url = self.handleWordpressSubstitutions(self.metamedia['url']),
                mimetype = self.formats[self.mediaFormat]['mimetype'],
                bytesize = self.byteSize,
                duration = "{:0>8}".format(str(datetime.timedelta(seconds=math.floor(self.length)))),
                episode = '{:04d}'.format(int(self.episode))
            )
        ))

        # GUID can't be set. Wish I could set it like this:
        # post.guid = self.getWordPressURL() + self.getSlug()

        if self.wordpressDraft is False:
            post.post_status = 'publish'

        # Tag the post with artists in media
        self.logger.info('Tag WordPress post...')
        for song in self.files:
            if 'artists' in song:
                for a in range(len(song['artists'])):
                    self.logger.debug('Going to add new artist %s from %s',
                        a,
                        song['musicbrainz_artistid']
                    )

                    post.terms.append(self.wpAddTerm(
                        song['musicbrainz_artistid'][a],
                        song['artists'][a]
                    ))
            else:
                post.terms.append(self.wpAddTerm(
                    song['musicbrainz_artistid'][0],
                    song['artist'][0]
                ))

        # Post it
        post.id = self.wp.call(posts.NewPost(post))

        # Update media post just to make things tighter and look nicer
        self.logger.info('Update WordPress media and attach to post...')
        self.metamedia = self.wp.call(posts.GetPost(self.metamedia['id']))
        self.metamedia.parent_id = post.id
        self.metamedia.title = self.title + " :: media"
        self.metamedia.slug = self.getSlug() + ".media"
        self.metamedia.content = """Podcast media file for <a href="/{slug}">{title}</a>""".format(
            slug = self.getSlug(),
            title = self.title
        )

        self.wp.call(posts.EditPost(self.metamedia.id, self.metamedia))


        # Update thumbnail post just to make things tighter and look nicer
        self.logger.info('Update WordPress thumbnail and attach to post...')
        self.metathumb = self.wp.call(posts.GetPost(self.metathumb['id']))
        self.metathumb.parent_id = post.id
        self.metathumb.title = self.title + " :: thumbnail"
        self.metathumb.slug = self.getSlug() + ".thumbnail"
        self.metathumb.content = """Thumbnail for <a href="/{slug}">{title}</a>""".format(
            slug = self.getSlug(),
            title = self.title
        )

        self.wp.call(posts.EditPost(self.metathumb.id, self.metathumb))



    def toYouTube(self):
        self.logger.info("Send media to YouTube...")

        ytfile = os.path.splitext(self.output)[0] + ".youtube.txt"
        yt = open(ytfile, mode='wt')
        yt.write(Template(self.youtubeDescription).safe_substitute(
            youtubeid    = self.youtubeID,
            youtubelist  = self.ytPLid,
            episodeurl   = self.getWordPressURL() + self.getSlug(),
        ))

        yt.close()

        command = [
            self.ytupload,
            "-c",                                      'Music',
            "-t",                                      "{title} « {podcast}".format(
                                                            title=self.title,
                                                            podcast=self.podcast
                                                        ),
            "--description-file",                       ytfile,
            "--playlist",                               self.ytPL,
            "--thumbnail",                              self.images['intro'],
            "--client-secrets",                         self.ytSecrets,
            "--credentials-file",                       self.ytCred,
            "--default-language",                       "en",
            "--default-audio-language",                 "pt"
           #"--tags={}".format("a"),
           #"--privacy=unlisted",
        ]

        if self.date:
            command.append("--recording-date")
            command.append(self.date.isoformat(timespec='microseconds').replace("+00:00", "Z"))

        command.append(self.youtubeOutput)

        if self.youtubeDebug:
            # Print the command and work with fake data
            self.logger.info(" ".join(command))
            self.youtubeID="CcJEgvs7Ovo"
        else:
            # Do the actual work with YouTube

            # Optimize media file for YouTube
            self.youtubefy()

            # Upload to YouTube
            self.youtubeID=subprocess.check_output(command)
            self.youtubeID=self.youtubeID.decode().rstrip() # bytes to string



    def toHTML(self):
        html = open(os.path.splitext(self.output)[0] + ".html", mode='wt')
        html.write(self.htmlDescription)
        html.close()
        
        cat=[]
        for song in self.files:
            if 'artists' in song:
                cat += song['artists']
            else:
                cat += song['artist']

        # remove duplicates
        cat=list(set(cat))
#         cat.sort()   # Unicode error

        categories = open(os.path.splitext(self.output)[0] + ".tags.txt", mode='wt')
        # os.write("\n".join(t))

        self.logger.debug('Tags: %s', json.dumps(cat))

        for a in cat:
            categories.write("{}\n".format(a))
        categories.close()

    #### End of methods for publishing (text, YouTube, WordPress)



def main():
    podcast = Podcast(logger=logging.DEBUG)
#     podcast = Podcast(logger=logging.INFO)

    parser = argparse.ArgumentParser(
        description='Create extended podcast from well tagged audio files',
        fromfile_prefix_chars='@'
    )

    parser.add_argument('-p', dest='podcast',
        help='podcast global name')

    parser.add_argument('-t', dest='title', default="",
        help='title for podcast')

    parser.add_argument('-i', dest='episode', default="",
        help='episode number')

    parser.add_argument('-f', dest='mediaFormat', default="video",
        help='Should be "audio" or "video". Defaults to "video".')

    parser.add_argument('-o', dest='output',
        help='output file name (defaults to "{podcast name} - {episode} - {title}.m4a)"')

    parser.add_argument('-m', dest='missingArtwork', default="MissingArtworkMusic.png",
        help='image to use in case audio file doesn’t have embeded arwork')
    
    parser.add_argument('-a', dest='podcastArtwork', default="artwork.svg",
        help='SVG file containing IDs "intro", "chapter", "credits", "end", "episode" that will be used to generate various podcast artwork')



    parser.add_argument('--description-template-html', dest='descriptionHTML', type=str,
        default='description.thtml', help="Jinja HTML template for podcast description")
    
    parser.add_argument('--description-template', dest='description', type=str,
        default='description.ttxt', help="Jinja template for podcast description embedded in media file")
    
    parser.add_argument('--excerpt-template', dest='excerpt', type=str,
        default='excerpt.ttxt', help="Jinja plain text template for post excerpt")




    parser.add_argument('--description-head', dest='descriptionHead', type=open,
        default=None, help="HTML template for description, before description prefix")
    
    parser.add_argument('--description-prefix', dest='descriptionPrefix', type=open,
        default=None, help="HTML template for description, before track list")
    
    parser.add_argument('--description-tracklist', dest='descriptionTracklist', type=open,
        default=None, help="HTML template for tracklist")
    
    parser.add_argument('--description-suffix', dest='descriptionSuffix', type=open,
        default=None, help="HTML template for description, after track list")




    parser.add_argument('--intro', dest='introDuration', type=int, default="3000",
        help="Duration in miliseconds for introduction image")

    parser.add_argument('--date', dest='date', default=None,
        help="""Date and time for post. Example: 2017-03-02 12:43 or simply 2017-03-02""")

    parser.add_argument('--server-folder', dest='serverFolder',
        help="""SSH/SCP/SFTP notation for server folder, as host.name.com:folder1/folder2/ (workaround while WordPress XML-RPC upload fails with large files)""")

    parser.add_argument('--wordpress-substitutions', dest='wordpressSubstitutions',
        action='append', nargs='+',
        help="""For WordPress post text only, substitute text from first argument with the text (shortcode?) from the second argument""")

    parser.add_argument('--wordpress-url', dest='wordpress',
        help="""WordPress URL, preferably ending with ‘/xmlrpc.php’""")

    parser.add_argument('--wordpress-user', dest='wordpressUser',
        help="""WordPress username""")

    parser.add_argument('--wordpress-pass', dest='wordpressPass',
        help="""WordPress password""")

    parser.add_argument('--draft', dest='wordpressDraft', action=argparse.BooleanOptionalAction,
        default=False, help="Keep post in draft mode")
        
    parser.add_argument('--nhml', dest='nhml', action=argparse.BooleanOptionalAction,
        default=False, help="Leave media as optimal NHML (True) or convert it into efficient (but still bigger) 2 FPS video")
    
        
    
    # Youtube support is being abandoned

    parser.add_argument('--youtube-upload-credentials', dest='ytCred',
        help="""YouTube credentials JSON file""")

    parser.add_argument('--youtube-upload-client-secrets', dest='ytSecrets',
        help="""YouTube client secrets JSON file""")

    parser.add_argument('--youtube-playlist', dest='ytPL',
        help="""YouTube playlist name""")

    parser.add_argument('--youtube-playlist-id', dest='ytPLid',
        help="""YouTube playlist id""")

    parser.add_argument('--youtube-debug', dest='youtubeDebug', action='store_true',
        help="""Do everything related to YouTube preparation but do not upload""")

    parser.add_argument('--youtube-id', dest='youtubeID',
        help="""Do not upload for YouTube, use this video ID instead.""")

    parser.add_argument('f', type=str, nargs='+',
        help='music files to be added to podcast')

    args = parser.parse_args(namespace=podcast)
    
    for f in podcast.f:
        podcast.add(f)

    podcast.make()


__name__ == '__main__' and main()

