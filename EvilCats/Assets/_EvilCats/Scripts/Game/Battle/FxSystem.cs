using System;
using System.Collections.Generic;
using EvilCats.Meta;
using TMPro;
using UnityEngine;

namespace EvilCats.Game
{
    /// <summary>
    /// Pooled battle effects: animated one-shots, jagged lightning built from stretched sprites,
    /// floating damage numbers, boss/enemy telegraphs, and coin/XP pickups that fly to the HUD.
    /// Everything runs on game time (Time.deltaTime), so effects pause with the battle and play
    /// twice as fast at 2x. Visual randomness uses UnityEngine.Random and never touches the
    /// simulation's seeded streams. Respects the flashes / damage-number / shake settings.
    /// </summary>
    public sealed class FxSystem : MonoBehaviour
    {
        // ---- colours shared with the HUD ---------------------------------------------------------
        public static readonly Color ArcColor = new Color(0.55f, 0.95f, 1f);
        public static readonly Color EmberColor = new Color(1f, 0.6f, 0.2f);
        public static readonly Color FrostColor = new Color(0.7f, 0.9f, 1f);
        public static readonly Color BoneColor = new Color(0.93f, 0.88f, 0.76f);
        public static readonly Color GravityColor = new Color(0.72f, 0.55f, 1f);
        public static readonly Color TrueColor = new Color(1f, 0.55f, 0.7f);
        public static readonly Color DangerColor = new Color(1f, 0.25f, 0.25f);
        public static readonly Color GoldColor = new Color(1f, 0.82f, 0.29f);
        public static readonly Color BarrierColor = new Color(0.78f, 0.96f, 1f);

        private const int MaxNumbers = 40;
        private const int MaxFlyers = 36;

        private BattleView _view;
        private SpriteLibrary _sp;
        private Transform _root;
        private Pool<SpriteAnimator> _pool;
        private Pool<TextMeshPro> _numberPool;
        private readonly List<Fx> _fx = new List<Fx>(128);
        private readonly List<Number> _numbers = new List<Number>(MaxNumbers);
        private readonly List<Flyer> _flyers = new List<Flyer>(MaxFlyers);
        private readonly List<Telegraph> _telegraphs = new List<Telegraph>(16);
        private readonly Dictionary<int, Fx> _wells = new Dictionary<int, Fx>();
        private readonly Dictionary<int, Fx> _rings = new Dictionary<int, Fx>();   // by followed enemy uid
        private Fx _reticle;
        private static Material _numberMaterial;

        /// <summary>World-space point the Spark Coins fly to (the HUD counter). Null = the citadel.</summary>
        public Func<Vector2> SparkTarget;
        /// <summary>Called when a flying coin reaches the counter (HUD pulse).</summary>
        public Action CoinArrived;

        private sealed class Fx
        {
            public SpriteAnimator anim;
            public SpriteRenderer sr;
            public float age, life;          // life <= 0: until a non-looping clip finishes
            public Vector2 pos, vel;
            public float scale0 = 1f, scale1 = 1f, alpha = 1f, fadeFrom = 0.6f;
            public int followUid;
            public Vector2 offset;
            public float blink;              // > 0: blink frequency (Hz)
            public bool blinkAccelerate;
            public Color color = Color.white;
            public bool alive;
        }

        private sealed class Number
        {
            public TextMeshPro text;
            public float age, life, scale;
            public Vector2 pos, vel;
            public Color color;
        }

        private sealed class Flyer
        {
            public SpriteAnimator anim;
            public Vector2 pos, vel;
            public float age, popTime, homeTime;
            public Vector2 homeFrom;
            public bool homing, coin;
        }

        private sealed class Telegraph
        {
            public GameObject root;
            public readonly List<SpriteRenderer> parts = new List<SpriteRenderer>();
            public readonly List<float> baseAlpha = new List<float>();
            public float age, life;
            public int followUid;
            public bool march;               // chevrons light up in sequence toward the target
        }

        private Settings S => GameApp.I != null && GameApp.I.Meta != null ? new Settings(GameApp.I.Meta.Data.settings) : new Settings(null);

        private readonly struct Settings
        {
            public readonly bool flashes, numbers;
            public Settings(SettingsData s)
            {
                flashes = s == null || s.flashes;
                numbers = s == null || s.damageNumbers;
            }
        }

        public void Init(BattleView view, SpriteLibrary sprites)
        {
            _view = view;
            _sp = sprites;
            _root = new GameObject("Fx").transform;
            _root.SetParent(view.transform, false);
            _pool = new Pool<SpriteAnimator>(() =>
            {
                var sr = WorldKit.Sprite(_root, "fx", null, WorldKit.FxOrder, Vector2.zero);
                var a = sr.gameObject.AddComponent<SpriteAnimator>();
                a.Target = sr;
                a.UseUnscaledTime = false;
                return a;
            });
            _numberPool = new Pool<TextMeshPro>(CreateNumber);
        }

        // =========================================================================================
        // Generic effects
        // =========================================================================================

        /// <summary>Play an animation once (or for `life` seconds if it loops). Size is in world units
        /// (diameter the effect should cover); 0 keeps the art's native size.</summary>
        public void Play(string anim, Vector2 pos, float size = 0f, Color? color = null, int order = WorldKit.FxOrder,
            float life = 0f, int followUid = 0, float rotation = 0f)
        {
            var clip = _sp.Anim(anim);
            if (clip == null || clip.frames.Length == 0 || clip.frames[0] == null) return;
            var fx = Get(order);
            fx.anim.enabled = true;
            fx.anim.Play(clip, true);
            fx.life = clip.loop ? Mathf.Max(0.1f, life) : life;
            float native = clip.frames[0].rect.width / SpriteLibrary.WorldPpu;
            fx.scale0 = fx.scale1 = size > 0f ? size / native : 1f;
            fx.color = color ?? Color.white;
            fx.pos = pos;
            fx.followUid = followUid;
            // keep the requested offset from the followed unit (e.g. a stun icon above its head)
            if (followUid > 0 && _view.Units != null && _view.Units.TryGetPos(followUid, out var up)) fx.offset = pos - up;
            fx.anim.transform.localRotation = Quaternion.Euler(0f, 0f, rotation);
            Apply(fx);
        }

        /// <summary>A static sprite that grows/fades over `life` seconds.</summary>
        public void Sprite(string sprite, Vector2 pos, float life, float size0, float size1, Color color, int order = WorldKit.FxOrder,
            Vector2 vel = default, float fadeFrom = 0.5f, float rotation = 0f)
        {
            var s = _sp.TryGet(sprite);
            if (s == null) return;
            var fx = Get(order);
            fx.anim.enabled = false;
            fx.sr.sprite = s;
            fx.life = Mathf.Max(0.05f, life);
            float native = s.rect.width / SpriteLibrary.WorldPpu;
            fx.scale0 = size0 / native;
            fx.scale1 = size1 / native;
            fx.color = color;
            fx.pos = pos;
            fx.vel = vel;
            fx.fadeFrom = fadeFrom;
            fx.anim.transform.localRotation = Quaternion.Euler(0f, 0f, rotation);
            Apply(fx);
        }

        private Fx Get(int order)
        {
            var a = _pool.Get();
            var fx = new Fx { anim = a, sr = a.Target, alive = true };
            fx.sr.sortingOrder = order;
            fx.sr.flipX = fx.sr.flipY = false;
            fx.anim.transform.localRotation = Quaternion.identity;
            _fx.Add(fx);
            return fx;
        }

        private void Release(Fx fx)
        {
            if (!fx.alive) return;
            fx.alive = false;
            if (fx.followUid > 0 && _rings.TryGetValue(fx.followUid, out var ring) && ring == fx) _rings.Remove(fx.followUid);
            fx.anim.transform.localRotation = Quaternion.identity;
            fx.anim.UseUnscaledTime = false;
            fx.sr.color = Color.white;
            _pool.Release(fx.anim);
        }

        private void Apply(Fx fx)
        {
            float t = fx.life > 0f ? Mathf.Clamp01(fx.age / fx.life) : fx.anim.NormalizedTime;
            float s = Mathf.Lerp(fx.scale0, fx.scale1, 1f - (1f - t) * (1f - t));
            fx.anim.transform.localScale = new Vector3(s, s, 1f);
            if (fx.followUid > 0 && _view.Units != null)
            {
                if (_view.Units.TryGetPos(fx.followUid, out var up)) fx.pos = up;
                else if (fx.life > 0f) fx.life = Mathf.Min(fx.life, fx.age + 0.15f);   // target gone: fade out
            }
            Vector2 p = fx.pos + fx.offset;
            fx.anim.transform.localPosition = new Vector3(p.x, p.y, 0f);
            float a = fx.alpha;
            if (fx.life > 0f && t > fx.fadeFrom) a *= 1f - (t - fx.fadeFrom) / Mathf.Max(0.001f, 1f - fx.fadeFrom);
            if (fx.blink > 0f)
            {
                float hz = fx.blinkAccelerate ? fx.blink * (1f + 3f * t) : fx.blink;
                a *= 0.45f + 0.55f * (0.5f + 0.5f * Mathf.Sin(fx.age * hz * Mathf.PI * 2f));
            }
            var c = fx.color;
            c.a *= a;
            fx.sr.color = c;
        }

        // =========================================================================================
        // Lightning: a jagged polyline of stretched "lightning_tex" segments (1 x 0.5 units natively)
        // =========================================================================================
        public void Lightning(Vector2 a, Vector2 b, Color color, float width = 0.32f, float life = 0.14f, float jitter = 0.28f)
        {
            float len = Vector2.Distance(a, b);
            if (len < 0.05f) return;
            var tex = _sp.TryGet("fx/lightning_tex");
            if (tex == null) return;
            if (!S.flashes) color.a *= 0.75f;
            int n = Mathf.Clamp(Mathf.CeilToInt(len / 0.7f), 2, 9);
            Vector2 dir = (b - a) / len, nrm = new Vector2(-dir.y, dir.x);
            Vector2 prev = a;
            float j = jitter * Mathf.Min(1f, len / 2f);
            for (int i = 1; i <= n; i++)
            {
                Vector2 p = i == n ? b : Vector2.Lerp(a, b, i / (float)n) + nrm * UnityEngine.Random.Range(-j, j);
                Segment(tex, prev, p, color, width, life);
                prev = p;
            }
        }

        private void Segment(Sprite tex, Vector2 a, Vector2 b, Color color, float width, float life)
        {
            float len = Vector2.Distance(a, b);
            var fx = Get(WorldKit.FxOrder + 5);
            fx.anim.enabled = false;
            fx.sr.sprite = tex;
            fx.life = life;
            fx.fadeFrom = 0.3f;
            fx.color = color;
            fx.pos = (a + b) * 0.5f;
            fx.scale0 = fx.scale1 = 1f;
            float ang = Mathf.Atan2(b.y - a.y, b.x - a.x) * Mathf.Rad2Deg;
            fx.anim.transform.localRotation = Quaternion.Euler(0f, 0f, ang);
            // non-uniform scale is re-applied every frame in Update via SegmentScale
            fx.offset = new Vector2(len / (tex.rect.width / SpriteLibrary.WorldPpu), width / (tex.rect.height / SpriteLibrary.WorldPpu));
            fx.followUid = -1;   // marker: stretched segment
            fx.anim.transform.localPosition = new Vector3(fx.pos.x, fx.pos.y, 0f);
            fx.anim.transform.localScale = new Vector3(fx.offset.x, fx.offset.y, 1f);
            fx.sr.color = color;
        }

        // =========================================================================================
        // Damage numbers (world-space TextMeshPro, pooled, capped)
        // =========================================================================================
        private TextMeshPro CreateNumber()
        {
            UI.EnsureFonts();
            var go = new GameObject("Number");
            go.transform.SetParent(_root, false);
            var t = go.AddComponent<TextMeshPro>();
            if (UI.FontBold != null) t.font = UI.FontBold;
            t.alignment = TextAlignmentOptions.Center;
            t.fontSize = 4.2f;
            t.rectTransform.sizeDelta = new Vector2(6f, 1.5f);
            t.sortingOrder = WorldKit.NumberOrder;
            t.raycastTarget = false;
            // one shared outlined material for every number (keeps them batched)
            if (_numberMaterial == null && t.font != null && t.font.material != null)
            {
                _numberMaterial = new Material(t.font.material) { name = "EC_NumberOutline" };
                _numberMaterial.SetFloat(ShaderUtilities.ID_OutlineWidth, 0.25f);
                _numberMaterial.SetColor(ShaderUtilities.ID_OutlineColor, new Color32(20, 10, 30, 255));
                _numberMaterial.EnableKeyword(ShaderUtilities.Keyword_Outline);
            }
            if (_numberMaterial != null) t.fontSharedMaterial = _numberMaterial;
            return t;
        }

        /// <summary>Floating number. kind: 0 enemy damage, 1 crit, 2 dot, 3 citadel damage, 4 barrier, 5 heal.</summary>
        public void DamageNumber(Vector2 pos, float amount, Color color, int kind)
        {
            if (!S.numbers || amount < 0.5f) return;
            if (_numbers.Count >= MaxNumbers)
            {
                var oldest = _numbers[0];
                _numbers.RemoveAt(0);
                _numberPool.Release(oldest.text);
            }
            var t = _numberPool.Get();
            string s = Mathf.RoundToInt(amount).ToString(System.Globalization.CultureInfo.InvariantCulture);
            float scale = 1f;
            switch (kind)
            {
                case 1: s += "!"; scale = 1.45f; color = GoldColor; break;
                case 2: scale = 0.75f; color.a = 0.85f; break;
                case 3: s = "-" + s; scale = 1.25f; color = DangerColor; break;
                case 4: s = "(" + s + ")"; scale = 1f; color = BarrierColor; break;
                case 5: s = "+" + s; scale = 1f; color = new Color(0.55f, 1f, 0.6f); break;
            }
            t.text = s;
            t.color = color;
            var n = new Number
            {
                text = t, age = 0f, life = kind == 1 ? 0.95f : 0.75f, scale = scale, color = color,
                pos = pos + new Vector2(UnityEngine.Random.Range(-0.25f, 0.25f), 0.5f + UnityEngine.Random.Range(0f, 0.2f)),
                vel = new Vector2(UnityEngine.Random.Range(-0.3f, 0.3f), kind == 3 ? 1.1f : 1.6f),
            };
            _numbers.Add(n);
            UpdateNumber(n, 0f);
        }

        private bool UpdateNumber(Number n, float dt)
        {
            n.age += dt;
            if (n.age >= n.life) return false;
            n.pos += n.vel * dt;
            n.vel *= Mathf.Max(0f, 1f - 3.5f * dt);
            float t = n.age / n.life;
            float pop = t < 0.15f ? Mathf.Lerp(1.5f, 1f, t / 0.15f) : 1f;
            n.text.transform.localPosition = new Vector3(n.pos.x, n.pos.y, 0f);
            n.text.transform.localScale = Vector3.one * n.scale * pop;
            var c = n.color;
            c.a *= t > 0.65f ? 1f - (t - 0.65f) / 0.35f : 1f;
            n.text.color = c;
            return true;
        }

        public static Color DamageTypeColor(int type)
        {
            switch (type)
            {
                case 0: return ArcColor;
                case 1: return EmberColor;
                case 2: return FrostColor;
                case 3: return BoneColor;
                case 4: return GravityColor;
                default: return TrueColor;
            }
        }

        // =========================================================================================
        // Pickups: coins pop out of fallen enemies and fly to the Spark counter; XP to the hero
        // =========================================================================================
        public void Coins(Vector2 pos, float sparks, float xp)
        {
            int coins = sparks <= 0f ? 0 : Mathf.Clamp(Mathf.CeilToInt(sparks / 5f), 1, 3);
            for (int i = 0; i < coins && _flyers.Count < MaxFlyers; i++) SpawnFlyer("fx/coin", pos, true);
            if (xp > 0f && _flyers.Count < MaxFlyers) SpawnFlyer("fx/xp_orb", pos, false);
        }

        private void SpawnFlyer(string anim, Vector2 pos, bool coin)
        {
            var clip = _sp.Anim(anim);
            if (clip == null) return;
            var a = _pool.Get();
            a.enabled = true;
            a.Target.sortingOrder = WorldKit.FxOrder + 20;
            a.Target.color = Color.white;
            a.transform.localScale = Vector3.one;
            a.transform.localRotation = Quaternion.identity;
            a.Play(clip, true);
            _flyers.Add(new Flyer
            {
                anim = a, pos = pos + new Vector2(0f, 0.3f), coin = coin,
                vel = new Vector2(UnityEngine.Random.Range(-1.6f, 1.6f), UnityEngine.Random.Range(2.5f, 4f)),
                popTime = UnityEngine.Random.Range(0.22f, 0.32f), homeTime = coin ? 0.42f : 0.35f,
            });
        }

        // =========================================================================================
        // Telegraphs
        // =========================================================================================

        /// <summary>Red chevrons marching along a boss charge lane.</summary>
        public void ChargeLane(Vector2 from, Vector2 to, float seconds)
        {
            var tg = NewTelegraph("ChargeLane", seconds);
            tg.march = true;
            float len = Vector2.Distance(from, to);
            if (len < 0.2f) return;
            Vector2 dir = (to - from) / len;
            float ang = Mathf.Atan2(dir.y, dir.x) * Mathf.Rad2Deg;
            var fill = _sp.TryGet("fx/telegraph_fill");
            if (fill != null)
            {
                var sr = WorldKit.Sprite(tg.root.transform, "Lane", fill, WorldKit.TelegraphOrder, (from + to) * 0.5f, new Color(1f, 0.2f, 0.2f, 0.28f));
                float n = fill.rect.width / SpriteLibrary.WorldPpu;
                sr.transform.localRotation = Quaternion.Euler(0f, 0f, ang);
                sr.transform.localScale = new Vector3(len / n, 1.4f / n, 1f);
                AddPart(tg, sr, 0.28f);
            }
            var chev = _sp.TryGet("fx/telegraph_chevron");
            if (chev != null)
                for (float d = 0.5f; d < len; d += 0.75f)
                {
                    var sr = WorldKit.Sprite(tg.root.transform, "Chevron", chev, WorldKit.TelegraphOrder + 1, from + dir * d, Color.white);
                    sr.transform.localRotation = Quaternion.Euler(0f, 0f, ang);
                    AddPart(tg, sr, 1f);
                }
        }

        /// <summary>Red wedge from the citadel toward `dir` (Mother Carrion's / Goldenfang's barrage).</summary>
        public void Sector(Vector2 dir, float halfAngleRad, float seconds)
        {
            var tg = NewTelegraph("Sector", seconds);
            float a0 = Mathf.Atan2(dir.y, dir.x);
            var wedge = WedgeSprite(halfAngleRad);
            var sr = WorldKit.Sprite(tg.root.transform, "Wedge", wedge, WorldKit.TelegraphOrder, Vector2.zero, Color.white);
            sr.transform.localRotation = Quaternion.Euler(0f, 0f, a0 * Mathf.Rad2Deg);
            AddPart(tg, sr, 1f);
            var edge = _sp.TryGet("fx/sector_edge");
            if (edge == null) return;
            foreach (float sgn in new[] { -1f, 1f })
            {
                float a = a0 + sgn * halfAngleRad;
                var d = new Vector2(Mathf.Cos(a), Mathf.Sin(a));
                for (float r = WedgeInner; r <= WedgeOuter; r += 0.55f)
                    AddPart(tg, WorldKit.Sprite(tg.root.transform, "Edge", edge, WorldKit.TelegraphOrder + 1, d * r, Color.white), 1f);
            }
        }

        private const float WedgeInner = 2.4f, WedgeOuter = 10.5f, WedgePpu = 8f;
        private readonly Dictionary<int, Sprite> _wedges = new Dictionary<int, Sprite>();

        /// <summary>
        /// A translucent, striped wedge pointing along +x with its tip at the pivot, generated once
        /// per angle at half the art resolution (chunky pixels match the pixel-art style). Drawn by
        /// a SpriteRenderer, so it works with any 2D renderer setup.
        /// </summary>
        private Sprite WedgeSprite(float halfAngleRad)
        {
            int key = Mathf.RoundToInt(halfAngleRad * Mathf.Rad2Deg * 10f);
            if (_wedges.TryGetValue(key, out var cached) && cached != null) return cached;
            int w = Mathf.CeilToInt(WedgeOuter * WedgePpu) + 1;
            int halfH = Mathf.CeilToInt(WedgeOuter * Mathf.Sin(Mathf.Min(halfAngleRad, Mathf.PI * 0.5f)) * WedgePpu) + 1;
            int h = halfH * 2;
            var px = new Color32[w * h];
            for (int y = 0; y < h; y++)
                for (int x = 0; x < w; x++)
                {
                    float u = (x + 0.5f) / WedgePpu, v = (y + 0.5f - halfH) / WedgePpu;
                    float r = Mathf.Sqrt(u * u + v * v);
                    float ang = Mathf.Abs(Mathf.Atan2(v, u));
                    if (r < WedgeInner || r > WedgeOuter || ang > halfAngleRad) continue;
                    float edgeDist = Mathf.Min(r - WedgeInner, WedgeOuter - r, (halfAngleRad - ang) * r);
                    float fall = Mathf.Lerp(0.42f, 0.16f, (r - WedgeInner) / (WedgeOuter - WedgeInner));
                    bool stripe = Mathf.FloorToInt((u + v) * 1.5f) % 2 == 0;
                    float a = edgeDist < 0.2f ? 0.75f : fall + (stripe ? 0.08f : 0f);
                    px[y * w + x] = new Color32(255, 64, 64, (byte)Mathf.RoundToInt(a * 255f));
                }
            var tex = new Texture2D(w, h, TextureFormat.RGBA32, false) { filterMode = FilterMode.Point, wrapMode = TextureWrapMode.Clamp, name = "SectorWedge" };
            tex.SetPixels32(px);
            tex.Apply(false, true);
            var sprite = UnityEngine.Sprite.Create(tex, new Rect(0, 0, w, h), new Vector2(0f, 0.5f), WedgePpu);
            sprite.name = "sector_wedge_" + key;
            _wedges[key] = sprite;
            return sprite;
        }

        /// <summary>
        /// Ring that follows an enemy (volley windup, shield stance, powder fuse, heal cast). One
        /// ring per enemy: a new one replaces the old, and EndRing removes it early (interrupted).
        /// </summary>
        public void Ring(int followUid, Vector2 pos, float radius, Color color, float seconds, bool accelerate = false)
        {
            var s = _sp.TryGet("fx/telegraph_circle");
            if (s == null) return;
            if (followUid > 0) EndRing(followUid, 0f);
            var fx = Get(WorldKit.TelegraphOrder + 2);
            fx.anim.enabled = false;
            fx.sr.sprite = s;
            fx.life = Mathf.Max(0.1f, seconds);
            fx.fadeFrom = 0.92f;
            float native = s.rect.width / SpriteLibrary.WorldPpu;
            fx.scale0 = fx.scale1 = 2f * radius / native;
            fx.color = color;
            fx.pos = pos;
            fx.followUid = followUid;
            fx.blink = 2.2f;
            fx.blinkAccelerate = accelerate;
            Apply(fx);
            if (followUid > 0) _rings[followUid] = fx;
        }

        /// <summary>Fades out the ring following this enemy (e.g. its powder fuse was interrupted).</summary>
        public void EndRing(int followUid, float fade = 0.15f)
        {
            if (!_rings.TryGetValue(followUid, out var fx)) return;
            _rings.Remove(followUid);
            if (!fx.alive) return;
            if (fade <= 0f) Release(fx);
            else fx.life = Mathf.Min(fx.life, fx.age + fade);
        }

        private Telegraph NewTelegraph(string name, float seconds)
        {
            var tg = new Telegraph { root = new GameObject("Telegraph " + name), life = Mathf.Max(0.2f, seconds) };
            tg.root.transform.SetParent(_root, false);
            _telegraphs.Add(tg);
            return tg;
        }

        private static void AddPart(Telegraph tg, SpriteRenderer sr, float alpha)
        {
            tg.parts.Add(sr);
            tg.baseAlpha.Add(alpha);
        }

        public void ClearTelegraphs()
        {
            foreach (var t in _telegraphs) if (t.root != null) Destroy(t.root);
            _telegraphs.Clear();
        }

        // =========================================================================================
        // Persistent effects: gravity wells (removed by uid) and the Arc Storm aim reticle
        // =========================================================================================
        public void GravityWell(int uid, Vector2 pos, float radius, float duration)
        {
            var clip = _sp.Anim("fx/gravity_well");
            if (clip == null) return;
            var fx = Get(WorldKit.TelegraphOrder + 10);
            fx.anim.enabled = true;
            fx.anim.Play(clip, true);
            fx.life = duration + 0.25f;
            fx.fadeFrom = 0.85f;
            float native = clip.frames[0].rect.width / SpriteLibrary.WorldPpu;
            fx.scale0 = 0.4f * 2f * radius / native;
            fx.scale1 = 2f * radius / native;
            fx.color = new Color(1f, 1f, 1f, 0.9f);
            fx.pos = pos;
            Apply(fx);
            _wells[uid] = fx;
        }

        public void EndGravityWell(int uid)
        {
            if (_wells.TryGetValue(uid, out var fx))
            {
                _wells.Remove(uid);
                if (fx.alive) fx.life = Mathf.Min(fx.life, fx.age + 0.2f);
            }
        }

        public void ShowReticle(bool show, Vector2 pos, float radius, bool valid)
        {
            if (!show)
            {
                if (_reticle != null) { Release(_reticle); _fx.Remove(_reticle); _reticle = null; }
                return;
            }
            if (_reticle == null || !_reticle.alive)
            {
                var clip = _sp.Anim("fx/target_reticle");
                if (clip == null) return;
                _reticle = Get(WorldKit.TelegraphOrder + 20);
                _reticle.anim.enabled = true;
                _reticle.anim.Play(clip, true);
                _reticle.life = 0f;
                _reticle.anim.UseUnscaledTime = true;
            }
            float native = _reticle.anim.Current != null ? _reticle.anim.Current.frames[0].rect.width / SpriteLibrary.WorldPpu : 2f;
            _reticle.scale0 = _reticle.scale1 = 2f * radius / native;
            _reticle.pos = pos;
            _reticle.color = valid ? Color.white : new Color(1f, 0.45f, 0.45f, 0.8f);
            _reticle.anim.transform.localScale = Vector3.one * _reticle.scale0;
            _reticle.anim.transform.localPosition = new Vector3(pos.x, pos.y, 0f);
            _reticle.sr.color = _reticle.color;
        }

        // =========================================================================================
        // Update
        // =========================================================================================
        private void Update()
        {
            float dt = Time.deltaTime;
            for (int i = _fx.Count - 1; i >= 0; i--)
            {
                var fx = _fx[i];
                if (!fx.alive) { _fx.RemoveAt(i); continue; }
                if (fx == _reticle) continue;   // driven by ShowReticle (unscaled while aiming)
                fx.age += dt;
                bool done = fx.life > 0f ? fx.age >= fx.life : (fx.anim.enabled && fx.anim.Finished);
                if (done)
                {
                    Release(fx);
                    _fx.RemoveAt(i);
                    continue;
                }
                if (fx.followUid == -1)
                {
                    // stretched lightning segment: fade only
                    float t = Mathf.Clamp01(fx.age / fx.life);
                    var c = fx.color;
                    c.a *= t > fx.fadeFrom ? 1f - (t - fx.fadeFrom) / (1f - fx.fadeFrom) : 1f;
                    fx.sr.color = c;
                    continue;
                }
                fx.pos += fx.vel * dt;
                Apply(fx);
            }

            for (int i = _numbers.Count - 1; i >= 0; i--)
            {
                if (UpdateNumber(_numbers[i], dt)) continue;
                _numberPool.Release(_numbers[i].text);
                _numbers.RemoveAt(i);
            }

            Vector2 coinTarget = SparkTarget != null ? SparkTarget() : _view.HeroPos;
            Vector2 xpTarget = _view.HeroCastPoint;
            for (int i = _flyers.Count - 1; i >= 0; i--)
            {
                var f = _flyers[i];
                f.age += dt;
                if (!f.homing)
                {
                    f.pos += f.vel * dt;
                    f.vel.y -= 14f * dt;
                    if (f.age >= f.popTime)
                    {
                        f.homing = true;
                        f.homeFrom = f.pos;
                        f.age = 0f;
                    }
                }
                else
                {
                    float t = Mathf.Clamp01(f.age / f.homeTime);
                    float e = t * t * (3f - 2f * t);
                    Vector2 target = f.coin ? coinTarget : xpTarget;
                    f.pos = Vector2.Lerp(f.homeFrom, target, e) + new Vector2(0f, Mathf.Sin(t * Mathf.PI) * 0.8f);
                    if (t >= 1f)
                    {
                        if (f.coin) CoinArrived?.Invoke();
                        _pool.Release(f.anim);
                        _flyers.RemoveAt(i);
                        continue;
                    }
                }
                f.anim.transform.localPosition = new Vector3(f.pos.x, f.pos.y, 0f);
            }

            for (int i = _telegraphs.Count - 1; i >= 0; i--)
            {
                var tg = _telegraphs[i];
                tg.age += dt;
                if (tg.age >= tg.life || tg.root == null)
                {
                    if (tg.root != null) Destroy(tg.root);
                    _telegraphs.RemoveAt(i);
                    continue;
                }
                float t = tg.age / tg.life;
                float urgency = 1f + 2.5f * t;   // blinks faster as the attack gets closer
                for (int k = 0; k < tg.parts.Count; k++)
                {
                    var sr = tg.parts[k];
                    if (sr == null) continue;
                    float a = tg.baseAlpha[k];
                    if (tg.march) a *= 0.35f + 0.65f * Mathf.Repeat(tg.age * 1.6f * urgency - k * 0.12f, 1f);
                    else a *= 0.55f + 0.45f * Mathf.Sin(tg.age * 6f * urgency);
                    var c = sr.color;
                    c.a = a;
                    sr.color = c;
                }
            }
        }

        /// <summary>Removes everything (used when the battle view is torn down or restarted).</summary>
        public void ClearAll()
        {
            foreach (var fx in _fx) Release(fx);
            _fx.Clear();
            foreach (var n in _numbers) _numberPool.Release(n.text);
            _numbers.Clear();
            foreach (var f in _flyers) _pool.Release(f.anim);
            _flyers.Clear();
            _wells.Clear();
            _rings.Clear();
            _reticle = null;
            ClearTelegraphs();
        }

        private void OnDestroy()
        {
            foreach (var w in _wedges.Values)
                if (w != null) { Destroy(w.texture); Destroy(w); }
            _wedges.Clear();
        }
    }
}
