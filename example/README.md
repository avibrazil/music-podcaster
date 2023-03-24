# Sample podcast
This folder contains files to build a podcast with its episodes on each subfolder. I use this files to make my own podcast https://abstrato.alkalay.net.

I start a new episode with:

`make new '0042 Some Episode Name'`

Then I enter the `0042 Some Episode Name` folder, edit `description.thtml` and `podcast.args`, and I simply execute `make` to build the media file and create the podcast post in WordPress. There is also `make test` to publish in a different WordPress site, meant for testing the process.

## Jinja Templates

Post text is controlled by:

 - `EPISODE/page.thtml` — ultimate HTML page layout
 - `EPISODE/page.ttxt` — ultimate plain text page layout
 - `EPISODE/description.thtml` — episode text that will be included in above layouts
 - `base-page.thtml` — overall HTML layout
 - `base-page.ttxt` — overall text layout
 - `page.thtml` — more specialized HTML layout
 - `page.ttxt` — more specialized text layout

Dependencies and derivations go like this:
- `base-page.thtml` ⬅︎ `page.thtml` ⬅︎ `EPISODE/page.thtml` ⬅︎ `EPISODE/description.thtml`
- `base-page.ttxt` ⬅︎ `page.ttxt` ⬅︎ `EPISODE/page.ttxt` ⬅︎ `EPISODE/description.thtml`

There is also:
- `excerpt.ttxt` — template to make WordPress excerpts

The plain text templates are used to embed textual description in media file tags. They can be inspected with tools such as `ffprobe` and `exiftool`. The HTML templates make WordPress posts.

## Podcast arguments

The `Makefile` calls the `podcaster.py` script passing arguments from 2 files:
- `default.args` or `default-test.args` — contains global podcast parameters valid for all episodes, such as WordPress address, template file names etc
- `EPISODE/podcast.args` — contains episode-specific arguments such as episode title and list of media files

