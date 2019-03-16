######################################################################################
##
## This makefile makes it easy to call the podcaster.py script.
## Put it in the episode preparation folder along with following files:
##
##   • podcast.args - list of media files and other arguments to pass to script
##   • description.thtml - podcast episode text
##
## Having the following files in parent directory:
##
##   • ../default.args - default configurations, things that don't change across episodes
##   • ../default-test.args - same, but for a test site
##   • ../head.thtml - episodes header template (HTML)
##   • ../suffix.thtml - episodes suffix template (HTML)
##   • ../excerpt.txt - episode excerpt template (plain text)
##
## HOW TO USE make TO BUILD EPISODES
##
##   • make - build media and submit to YouTube and WordPress site
##   • make all - same
##   • make test - same as "all" but submit to test YouTube and Wordpress targets
##   • make all [YouTubeID] - same but do not build media for YouTube, use existing video instead
##   • make test [YouTubeID] - same but for a test site
##
##
## Part of https://github.com/avibrazil/music-podcaster
## 
## Avi Alkalay <avi at unix dot sh>
## 2019-03-16
##


DEPS = ../default.args ../default-test.args podcast.args ../head.thtml description.thtml ../suffix.thtml ../excerpt.txt
PODCASTER = ${HOME}/src/music-podcaster/podcaster.py



# Following lines from https://stackoverflow.com/a/47008498

args = `arg="$(filter-out $@,$(MAKECMDGOALS))" && [[ -n "$$arg" ]] && echo --youtube-id $${arg:-${1}}`

%:
	@:








all: clean $(DEPS)
	ssh abstra.to echo
	$(PODCASTER) @../default.args @podcast.args $(call args,"")

test: clean $(DEPS)
	ssh test.abstra.to echo
	$(PODCASTER) @../default-test.args @podcast.args $(call args,"")

cleantmp:
	rm -f tmp* *svg *txt

cleanmedia:
	rm -f *m4a *mp4 *jpg;

clean: cleantmp cleanmedia
