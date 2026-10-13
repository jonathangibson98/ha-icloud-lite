# City Photo for Home Assistant

Pulls random Unsplash photos for collections you define (city, ocean, whatever)
and gives you Home Assistant image entities that update the moment a new photo lands.

This repo has two parts. You need both:

1. **Add-on** (`photo_puller/`): holds your Unsplash key and settings, downloads the photos.
2. **Integration** (`custom_components/photo_puller/`): creates the image entities.

Requires Home Assistant OS or Supervised (add-ons don't exist on Container installs).
Get a free Unsplash Access Key at https://unsplash.com/developers.

## Install the add-on

1. Settings > Add-ons > Add-on Store > three dots (top right) > Repositories
2. Paste `https://github.com/jonathangibson98/ha-photo-puller` and click Add
3. Refresh the page, scroll down, open **City Photo**, and Install
4. Configuration tab: paste your Unsplash Access Key, set up your collections, Save
5. Start

## Install the integration (HACS)

1. HACS > three dots (top right) > Custom repositories
2. Paste `https://github.com/jonathangibson98/ha-photo-puller`, set Type to **Integration**, Add
3. Find **City Photo** in HACS, Download, then restart Home Assistant
4. Settings > Devices & services > Add Integration > **City Photo** > Submit

No HACS? Copy `custom_components/photo_puller` into `/config/custom_components/` and restart.

## Collections

Each collection has a name, search terms, and an orientation (`landscape`, `portrait`, or `both`).
Every collection becomes a device with one image entity per orientation, e.g.
`image.ocean_photos_landscape`. Each image entity carries `photographer`, `photo_url`
and `search_term` attributes. Unsplash asks that you credit photographers.

Unsplash's free tier allows 50 requests per hour. Each image costs one request per cycle.
