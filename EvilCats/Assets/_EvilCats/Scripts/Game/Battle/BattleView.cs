using System.Collections.Generic;
using EvilCats.Content;
using EvilCats.Core;
using EvilCats.Meta;
using EvilCats.Sim;
using UnityEngine;

namespace EvilCats.Game
{
    /// <summary>
    /// Renders the battlefield from simulation state + events: terrain generated from the route
    /// data (paths always match the real routes), the citadel with Arc Light Cat and the station
    /// modules, enemies, projectiles and effects. Pure presentation: never changes the simulation.
    /// </summary>
    public sealed class BattleView : MonoBehaviour
    {
        public Battle Battle;
        public CameraRig Rig;
        public FxSystem Fx;
        public UnitViews Units;
        private SpriteLibrary _sp;
        private Transform _world;
        private string _biome;

        // citadel group
        private SpriteRenderer _citadel, _cracks, _reinforce, _barrier;
        private SpriteAnimator _heroAnim, _stormheart, _barrierAnim;
        private SpriteRenderer _heroRenderer;
        private string _heroSkin = "arc_light_cat";
        private readonly Dictionary<string, SpriteAnimator> _stations = new Dictionary<string, SpriteAnimator>();
        private readonly Dictionary<string, string> _stationClipPrefix = new Dictionary<string, string>();
        private readonly Dictionary<string, SpriteRenderer> _slotGlows = new Dictionary<string, SpriteRenderer>();
        private readonly List<SpriteRenderer> _synergyDots = new List<SpriteRenderer>();
        private SpriteRenderer _rangeRing;
        private int _shownReinforce = -1, _shownCracks = -1;

        public Vector2 HeroPos { get; private set; }
        public Vector2 HeroCastPoint => HeroPos + new Vector2(0.45f, 1.9f);

        public void Init(Battle battle, CameraRig rig, string heroSkin)
        {
            Battle = battle;
            Rig = rig;
            _sp = GameApp.I.Sprites;
            _heroSkin = string.IsNullOrEmpty(heroSkin) ? "arc_light_cat" : heroSkin;
            _world = new GameObject("World").transform;
            _world.SetParent(transform, false);
            _biome = battle.Spec.biome ?? "gravewood";
            BuildTerrain();
            BuildCitadel();
            RebuildStations();
            Fx = gameObject.AddComponent<FxSystem>();
            Fx.Init(this, _sp);
            Units = gameObject.AddComponent<UnitViews>();
            Units.Init(this, _sp);
        }

        // ------------------------------------------------------------------------------------
        // Terrain: tiled ground, paths stamped along the actual routes, props kept off the paths.
        // ------------------------------------------------------------------------------------
        private void BuildTerrain()
        {
            var ground = WorldKit.Sprite(_world, "Ground", _sp.Get("env/" + _biome + "/ground"), WorldKit.GroundOrder, Vector2.zero);
            ground.drawMode = SpriteDrawMode.Tiled;
            ground.tileMode = SpriteTileMode.Continuous;
            ground.size = new Vector2(34f, 44f);
            var rng = new Rng(Hash.Fnv1a64(Battle.Spec.missionId + ":terrain"), 4u);
            var pathSprites = new List<Sprite>();
            for (int i = 0; i < 4; i++) { var s = _sp.TryGet("env/" + _biome + "/path/" + i); if (s != null) pathSprites.Add(s); }
            var pathPoints = new List<Vector2>();
            if (pathSprites.Count > 0)
            {
                foreach (var r in Battle.Routes.routes)
                {
                    // extend from the edge (and a little beyond it) to the citadel ring
                    for (float d = -1.5f; d <= r.Length + 0.01f; d += 0.33f)
                    {
                        Vec2 p = d < 0 ? r.Start - (r.Sample(0.5f) - r.Start).Normalized * (-d) : r.Sample(d);
                        Stamp(p, pathSprites, rng);
                        pathPoints.Add(new Vector2(p.x, p.y));
                    }
                    Vec2 end = r.End;
                    Vec2 ring = end.Normalized * (Battle.C.Tuning.arena.meleeRing + 0.2f);
                    for (float t = 0f; t <= 1f; t += 0.15f)
                    {
                        Vec2 p = Vec2.Lerp(end, ring, t);
                        Stamp(p, pathSprites, rng);
                        pathPoints.Add(new Vector2(p.x, p.y));
                    }
                }
            }
            // props: seeded, away from paths, the citadel and each other
            var props = new List<string>();
            string prefix = "env/" + _biome + "/prop/";
            string[] candidates = _biome == "moonfall"
                ? new[] { "cat_statue_a", "cat_statue_b", "pillar_a", "pillar_b", "pillar_c", "rubble_a", "rubble_b", "rubble_c", "crystal_a", "crystal_b", "brazier", "puddle", "banner_torn", "grass_a", "grass_b" }
                : new[] { "tree_dead_a", "tree_dead_b", "tree_dead_c", "wall_broken_a", "wall_broken_b", "wall_broken_c", "grave_a", "grave_b", "grave_c", "grave_d", "bush_a", "bush_b", "mushroom_a", "mushroom_b", "lantern_post", "stump", "rock_a", "rock_b", "grass_a", "grass_b", "grass_c" };
            foreach (var c in candidates) if (_sp.Has(prefix + c)) props.Add(c);
            var placed = new List<Vector2>();
            int attempts = 0;
            while (placed.Count < 30 && attempts++ < 600 && props.Count > 0)
            {
                var p = new Vector2(rng.Range(-11f, 11f), rng.Range(-13f, 13f));
                if (p.magnitude < 4.2f) continue;
                bool bad = false;
                foreach (var q in pathPoints) if ((q - p).sqrMagnitude < 1.2f * 1.2f) { bad = true; break; }
                if (bad) continue;
                foreach (var q in placed) if ((q - p).sqrMagnitude < 1.5f * 1.5f) { bad = true; break; }
                if (bad) continue;
                placed.Add(p);
                string name = props[rng.Range(0, props.Count)];
                var sr = WorldKit.Sprite(_world, name, _sp.Get(prefix + name), WorldKit.SortY(p.y), p);
                if (rng.Chance(0.5f)) sr.flipX = true;
            }
        }

        private void Stamp(Vec2 p, List<Sprite> sprites, Rng rng)
        {
            var sr = WorldKit.Sprite(_world, "Path", sprites[rng.Range(0, sprites.Count)], WorldKit.PathOrder + rng.Range(0, 3),
                new Vector2(p.x + rng.Range(-0.08f, 0.08f), p.y + rng.Range(-0.08f, 0.08f)));
            sr.flipX = rng.Chance(0.5f);
            sr.flipY = rng.Chance(0.5f);
        }

        // ------------------------------------------------------------------------------------
        // Citadel, Arc Light Cat and stations
        // ------------------------------------------------------------------------------------
        private void BuildCitadel()
        {
            var root = new GameObject("Citadel").transform;
            root.SetParent(_world, false);
            var shadow = _sp.TryGet("citadel/shadow");
            if (shadow != null) WorldKit.Sprite(root, "Shadow", shadow, WorldKit.CitadelOrder - 2, Vector2.zero);
            _citadel = WorldKit.Sprite(root, "Base", _sp.Get("citadel/base"), WorldKit.CitadelOrder, Vector2.zero);
            _reinforce = WorldKit.Sprite(root, "Reinforce", null, WorldKit.CitadelOrder + 1, Vector2.zero);
            _cracks = WorldKit.Sprite(root, "Cracks", null, WorldKit.CitadelOrder + 1, Vector2.zero);
            var sh = WorldKit.Sprite(root, "Stormheart", null, WorldKit.StormheartOrder, Anchor("stormheart", new Vector2(-1.2f, 2.2f)));
            _stormheart = sh.gameObject.AddComponent<SpriteAnimator>();
            _stormheart.Target = sh;
            _stormheart.UseUnscaledTime = false;
            _stormheart.Play(_sp.Anim("citadel/stormheart"));
            HeroPos = Anchor("hero", new Vector2(0f, 0.75f));
            _heroRenderer = WorldKit.Sprite(root, "ArcLightCat", null, WorldKit.HeroOrder, HeroPos);
            _heroAnim = _heroRenderer.gameObject.AddComponent<SpriteAnimator>();
            _heroAnim.Target = _heroRenderer;
            _heroAnim.UseUnscaledTime = false;
            HeroIdle();
            var bar = WorldKit.Sprite(root, "Barrier", null, WorldKit.FxOrder - 10, Anchor("barrier_center", new Vector2(0f, 1f)));
            bar.transform.localScale = Vector3.one * 0.78f;
            _barrierAnim = bar.gameObject.AddComponent<SpriteAnimator>();
            _barrierAnim.Target = bar;
            _barrierAnim.UseUnscaledTime = false;
            _barrierAnim.Play(_sp.Anim("fx/barrier_ring"));
            _barrier = bar;
            _barrier.enabled = false;
            var ring = _sp.TryGet("fx/range_ring");
            if (ring != null)
            {
                _rangeRing = WorldKit.Sprite(_world, "RangeRing", ring, WorldKit.TelegraphOrder + 5, Vector2.zero, new Color(0.4f, 0.95f, 1f, 0.35f));
                _rangeRing.enabled = false;
            }
        }

        private Vector2 Anchor(string name, Vector2 fallback)
        {
            return _sp.TryAnchor("citadel/base", name, out var o) ? o : fallback;
        }

        public Vector2 SlotAnchor(string slot)
        {
            switch (slot)
            {
                case "crown": return Anchor("crown", new Vector2(0f, 3.9f));
                case "middle": return Anchor("middle", new Vector2(2.06f, 0.81f));
                default: return Anchor("base", new Vector2(0f, -1.06f));
            }
        }

        private static int SlotOrder(string slot) => slot == "crown" ? WorldKit.CrownOrder : slot == "middle" ? WorldKit.MiddleOrder : WorldKit.BaseOrder;

        /// <summary>Rebuild station sprites (loadout changes, tier visuals, synergy links).</summary>
        public void RebuildStations()
        {
            foreach (var kv in _stations) if (kv.Value != null) Destroy(kv.Value.gameObject);
            _stations.Clear();
            _stationClipPrefix.Clear();
            foreach (var g in _slotGlows.Values) if (g != null) Destroy(g.gameObject);
            _slotGlows.Clear();
            var meta = GameApp.I.Meta;
            int dmgLevel = Battle.UpgradeLevel("damage");
            foreach (var slot in Battle.C.Tuning.slots)
            {
                Vector2 at = SlotAnchor(slot.id);
                if (Battle.Loadout.TryGetValue(slot.id, out var moduleId) && !string.IsNullOrEmpty(moduleId))
                {
                    int tier = Battle.Setup.ignorePermanent ? 1 : (Battle.Setup.moduleTiers.TryGetValue(moduleId, out var t) ? t : 1);
                    // purchased run upgrades visibly improve the weapons too
                    int visual = Mathf.Min(3, GameMeta.VisualTier(tier) + (dmgLevel >= 8 ? 1 : 0));
                    string prefix = "station/" + moduleId + "/t" + visual + "/";
                    var sr = WorldKit.Sprite(_world, moduleId, null, SlotOrder(slot.id), at);
                    var anim = sr.gameObject.AddComponent<SpriteAnimator>();
                    anim.Target = sr;
                    anim.UseUnscaledTime = false;
                    anim.Play(_sp.Anim(prefix + "idle"));
                    _stations[slot.id] = anim;
                    _stationClipPrefix[slot.id] = prefix;
                }
                else if (Battle.UnlockedSlots.Contains(slot.id))
                {
                    var glow = _sp.TryGet("citadel/slot_glow");
                    if (glow != null) _slotGlows[slot.id] = WorldKit.Sprite(_world, "SlotGlow " + slot.id, glow, SlotOrder(slot.id), at);
                }
            }
            BuildSynergyLinks();
        }

        private void BuildSynergyLinks()
        {
            foreach (var d in _synergyDots) if (d != null) Destroy(d.gameObject);
            _synergyDots.Clear();
            var dot = _sp.TryGet("fx/synergy_link");
            if (dot == null) return;
            foreach (var syn in StatsBuilder.ActiveSynergies(Battle.C, new Dictionary<string, string>(Battle.Loadout)))
            {
                string a = StatsBuilder.SlotOf(Battle.Loadout, syn.a), b = StatsBuilder.SlotOf(Battle.Loadout, syn.b);
                Vector2 pa = SlotAnchor(a) + new Vector2(0f, 0.5f), pb = SlotAnchor(b) + new Vector2(0f, 0.5f);
                int n = Mathf.Max(3, Mathf.RoundToInt(Vector2.Distance(pa, pb) / 0.35f));
                for (int i = 1; i < n; i++)
                    _synergyDots.Add(WorldKit.Sprite(_world, "Synergy", dot, WorldKit.BaseOrder + 1, Vector2.Lerp(pa, pb, i / (float)n)));
            }
        }

        public void StationFired(string slot)
        {
            if (slot == null || !_stations.TryGetValue(slot, out var anim) || anim == null) return;
            string prefix = _stationClipPrefix[slot];
            anim.Play(_sp.Anim(prefix + "fire"), true, _sp.Anim(prefix + "idle"));
        }

        public Vector2 StationMuzzle(string slot) => SlotAnchor(slot) + new Vector2(0f, 1.0f);

        public void HeroIdle() => _heroAnim.Play(_sp.Anim("hero/" + _heroSkin + "/idle"));

        public void HeroClip(string clip, bool returnToIdle = true)
        {
            var a = _sp.Anim("hero/" + _heroSkin + "/" + clip);
            if (a == null) return;
            _heroAnim.Play(a, true, returnToIdle ? _sp.Anim("hero/" + _heroSkin + "/idle") : null);
        }

        public bool HeroBusy => _heroAnim.Current != null && !_heroAnim.Current.loop && !_heroAnim.Finished;

        public void ShowRange(bool show, float radius)
        {
            if (_rangeRing == null) return;
            _rangeRing.enabled = show;
            if (show)
            {
                float native = _rangeRing.sprite.rect.width / SpriteLibrary.WorldPpu;   // diameter in units
                _rangeRing.transform.localScale = Vector3.one * (2f * radius / native);
            }
        }

        private void Update()
        {
            if (Battle == null) return;
            // barrier visual, distinct from health: a shimmering ring while any barrier exists
            bool barrier = Battle.BarrierTotal > 0.5f;
            if (_barrier.enabled != barrier) _barrier.enabled = barrier;
            if (barrier) _barrier.color = new Color(1f, 1f, 1f, Mathf.Lerp(0.45f, 1f, Mathf.Clamp01(Battle.BarrierTotal / (Battle.MaxHp * 0.25f))));
            // damage state overlays
            float hp = Battle.MaxHp > 0 ? Battle.Hp / Battle.MaxHp : 1f;
            int cracks = hp <= 0.25f ? 2 : hp <= 0.5f ? 1 : 0;
            if (cracks != _shownCracks)
            {
                _shownCracks = cracks;
                _cracks.sprite = cracks == 0 ? null : _sp.TryGet("citadel/cracks" + cracks);
            }
            int maxLvl = Battle.UpgradeLevel("max_health");
            int reinforce = maxLvl >= 11 ? 3 : maxLvl >= 7 ? 2 : maxLvl >= 3 ? 1 : 0;
            if (reinforce != _shownReinforce)
            {
                _shownReinforce = reinforce;
                _reinforce.sprite = reinforce == 0 ? null : _sp.TryGet("citadel/reinforce" + reinforce);
            }
        }

        public void ShowRuin()
        {
            var ruin = _sp.TryGet("citadel/ruin");
            if (ruin != null) { _citadel.sprite = ruin; _cracks.sprite = null; _reinforce.sprite = null; }
            _stormheart.gameObject.SetActive(false);
            foreach (var s in _stations.Values) if (s != null) s.gameObject.SetActive(false);
        }
    }
}
