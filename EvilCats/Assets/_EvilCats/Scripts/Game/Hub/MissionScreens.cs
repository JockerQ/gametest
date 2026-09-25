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
    // Missions: the 12-mission campaign in two biomes, plus Daily Challenge and Endless entries
    // =============================================================================================
    public sealed class MissionsScreen : HubScreen
    {
        public override string TitleKey => "ui.missions";
        public override string Tab => "missions";

        public override void Build(RectTransform content)
        {
            var list = UI.ScrollList(content, out _, Theme.S2, Theme.S3);
            UI.Stretch((RectTransform)list.parent.parent);

            // extra modes
            var endless = HubKit.Card(list, 0f, "ui/card", Meta.EndlessUnlocked ? (Color?)null : new Color(0.6f, 0.6f, 0.65f));
            var er = HubKit.Row(endless, 30f);
            UI.Icon(er, Meta.EndlessUnlocked ? "icon/star_burst" : "icon/lock", 26f);
            HubKit.Label(er, L.T("ui.endless"), Theme.FontH2, Theme.Gold, true, -1, 1);
            if (Meta.EndlessUnlocked)
            {
                HubKit.Wrap(endless, L.T("ui.endless_desc") + "\n" + L.F("ui.endless_best", ("n", Data.endless.bestWave)), Theme.FontSmall, Theme.Text);
                UI.Button(endless, L.T("ui.play"), Hub.StartEndless, ButtonStyle.Primary, "icon/play", 46f, Theme.FontBody);
            }
            else HubKit.Wrap(endless, L.F("ui.endless_locked", ("mission", HubKit.MissionName(C.Endless.requiresMission))), Theme.FontSmall, Theme.TextDim);

            string biome = null;
            foreach (var m in C.Missions)
            {
                if (m.biome != biome)
                {
                    biome = m.biome;
                    HubKit.Section(list, L.T("biome." + biome));
                }
                MissionCard(list, m);
            }
        }

        private void MissionCard(RectTransform list, MissionDef m)
        {
            bool unlocked = Meta.IsMissionUnlocked(m);
            Data.missions.TryGetValue(m.id, out var rec);
            bool cleared = rec != null && rec.cleared;
            var card = HubKit.Card(list, 0f, "ui/card", unlocked ? (cleared ? new Color(0.85f, 1f, 0.88f) : Color.white) : new Color(0.55f, 0.55f, 0.6f));
            var top = HubKit.Row(card, 30f);
            var num = UI.Text(top, m.index.ToString(), Theme.FontH2, Theme.Cyan, TextAlignmentOptions.Center, true);
            UI.Size(num, 28f, 30f);
            HubKit.Label(top, HubKit.MissionName(m.id), Theme.FontH2, unlocked ? Theme.Text : Theme.TextMuted, true, -1, 1);
            if (!string.IsNullOrEmpty(m.boss)) UI.Icon(top, "icon/enemy/" + m.boss, 26f);
            UI.Icon(top, !unlocked ? "icon/lock" : cleared ? "icon/check" : "icon/play", 22f, cleared ? Theme.Green : (Color?)null);
            if (!unlocked)
            {
                HubKit.Wrap(card, L.F("mission.locked", ("mission", HubKit.MissionName(m.requiresMission))), Theme.FontSmall, Theme.TextDim);
                return;
            }
            HubKit.Wrap(card, L.T("mission." + m.id + ".desc"), Theme.FontSmall, Theme.Text);
            var info = new List<string> { L.F("mission.waves", ("n", m.waves)) };
            if (rec != null && rec.bestWave > 0 && !cleared) info.Add(L.F("mission.best", ("n", rec.bestWave)));
            if (cleared) info.Add(L.T("mission.cleared") + (rec.bestTimeSec > 0f ? " (" + TextFormat.Duration(rec.bestTimeSec) + ")" : ""));
            foreach (var mod in m.modifiers) info.Add("<color=#ff9a3c>" + L.T("modifier." + mod + ".name") + "</color>");
            HubKit.Wrap(card, string.Join("  ·  ", info), Theme.FontTiny, Theme.TextDim);
            // rewards: Moon Gold (full on first clear, reduced on replays), shards and new stations
            var rw = new List<string>();
            float frac = cleared ? C.Tuning.economy.replayMoonGoldFraction : 1f;
            rw.Add(Mathf.FloorToInt(m.moonGold * frac * Meta.PermanentFactor("econ.moonGold")) + " " + L.T("ui.moon_gold"));
            if (!cleared && m.firstClearShards > 0) rw.Add(m.firstClearShards + " " + L.T("ui.storm_shards"));
            if (!cleared && !string.IsNullOrEmpty(m.unlocksModule)) rw.Add(L.T("module." + m.unlocksModule + ".name"));
            HubKit.Wrap(card, "<color=#ffd24a>" + L.T("mission.reward") + ":</color> " + string.Join(", ", rw), Theme.FontTiny, Theme.Text);
            var press = card.gameObject.AddComponent<PressHandler>();
            press.OnTap = () => { App.Audio?.Play("ui_click"); Hub.Open(new LoadoutScreen(m.id)); };
        }
    }

    // =============================================================================================
    // Loadout: choose stations for the three citadel slots before a mission
    // =============================================================================================
    public sealed class LoadoutScreen : HubScreen
    {
        private readonly string _missionId;
        public LoadoutScreen(string missionId = null) { _missionId = missionId; }
        public override string TitleKey => "ui.loadout";
        public override string Tab => _missionId != null ? "missions" : "stations";

        public override void Build(RectTransform content)
        {
            var list = UI.ScrollList(content, out _, Theme.S2, Theme.S3);
            UI.Stretch((RectTransform)list.parent.parent);
            var m = C.Mission(_missionId);
            if (m != null)
            {
                var head = HubKit.Card(list, 0f, "ui/card", Theme.Gold);
                HubKit.Label(head, HubKit.MissionName(m.id), Theme.FontH1, Theme.Gold, true);
                var bits = new List<string> { L.T("biome." + m.biome), L.F("mission.waves", ("n", m.waves)) };
                if (!string.IsNullOrEmpty(m.boss)) bits.Add(L.T("boss." + m.boss + ".name"));
                HubKit.Wrap(head, string.Join("  ·  ", bits), Theme.FontSmall, Theme.TextDim);
                foreach (var mod in m.modifiers)
                    HubKit.Wrap(head, "<color=#ff9a3c>" + L.T("modifier." + mod + ".name") + ":</color> " + L.T("modifier." + mod + ".desc"), Theme.FontTiny, Theme.Text);
            }

            HubKit.Section(list, L.T("ui.modules"));
            foreach (var slot in C.Tuning.slots) SlotRow(list, slot);

            var syn = StatsBuilder.ActiveSynergies(C, new Dictionary<string, string>(Data.loadout));
            var sc = HubKit.Card(list, 0f, "ui/card", syn.Count > 0 ? Theme.Gold : (Color?)null);
            if (syn.Count == 0) HubKit.Wrap(sc, L.T("ui.no_synergy"), Theme.FontSmall, Theme.TextDim);
            foreach (var s in syn)
            {
                HubKit.Label(sc, L.T("ui.synergy_active") + ": " + L.T("synergy." + s.id + ".name"), Theme.FontBody, Theme.Gold, true);
                HubKit.Wrap(sc, L.T("synergy." + s.id + ".desc"), Theme.FontSmall, Theme.Text);
            }

            HubKit.Section(list, L.T("ui.target"));
            var pr = HubKit.Row(list, 48f, Theme.S1);
            ((HorizontalLayoutGroup)pr.GetComponent<HorizontalLayoutGroup>()).childForceExpandWidth = true;
            Priority(pr, TargetPriority.Nearest, "nearest", "icon/target_nearest");
            Priority(pr, TargetPriority.Strongest, "strongest", "icon/target_strongest");
            Priority(pr, TargetPriority.RangedThreat, "rangedThreat", "icon/target_ranged");

            if (m != null)
            {
                UI.Spacer(list, 6f);
                var start = UI.Button(list, L.T("ui.start"), () => Hub.StartMission(m.id), ButtonStyle.Primary, "icon/play", 58f, Theme.FontH1, "ui_click");
                UI.Size(start, -1, 58f, -1, -1, 58f);
            }
        }

        private void Priority(RectTransform row, TargetPriority p, string key, string icon)
        {
            bool on = Data.defaultPriority == p;
            var b = UI.Button(row, L.T("priority." + key), () =>
            {
                Data.defaultPriority = p;
                Toast.Show(L.T("priority." + key + ".desc"), Theme.Cyan);
                App.SaveNow();
            }, on ? ButtonStyle.Primary : ButtonStyle.Normal, icon, 46f, Theme.FontSmall);
            UI.Size(b, -1, 46f, 1);
        }

        private void SlotRow(RectTransform list, SlotDef slot)
        {
            bool unlocked = Data.slotsUnlocked.Contains(slot.id);
            Data.loadout.TryGetValue(slot.id, out var moduleId);
            var card = HubKit.Card(list, 76f, "ui/card", unlocked ? (Color?)null : new Color(0.55f, 0.55f, 0.6f));
            var row = HubKit.Row(card, 52f);
            var frame = UI.Img(row, "ui/slot_frame", null, false, "Frame");
            UI.Size(frame, 52f, 52f);
            if (!string.IsNullOrEmpty(moduleId))
            {
                var ic = UI.Icon(frame.transform, "icon/module/" + moduleId, 40f);
                UI.Place(ic.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(40f, 40f));
            }
            else if (!unlocked)
            {
                var ic = UI.Icon(frame.transform, "icon/lock", 26f);
                UI.Place(ic.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(26f, 26f));
            }
            var col = UI.Rect(row, "Text");
            UI.Size(col, -1, 52f, 1);
            UI.VLayout(col, 0f, 0f, TextAnchor.MiddleLeft);
            HubKit.Label(col, L.T("slot." + slot.id + ".name") + "  <size=10><color=#b9aed3>" + L.T("slot." + slot.id + ".desc") + "</color></size>", Theme.FontBody, Theme.Cyan, true);
            string line = !unlocked ? SlotLockText(slot.id)
                : string.IsNullOrEmpty(moduleId) ? L.T("ui.empty_slot")
                : L.T("module." + moduleId + ".name") + "  ·  " + L.F("ui.tier", ("n", Data.ModuleTier(moduleId)));
            HubKit.Label(col, line, Theme.FontSmall, unlocked ? Theme.Text : Theme.TextDim);
            if (!unlocked) return;
            var swap = UI.IconButton(row, "icon/swap", () => PickModule(slot.id), 44f);
            UI.Size(swap, 44f, 44f);
            card.gameObject.AddComponent<PressHandler>().OnTap = () => PickModule(slot.id);
        }

        private string SlotLockText(string slot)
        {
            foreach (var m in C.Missions)
                foreach (var su in m.slotUnlocks)
                    if (su.slot == slot) return L.F("ui.slot_locked", ("mission", HubKit.MissionName(m.id)));
            return L.T("ui.locked");
        }

        /// <summary>Choose which unlocked station goes into a slot, with the stats it would have there.</summary>
        private void PickModule(string slot)
        {
            var d = Hub.Dialog(340f);
            var title = UI.Text(d, L.T("slot." + slot + ".name") + ": " + L.T("slot." + slot + ".desc"), Theme.FontBody, Theme.Cyan, TextAlignmentOptions.Center, true);
            UI.Size(title, -1, 24f);
            Data.loadout.TryGetValue(slot, out var current);
            // the list scrolls inside the dialog so six stations fit on small phones
            var options = UI.ScrollList(d, out _, Theme.S2, 0f);
            UI.Size(options.parent.parent, -1, 330f, -1, -1, 330f);
            foreach (var mod in C.Modules)
            {
                var state = Meta.GetModuleState(mod.id);
                if (state != ModuleState.Unlocked) continue;
                string id = mod.id;
                bool equippedHere = current == id;
                var card = HubKit.Card(options, 0f, "ui/card", equippedHere ? Theme.Gold : (Color?)null);
                var row = HubKit.Row(card, 30f);
                UI.Icon(row, "icon/module/" + id, 28f);
                HubKit.Label(row, L.T("module." + id + ".name"), Theme.FontBody, Theme.Family(mod.family), true, -1, 1);
                string elsewhere = StatsBuilder.SlotOf(Data.loadout, id);
                if (elsewhere != null && elsewhere != slot) HubKit.Label(row, L.T("slot." + elsewhere + ".name"), Theme.FontTiny, Theme.TextDim);
                var stats = StatText.Preview(C, Data.loadout, slot, id, null, null, Data.nodes, Data.moduleTiers, false);
                var lines = new List<string>();
                foreach (var (_, label, value) in StatText.Module(stats)) lines.Add(label + " <b>" + value + "</b>");
                HubKit.Wrap(card, string.Join("   ", lines), Theme.FontTiny, Theme.Text);
                var syn = StatText.NewSynergies(C, Data.loadout, slot, id);
                if (syn.Count > 0) HubKit.Wrap(card, "<color=#ffd24a>" + L.T("ui.synergy_active") + ": " + L.T("synergy." + syn[0].id + ".name") + "</color>", Theme.FontTiny, Theme.Text);
                card.gameObject.AddComponent<PressHandler>().OnTap = () =>
                {
                    Hub.CloseDialog(d);
                    var r = Meta.SetSlot(slot, id, GameApp.UtcNow);
                    if (r == MetaResult.Ok) App.Audio?.Play("ui_toggle");
                    else Hub.Explain(r);
                };
            }
            if (!string.IsNullOrEmpty(current))
                UI.Button(d, L.T("ui.remove"), () =>
                {
                    Hub.CloseDialog(d);
                    Hub.Explain(Meta.SetSlot(slot, null, GameApp.UtcNow));
                }, ButtonStyle.Normal, "icon/minus", 44f, Theme.FontBody);
            UI.Button(d, L.T("ui.close"), () => Hub.CloseDialog(d), ButtonStyle.Normal, null, 44f, Theme.FontBody, "ui_back");
        }
    }
}
