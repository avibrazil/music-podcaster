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
##   • ../tracklist.thtml - Jinja HTML template for tracklist
##   • ../suffix.thtml - episodes suffix template (HTML)
##   • ../excerpt.txt - episode excerpt template (plain text)
##
## HOW TO USE make TO BUILD EPISODES
##
##   • make - build media and submit to YouTube and WordPress site
##   • make all - same
##   • make test - same as "all" but submit to test YouTube and Wordpress targets
##
##
## Part of https://github.com/avibrazil/music-podcaster
## 
## Avi Alkalay <avi at unix dot sh>
## 2019-03-16
##


DEPS = ../default.args ../default-test.args podcast.args ../head.thtml description.thtml ../suffix.thtml ../tracklist.thtml ../excerpt.txt
PODCASTER = ${HOME}/src/music-podcaster/podcaster.py

# Following lines from https://stackoverflow.com/a/47008498

FOLDER=$(filter-out $@,$(MAKECMDGOALS))
EPISODE=`echo ${FOLDER} | cut -c 1-4`
TITLE=`echo ${FOLDER} | cut -c 6-`

args = `arg="$(filter-out $@,$(MAKECMDGOALS))" && [[ -n "$$arg" ]] && echo --youtube-id $${arg:-${1}}`

%:
	@:








all: clean $(DEPS)
	# Warm up host key, check if it is valid and pre-authenticated
	ssh abstrato.alkalay.net echo
	$(PODCASTER) @../default.args @podcast.args $(call args,"")

test: clean $(DEPS)
	# Warm up host key, check if it is valid and pre-authenticated
	ssh abstrato-test.alkalay.net echo
	$(PODCASTER) @../default-test.args @podcast.args $(call args,"")

cleantmp:
	rm -f tmp* *.svg *.txt

cleanmedia:
	rm -f *.m4a *.m4v *.mp4 *.jpg;

clean: cleantmp cleanmedia

nnew:
	echo ${FOLDER};
	echo ${EPISODE};
	echo ${TITLE};

new:
	-mkdir "${FOLDER}";
	ln -s ../Makefile "${FOLDER}"/Makefile;
	ln -s ../page.thtml "${FOLDER}"/page.thtml;
	ln -s ../page.ttxt "${FOLDER}"/page.ttxt;
	cp example-description.thtml "${FOLDER}"/description.thtml;
	@printf -- "-i\n\
	${EPISODE}\n\
	-t\n\
	${TITLE}\n\
    " > "${FOLDER}"/podcast.args
