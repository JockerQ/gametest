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
    // Stations: unlock modules with Storm Shards, raise their permanent tier with Moon Gold
    // =============================================================================================
    public sealed class StationsScreen : HubScreen
    {
        public override string TitleKey => "ui.modules";
        public override string Tab => "stations";

        public override void Build(RectTransform content)
        {
            var list = UI.ScrollList(content, out _, Theme.S2, Theme.S3);
            UI.Stretch((RectTransform)list.parent.parent);
            UI.Button(list, L.T("ui.loadout"), () => Hub.Open(new LoadoutScreen()), ButtonStyle.Primary, "icon/swap", 50f, Theme.FontH2);
            var mods = new List<ModuleDef>(C.Modules);
            mods.Sort((a, b) => a.order.CompareTo(b.order));
            foreach (var m in mods) ModuleCard(list, m);
        }

        private void ModuleCard(RectTransform list, ModuleDef m)
        {
            var state = Meta.GetModuleState(m.id);
            var card = HubKit.Card(list, 0f, "ui/card", state == ModuleState.Locked ? new Color(0.55f, 0.55f, 0.6f) : (Color?)null);
            var head = HubKit.Row(card, 56f);
            var portrait = UI.Img(head, "portrait/" + m.id, null, false, "Portrait");
            portrait.preserveAspect = true;
            UI.Size(portrait, 56f, 56f);
            var col = UI.Rect(head, "Names");
            UI.Size(col, -1, 56f, 1);
            UI.VLayout(col, 0f, 0f, TextAnchor.MiddleLeft);
            HubKit.Label(col, L.T("module." + m.id + ".name"), Theme.FontH2, Theme.Family(m.family), true);
            HubKit.Label(col, L.T("module." + m.id + ".operator"), Theme.FontTiny, Theme.TextDim);
            string slot = StatsBuilder.SlotOf(Data.loadout, m.id);
            if (slot != null) HubKit.Label(col, L.T("ui.equipped") + ": " + L.T("slot." + slot + ".name"), Theme.FontTiny, Theme.Gold);
            HubKit.Wrap(card, L.T("module." + m.id + ".desc"), Theme.FontSmall, Theme.Text);

            switch (state)
            {
                case ModuleState.Locked:
                    HubKit.Wrap(card, L.F("mission.locked", ("mission", HubKit.MissionName(m.unlockMission))), Theme.FontSmall, Theme.TextDim);
                    return;
                case ModuleState.Available:
                {
                    bool can = Data.stormShards >= m.unlockShards;
                    UI.Button(card, L.T("ui.unlock") + "  " + m.unlockShards + " " + L.T("ui.storm_shards"), () =>
                    {
                        var r = Meta.UnlockModule(m.id, GameApp.UtcNow);
                        if (r == MetaResult.Ok) { App.Audio?.Play("unlock"); Toast.Show(L.F("ui.unlocked_module", ("name", L.T("module." + m.id + ".name"))), Theme.Gold); }
                        else Hub.Explain(r);
                    }, can ? ButtonStyle.Primary : ButtonStyle.Normal, "icon/storm_shard", 46f, Theme.FontBody);
                    return;
                }
            }

            int tier = Data.ModuleTier(m.id), max = Meta.MaxTier(m.id);
            string previewSlot = slot ?? "middle";
            var now = StatText.Preview(C, Data.loadout, previewSlot, m.id, null, null, Data.nodes, Data.moduleTiers, false);
            var lines = new List<string>();
            if (tier < max)
            {
                var tiers = new Dictionary<string, int>(Data.moduleTiers) { [m.id] = tier + 1 };
                var next = StatText.Preview(C, Data.loadout, previewSlot, m.id, null, null, Data.nodes, tiers, false);
                var a = StatText.Module(now);
                var b = StatText.Module(next);
                for (int i = 0; i < a.Count && i < b.Count; i++)
                    lines.Add(a[i].label + " " + (a[i].value == b[i].value ? "<b>" + a[i].value + "</b>" : L.F("ui.stat_before_after", ("before", a[i].value), ("after", "<color=#8be38f><b>" + b[i].value + "</b></color>"))));
            }
            else foreach (var (_, label, value) in StatText.Module(now)) lines.Add(label + " <b>" + value + "</b>");
            HubKit.Wrap(card, (slot == null ? "<color=#7f7499>" + L.F("ui.preview_in_slot", ("slot", L.T("slot.middle.name"))) + "</color>\n" : "") + string.Join("   ", lines), Theme.FontTiny, Theme.Text);

            var foot = HubKit.Row(card, 46f);
            var stars = UI.Rect(foot, "Tier");
            UI.Size(stars, -1, 46f, 1);
            UI.HLayout(stars, 2f, 0f, TextAnchor.MiddleLeft, false);
            for (int i = 1; i <= max; i++) UI.Icon(stars, i <= tier ? "icon/star" : "icon/star_empty", 18f);
            if (tier < max)
            {
                int cost = Meta.TierCost(m.id);
                bool can = Data.moonGold >= cost;
                var b = UI.Button(foot, L.T("ui.upgrade") + " " + TextFormat.Compact(cost), () =>
                {
                    var r = Meta.UpgradeModuleTier(m.id, GameApp.UtcNow);
                    if (r == MetaResult.Ok) App.Audio?.Play("purchase");
                    else Hub.Explain(r);
                }, can ? ButtonStyle.Primary : ButtonStyle.Normal, "icon/moon_gold", 44f, Theme.FontSmall);
                UI.Size(b, 150f, 44f);
            }
            else HubKit.Label(foot, L.T("upgrade.max"), Theme.FontBody, Theme.Green, true, 80f);
        }
    }

    // =============================================================================================
    // Upgrades: the permanent tree (Moon Gold), four branches with prerequisites
    // =============================================================================================
    public sealed class UpgradesScreen : HubScreen
    {
        public override string TitleKey => "ui.upgrades";
        public override string Tab => "upgrades";

        public override void Build(RectTransform content)
        {
            var list = UI.ScrollList(content, out _, Theme.S2, Theme.S3);
            UI.Stretch((RectTransform)list.parent.parent);
            HubKit.Wrap(list, L.T("ui.upgrades_note"), Theme.FontSmall, Theme.TextDim, TextAlignmentOptions.Top);
            var nodes = new List<PermanentNodeDef>(C.Progression.nodes);
            nodes.Sort((a, b) => a.order.CompareTo(b.order));
            foreach (var branch in new[] { "arc", "citadel", "stations", "earnings" })
            {
                HubKit.Section(list, L.T("branch." + branch));
                foreach (var n in nodes) if (n.branch == branch) NodeCard(list, n);
            }
        }

        private void NodeCard(RectTransform list, PermanentNodeDef n)
        {
            int level = Data.NodeLevel(n.id);
            var can = Meta.CanBuyNode(n.id);
            bool locked = can == MetaResult.RequirementMissing || can == MetaResult.Locked;
            bool maxed = level >= n.maxLevel;
            var card = HubKit.Card(list, 0f, "ui/card", locked ? new Color(0.55f, 0.55f, 0.6f) : maxed ? new Color(0.85f, 1f, 0.88f) : (Color?)null);
            var head = HubKit.Row(card, 26f);
            HubKit.Label(head, L.T("node." + n.id + ".name"), Theme.FontBody, locked ? Theme.TextMuted : Theme.Gold, true, -1, 1);
            HubKit.Label(head, L.F("upgrade.level", ("n", level), ("max", n.maxLevel)), Theme.FontSmall, Theme.TextDim, false, 70f);
            HubKit.Wrap(card, TextFormat.Fill(L.T("node." + n.id + ".desc"), null, n.mods, null), Theme.FontSmall, Theme.Text);
            if (locked)
            {
                string why = !string.IsNullOrEmpty(n.requiresNode) && Data.NodeLevel(n.requiresNode) < n.requiresLevel
                    ? L.F("ui.requires_node", ("name", L.T("node." + n.requiresNode + ".name")), ("n", n.requiresLevel))
                    : L.F("ui.requires", ("what", L.F("ui.requires_mission", ("mission", HubKit.MissionName(n.requiresMission)))));
                HubKit.Wrap(card, why, Theme.FontTiny, Theme.Red);
                return;
            }
            if (maxed) return;
            int cost = Meta.NodeCost(n.id);
            var b = UI.Button(card, L.T("ui.buy") + "  " + TextFormat.Compact(cost), () =>
            {
                var r = Meta.BuyNode(n.id, GameApp.UtcNow);
                if (r == MetaResult.Ok) App.Audio?.Play("purchase");
                else Hub.Explain(r);
            }, can == MetaResult.Ok ? ButtonStyle.Primary : ButtonStyle.Normal, "icon/moon_gold", 42f, Theme.FontBody);
            UI.Size(b, -1, 42f, -1, -1, 42f);
        }
    }
}
