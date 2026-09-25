using System;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace EvilCats.Game
{
    /// <summary>A named animation: frames + timing (from the atlas JSON).</summary>
    public sealed class SpriteAnim
    {
        public string name;
        public Sprite[] frames;
        public Sprite[] flash;      // white silhouettes with the same layout (null if none)
        public float fps;
        public bool loop;
        public float Duration => frames.Length / Mathf.Max(1f, fps);
    }

    /// <summary>
    /// Loads the generated atlases (Resources/ECArt/&lt;atlas&gt;.png + &lt;atlas&gt;_atlas.json) and
    /// slices them into Sprites at runtime with Sprite.Create. World atlases use 16 px per unit;
    /// UI atlases use 50 px per unit so one art pixel is 2 UI units at the 100 px/unit canvas scale.
    /// </summary>
    public sealed class SpriteLibrary
    {
        public const float WorldPpu = 16f;
        public const float UiPpu = 50f;
        public static readonly string[] Atlases =
        {
            "hero", "stations", "enemies", "bosses", "citadel", "env_gravewood", "env_moonfall", "fx", "ui", "icons", "portraits",
        };
        private static readonly HashSet<string> UiAtlases = new HashSet<string> { "ui", "icons", "portraits" };

        private readonly Dictionary<string, Sprite> _sprites = new Dictionary<string, Sprite>(2048);
        private readonly Dictionary<string, Sprite> _uiCopies = new Dictionary<string, Sprite>();
        private readonly Dictionary<string, Sprite> _flash = new Dictionary<string, Sprite>(1024);
        private readonly Dictionary<string, SpriteAnim> _anims = new Dictionary<string, SpriteAnim>(512);
        private readonly Dictionary<string, Dictionary<string, Vector2>> _anchors = new Dictionary<string, Dictionary<string, Vector2>>();
        public readonly List<string> Problems = new List<string>();
        private Sprite _missing;

        public int Count => _sprites.Count;

        public void LoadAll()
        {
            foreach (var a in Atlases) LoadAtlas(a);
            _missing = MakeMissingSprite();
        }

        private void LoadAtlas(string atlas)
        {
            var meta = Resources.Load<TextAsset>("ECArt/" + atlas + "_atlas");
            var tex = Resources.Load<Texture2D>("ECArt/" + atlas);
            if (meta == null || tex == null)
            {
                Problems.Add("art: atlas '" + atlas + "' missing (run Tools/art/build_all.py)");
                return;
            }
            PrepareTexture(tex);
            var flashTex = Resources.Load<Texture2D>("ECArt/" + atlas + "_flash");
            if (flashTex != null) PrepareTexture(flashTex);
            JObject root;
            try { root = JObject.Parse(meta.text); }
            catch (Exception e) { Problems.Add("art: " + atlas + " json: " + e.Message); return; }
            float ppu = UiAtlases.Contains(atlas) ? UiPpu : WorldPpu;
            int texH = tex.height;
            if (tex.width != (int?)root["width"] || tex.height != (int?)root["height"])
                Problems.Add("art: " + atlas + " texture size differs from JSON (was it resized on import?)");
            var sprites = root["sprites"] as JObject;
            if (sprites == null) return;
            foreach (var kv in sprites)
            {
                var d = (JObject)kv.Value;
                int x = (int)d["x"], y = (int)d["y"], w = (int)d["w"], h = (int)d["h"];
                var pv = d["pivot"] as JArray;
                var pivot = pv != null ? new Vector2((float)pv[0], (float)pv[1]) : new Vector2(0.5f, 0.5f);
                var border = Vector4.zero;
                if (d["border"] is JArray b && b.Count == 4) border = new Vector4((float)b[0], (float)b[1], (float)b[2], (float)b[3]);
                // JSON rects are top-left based; Unity textures are bottom-left based.
                var rect = new Rect(x, texH - y - h, w, h);
                if (rect.xMin < 0 || rect.yMin < 0 || rect.xMax > tex.width || rect.yMax > tex.height)
                {
                    Problems.Add("art: sprite '" + kv.Key + "' outside atlas");
                    continue;
                }
                var s = Sprite.Create(tex, rect, pivot, ppu, 0, SpriteMeshType.FullRect, border);
                s.name = kv.Key;
                _sprites[kv.Key] = s;
                if (flashTex != null)
                {
                    var f = Sprite.Create(flashTex, rect, pivot, ppu, 0, SpriteMeshType.FullRect, border);
                    f.name = kv.Key + "#flash";
                    _flash[kv.Key] = f;
                }
                if (d["anchors"] is JObject anchors)
                {
                    var dict = new Dictionary<string, Vector2>();
                    foreach (var an in anchors)
                        if (an.Value is JArray arr && arr.Count == 2)
                            dict[an.Key] = new Vector2((float)arr[0], (float)arr[1]) / WorldPpu;   // px -> world units
                    _anchors[kv.Key] = dict;
                }
            }
            if (root["anims"] is JObject anims)
            {
                foreach (var kv in anims)
                {
                    var d = (JObject)kv.Value;
                    var names = d["frames"] as JArray;
                    if (names == null || names.Count == 0) continue;
                    var frames = new Sprite[names.Count];
                    Sprite[] flash = flashTex != null ? new Sprite[names.Count] : null;
                    for (int i = 0; i < names.Count; i++)
                    {
                        _sprites.TryGetValue((string)names[i], out frames[i]);
                        if (flash != null) _flash.TryGetValue((string)names[i], out flash[i]);
                    }
                    _anims[kv.Key] = new SpriteAnim
                    {
                        name = kv.Key, frames = frames, flash = flash,
                        fps = (float?)d["fps"] ?? 8f, loop = (bool?)d["loop"] ?? true,
                    };
                }
            }
        }

        /// <summary>Pixel art must stay crisp: point filtering, no wrapping (also enforced on import).</summary>
        private static void PrepareTexture(Texture2D t)
        {
            t.filterMode = FilterMode.Point;
            t.wrapMode = TextureWrapMode.Clamp;
        }

        private static Sprite MakeMissingSprite()
        {
            var t = new Texture2D(4, 4, TextureFormat.RGBA32, false) { filterMode = FilterMode.Point };
            var px = new Color32[16];
            for (int i = 0; i < 16; i++) px[i] = (i + i / 4) % 2 == 0 ? new Color32(255, 0, 255, 255) : new Color32(0, 0, 0, 255);
            t.SetPixels32(px);
            t.Apply();
            return Sprite.Create(t, new Rect(0, 0, 4, 4), new Vector2(0.5f, 0.5f), 4f);
        }

        public bool Has(string name) => name != null && _sprites.ContainsKey(name);

        /// <summary>Returns the sprite, or a visible magenta checker so a missing asset is obvious but harmless.</summary>
        public Sprite Get(string name)
        {
            if (name != null && _sprites.TryGetValue(name, out var s)) return s;
            return _missing;
        }

        public Sprite TryGet(string name) => name != null && _sprites.TryGetValue(name, out var s) ? s : null;

        /// <summary>A world-atlas sprite re-sliced at UI scale (e.g. the hero on the home screen).</summary>
        public Sprite GetForUi(string name, float uiUnitsPerPixel = 2f)
        {
            string key = name + "@" + uiUnitsPerPixel;
            if (_uiCopies.TryGetValue(key, out var c)) return c;
            var src = TryGet(name);
            if (src == null) return _missing;
            var r = src.textureRect;
            c = Sprite.Create(src.texture, r, new Vector2(src.pivot.x / r.width, src.pivot.y / r.height), 100f / uiUnitsPerPixel, 0, SpriteMeshType.FullRect, src.border);
            c.name = key;
            _uiCopies[key] = c;
            return c;
        }

        public Sprite GetFlash(string name) => name != null && _flash.TryGetValue(name, out var s) ? s : null;

        public SpriteAnim Anim(string name) => name != null && _anims.TryGetValue(name, out var a) ? a : null;

        public bool HasAnim(string name) => name != null && _anims.ContainsKey(name);

        /// <summary>Anchor (world units, relative to the sprite pivot) defined in the atlas JSON.</summary>
        public bool TryAnchor(string sprite, string anchor, out Vector2 offset)
        {
            offset = Vector2.zero;
            return sprite != null && _anchors.TryGetValue(sprite, out var d) && d.TryGetValue(anchor, out offset);
        }
    }
}
