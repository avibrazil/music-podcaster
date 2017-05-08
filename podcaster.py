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

import argparse
import mutagen
import pprint
import tempfile
import subprocess
import json
import unicodedata
from unidecode import unidecode
import re
import datetime
import logging
from PIL import Image
import os
import math
import sys
from string import Template


from wordpress_xmlrpc import Client, WordPressPost, WordPressTerm
from wordpress_xmlrpc.methods import media, posts, taxonomies
from wordpress_xmlrpc.compat import xmlrpc_client



class Podcast:

    #### Methods for orchestration

    def __init__ (self, logger=logging.ERROR):
        self.ytupload = "/home/aviram/src/youtube-upload/bin/youtube-upload"
        self.audio = None
        self.length = 0
        self.files = []
        self.chapterImagesInfo = """<?xml version="1.0" encoding="UTF-8" ?>
            <NHNTStream version="1.0" timeScale="1000"
            mediaType="vide" mediaSubType="jpeg" width="1280" height="720"
            codecVendor="....">"""
        self.chapterInfo = """<?xml version="1.0" encoding="UTF-8" ?>
            <TextStream version="1.1">
                <TextStreamHeader><TextSampleDescription/>
                </TextStreamHeader>"""
        
        self.targetEncoding = 'UTF-8'
        
        logging.basicConfig()
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logger)
        
        self.logger.info("Get media info...")

    def make(self):
        # Compute output file name
        if (self.output == None):
            if self.podcast:                 self.output = self.podcast
            if self.output and self.episode: self.output += "-"
            if self.episode:                 self.output += '{:04d}'.format(int(self.episode))
            if self.output and self.title:   self.output += "-"
            if self.title:                   self.output += self.safeFileName(self.title)
            if self.output:
                self.output = self.output.replace(" ","_")
        
        if self.output == None:              self.output = "output"
        if not self.output.endswith('.m4a'): self.output += '.m4a'

        self.sampleOutput = self.output.replace('.m4a', '.sample.m4a')
        self.youtubeOutput = self.output.replace('.m4a', '.youtube.mp4')
        
        self.makeDescriptions()
        
        if not self.logger.isEnabledFor(logging.DEBUG):
            # Generate images for each audio file
            self.imagify()
        
            # Make the audio track
            self.concatAudioFiles()
        
            # Merge audio and chapters into one final M4A media file
            self.extendedPodcast()
        
            # Write HTML file with full description
            #self.toHTML()
        
            # Write textual description optimized for YouTube
            self.toYouTube()
        
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
        info = {}
        audio = mutagen.File(f, easy=True)
    
        info['theLength']=audio.info.length
        info.update(audio)
    
        # Now get only cover art and composer
        audio = mutagen.File(f, easy=False)
        
        k = audio.keys()
        if u'\xa9wrt' in k:
            info['composer']=audio[u'\xa9wrt']

        if '----:com.apple.iTunes:MusicBrainz Work Id' in k:
            info['musicbrainz_workid']=[]
            for i in range(len(audio['----:com.apple.iTunes:MusicBrainz Work Id'])):
                info['musicbrainz_workid'].append(
                    audio['----:com.apple.iTunes:MusicBrainz Work Id'][i].decode('UTF-8')
                )

        if '----:com.apple.iTunes:WORK' in k:
            info['work']=[]
            for i in range(len(audio['----:com.apple.iTunes:WORK'])):
                info['work'].append(
                    audio['----:com.apple.iTunes:WORK'][i].decode('UTF-8')
                )

        if '----:com.apple.iTunes:ARTISTS' in k:
            info['artists']=[]
            for i in range(len(audio['----:com.apple.iTunes:ARTISTS'])):
                info['artists'].append(
                    audio['----:com.apple.iTunes:ARTISTS'][i].decode('UTF-8')
                )

        if u'TXXX:Artists' in k:
            # Handle multiple artists on MP3
            info['artists']=audio[u'TXXX:Artists'].text[0].split("/")
            if 'musicbrainz_artistid' in info:
                info['musicbrainz_artistid'] = info['musicbrainz_artistid'][0].split("/")

        if self.logger.isEnabledFor(logging.DEBUG):
            # delete artwork for better debugging
            if 'covr' in k:
                del audio['covr']
            elif u'APIC:' in k:
                del audio['APIC:']
        else:
            # if not debug mode, process cover art
            if 'covr' in k:
                info['artwork']=audio['covr'][0]
            elif u'APIC:' in k:
                info['artwork']=audio['APIC:'].data

        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug('file: %s', json.dumps(info))
    
        return info

    def add(self, name):
        f = {'file': name}
        f.update(self.musicInfo(name))
        
        self.length += f['theLength']
        
        self.files.append(f)
    
    #### End of methods for gathering data




    #### Methods for content generation and manipulation
    
    def safeFileName(self, s):
        safe = s
        safe = safe.replace('•','-')
        safe = safe.replace('|','-')
        safe = safe.replace('/','-')
        safe = safe.replace('\\','-')
        return unidecode(safe)
    
    def removeHTML(self, s):
        return re.sub(r'<[^>]+>','', s)

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

        with open("{}/{}".format(os.path.dirname(sys.argv[0]),self.chapterTemplate), 'r') as myfile:
            template=myfile.read()    

        template = template.format(**theData)

        # SVG data is ready in memory, now write SVG file
        theTemplate = tempfile.NamedTemporaryFile(suffix='.svg', dir='.', encoding=self.targetEncoding, mode='w+t', delete=False)
        theTemplate.write(template)
        theTemplate.close()

        # Generate PNG from SVG
        thePresentation = tempfile.mkstemp(suffix='.png')
        os.close(thePresentation[0])

        FNULL = open(os.devnull, 'w+')
        subprocess.call(
            [
                "inkscape", "--without-gui",
                "--export-id={}".format(svgid),
                "-w", str(w),
                "-h", str(h),
                "-e", thePresentation[1], theTemplate.name
            ],
            stdin=FNULL,
            stdout=FNULL,
            stderr=FNULL
        )
        
        FNULL.close()

        os.remove(theTemplate.name)       # remove temporary SVG

        # Convert PNG to JPG
        thePresentationJPG=tempfile.mkstemp(suffix='.jpg', dir='.')
        os.close(thePresentationJPG[0])

        im = Image.open(thePresentation[1])
        im.save(thePresentationJPG[1], quality=85, optimize=True)

        os.remove(thePresentation[1])   # remove temporary PNG
    
        return thePresentationJPG[1]

    def songCompleteNameHTML(self, song):
#         self.logger.debug('songCompleteNameHTML: %s', json.dumps(song))

        composerTemplate="""<br/><span class="composer">Comp.: {composer}</span>"""
        albumTemplate="""<br/><span class="album">Album: {album}</span>"""
        template="""
            <span class="song">
                <span class="artists">{artist}</span>
                <span class="separator"> ♬ </span>
                <span class="title">{title}</span> <span class="duration">[{l}]</span>
                {composer}{album}
            </span>
        """
        albumYear=""" <span class="yearwrap">(<span class="year">{:.4}</span>)</span>"""

        
        # Compute song title
        try:
            title = """<a href="https://musicbrainz.org/recording/{id}">{title}</a>""".format(
                id = song['musicbrainz_trackid'][0],
                title = song['title'][0]
            )
        except KeyError:
            title = song['title'][0]

        
        # Compute artist name
        try:
            artist = song['artist'][0]
            if len(song['musicbrainz_artistid']) == 1:
                # Only 1 artist
                artist = """<a href="https://musicbrainz.org/artist/{mbid}">{artist}</a>""".format(
                    mbid = song['musicbrainz_artistid'][0],
                    artist = song['artist'][0]
                )
            else:
                # Multiple artists
                for i in range(len(song['musicbrainz_artistid'])):
                    # Attempt to replace each single artist by its single MB link
                    self.logger.debug('songCompleteNameHTML:replacing artist: %s', song['artists'][i])
                    artist = artist.replace(
                        song['artists'][i],
                        """<a href="https://musicbrainz.org/artist/{mbid}">{artist}</a>""".format(
                            artist = song['artists'][i],
                            mbid = song['musicbrainz_artistid'][i]
                        )
                    )
        except KeyError:
            artist = song['artist'][0]


        # Compute composer
        try:
            composer = ', '.join(song['composer'])
#             if 'musicbrainz_workid' in song:
#                 co=[]
#                 for i in range(len(song['composer'])):
#                     co.append("""<a href="https://musicbrainz.org/work/{id}">{comp}</a>""".format(
#                         id = str(song['musicbrainz_workid'][i]),
#                         comp = song['composer'][i].encode(self.targetEncoding)
#                     ))
#                 composer = ' • '.join(co)
            composer = composerTemplate.format(composer = composer)
        except KeyError:
            composer = ""


        # Compute album year
        try:
            albumYear = albumYear.format(song['date'][0])
        except KeyError:
            albumYear = ""
        

        # Compute album
        album = ""
        if 'album' in song:
            if 'musicbrainz_albumid' in song:
                album = """<a href="https://musicbrainz.org/release/{id}">{album}</a>""".format(
                    id = song['musicbrainz_albumid'][0],
                    album = song['album'][0] + albumYear
                )
            else:
                album = song['album'][0] + albumYear

            album = albumTemplate.format(album = album)

                    
        l = str(datetime.timedelta(seconds=math.floor(song['theLength'])))
        if song['theLength'] < 60*60:
            if song['theLength'] < 10*60:
                l=l[-4:]
            else:
                l=l[-5:]

        return template.format(
            artist = artist,
            album = album,
            composer = composer,
            title = title,
            l = l
        ).replace('\n', ' ')

    def songCompleteName(self, song):
        albumYear=" ({:.4})"
        template="{artist} ♫ {title} [{l}]"
        
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
                theArtwork=tempfile.mkstemp(dir='.')
                os.write(theArtwork[0], self.files[i]['artwork'])
                os.close(theArtwork[0])
                self.files[i]['artworkFile'] = theArtwork[1]
            else:
                self.files[i]['artworkFile'] = "{}/{}".format(
                    os.path.dirname(sys.argv[0]),
                    self.missingArtwork
                )


        # build GPAC's NHML sequence of images for video
        cursor=0 # milliseconds
        self.images = {}
        if self.introDuration > 0:
            self.logger.debug('About to make Intro image')

            data = {
                'TITLE': self.title,
                'EPISODEURL': self.getWordPressURL() + self.getSlug(),
                'NO': self.episode
            }
            
            self.images['intro']=self.templateSVGtoJPG("intro", 1280, 720, data)

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
                data['PREV_NAME']=self.files[i-1]['title'][0].replace('&',"&amp;")
                data['PREV_ARTIST']=self.files[i-1]['artist'][0].replace('&',"&amp;")
                data['PREV_COVER_ART_PATH']=self.files[i-1]['artworkFile']
            else:
                data['PREV_VISIBILITY']="none"
                data['PREV_NAME']=data['PREV_ARTIST']=data['PREV_COVER_ART_PATH']="whatever"
            
            if i < len(self.files)-1:
                data['NEXT_VISIBILITY']="visible"
                data['NEXT_NAME']=self.files[i+1]['title'][0].replace('&',"&amp;")
                data['NEXT_ARTIST']=self.files[i+1]['artist'][0].replace('&',"&amp;")
                data['NEXT_COVER_ART_PATH']=self.files[i+1]['artworkFile']
            else:
                data['NEXT_VISIBILITY']="none"
                data['NEXT_NAME']=data['NEXT_ARTIST']=data['NEXT_COVER_ART_PATH']="whatever"

            data['NAME']=self.files[i]['title'][0].replace('&',"&amp;")
            data['ARTIST']=self.files[i]['artist'][0].replace('&',"&amp;")
            data['ALBUM']=self.files[i]['album'][0].replace('&',"&amp;") + albumYear
            data['COVER_ART_PATH']=self.files[i]['artworkFile']

            data['COMPOSER']=""
            if 'composer' in self.files[i]:
                data['COMPOSER']=", ".join(self.files[i]['composer']).replace('&',"&amp;")
        

            self.files[i]['image'] = self.templateSVGtoJPG("chapter", 1280, 720, data)

            self.chapterInfo += self.timedTextChapter(cursor/1000, self.songCompleteName(self.files[i]))

            self.chapterImagesInfo += """<NHNTSample DTS="{cursor}" mediaFile="{file}" isRAP="yes" />\n""".format(
                cursor=cursor,
                file=self.files[i]['image']
            )

            cursor += 1000 * self.files[i]['theLength']
            i += 1
        
        # Add image for credits...
        self.images['credits'] = self.templateSVGtoJPG("credits", 1280, 720)
        
        self.chapterInfo += self.timedTextChapter(cursor/1000, "Credits")

        self.chapterImagesInfo += """<NHNTSample DTS="{cursor}" mediaFile="{file}" isRAP="yes" />\n""".format(
            cursor=cursor,
            file=self.images['credits']
        )
        
        cursor += self.introDuration
        

        self.images['end']     = self.templateSVGtoJPG("end", 1280, 720)

        self.chapterInfo += self.timedTextChapter(cursor/1000, None)

        self.chapterImagesInfo += """<NHNTSample DTS="{cursor}" duration="{dur}" mediaFile="{file}" isRAP="yes" />\n""".format(
            cursor=cursor,
            file=self.images['end'],
            dur=1000
        )
        
        self.chapterInfo += """</TextStream>\n"""
        self.chapterImagesInfo += """</NHNTStream>\n"""

    def makeDescriptions(self):
        self.description=""
        self.artist=""
        tracks=""
        htmlTracks=""
        youtubeTracks=""
        composers=""
        albums=""
        
        i=0
        pos=self.introDuration/1000
        self.logger.info("Build track textual content from media tags...")
        for song in self.files:
            i+=1
            name=self.songCompleteName(song)
            tracks += "{i:02}. {name}\n".format(
                i=i,
                name=name
            )

            htmlTracks += """\n<li class="track">{}</li>\n""".format(
                self.songCompleteNameHTML(song)
            )
            
            youtubeTracks += "{i:02}. [{pos}] {name}\n".format(
                i=i,
                name=name,
                # http://stackoverflow.com/a/31946730/367824
                pos = "{:0>8}".format(str(datetime.timedelta(seconds=math.floor(pos))))
            )
            pos += song['theLength']
            
            if 'composer' in song:
                composers += "{i:02}. {name}\n".format(
                    i=i,
                    name=', '.join(song['composer'])
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
                    album=', '.join(song['album']),
                    albumArtist=albumArtist,
                    year=albumYear
                )
            
            if (not self.title or self.title.endswith(" | ")):
                self.title += song['title'][0]
                self.title += " | "
        
            if self.artist: self.artist += " | "
            self.artist += song['artist'][0]

        if self.descriptionPrefix:
            self.descriptionPrefixText = self.descriptionPrefix.read()
        else:
            self.descriptionPrefixText=""
        
        if self.descriptionHead:
            self.descriptionHeadText = Template(
                self.descriptionHead.read()
            ).safe_substitute(youtubelist=self.ytPL)
        else:        
            self.descriptionHeadText=""
        
        if self.descriptionSuffix:
            self.descriptionSuffixText = Template(
                self.descriptionSuffix.read()
            ).safe_substitute(episodeurl=self.getWordPressURL() + self.getSlug())
        else:        
            self.descriptionSuffixText=""
        
        template="{head}{prefix}\n\nTRACK LIST\n{tracks}\n\nCOMPOSERS\n{composers}\n\nALBUMS\n{albums}\n{suffix}"
        htmlTemplate="""{head}{prefix}
        
            <div class="podcast-parts">
                <ol>
                    {tracks}
                </ol>
            </div>
            
            {suffix}"""
        
        self.description = template.format(
            head   = self.removeHTML(self.descriptionHeadText),
            prefix = self.removeHTML(self.descriptionPrefixText),
            tracks=tracks,
            composers=composers,
            albums=albums,
            suffix = self.removeHTML(self.descriptionSuffixText)
        ) 
        
        self.htmlDescription = htmlTemplate.format(
            prefix = self.descriptionPrefixText,
            tracks=htmlTracks,
            head   = self.descriptionHeadText,
            suffix = self.descriptionSuffixText
        )
        
        self.youtubeDescription = template.format(
            head   = self.removeHTML(self.descriptionHeadText),
            prefix = self.removeHTML(self.descriptionPrefixText),
            tracks=youtubeTracks,
            composers=composers,
            albums=albums,
            suffix = self.removeHTML(self.descriptionSuffixText)
        ) 
        
        if self.title.endswith(' | '): self.title = self.title[:-3]

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
    
    
        coder=[
            "-y",
            "-filter_complex",
            "concat=n={number_of_songs}:v=0:a=1 [out]".format(
                number_of_songs = len(self.files)
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

        # Properly tag it
        subprocess.call([
            "mp4tags",
            "-H", "1",
            "-X", "clean",
            "-i", "podcast",
            "-B", "1",
            "-M", str(self.episode),
            "-E", "https://github.com/avibrazil/music-podcaster",
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
        
        self.byteSize = os.path.getsize(self.output)

    def youtubefy(self):
        # YouTube has problems with extended podcasts. Re-encode video for submission.
        
        self.logger.info("Optimizing media for YouTube...")
        
        FNULL = open(os.devnull, 'w+')
        subprocess.call(
            [
                "ffmpeg", "-y",
                "-i", self.output,
                "-c:v", "libx264", "-tune", "stillimage", "-vf", "fps=2", # video filters
                "-c:a", "copy", # audio processing: just copy source
                self.youtubeOutput
            ],
            stdin=FNULL,
            stdout=FNULL,
            stderr=FNULL
        )

        FNULL.close()


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
        return 'e{:04d}'.format(int(self.episode))
    
    def getWordPressURL(self):
        url = self.wordpress.replace('xmlrpc.php', '')
        self.logger.debug('WordPress URL:  %s', url)

        return url

    def toWordPress(self):
        self.wp = Client(self.wordpress, self.wordpressUser, self.wordpressPass)
        
        self.wpCategories = self.wp.call(taxonomies.GetTerms('post_tag'))
        
        # Upload media
        metamedia = {
            'name': self.output,
            'type': 'audio/x-m4a',  # mimetype
        }

        with open(self.output, 'rb') as themedia:
#                 metamedia['bits'] = xmlrpc_client.Binary(themedia.read())
                metamedia['bits'] = xmlrpc_client.Binary(bytearray(10)) #dummy placeholder

        self.logger.info('Upload to WordPress...')
        metamedia.update(self.wp.call(media.UploadFile(metamedia)))
        subprocess.call([
            "scp",
            self.output,
            self.serverFolder
        ])
        
        # Create post for WordPress
        self.logger.info('Create WordPress post...')
        post = WordPressPost()
        post.title = '{title}'.format(i=int(self.episode), title=self.title)
        post.slug = self.getSlug()
        post.content = 	Template(self.htmlDescription).safe_substitute(
            youtubeid=self.youtubeID,
            mediaurl=metamedia['url']
        )
        post.custom_fields = []
        post.custom_fields.append({
            'key': 'enclosure',
            'value': """{url}\n{bytesize}\naudio/x-m4a\na:1:{{s:8:"duration";s:8:"{duration}";}}""".format(
                url = metamedia['url'],
                bytesize = self.byteSize,
                duration = "{:0>8}".format(str(datetime.timedelta(seconds=math.floor(self.length))))
            )
        })
        
        if self.wordpressDraft == False:
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
        metamedia = self.wp.call(posts.GetPost(metamedia['id']))
        metamedia.parent_id = post.id
        metamedia.title = self.title + " :: media"
        metamedia.slug = self.getSlug() + ".media"
        metamedia.content = """Podcast media file for <a href="/{slug}">{title}</a>""".format(
            slug = self.getSlug(),
            title = self.title
        )

        self.wp.call(posts.EditPost(metamedia.id, metamedia))
        
    def toYouTube(self):
        self.youtubefy()

        self.logger.info("Send media to YouTube...")

        yt = open(os.path.splitext(self.output)[0] + ".youtube.txt", mode='wt')
        yt.write(self.youtubeDescription)
        yt.close()
        
        self.youtubeID=subprocess.check_output([
            self.ytupload,
            "-c", 'Music',
            "-t", "{title} « {podcast}".format(
                index=int(self.episode),
                title=self.title,
                podcast=self.podcast
            ),
            "-d", self.youtubeDescription,
#            "--tags={}".format("a"),
            "--privacy=unlisted",
            "--playlist={}".format(self.ytPL),
            "--client-secrets=" + self.ytCred,
            "--thumbnail=" + self.images['intro'],
            self.youtubeOutput
        ])
        
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
#     p = Podcast(logger=logging.DEBUG)
    p = Podcast(logger=logging.INFO)

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

    parser.add_argument('-o', dest='output',
        help='output file name (defaults to "{podcast name} - {episode} - {title}.m4a)"')

    parser.add_argument('-c', dest='chapterTemplate', default="artwork.svg",
        help='SVG file to be used as template for each chapter image')

    parser.add_argument('-m', dest='missingArtwork', default="MissingArtworkMusic.png",
        help="image to use in case audio file doesn't have embeded arwork")
    
    parser.add_argument('-a', dest='podcastArtwork', default="PodcastArtwork.jpg",
        help="image to embed as artwork in final M4A podcast file")
    
    parser.add_argument('--description-head', dest='descriptionHead', type=open,
        default=None, help="HTML text for description, before description prefix")
    
    parser.add_argument('--description-prefix', dest='descriptionPrefix', type=open,
        default=None, help="HTML text for description, before track list")
    
    parser.add_argument('--description-suffix', dest='descriptionSuffix', type=open,
        default=None, help="text for description, after track list")

    parser.add_argument('--intro', dest='introDuration', type=int, default="3000",
        help="Duration in miliseconds for introduction image")

    parser.add_argument('--server-folder', dest='serverFolder',
        help="""SSH/SCP/SFTP notation for server folder, as host.name.com:folder1/folder2/ (workaround while WordPress XML-RPC upload fails with large files)""")

    parser.add_argument('--wordpress-url', dest='wordpress',
        help="""WordPress URL, preferably ending with ‘/xmlrpc.php’""")

    parser.add_argument('--wordpress-user', dest='wordpressUser',
        help="""WordPress username""")

    parser.add_argument('--wordpress-pass', dest='wordpressPass',
        help="""WordPress password""")

    parser.add_argument('-d', dest='wordpressDraft', action='store_true',
        default=False, help="Keep post in draft mode")

    parser.add_argument('--youtube-credentials', dest='ytCred',
        help="""YouTube credentials JSON file""")

    parser.add_argument('--youtube-playlist', dest='ytPL',
        help="""YouTube playlist name""")

    parser.add_argument('f', type=str, nargs='+',
                        help='music files to be added to podcast')

    args = parser.parse_args(namespace=p)
    
    for f in p.f:
        p.add(f)

    p.make()


__name__ == '__main__' and main()

