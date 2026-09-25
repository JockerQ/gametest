using System.Collections.Generic;
using EvilCats.Content;

namespace EvilCats.Game
{
    /// <summary>
    /// Checks that every piece of art the game will ask for actually exists, derived from the
    /// content data (modules, enemies, bosses, perks, cosmetics...) plus the fixed effect/UI names
    /// used by the presentation code. Used by the Editor menu, the build pre-check and tests, so a
    /// missing sprite is reported before a player could ever see a magenta placeholder.
    /// </summary>
    public static class AssetAudit
    {
        /// <summary>Animation clips the battle presentation plays by name.</summary>
        public static readonly string[] FxClips =
        {
            "fx/arc_storm_strike", "fx/barrier_ring", "fx/bleed", "fx/boss_aura", "fx/burn", "fx/coin", "fx/death_poof",
            "fx/dust", "fx/elite_aura", "fx/explosion", "fx/frost_burst", "fx/gravity_well", "fx/heal", "fx/impact",
            "fx/level_up", "fx/powder_blast", "fx/priest_heal_ring", "fx/shatter", "fx/shell", "fx/spark_hit", "fx/stun",
            "fx/target_reticle", "fx/winter_ring", "fx/xp_orb", "fx/feather", "citadel/stormheart",
        };

        /// <summary>Single sprites the presentation and UI use by name.</summary>
        public static readonly string[] Sprites =
        {
            "fx/armour_break", "fx/arrow", "fx/ballista_bolt", "fx/chill", "fx/frozen", "fx/lightning_tex", "fx/mark",
            "fx/range_ring", "fx/sector_edge", "fx/shadow", "fx/synergy_link", "fx/telegraph_chevron", "fx/telegraph_circle",
            "fx/telegraph_fill", "citadel/base", "citadel/shadow", "citadel/cracks1", "citadel/cracks2", "citadel/reinforce1",
            "citadel/reinforce2", "citadel/reinforce3", "citadel/ruin", "citadel/slot_glow", "logo/emblem",
            "ui/badge", "ui/bar_bg", "ui/bar_fill", "ui/button", "ui/button_disabled", "ui/button_gold", "ui/button_pressed",
            "ui/button_red", "ui/card", "ui/dock", "ui/panel", "ui/panel_inset", "ui/ring", "ui/slider_bg", "ui/slider_fill",
            "ui/slider_handle", "ui/slot_frame", "ui/tab", "ui/tab_active", "ui/toggle_off", "ui/toggle_on", "ui/tooltip",
            "ui/topbar", "ui/vignette", "ui/white",
        };

        public static readonly string[] CitadelAnchors = { "hero", "stormheart", "crown", "middle", "base", "barrier_center" };

        public static List<string> Run(GameContent c, SpriteLibrary sp)
        {
            var problems = new List<string>();
            if (c == null || sp == null) { problems.Add("content or sprites not loaded"); return problems; }
            problems.AddRange(sp.Problems);
            void Sprite(string name, string why) { if (!sp.Has(name)) problems.Add("missing sprite '" + name + "' (" + why + ")"); }
            void Clip(string name, string why) { if (!sp.HasAnim(name)) problems.Add("missing animation '" + name + "' (" + why + ")"); }

            foreach (var n in FxClips) Clip(n, "effects");
            foreach (var n in Sprites) Sprite(n, "presentation/UI");
            foreach (var a in CitadelAnchors)
                if (!sp.TryAnchor("citadel/base", a, out _)) problems.Add("citadel/base is missing anchor '" + a + "'");

            foreach (var m in c.Modules)
            {
                Sprite("icon/module/" + m.id, "module icon");
                Sprite("portrait/" + m.id, "module portrait");
                for (int t = 1; t <= 3; t++)
                {
                    Clip("station/" + m.id + "/t" + t + "/idle", "station art");
                    Clip("station/" + m.id + "/t" + t + "/fire", "station art");
                }
            }
            foreach (var p in c.Perks) Sprite("icon/perk/" + p.id, "perk icon");
            foreach (var u in c.Upgrades) Sprite("icon/" + (string.IsNullOrEmpty(u.icon) ? "up_arrow" : u.icon), "upgrade icon");
            foreach (var e in c.Enemies)
            {
                if (e.swarmCount > 1 && !string.IsNullOrEmpty(e.unitId)) { Sprite("icon/enemy/" + e.id, "enemy icon"); continue; }
                string move = e.flying ? "fly" : "walk";
                foreach (var variant in new[] { e.id, e.id + "_elite" })
                {
                    Clip("enemy/" + variant + "/" + move, "enemy movement");
                    Clip("enemy/" + variant + "/death", "enemy death");
                    Clip("enemy/" + variant + "/attack", "enemy attack");
                }
                if (!e.isUnitOnly) Sprite("icon/enemy/" + e.id, "enemy icon");
            }
            foreach (var b in c.Bosses)
            {
                Clip("boss/" + b.id + "/" + (b.flying ? "fly" : "walk"), "boss movement");
                Clip("boss/" + b.id + "/defeat", "boss defeat");
                Sprite("portrait/" + b.id, "boss portrait");
                Sprite("icon/enemy/" + b.id, "boss icon");
            }
            foreach (var cos in c.Progression.cosmetics)
                if (cos.kind == "hero_skin")
                    foreach (var clip in new[] { "idle", "attack", "cast", "hit", "victory", "defeat" })
                        Clip("hero/" + cos.id + "/" + clip, "hero skin");
            foreach (var a in c.Progression.avatars) Sprite("avatar/" + a, "avatar");
            var biomes = new HashSet<string>();
            foreach (var m in c.Missions) biomes.Add(m.biome);
            foreach (var b in biomes)
            {
                Sprite("env/" + b + "/ground", "biome ground");
                Sprite("env/" + b + "/path/0", "biome path");
            }
            return problems;
        }
    }
}
