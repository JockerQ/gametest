using System.Collections.Generic;
using EvilCats.Content;
using EvilCats.Meta;
using EvilCats.Sim;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

namespace EvilCats.Game
{
    // =============================================================================================
    // Daily: 7-day attendance, three objectives, the Daily Challenge and offline Moon Gold
    // =============================================================================================
    public sealed class DailyScreen : HubScreen
    {
        public override string TitleKey => "ui.daily.title";
        public override string Tab => "daily";

        public override void Build(RectTransform content)
        {
            Meta.EnsureDaily(GameApp.LocalNow);
            var list = UI.ScrollList(content, out _, Theme.S3, Theme.S3);
            UI.Stretch((RectTransform)list.parent.parent);
            Attendance(list);
            Objectives(list);
            Challenge(list);
            Offline(list);
        }

        private void Attendance(RectTransform list)
        {
            var card = HubKit.Card(list);
            HubKit.Label(card, L.T("ui.daily.attendance"), Theme.FontH2, Theme.Gold, true);
            HubKit.Wrap(card, L.T("ui.daily.attendance_note"), Theme.FontTiny, Theme.TextDim);
            var rewards = C.Progression.attendance;
            bool available = Meta.AttendanceAvailable(GameApp.LocalNow, out bool clockBack);
            int next = Data.attendance.dayIndex;
            var grid = UI.Rect(card, "Days");
            UI.Size(grid, -1, 70f, -1, -1, 70f);
            var h = UI.HLayout(grid, 3f, 0f);
            h.childForceExpandWidth = true;
            for (int i = 0; i < rewards.Count; i++)
            {
                bool claimed = i < next;
                bool today = i == next && available;
                var tile = UI.Img(grid, "ui/slot_frame", today ? Theme.Gold : claimed ? new Color(0.6f, 0.9f, 0.65f) : Color.white, false, "Day" + (i + 1));
                tile.type = Image.Type.Sliced;
                tile.preserveAspect = false;
                UI.Size(tile, -1, 70f, 1);
                var day = UI.Text(tile.transform, L.F("ui.daily.day", ("n", i + 1)), 8f, Theme.TextDim, TextAlignmentOptions.Top, true);
                UI.Stretch(day.rectTransform, 1, 3, 1, 3);
                var r = rewards[i];
                // Claimed days show a check icon (the pixel font has no check-mark glyph).
                var ic = UI.Icon(tile.transform, claimed ? "icon/check" : r.stormShards > 0 ? "icon/storm_shard" : "icon/moon_gold", 20f, claimed ? Theme.Green : (Color?)null);
                UI.Place(ic.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0f, 2f), new Vector2(20f, 20f));
                string amount = r.stormShards > 0 ? r.moonGold + "+" + r.stormShards : r.moonGold.ToString();
                var a = UI.Text(tile.transform, amount, 9f, claimed ? Theme.TextMuted : Theme.Text, TextAlignmentOptions.Bottom, true);
                UI.Stretch(a.rectTransform, 1, 3, 1, 4);
            }
            if (clockBack) HubKit.Wrap(card, L.T("ui.daily.clock_warning"), Theme.FontTiny, Theme.Red);
            var claim = UI.Button(card, available ? L.T("ui.claim") : L.T("ui.claimed"), () =>
            {
                var res = Meta.ClaimAttendance(GameApp.UtcNow, GameApp.LocalNow);
                if (res == MetaResult.Ok) { App.Audio?.Play("reward"); Toast.Show(L.T("ui.claimed"), Theme.Gold); }
                else Hub.Explain(res);
            }, available ? ButtonStyle.Primary : ButtonStyle.Normal, available ? "icon/gift" : "icon/check", 46f, Theme.FontBody, null);
            claim.interactable = available;
        }

        private void Objectives(RectTransform list)
        {
            var card = HubKit.Card(list);
            HubKit.Label(card, L.T("ui.daily.objectives"), Theme.FontH2, Theme.Gold, true);
            foreach (var id in Data.daily.objectives)
            {
                if (!C.ObjectiveById.TryGetValue(id, out var o)) continue;
                long progress = Meta.ObjectiveProgress(id);
                bool claimed = Data.daily.claimed.Contains(id);
                bool ready = Meta.ObjectiveReady(id);
                var row = HubKit.Row(card, 44f);
                var col = UI.Rect(row, "Text");
                UI.Size(col, -1, 44f, 1);
                UI.VLayout(col, 2f, 0f, TextAnchor.MiddleLeft);
                HubKit.Label(col, L.T("objective." + id + ".desc") + "  <color=#ffd24a>" + RewardText(o.reward) + "</color>", Theme.FontSmall, Theme.Text);
                var bar = UI.ProgressBar(col, ready || claimed ? Theme.Green : Theme.Cyan, 10f, false, null, false);
                bar.Set(o.target > 0 ? Mathf.Clamp01((float)progress / o.target) : 1f);
                HubKit.Label(col, L.F("achievement.progress", ("now", System.Math.Min(progress, o.target)), ("target", o.target)), Theme.FontTiny, Theme.TextDim);
                var b = UI.Button(row, claimed ? L.T("ui.claimed") : L.T("ui.claim"), () =>
                {
                    var res = Meta.ClaimObjective(id, GameApp.UtcNow, GameApp.LocalNow);
                    if (res == MetaResult.Ok) App.Audio?.Play("claim");
                    else Hub.Explain(res);
                }, ready ? ButtonStyle.Primary : ButtonStyle.Normal, null, 40f, Theme.FontSmall, null);
                UI.Size(b, 80f, 40f);
                b.interactable = ready;
            }
            if (Data.daily.objectives.Count == 0) HubKit.Wrap(card, L.T("ui.nothing_to_claim"), Theme.FontSmall, Theme.TextDim);
        }

        private void Challenge(RectTransform list)
        {
            var card = HubKit.Card(list, 0f, "ui/card", Meta.DailyUnlocked ? (Color?)null : new Color(0.55f, 0.55f, 0.6f));
            HubKit.Label(card, L.T("ui.daily.challenge"), Theme.FontH2, Theme.Gold, true);
            if (!Meta.DailyUnlocked)
            {
                HubKit.Wrap(card, L.F("ui.daily.challenge_locked", ("mission", HubKit.MissionName(C.Daily.requiresMission))), Theme.FontSmall, Theme.TextDim);
                return;
            }
            HubKit.Wrap(card, L.T("ui.daily.challenge_desc"), Theme.FontSmall, Theme.Text);
            var cfg = GameMeta.DailyChallenge(C, GameApp.UtcNow);
            var bits = new List<string>();
            foreach (var kv in cfg.loadout) bits.Add(L.T("module." + kv.Value + ".name"));
            HubKit.Wrap(card, L.T("ui.modules") + ": " + string.Join(", ", bits), Theme.FontTiny, Theme.TextDim);
            foreach (var mod in cfg.modifiers) HubKit.Wrap(card, "<color=#ff9a3c>" + L.T("modifier." + mod + ".name") + ":</color> " + L.T("modifier." + mod + ".desc"), Theme.FontTiny, Theme.Text);
            if (!string.IsNullOrEmpty(cfg.boss)) HubKit.Wrap(card, L.T("announce.boss").Replace("{name}", L.T("boss." + cfg.boss + ".name")), Theme.FontTiny, Theme.Red);
            string today = GameApp.UtcNow.ToString("yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture);
            long best = Data.daily.challengeDate == today ? Data.daily.challengeBestScore : 0;
            HubKit.Wrap(card, L.F("ui.daily.challenge_best", ("score", best)) + (best > 0 ? "  (" + L.F("announce.wave", ("n", Data.daily.challengeBestWave)) + ")" : ""), Theme.FontSmall, Theme.Gold);
            bool rewardTaken = Meta.IsClaimed("dailychallenge:" + today);
            HubKit.Wrap(card, rewardTaken ? L.T("ui.daily.reward_taken") : L.F("ui.daily.reward_first", ("n", C.Daily.moonGold)), Theme.FontTiny, Theme.TextDim);
            UI.Button(card, L.T("ui.play"), Hub.StartDaily, ButtonStyle.Primary, "icon/play", 48f, Theme.FontBody);
        }

        private void Offline(RectTransform list)
        {
            var card = HubKit.Card(list);
            HubKit.Label(card, L.T("ui.daily.offline"), Theme.FontH2, Theme.Gold, true);
            float rate = Meta.OfflineRatePerHour();
            if (Data.offline.stampUtcTicks == 0 || rate <= 0f)
            {
                HubKit.Wrap(card, L.T("ui.daily.offline_locked"), Theme.FontSmall, Theme.TextDim);
                return;
            }
            HubKit.Wrap(card, L.F("ui.daily.offline_rate", ("rate", TextFormat.Number(Mathf.Round(rate * 10f) / 10f)), ("cap", TextFormat.Number(C.Tuning.offline.capHours))), Theme.FontSmall, Theme.Text);
            long pending = Meta.OfflinePending(GameApp.UtcNow, out double hours, out bool back);
            if (back) HubKit.Wrap(card, L.T("ui.daily.clock_warning"), Theme.FontTiny, Theme.Red);
            var bar = UI.ProgressBar(card, Theme.Gold, 10f);
            bar.Set((float)(hours / C.Tuning.offline.capHours));
            HubKit.Wrap(card, L.F("ui.daily.offline_ready", ("amount", pending)) + "  (" + TextFormat.Number(System.Math.Round(hours, 1)) + "h)", Theme.FontSmall, Theme.Gold);
            bool can = pending > 0 && hours * 60.0 >= C.Tuning.offline.minCollectMinutes;
            var b = UI.Button(card, L.T("ui.collect"), () =>
            {
                var res = Meta.CollectOffline(GameApp.UtcNow, out long amount);
                if (res == MetaResult.Ok) { App.Audio?.Play("reward"); Toast.Show("+" + amount + " " + L.T("ui.moon_gold"), Theme.Gold); }
                else Hub.Explain(res);
            }, can ? ButtonStyle.Primary : ButtonStyle.Normal, "icon/moon_gold", 46f, Theme.FontBody, null);
        }

        public static string RewardText(RewardDef r)
        {
            var parts = new List<string>();
            if (r == null) return "";
            if (r.moonGold > 0) parts.Add("+" + r.moonGold + " " + L.T("ui.moon_gold"));
            if (r.stormShards > 0) parts.Add("+" + r.stormShards + " " + L.T("ui.storm_shards"));
            if (!string.IsNullOrEmpty(r.cosmetic)) parts.Add(L.T("cosmetic." + r.cosmetic + ".name"));
            return string.Join(", ", parts);
        }
    }

    // =============================================================================================
    // Achievements
    // =============================================================================================
    public sealed class AchievementsScreen : HubScreen
    {
        public override string TitleKey => "ui.achievements";
        public override string Tab => "more";

        public override void Build(RectTransform content)
        {
            var list = UI.ScrollList(content, out _, Theme.S2, Theme.S3);
            UI.Stretch((RectTransform)list.parent.parent);
            var all = new List<AchievementDef>(C.Progression.achievements);
            // ready to claim first, then unfinished, then claimed
            all.Sort((a, b) =>
            {
                int ra = Rank(a), rb = Rank(b);
                return ra != rb ? ra.CompareTo(rb) : a.order.CompareTo(b.order);
            });
            int claimedCount = Data.achievementsClaimed.Count;
            HubKit.Wrap(list, claimedCount + " / " + all.Count, Theme.FontSmall, Theme.TextDim, TextAlignmentOptions.Top);
            foreach (var a in all) Card(list, a);
        }

        private int Rank(AchievementDef a) => Meta.AchievementReady(a.id) ? 0 : Data.achievementsClaimed.Contains(a.id) ? 2 : 1;

        private void Card(RectTransform list, AchievementDef a)
        {
            bool claimed = Data.achievementsClaimed.Contains(a.id);
            bool ready = Meta.AchievementReady(a.id);
            long now = Meta.AchievementProgress(a.id);
            var card = HubKit.Card(list, 0f, "ui/card", ready ? Theme.Gold : claimed ? new Color(0.7f, 0.9f, 0.72f) : (Color?)null);
            var row = HubKit.Row(card, 30f);
            UI.Icon(row, claimed ? "icon/check" : "icon/trophy", 24f, claimed ? Theme.Green : ready ? Theme.Gold : Theme.TextDim);
            HubKit.Label(row, L.T("achievement." + a.id + ".name"), Theme.FontBody, ready ? Theme.Gold : Theme.Text, true, -1, 1);
            HubKit.Wrap(card, L.T("achievement." + a.id + ".desc") + "  <color=#ffd24a>" + DailyScreen.RewardText(a.reward) + "</color>", Theme.FontSmall, Theme.Text);
            var bar = UI.ProgressBar(card, claimed || ready ? Theme.Green : Theme.Cyan, 10f);
            bar.Set(a.target > 0 ? Mathf.Clamp01((float)now / a.target) : 1f);
            HubKit.Label(card, L.F("achievement.progress", ("now", System.Math.Min(now, a.target)), ("target", a.target)), Theme.FontTiny, Theme.TextDim);
            if (ready)
                UI.Button(card, L.T("ui.claim"), () =>
                {
                    var r = Meta.ClaimAchievement(a.id, GameApp.UtcNow);
                    if (r == MetaResult.Ok) { App.Audio?.Play("reward"); Toast.Show(DailyScreen.RewardText(a.reward), Theme.Gold); }
                    else Hub.Explain(r);
                }, ButtonStyle.Primary, "icon/gift", 44f, Theme.FontBody, null);
        }
    }

    // =============================================================================================
    // Records (local only; no fabricated online rankings)
    // =============================================================================================
    public sealed class RecordsScreen : HubScreen
    {
        public override string TitleKey => "ui.records.title";
        public override string Tab => "more";

        public override void Build(RectTransform content)
        {
            var list = UI.ScrollList(content, out _, Theme.S2, Theme.S3);
            UI.Stretch((RectTransform)list.parent.parent);
            HubKit.Wrap(list, L.T("ui.records.local_note"), Theme.FontTiny, Theme.TextDim, TextAlignmentOptions.Top);
            var card = HubKit.Card(list);
            Line(card, "ui.records.runs", Data.Lifetime("runs_played"));
            Line(card, "ui.records.victories", Data.Lifetime("victories"));
            Line(card, "ui.records.kills", Data.Lifetime("kills"));
            Line(card, "ui.records.best_chain", Data.Lifetime("max_chain"));
            Line(card, "ui.records.endless", Data.endless.bestWave);
            Line(card, "ui.records.daily", Data.daily.challengeBestScore);
            HubKit.Section(list, L.T("ui.missions"));
            var mc = HubKit.Card(list);
            foreach (var m in C.Missions)
            {
                if (!Data.missions.TryGetValue(m.id, out var r) || r.attempts == 0) continue;
                string v = r.cleared ? L.T("mission.cleared") + " · " + TextFormat.Duration(r.bestTimeSec) : L.F("mission.best", ("n", r.bestWave));
                var row = HubKit.Row(mc, 24f);
                HubKit.Label(row, m.index + ". " + HubKit.MissionName(m.id), Theme.FontSmall, Theme.Text, false, -1, 1);
                HubKit.Label(row, v, Theme.FontSmall, r.cleared ? Theme.Green : Theme.TextDim, false, 130f);
            }
        }

        private static void Line(RectTransform card, string key, long value)
        {
            var row = HubKit.Row(card, 26f);
            HubKit.Label(row, L.T(key), Theme.FontBody, Theme.Text, false, -1, 1);
            HubKit.Label(row, TextFormat.Compact(value), Theme.FontBody, Theme.Gold, true, 90f);
        }
    }
}
