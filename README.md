# Blend Swap Browser

Search, download, and import [Blend Swap](https://blendswap.com) assets without
leaving Blender. A sidebar panel that talks to the official Blend Swap REST API.

Unofficial community add-on. It is not affiliated with Blend Swap. You bring
your own API key.

## Features

- **Search** the catalog with filters for type, format, license, and sort
  order, with paging through all results.
- **Download and import** the selected asset straight into the scene. Handles
  `.blend` (append or link), plus `.zip`, FBX, glTF, OBJ, and STL.
- **Download cache**: every download is kept, so re-importing an asset costs no
  credits and needs no network. The cache folder is configurable.
- **Cached** tab lists everything you have already downloaded, for free
  re-import.
- **My Uploads** lists the assets you have uploaded, with their review state.
- **Favorites** for one-click access to assets you care about (see the note
  below).
- **Account readout** showing credits, free downloads left today, daily request
  usage, and when the daily limits reset.
- Attribution (title, author, license, URL) is printed to the console on every
  import, to make Creative Commons credit easy.

## Install

This is a Blender extension (Blender 4.2+).

1. Download the packaged `.zip` (or build it, see below).
2. Drag the `.zip` onto the Blender window, or use
   `Edit > Preferences > Get Extensions > Install from Disk`. Enable
   **Blend Swap Browser**.
3. Get an API key at [blendswap.com/dashboard/api](https://blendswap.com/dashboard/api)
   and paste it into the extension preferences.
4. Open the sidebar in the 3D viewport (press <kbd>N</kbd>) and switch to the
   **Blend Swap** tab.

Online access must be enabled in `Preferences > System > Network` for the
extension to reach the API.

## Build

Package the extension zip with the Blender command line:

```
blender --command extension build --source-dir . --output-dir dist
```

Validate it before publishing:

```
blender --command extension validate dist/blendswap_browser-0.2.1.zip
```

Submit the built zip at [extensions.blender.org](https://extensions.blender.org).

## Favorites are local

Blend Swap's website has Liked Assets and Collections, but the public API
exposes neither. Until it does, favorites are stored in a JSON file on your
computer and are never synced back to your account. When Blend Swap ships those
endpoints, favorites can be switched to real account sync.

## Downloads cost

Each account gets a handful of free downloads per day (shared with the website).
After that, downloads cost credits. The account readout in the panel shows how
many free downloads and credits you have left; search and browsing are free.

## Requirements

- Blender 4.2 or newer.
- A Blend Swap account and API key.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
