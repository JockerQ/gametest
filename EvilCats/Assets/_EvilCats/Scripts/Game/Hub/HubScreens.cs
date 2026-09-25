using System.Collections.Generic;
using EvilCats.Content;
using EvilCats.Meta;
using EvilCats.Sim;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

namespace EvilCats.Game
{
    /// <summary>Small helpers shared by the hub screens.</summary>
    public static class HubKit
    {
        /// <summary>Places a sprite at native pixel-art scale with its real pivot at `pos` (UI units).</summary>
        public static Image PlaceSprite(RectTransform parent, Sprite sprite, Vector2 pos, string name = "Sprite")
        {
            var img = UI.Img(parent, null, null, false, name);
            img.sprite = sprite;
            if (sprite == null) return img;
            img.SetNativeSize();
            var r = sprite.rect;
            img.rectTransform.anchorMin = img.rectTransform.anchorMax = new Vector2(0.5f, 0f);
            img.rectTransform.pivot = new Vector2(sprite.pivot.x / r.width, sprite.pivot.y / r.height);
            img.rectTransform.anchoredPosition = pos;
            return img;
        }

        /// <summary>An animated world clip shown in the UI at `upp` UI units per art pixel.</summary>
        public static Image AnimatedSprite(RectTransform parent, string clip, float upp, Vector2 pos)
        {
            var sp = GameApp.I.Sprites;
            var anim = sp.Anim(clip);
            if (anim == null || anim.frames.Length == 0 || anim.frames[0] == null) return null;
            var frames = new Sprite[anim.frames.Length];
            for (int i = 0; i < frames.Length; i++) frames[i] = anim.frames[i] != null ? sp.GetForUi(anim.frames[i].name, upp) : null;
            var img = PlaceSprite(parent, frames[0], pos, clip);
            var a = img.gameObject.AddComponent<UIImageAnimator>();
            a.Target = img;
            a.Frames = frames;
            a.Fps = anim.fps;
            return img;
        }

        public static Color BannerColor(string bannerId)
        {
            switch (bannerId)
            {
                case "banner_crimson": return Theme.Hex("d23b4a");
                case "banner_moon": return Theme.Hex("c9d4ff");
                case "banner_storm": return Theme.Hex("62eeff");
                case "banner_supporter": return Theme.Hex("ffd24a");
                default: return Theme.Hex("a57ad6");
            }
        }

        /// <summary>A bordered card (vertical layout inside) for list screens.</summary>
        public static RectTransform Card(Transform parent, float minHeight = 0f, string sprite = "ui/card", Color? tint = null)
        {
            var img = UI.Img(parent, sprite, tint, true, "Card");
            img.type = Image.Type.Sliced;
            img.preserveAspect = false;
            var v = UI.VLayout(img, Theme.S1, 0f, TextAnchor.UpperLeft);
            v.padding = new RectOffset(12, 12, 10, 10);
            if (minHeight > 0f) UI.Size(img, -1, -1, -1, -1, minHeight);
            return img.rectTransform;
        }

        public static RectTransform Row(Transform parent, float height, float spacing = Theme.S2)
        {
            var r = UI.Rect(parent, "Row");
            UI.Size(r, -1, height, -1, -1, height);
            var h = UI.HLayout(r, spacing, 0f, TextAnchor.MiddleLeft, false);
            h.childForceExpandWidth = false;
            return r;
        }

        public static TextMeshProUGUI Label(Transform parent, string text, float size, Color color, bool bold = false, float width = -1f, float flex = -1f)
        {
            var t = UI.Text(parent, text, size, color, TextAlignmentOptions.MidlineLeft, bold);
            t.overflowMode = TextOverflowModes.Overflow;
            UI.Size(t, width, -1, flex);
            return t;
        }

        public static TextMeshProUGUI Wrap(Transform parent, string text, float size, Color color, TextAlignmentOptions align = TextAlignmentOptions.TopLeft)
        {
            var t = UI.Text(parent, text, size, color, align);
            t.overflowMode = TextOverflowModes.Overflow;
            return t;
        }

        public static RectTransform Section(Transform parent, string title)
        {
            var t = UI.Text(parent, title, Theme.FontH2, Theme.Cyan, TextAlignmentOptions.BottomLeft, true, "Section");
            UI.Size(t, -1, 30f);
            return t.rectTransform;
        }

        public static string MissionName(string id) => L.T("mission." + id + ".name");
    }

    // =============================================================================================
    // Home: the citadel diorama, the next mission and quick entries
    // =============================================================================================
    public sealed class HomeScreen : HubScreen
    {
        public override string Tab => "home";

        public override void Build(RectTransform content)
        {
            var scroll = UI.ScrollList(content, out _, Theme.S3, Theme.S3);
            UI.Stretch((RectTransform)scroll.parent.parent);
            BuildDiorama(scroll);
            var cp = Data.activeRun;
            if (cp != null)
            {
                var resume = HubKit.Card(scroll, 0f, "ui/card", Theme.Cyan);
                HubKit.Label(resume, L.T("ui.resume_title"), Theme.FontH2, Theme.Cyan, true);
                HubKit.Wrap(resume, L.F("ui.resume_body", ("mission", cp.mode == BattleMode.Campaign ? HubKit.MissionName(cp.missionId) : cp.mode == BattleMode.Endless ? L.T("ui.endless") : L.T("ui.daily.challenge")), ("wave", cp.nextWave)), Theme.FontSmall, Theme.Text);
                UI.Button(resume, L.T("ui.resume"), Hub.OfferResume, ButtonStyle.Primary, "icon/play", 48f);
            }
            var next = Meta.NextCampaignMission();
            if (next != null)
            {
                var card = HubKit.Card(scroll);
                HubKit.Label(card, L.T("biome." + next.biome) + " · " + next.index + "/" + C.Missions.Count, Theme.FontTiny, Theme.TextDim);
                HubKit.Label(card, HubKit.MissionName(next.id), Theme.FontH1, Theme.Gold, true);
                HubKit.Wrap(card, L.T("mission." + next.id + ".desc"), Theme.FontSmall, Theme.Text);
                var rec = Data.missions.TryGetValue(next.id, out var r) ? r : null;
                string status = rec != null && rec.cleared ? L.T("mission.cleared") : rec != null && rec.bestWave > 0 ? L.F("mission.best", ("n", rec.bestWave)) : L.F("mission.waves", ("n", next.waves));
                HubKit.Label(card, status, Theme.FontTiny, Theme.TextDim);
                UI.Button(card, L.T("ui.play"), () => Hub.Open(new LoadoutScreen(next.id)), ButtonStyle.Primary, "icon/play", 56f, Theme.FontH1);
            }
            var row = UI.Rect(scroll, "Modes");
            UI.Size(row, -1, 56f, -1, -1, 56f);
            UI.HLayout(row, Theme.S2, 0f);
            ModeButton(row, L.T("ui.daily.challenge"), "icon/calendar", Meta.DailyUnlocked, L.F("ui.daily.challenge_locked", ("mission", HubKit.MissionName(C.Daily.requiresMission))), () => Hub.Open(new DailyScreen(), true));
            ModeButton(row, L.T("ui.endless"), "icon/star_burst", Meta.EndlessUnlocked, L.F("ui.endless_locked", ("mission", HubKit.MissionName(C.Endless.requiresMission))), () => Hub.Open(new MissionsScreen(), true));
        }

        private void ModeButton(RectTransform row, string label, string icon, bool unlocked, string lockedReason, System.Action open)
        {
            var b = UI.Button(row, label, () =>
            {
                if (!unlocked) { App.Audio?.Play("ui_denied"); Toast.Show(lockedReason); return; }
                open();
            }, ButtonStyle.Normal, unlocked ? icon : "icon/lock", 52f, Theme.FontBody);
            if (!unlocked) b.GetComponent<Image>().color = new Color(1f, 1f, 1f, 0.55f);
        }

        /// <summary>The citadel with Arc Light Cat and the equipped stations, drawn from the battle art.</summary>
        private void BuildDiorama(RectTransform parent)
        {
            var sp = App.Sprites;
            const float upp = 1.6f;    // UI units per art pixel
            var box = UI.Img(parent, "ui/panel_inset", null, false, "Diorama");
            box.type = Image.Type.Sliced;
            box.preserveAspect = false;
            UI.Size(box, -1, 270f, -1, -1, 270f);
            box.gameObject.AddComponent<RectMask2D>();
            string biome = Meta.NextCampaignMission() != null ? Meta.NextCampaignMission().biome : "gravewood";
            var ground = UI.Img(box.transform, null, new Color(1f, 1f, 1f, 0.55f), false, "Ground");
            ground.sprite = sp.GetForUi("env/" + biome + "/ground", upp);
            ground.type = Image.Type.Tiled;
            ground.preserveAspect = false;
            UI.Stretch(ground.rectTransform, 4, 4, 4, 4);
            var stage = UI.Rect(box.transform, "Stage");
            stage.anchorMin = new Vector2(0.5f, 0f);
            stage.anchorMax = new Vector2(0.5f, 0f);
            stage.sizeDelta = Vector2.zero;
            stage.anchoredPosition = Vector2.zero;
            Vector2 p = new Vector2(0f, 60f);   // citadel pivot inside the box
            var shadow = sp.TryGet("citadel/shadow");
            if (shadow != null) HubKit.PlaceSprite(stage, sp.GetForUi("citadel/shadow", upp), p, "Shadow");
            HubKit.PlaceSprite(stage, sp.GetForUi("citadel/base", upp), p, "Citadel");
            float px = 16f * upp;   // world units -> UI units
            if (sp.TryAnchor("citadel/base", "stormheart", out var sh)) HubKit.AnimatedSprite(stage, "citadel/stormheart", upp, p + sh * px);
            foreach (var slot in C.Tuning.slots)
            {
                if (!Data.loadout.TryGetValue(slot.id, out var mod) || string.IsNullOrEmpty(mod)) continue;
                if (!sp.TryAnchor("citadel/base", slot.id, out var at)) continue;
                int visual = GameMeta.VisualTier(Data.ModuleTier(mod));
                HubKit.AnimatedSprite(stage, "station/" + mod + "/t" + visual + "/idle", upp, p + at * px);
            }
            Vector2 heroAt = sp.TryAnchor("citadel/base", "hero", out var ha) ? p + ha * px : p + new Vector2(0f, 21f);
            HubKit.AnimatedSprite(stage, "hero/" + Data.heroSkin + "/idle", upp, heroAt);
            // banner cosmetic: a flag in the banner colour on each side of the citadel
            foreach (float side in new[] { -1f, 1f })
            {
                var flag = UI.Icon(stage, "icon/flag", 30f, HubKit.BannerColor(Data.banner));
                flag.rectTransform.anchorMin = flag.rectTransform.anchorMax = new Vector2(0.5f, 0f);
                flag.rectTransform.anchoredPosition = p + new Vector2(side * 110f, 40f);
            }
            var title = UI.Text(box.transform, L.T("game.title").ToUpperInvariant(), Theme.FontH1, Theme.Cyan, TextAlignmentOptions.Top, true, "Title");
            UI.Stretch(title.rectTransform, 8, 8, 8, 8);
            title.outlineWidth = 0.2f;
            title.outlineColor = new Color32(30, 12, 50, 255);
            var hero = UI.Text(box.transform, L.T("hero.name"), Theme.FontSmall, Theme.TextDim, TextAlignmentOptions.Top, false, "Hero");
            UI.Stretch(hero.rectTransform, 8, 34, 8, 8);
        }
    }

    // =============================================================================================
    // More: secondary screens
    // =============================================================================================
    public sealed class MoreScreen : HubScreen
    {
        public override string TitleKey => "ui.more";
        public override string Tab => "more";

        public override void Build(RectTransform content)
        {
            var list = UI.ScrollList(content, out _, Theme.S2, Theme.S4);
            UI.Stretch((RectTransform)list.parent.parent);
            int ready = 0;
            foreach (var a in C.Progression.achievements) if (Meta.AchievementReady(a.id)) ready++;
            Entry(list, "icon/trophy", L.T("ui.achievements") + (ready > 0 ? "  (" + ready + ")" : ""), () => Hub.Open(new AchievementsScreen()));
            Entry(list, "icon/star", L.T("ui.records"), () => Hub.Open(new RecordsScreen()));
            Entry(list, "icon/shop", L.T("ui.shop"), () => Hub.Open(new ShopScreen()));
            Entry(list, "icon/profile", L.T("ui.profile"), () => Hub.Open(new ProfileScreen()));
            Entry(list, "icon/settings", L.T("ui.settings"), () => Hub.Open(new SettingsScreen()));
            Entry(list, "icon/info", L.T("ui.credits"), () => Hub.Open(new CreditsScreen()));
        }

        private static void Entry(RectTransform list, string icon, string label, System.Action open)
        {
            var b = UI.Button(list, label, open, ButtonStyle.Normal, icon, 56f, Theme.FontH2);
            UI.Size(b, -1, 56f, -1, -1, 56f);
        }
    }

    public sealed class CreditsScreen : HubScreen
    {
        public override string TitleKey => "ui.credits.title";
        public override string Tab => "more";

        public override void Build(RectTransform content)
        {
            var list = UI.ScrollList(content, out _, Theme.S3, Theme.S4);
            UI.Stretch((RectTransform)list.parent.parent);
            var logo = UI.Img(list, "logo/emblem", null, false, "Logo");
            logo.preserveAspect = true;
            UI.Size(logo, -1, 96f, -1, -1, 96f);
            HubKit.Wrap(list, L.T("ui.credits.body"), Theme.FontSmall, Theme.Text, TextAlignmentOptions.Top);
            HubKit.Wrap(list, L.T("ui.credits.licenses"), Theme.FontTiny, Theme.TextDim, TextAlignmentOptions.Top);
            HubKit.Wrap(list, L.T("ui.credits.privacy"), Theme.FontTiny, Theme.TextDim, TextAlignmentOptions.Top);
            HubKit.Wrap(list, L.T("ui.credits.support"), Theme.FontTiny, Theme.TextDim, TextAlignmentOptions.Top);
            HubKit.Wrap(list, L.F("ui.credits.version", ("v", GameApp.Version)), Theme.FontTiny, Theme.TextMuted, TextAlignmentOptions.Top);
        }
    }

    // =============================================================================================
    // Results: shown on returning from a battle
    // =============================================================================================
    public sealed class ResultsScreen : HubScreen
    {
        private readonly BattleOutcome _o;
        public ResultsScreen(BattleOutcome o) { _o = o; }
        public override string TitleKey => "ui.rewards";
        public override string Tab => "home";

        public override void Build(RectTransform content)
        {
            var list = UI.ScrollList(content, out _, Theme.S3, Theme.S4);
            UI.Stretch((RectTransform)list.parent.parent);
            var r = _o.result;
            var rw = _o.rewards;
            var head = UI.Text(list, r.victory ? L.T("ui.victory") : L.T("ui.defeat"), Theme.FontTitle, r.victory ? Theme.Gold : Theme.Red, TextAlignmentOptions.Center, true);
            UI.Size(head, -1, 40f);
            string where = r.mode == BattleMode.Campaign ? HubKit.MissionName(r.missionId) : r.mode == BattleMode.Endless ? L.T("ui.endless") : L.T("ui.daily.challenge");
            HubKit.Wrap(list, where, Theme.FontBody, Theme.TextDim, TextAlignmentOptions.Center);
            var card = HubKit.Card(list);
            HubKit.Label(card, r.totalWaves > 0 ? L.F("ui.waves_cleared", ("n", r.wavesCleared), ("total", r.totalWaves)) : L.F("ui.waves_cleared_endless", ("n", r.wavesCleared)), Theme.FontBody, Theme.Text);
            HubKit.Label(card, L.F("ui.kills", ("n", r.stats.kills)), Theme.FontSmall, Theme.Text);
            HubKit.Label(card, L.F("ui.level_reached", ("n", r.levelReached)), Theme.FontSmall, Theme.Text);
            HubKit.Label(card, L.F("ui.time", ("t", TextFormat.Duration(r.stats.timeSec))), Theme.FontSmall, Theme.Text);
            if (r.mode != BattleMode.Campaign) HubKit.Label(card, L.F("ui.score", ("n", r.score)), Theme.FontSmall, Theme.Gold);

            if (rw != null)
            {
                var rc = HubKit.Card(list, 0f, "ui/card", Theme.Gold);
                HubKit.Label(rc, L.T("ui.rewards"), Theme.FontH2, Theme.Gold, true);
                bool any = false;
                if (rw.moonGold > 0) { Reward(rc, "icon/moon_gold", "+" + TextFormat.Compact(rw.moonGold) + " " + L.T("ui.moon_gold")); any = true; }
                if (rw.stormShards > 0) { Reward(rc, "icon/storm_shard", "+" + rw.stormShards + " " + L.T("ui.storm_shards")); any = true; }
                if (rw.firstClear) { Reward(rc, "icon/star", L.T("ui.first_clear")); any = true; }
                if (rw.newRecord) { Reward(rc, "icon/trophy", L.T("ui.new_record")); any = true; }
                foreach (var slot in rw.slotsUnlocked) { Reward(rc, "icon/plus", L.F("announce.slot_unlocked", ("slot", L.T("slot." + slot + ".name")))); any = true; }
                if (!any) HubKit.Wrap(rc, L.T("ui.no_rewards"), Theme.FontSmall, Theme.TextDim);
                if (!string.IsNullOrEmpty(rw.moduleUnlocked))
                {
                    var mc = HubKit.Card(list, 0f, "ui/card", Theme.Cyan);
                    HubKit.Label(mc, L.F("ui.unlocked_module", ("name", L.T("module." + rw.moduleUnlocked + ".name"))), Theme.FontBody, Theme.Cyan, true);
                    if (rw.moduleNeedsShards) HubKit.Wrap(mc, L.T("ui.module_needs_shards"), Theme.FontSmall, Theme.Text);
                    UI.Button(mc, L.T("ui.modules"), () => Hub.Open(new StationsScreen(), true), ButtonStyle.Normal, "icon/module/" + rw.moduleUnlocked, 46f, Theme.FontBody);
                }
                if (rw.achievementsReady.Count > 0)
                    UI.Button(list, L.F("ui.achievements_ready", ("n", rw.achievementsReady.Count)), () => Hub.Open(new AchievementsScreen()), ButtonStyle.Normal, "icon/trophy", 48f, Theme.FontBody);
                if (rw.objectivesReady.Count > 0)
                    UI.Button(list, L.T("ui.daily.objectives") + " (" + rw.objectivesReady.Count + ")", () => Hub.Open(new DailyScreen(), true), ButtonStyle.Normal, "icon/calendar", 48f, Theme.FontBody);
            }
            if (!r.victory && !string.IsNullOrEmpty(r.principalDamageSource))
            {
                var tip = HubKit.Card(list);
                HubKit.Wrap(tip, L.F("ui.defeat_cause", ("source", StatText.SourceName(C, r.principalDamageSource)), ("pct", TextFormat.Percent(r.principalDamageShare))), Theme.FontSmall, Theme.Red);
                HubKit.Wrap(tip, "<b>" + L.T("ui.defeat_try") + ":</b> " + L.T(StatText.TipKey(C, r.principalDamageSource)), Theme.FontSmall, Theme.Cyan);
                HubKit.Wrap(tip, L.T("ui.defeat_upgrade_hint"), Theme.FontTiny, Theme.TextDim);
            }
            var row = UI.Rect(list, "Buttons");
            UI.Size(row, -1, 56f, -1, -1, 56f);
            UI.HLayout(row, Theme.S2, 0f);
            if (r.mode == BattleMode.Campaign && C.Mission(r.missionId) != null)
                UI.Button(row, L.T("ui.retry"), () => Hub.Open(new LoadoutScreen(r.missionId)), ButtonStyle.Normal, "icon/refresh", 52f, Theme.FontBody);
            UI.Button(row, L.T("ui.continue"), () => Hub.Open(new HomeScreen(), true), ButtonStyle.Primary, "icon/home", 52f, Theme.FontBody);

            // chapter ending (once): after Sir Barkhelm and after King Goldenfang
            if (rw != null && !string.IsNullOrEmpty(rw.chapterScene) && !Data.tutorial.chapterScenesSeen.Contains(rw.chapterScene))
            {
                Data.tutorial.chapterScenesSeen.Add(rw.chapterScene);
                App.SaveNow();
                string boss = rw.chapterScene == "gravewood" ? "sir_barkhelm" : "king_goldenfang";
                var d = Hub.Dialog(320f);
                var portrait = UI.Img(d, "portrait/" + boss, null, false, "Portrait");
                portrait.preserveAspect = true;
                UI.Size(portrait, -1, 120f);
                var t = UI.Text(d, L.T("biome." + rw.chapterScene), Theme.FontH2, Theme.Gold, TextAlignmentOptions.Center, true);
                UI.Size(t, -1, 26f);
                HubKit.Wrap(d, L.T("chapter." + rw.chapterScene + ".end"), Theme.FontBody, Theme.Text, TextAlignmentOptions.Center);
                UI.Button(d, L.T("ui.continue"), () => Hub.CloseDialog(d), ButtonStyle.Primary, null, 48f);
                App.Audio?.Play("reward");
            }
        }

        private static void Reward(RectTransform parent, string icon, string text)
        {
            var row = HubKit.Row(parent, 28f);
            UI.Icon(row, icon, 22f);
            HubKit.Label(row, text, Theme.FontBody, Theme.Text, false, -1, 1);
        }

        public override void Refresh() { }   // static summary; do not rebuild (would re-show the chapter scene check)
    }
}
