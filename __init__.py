# SPDX-License-Identifier: GPL-3.0-or-later
"""Blend Swap Browser: search, download, and import Blend Swap assets from
inside Blender using the official Blend Swap REST API.

Unofficial community add-on. You supply your own API key (bsk_live_...).
Packaged as a Blender extension; metadata lives in blender_manifest.toml.
"""

import json
import os
import tempfile
import zipfile
import urllib.request
import urllib.parse
import urllib.error

import bpy
from bpy.props import (
    StringProperty,
    EnumProperty,
    IntProperty,
    BoolProperty,
    CollectionProperty,
)
from bpy.types import (
    AddonPreferences,
    Operator,
    Panel,
    PropertyGroup,
    UIList,
)

API_BASE = "https://blendswap.com/api/v1"
USER_AGENT = "BlendSwapBrowser/0.1 (Blender add-on)"

# The "Any" option means "no filter". Its identifier must be a non-empty
# string (Blender can't select an empty-string enum id), so it is "ANY" and
# gets dropped from the request in _filter_value().
ANY = "ANY"

LICENSE_ITEMS = [
    (ANY, "Any", "No license filter"),
    ("cc0", "CC0", "Public domain"),
    ("cc_by", "CC-BY", "Attribution"),
    ("cc_by_sa", "CC-BY-SA", "Attribution, ShareAlike"),
    ("cc_by_nc", "CC-BY-NC", "Attribution, NonCommercial"),
    ("gal", "GAL", "General Asset License"),
    ("commercial", "Commercial", "BlendSwap Commercial"),
]

TYPE_ITEMS = [
    (ANY, "Any", "No type filter"),
    ("model_3d", "3D Model", ""),
    ("material", "Material", ""),
    ("hdri", "HDRI", ""),
    ("addon", "Add-on", ""),
    ("tool", "Tool", ""),
    ("theme", "Theme", ""),
    ("simulation", "Simulation", ""),
]

FORMAT_ITEMS = [
    (ANY, "Any", "No format filter"),
    ("blender", "Blender (.blend)", ""),
    ("fbx", "FBX", ""),
    ("gltf", "glTF", ""),
    ("obj", "OBJ", ""),
    ("stl", "STL", ""),
    ("usd", "USD", ""),
    ("texture", "Texture", ""),
]

SORT_ITEMS = [
    ("newest", "Newest", ""),
    ("downloads", "Most Downloaded", ""),
    ("likes", "Most Liked", ""),
]


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _get_key(context):
    prefs = context.preferences.addons[__name__].preferences
    return (prefs.api_key or "").strip()


def _request(context, method, path, params=None, body=None):
    """Call the Blend Swap API. Returns parsed JSON dict.

    Raises RuntimeError with a friendly message on failure.
    """
    # Extensions must respect the user's global online-access setting.
    if not bpy.app.online_access:
        raise RuntimeError(
            "Online access is off. Enable it in Preferences > System > Network."
        )

    key = _get_key(context)
    if not key:
        raise RuntimeError("No API key set. Add it in the add-on preferences.")

    url = API_BASE + path
    if params:
        clean = {k: v for k, v in params.items() if v not in (None, "")}
        if clean:
            url += "?" + urllib.parse.urlencode(clean)

    data = None
    headers = {
        "Authorization": "Bearer " + key,
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode("utf-8"))
            msg = payload.get("message") or payload.get("error") or str(e)
        except Exception:
            msg = str(e)
        if e.code == 401:
            raise RuntimeError("Unauthorized — check your API key.")
        if e.code == 402:
            raise RuntimeError("Insufficient credits: " + msg)
        if e.code == 429:
            raise RuntimeError("Rate limited — slow down and retry.")
        raise RuntimeError("API error %s: %s" % (e.code, msg))
    except urllib.error.URLError as e:
        raise RuntimeError("Network error: %s" % e.reason)


def _download_file(url, dest_path):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp, open(dest_path, "wb") as f:
        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            f.write(chunk)


# ---------------------------------------------------------------------------
# Local favorites
#
# Blend Swap's website has "Liked Assets" and "Collections", but the public
# API exposes neither (no endpoint, no /me field, no filter). Until it does,
# favorites live in a JSON file on this machine and are never synced back to
# the account. Each entry keeps a cached snapshot of the asset so the list
# still renders offline; it is refreshed from the API whenever possible.
# ---------------------------------------------------------------------------

def _fav_path():
    cfg = bpy.utils.user_resource("CONFIG", create=True)
    return os.path.join(cfg, "blendswap_favorites.json")


def _load_favs():
    try:
        with open(_fav_path(), "r") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return []


def _save_favs(favs):
    with open(_fav_path(), "w") as f:
        json.dump(favs, f, indent=2)


def _fav_ids():
    return {int(x.get("id", 0)) for x in _load_favs()}


def _on_mode_change(self, context):
    # Results are mode-specific; clear them so tabs don't show stale cross-tab data.
    self.blendswap_results.clear()
    self.blendswap_result_index = 0


def _fill_row(r, item, status=""):
    """Populate a result PropertyGroup from an API asset dict."""
    r.asset_id = item.get("id", 0)
    r.title = item.get("title", "(untitled)")
    author = item.get("author") or {}
    r.author = author.get("username", "")
    lic = item.get("license") or {}
    r.license = lic.get("name", "")
    r.asset_type = item.get("asset_type_label", item.get("asset_type", ""))
    r.downloads = (item.get("counts") or {}).get("downloads", 0)
    r.web_url = item.get("url", "")
    r.status = status
    r.favorited = int(item.get("id", 0)) in _fav_ids()


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

class BlendSwapResult(PropertyGroup):
    asset_id: IntProperty()
    title: StringProperty()
    author: StringProperty()
    license: StringProperty()
    asset_type: StringProperty()
    downloads: IntProperty()
    web_url: StringProperty()
    status: StringProperty()  # upload review state, when in My Uploads
    favorited: BoolProperty()


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

class BLENDSWAP_OT_search(Operator):
    bl_idname = "blendswap.search"
    bl_label = "Search Blend Swap"
    bl_description = "Search the Blend Swap catalog"

    def execute(self, context):
        scn = context.scene
        drop_any = lambda v: "" if v == ANY else v
        params = {
            # Blend Swap's q is case-sensitive; normalize so "Rust" == "rust".
            "q": scn.blendswap_query.lower(),
            "license": drop_any(scn.blendswap_license),
            "type": drop_any(scn.blendswap_type),
            "format": drop_any(scn.blendswap_format),
            "sort": scn.blendswap_sort,
            "per_page": 25,
        }
        try:
            payload = _request(context, "GET", "/assets", params=params)
        except RuntimeError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}

        scn.blendswap_results.clear()
        for item in payload.get("data", []):
            _fill_row(scn.blendswap_results.add(), item)

        scn.blendswap_result_index = 0
        n = len(scn.blendswap_results)
        pg = payload.get("pagination") or {}
        self.report({"INFO"}, "Found %d of %s results" % (n, pg.get("count", n)))
        return {"FINISHED"}


class BLENDSWAP_OT_my_uploads(Operator):
    bl_idname = "blendswap.my_uploads"
    bl_label = "My Uploads"
    bl_description = "List the assets you've uploaded to Blend Swap"

    def execute(self, context):
        scn = context.scene
        try:
            payload = _request(context, "GET", "/uploads", params={"per_page": 100})
        except RuntimeError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}

        scn.blendswap_results.clear()
        for item in payload.get("data", []):
            _fill_row(
                scn.blendswap_results.add(), item,
                status=item.get("review_state", item.get("status", "")),
            )
        scn.blendswap_result_index = 0
        self.report({"INFO"}, "You have %d upload(s)" % len(scn.blendswap_results))
        return {"FINISHED"}


class BLENDSWAP_OT_favorites(Operator):
    bl_idname = "blendswap.favorites"
    bl_label = "Favorites"
    bl_description = "Show your locally saved favorites (refreshed from the API)"

    def execute(self, context):
        scn = context.scene
        favs = _load_favs()
        scn.blendswap_results.clear()
        for fav in favs:
            # Try a fresh pull; fall back to the cached snapshot if offline.
            try:
                payload = _request(context, "GET", "/assets/%d" % int(fav["id"]))
                item = payload.get("data", payload)
            except (RuntimeError, KeyError, ValueError):
                item = fav
            _fill_row(scn.blendswap_results.add(), item)
        scn.blendswap_result_index = 0
        self.report({"INFO"}, "%d favorite(s)" % len(scn.blendswap_results))
        return {"FINISHED"}


class BLENDSWAP_OT_toggle_fav(Operator):
    bl_idname = "blendswap.toggle_fav"
    bl_label = "Toggle Favorite"
    bl_description = "Add or remove this asset from your local favorites"

    index: IntProperty(default=-1)  # row to toggle; -1 = active selection

    def execute(self, context):
        scn = context.scene
        if not scn.blendswap_results:
            return {"CANCELLED"}
        idx = self.index if self.index >= 0 else scn.blendswap_result_index
        if idx < 0 or idx >= len(scn.blendswap_results):
            return {"CANCELLED"}
        r = scn.blendswap_results[idx]
        favs = _load_favs()
        ids = {int(x.get("id", 0)) for x in favs}
        if r.asset_id in ids:
            favs = [x for x in favs if int(x.get("id", 0)) != r.asset_id]
            r.favorited = False
            msg = "Removed from favorites"
        else:
            favs.append({
                "id": r.asset_id, "title": r.title,
                "author": {"username": r.author},
                "license": {"name": r.license},
                "asset_type_label": r.asset_type, "url": r.web_url,
            })
            r.favorited = True
            msg = "Added to favorites"
        _save_favs(favs)
        self.report({"INFO"}, msg)
        return {"FINISHED"}


def _apply_account(scn, data):
    """Store parsed /me fields onto the scene for the status readout."""
    rl = data.get("rate_limits") or {}
    scn.blendswap_credits = int(data.get("credits", 0))
    scn.blendswap_free_left = int(data.get("api_free_downloads_remaining_today", 0))
    scn.blendswap_free_cap = int(data.get("api_download_cap", 0))
    scn.blendswap_reqs_today = int(rl.get("requests_today", 0))
    scn.blendswap_reqs_cap = int(rl.get("requests_per_day", 1000))
    scn.blendswap_username = (data.get("user") or {}).get("username", "")
    scn.blendswap_has_account = True


class BLENDSWAP_OT_balance(Operator):
    bl_idname = "blendswap.balance"
    bl_label = "Refresh Account"
    bl_description = "Refresh credits, free downloads, and daily request usage"

    def execute(self, context):
        try:
            payload = _request(context, "GET", "/me")
        except RuntimeError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        data = payload.get("data", payload)
        _apply_account(context.scene, data)
        self.report(
            {"INFO"},
            "%d credits · %d/%d free downloads today"
            % (context.scene.blendswap_credits,
               context.scene.blendswap_free_left,
               context.scene.blendswap_free_cap),
        )
        return {"FINISHED"}


class BLENDSWAP_OT_open_web(Operator):
    bl_idname = "blendswap.open_web"
    bl_label = "Open on Blend Swap"
    bl_description = "Open the selected asset's page in your browser"

    def execute(self, context):
        scn = context.scene
        if not scn.blendswap_results:
            return {"CANCELLED"}
        r = scn.blendswap_results[scn.blendswap_result_index]
        if r.web_url:
            bpy.ops.wm.url_open(url=r.web_url)
        return {"FINISHED"}


class BLENDSWAP_OT_import(Operator):
    bl_idname = "blendswap.import_asset"
    bl_label = "Download & Import"
    bl_description = (
        "Download the selected asset (may cost credits) and import it into the scene"
    )

    link: BoolProperty(name="Link", default=False)

    def execute(self, context):
        scn = context.scene
        if not scn.blendswap_results:
            self.report({"ERROR"}, "No results — search first.")
            return {"CANCELLED"}
        r = scn.blendswap_results[scn.blendswap_result_index]

        try:
            resp = _request(
                context, "POST", "/downloads", body={"asset_id": r.asset_id}
            )
        except RuntimeError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}

        dl_url = resp.get("download_url")
        if not dl_url:
            self.report({"ERROR"}, "No download URL returned.")
            return {"CANCELLED"}

        file_meta = resp.get("file") or {}
        filename = file_meta.get("filename") or ("asset_%d.blend" % r.asset_id)
        tmp_dir = tempfile.mkdtemp(prefix="blendswap_")
        dest = os.path.join(tmp_dir, filename)

        try:
            _download_file(dl_url, dest)
        except Exception as e:
            self.report({"ERROR"}, "Download failed: %s" % e)
            return {"CANCELLED"}

        # Attribution to console/info for CC compliance.
        lic = (resp.get("license") or {}).get("name", r.license)
        print(
            "[Blend Swap] '%s' by %s — license: %s — %s"
            % (r.title, r.author, lic, r.web_url)
        )

        try:
            self._import_path(dest)
        except Exception as e:
            self.report({"ERROR"}, "Import failed: %s" % e)
            return {"CANCELLED"}

        charged = resp.get("charged")
        remaining = resp.get("credits_remaining")
        # Keep the status readout current without a second API call.
        scn = context.scene
        if remaining is not None:
            scn.blendswap_credits = int(remaining)
        if not charged and scn.blendswap_free_left > 0:
            scn.blendswap_free_left -= 1
        note = ""
        if charged:
            note = " (10 credits, %s left)" % remaining
        self.report({"INFO"}, "Imported '%s'%s" % (r.title, note))
        return {"FINISHED"}

    def _import_path(self, path):
        """Import a downloaded file by extension; unzip and find the .blend first."""
        lower = path.lower()

        if lower.endswith(".zip"):
            extract_dir = path + "_extracted"
            with zipfile.ZipFile(path) as z:
                z.extractall(extract_dir)
            blend = None
            for root, _dirs, files in os.walk(extract_dir):
                for f in files:
                    if f.lower().endswith(".blend"):
                        blend = os.path.join(root, f)
                        break
                if blend:
                    break
            if blend:
                self._append_blend(blend)
            else:
                raise RuntimeError(
                    "Zip contained no .blend. Extracted to: %s" % extract_dir
                )
            return

        if lower.endswith(".blend"):
            self._append_blend(path)
        elif lower.endswith((".fbx",)):
            bpy.ops.import_scene.fbx(filepath=path)
        elif lower.endswith((".glb", ".gltf")):
            bpy.ops.import_scene.gltf(filepath=path)
        elif lower.endswith(".obj"):
            bpy.ops.wm.obj_import(filepath=path)
        elif lower.endswith(".stl"):
            bpy.ops.wm.stl_import(filepath=path)
        else:
            raise RuntimeError("Downloaded file saved to %s (no importer)" % path)

    def _append_blend(self, blend_path):
        # Append (or link) all objects from the downloaded .blend.
        with bpy.data.libraries.load(blend_path, link=self.link) as (src, dst):
            dst.objects = list(src.objects)

        linked = 0
        for obj in dst.objects:
            if obj is not None:
                bpy.context.collection.objects.link(obj)
                linked += 1
        if linked == 0:
            raise RuntimeError("No objects found in %s" % os.path.basename(blend_path))


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

def _draw_wrapped(layout, context, text, icon="NONE"):
    """Draw multi-line help text, word-wrapped to the current panel width.

    Blender labels never wrap on their own, so we estimate how many characters
    fit and split on word boundaries. The first line carries the icon.
    """
    import textwrap

    # ~7 px per character at the default UI scale; leave room for the margin.
    char_w = 7 * context.preferences.system.ui_scale
    max_chars = max(16, int((context.region.width - 20) / char_w))

    col = layout.column(align=True)
    col.scale_y = 0.8
    for i, line in enumerate(textwrap.wrap(text, max_chars)):
        col.label(text=line, icon=icon if i == 0 else "BLANK1")

class BLENDSWAP_UL_results(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data,
                  active_prop, index=0, flt_flag=0):
        row = layout.row(align=True)
        star = "SOLO_ON" if item.favorited else "SOLO_OFF"
        op = row.operator("blendswap.toggle_fav", text="", icon=star, emboss=False)
        op.index = index
        row.label(text=item.title, icon="MESH_DATA")
        sub = row.row()
        sub.alignment = "RIGHT"
        if item.status:
            sub.label(text=item.status.upper())
        elif item.license:
            sub.label(text=item.license)


class BLENDSWAP_PT_panel(Panel):
    bl_label = "Blend Swap"
    bl_idname = "BLENDSWAP_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Blend Swap"

    def draw(self, context):
        layout = self.layout
        scn = context.scene

        if not _get_key(context):
            box = layout.box()
            box.label(text="Set your API key in preferences", icon="ERROR")
            box.operator("blendswap.open_prefs", icon="PREFERENCES")
            return

        # Account status readout
        box = layout.box()
        row = box.row(align=True)
        if scn.blendswap_has_account:
            col = row.column(align=True)
            if scn.blendswap_username:
                col.label(text="Signed in as %s" % scn.blendswap_username,
                          icon="USER")
            col.label(
                text="%d credits · %d/%d free dls today"
                % (scn.blendswap_credits, scn.blendswap_free_left,
                   scn.blendswap_free_cap),
                icon="FUND",
            )
            col.label(
                text="%d/%d requests today"
                % (scn.blendswap_reqs_today, scn.blendswap_reqs_cap),
                icon="TIME",
            )
        else:
            row.label(text="Account: click refresh", icon="FUND")
        row.operator("blendswap.balance", text="", icon="FILE_REFRESH")

        # Mode selector: Search / My Uploads / Favorites
        row = layout.row(align=True)
        row.prop(scn, "blendswap_mode", expand=True)

        mode = scn.blendswap_mode
        if mode == "SEARCH":
            col = layout.column(align=True)
            col.prop(scn, "blendswap_query", text="", icon="VIEWZOOM")
            r1 = col.row(align=True)
            r1.prop(scn, "blendswap_type", text="")
            r1.prop(scn, "blendswap_format", text="")
            r2 = col.row(align=True)
            r2.prop(scn, "blendswap_license", text="")
            r2.prop(scn, "blendswap_sort", text="")
            col.operator("blendswap.search", icon="VIEWZOOM")
        elif mode == "UPLOADS":
            layout.operator("blendswap.my_uploads", icon="FILE_REFRESH")
        else:  # FAVORITES
            layout.operator("blendswap.favorites", icon="FILE_REFRESH")
            # Be explicit that these are local-only until the API catches up.
            _draw_wrapped(
                layout, context,
                "Local favorites, this computer only. Blend Swap has no "
                "likes or collections API yet.",
                icon="INFO",
            )

        layout.template_list(
            "BLENDSWAP_UL_results", "", scn, "blendswap_results",
            scn, "blendswap_result_index", rows=6,
        )

        if scn.blendswap_results:
            r = scn.blendswap_results[scn.blendswap_result_index]
            box = layout.box()
            box.label(text=r.title)
            info = "by %s · %s · %d dl" % (r.author, r.asset_type, r.downloads)
            if r.status:
                info = "%s · %s" % (r.status.upper(), info)
            box.label(text=info)
            row = box.row(align=True)
            row.operator("blendswap.import_asset", icon="IMPORT")
            fav_icon = "SOLO_ON" if r.favorited else "SOLO_OFF"
            row.operator("blendswap.toggle_fav", text="", icon=fav_icon)
            row.operator("blendswap.open_web", text="", icon="URL")


class BLENDSWAP_OT_open_prefs(Operator):
    bl_idname = "blendswap.open_prefs"
    bl_label = "Open Preferences"

    def execute(self, context):
        bpy.ops.screen.userpref_show()
        context.preferences.active_section = "ADDONS"
        return {"FINISHED"}


class BlendSwapPrefs(AddonPreferences):
    bl_idname = __name__

    api_key: StringProperty(
        name="API Key",
        description="Your Blend Swap API key (starts with bsk_live_). "
        "Create one at blendswap.com/dashboard/api",
        subtype="PASSWORD",
        default="",
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "api_key")
        layout.operator("wm.url_open", text="Get an API key", icon="URL").url = (
            "https://blendswap.com/dashboard/api"
        )


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

classes = (
    BlendSwapResult,
    BLENDSWAP_OT_search,
    BLENDSWAP_OT_my_uploads,
    BLENDSWAP_OT_favorites,
    BLENDSWAP_OT_toggle_fav,
    BLENDSWAP_OT_balance,
    BLENDSWAP_OT_open_web,
    BLENDSWAP_OT_import,
    BLENDSWAP_OT_open_prefs,
    BLENDSWAP_UL_results,
    BLENDSWAP_PT_panel,
    BlendSwapPrefs,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)

    S = bpy.types.Scene
    S.blendswap_mode = EnumProperty(
        name="Mode",
        items=[
            ("SEARCH", "Search", "Search the Blend Swap catalog", "VIEWZOOM", 0),
            ("UPLOADS", "Mine", "Your uploaded assets", "USER", 1),
            ("FAVORITES", "Favorites", "Your saved favorites", "SOLO_ON", 2),
        ],
        default="SEARCH",
        update=_on_mode_change,
    )
    S.blendswap_query = StringProperty(name="Search", default="")
    S.blendswap_license = EnumProperty(name="License", items=LICENSE_ITEMS, default=ANY)
    S.blendswap_type = EnumProperty(name="Type", items=TYPE_ITEMS, default=ANY)
    S.blendswap_format = EnumProperty(name="Format", items=FORMAT_ITEMS, default=ANY)
    S.blendswap_sort = EnumProperty(name="Sort", items=SORT_ITEMS, default="newest")
    S.blendswap_results = CollectionProperty(type=BlendSwapResult)
    S.blendswap_result_index = IntProperty(
        name="Asset",
        description="Selected Blend Swap asset",
        default=0,
    )
    S.blendswap_has_account = BoolProperty(default=False)
    S.blendswap_username = StringProperty(default="")
    S.blendswap_credits = IntProperty(default=0)
    S.blendswap_free_left = IntProperty(default=0)
    S.blendswap_free_cap = IntProperty(default=0)
    S.blendswap_reqs_today = IntProperty(default=0)
    S.blendswap_reqs_cap = IntProperty(default=1000)


def unregister():
    S = bpy.types.Scene
    for attr in (
        "blendswap_mode", "blendswap_query", "blendswap_license", "blendswap_type",
        "blendswap_format", "blendswap_sort", "blendswap_results",
        "blendswap_result_index",
        "blendswap_has_account", "blendswap_username", "blendswap_credits",
        "blendswap_free_left", "blendswap_free_cap",
        "blendswap_reqs_today", "blendswap_reqs_cap",
    ):
        if hasattr(S, attr):
            delattr(S, attr)

    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
