# BlendSwap Browser

Search, download, and import [BlendSwap](https://blendswap.com) assets from a
sidebar panel inside Blender, using the official BlendSwap REST API.

Unofficial community add-on, not affiliated with BlendSwap. Bring your own API key.

## Features

- Search with filters for type, format, license, and sort, paged through all results.
- Download and import into the scene: `.blend` (append or link), `.zip`, FBX,
  glTF, OBJ, STL.
- Download cache: re-importing an asset uses no credits and no network. Cache
  folder is configurable.
- Cached tab lists what you have already downloaded, for free re-import.
- Mine tab lists your uploads with their review state.
- Favorites, stored locally (see below).
- Account readout: credits, free downloads left today, daily request usage, and
  when the daily limits reset.
- Prints attribution (title, author, license, URL) to the console on each import.

## Install

Blender 4.2 or newer.

**Recommended: add the Plastic Wool repository** so it installs in one click
and updates itself.

1. `Preferences > Get Extensions > Repositories > + > Add Remote Repository`.
2. Paste `https://plasticwool.com/blender/index.json` and tick *Check for
   Updates on Startup*.
3. Search for BlendSwap Browser and install.

Or download the `.zip` from [Releases](https://github.com/jacebot/blendswap-browser/releases)
and drag it onto Blender.

Then:

1. Get an API key at [blendswap.com/dashboard/api](https://blendswap.com/dashboard/api)
   and paste it into the extension preferences.
2. Open the viewport sidebar (`N`) and pick the BlendSwap tab.

Online access must be on in `Preferences > System > Network`.

More free Blender tools at [plasticwool.com/blender](https://plasticwool.com/blender).

## Build

```
blender --command extension build --source-dir . --output-dir dist
blender --command extension validate dist/blendswap_browser-0.3.0.zip
```

Submit the built zip at [extensions.blender.org](https://extensions.blender.org).

## Favorites are local

BlendSwap's website has Liked Assets and Collections, but the public API exposes
neither. Until it does, favorites live in a JSON file on your computer and do not
sync to your account.

## Downloads cost

Each account gets a few free downloads per day, shared with the website. After
that, downloads cost credits. Cached assets re-import for free. Search and
browsing are always free.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
