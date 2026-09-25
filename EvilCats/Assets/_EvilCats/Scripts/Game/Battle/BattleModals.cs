using System;
using System.Collections.Generic;
using EvilCats.Content;
using EvilCats.Meta;
using EvilCats.Sim;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

namespace EvilCats.Game
{
    /// <summary>
    /// Every battle decision and interruption as a modal on its own canvas: perk choice (select,
    /// then confirm), station choice for a newly unlocked slot (with the real resulting stats),
    /// boss introduction, pause with quick settings, revive (honest about unavailable ads),
    /// confirmation dialogs and the victory/defeat summary with the main damage source, a
    /// counter tip and a fast retry. The battle does not advance while any modal is open.
    /// </summary>
    public sealed class BattleModals : MonoBehaviour
    {
        private RectTransform _root;
        private readonly List<Modal> _stack = new List<Modal>();

        private sealed class Modal
        {
            public RectTransform layer;
            public Func<bool> back;          // Android back button; return true when handled
            public string kind;
        }

        public bool IsOpen => _stack.Count > 0;
        public bool IsShowing(string kind) => _stack.Exists(m => m.kind == kind);

        public void Init()
        {
            _root = UI.CreateCanvas("BattleModals", 200, out _);
        }

        public bool Back()
        {
            if (_stack.Count == 0) return false;
            var top = _stack[_stack.Count - 1];
            if (top.back != null) top.back();
            return true;   // modals always consume the back button
        }

        public void CloseAll()
        {
            foreach (var m in _stack) if (m.layer != null) Destroy(m.layer.gameObject);
            _stack.Clear();
        }

        private void Close(Modal m)
        {
            if (m == null) return;
            _stack.Remove(m);
            if (m.layer != null) Destroy(m.layer.gameObject);
        }

        private Modal Open(string kind, out RectTransform panel, float width = 340f, float height = 0f, Color? dim = null)
        {
            var m = new Modal { kind = kind };
            m.layer = UI.Blocker(_root, dim);
            var p = UI.Panel(m.layer, "ui/panel", "Panel");
            panel = p.rectTransform;
            UI.Place(panel, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(width, height > 0f ? height : 300f));
            var v = UI.VLayout(p, Theme.S2, Theme.S4, TextAnchor.UpperCenter);
            v.padding = new RectOffset(14, 14, 14, 14);
            if (height <= 0f)
            {
                var fit = p.gameObject.AddComponent<ContentSizeFitter>();
                fit.verticalFit = ContentSizeFitter.FitMode.PreferredSize;
            }
            _stack.Add(m);
            return m;
        }

        private static TextMeshProUGUI Title(Transform parent, string text, Color? color = null)
        {
            var t = UI.Text(parent, text, Theme.FontH1, color ?? Theme.Gold, TextAlignmentOptions.Center, true, "Title");
            UI.Size(t, -1, 30f);
            t.enableAutoSizing = true;
            t.fontSizeMin = 14f;
            t.fontSizeMax = Theme.FontH1;
            return t;
        }

        private static TextMeshProUGUI Line(Transform parent, string text, float size = Theme.FontBody, Color? color = null, TextAlignmentOptions align = TextAlignmentOptions.Center)
        {
            // inside the panel's vertical layout the height comes from the text's preferred height
            var t = UI.Text(parent, text, size, color ?? Theme.Text, align, false, "Line");
            t.overflowMode = TextOverflowModes.Overflow;
            return t;
        }

        // =========================================================================================
        // Perk choice
        // =========================================================================================
        public void ShowPerkChoice(Battle b, Action<int> onConfirm)
        {
            var offer = b.CurrentOffer;
            if (offer == null) return;
            var m = Open("perk", out var panel, 344f);
            m.back = () => true;   // a choice is required; back does nothing
            Title(panel, L.T("ui.perk_title"), Theme.Cyan);
            Line(panel, L.F("ui.perk_subtitle", ("n", offer.level)), Theme.FontSmall, Theme.TextDim);
            int selected = -1;
            var cards = new List<Image>();
            Button confirm = null;
            for (int i = 0; i < offer.choices.Count; i++)
            {
                int index = i;
                var card = PerkCard(panel, b, offer.choices[i]);
                cards.Add(card);
                var press = card.gameObject.AddComponent<PressHandler>();
                press.OnTap = () =>
                {
                    if (selected == index)
                    {
                        // tapping the selected card again confirms it (fast path)
                        Close(m);
                        onConfirm(index);
                        return;
                    }
                    selected = index;
                    for (int k = 0; k < cards.Count; k++) cards[k].color = k == index ? Theme.Gold : new Color(0.7f, 0.68f, 0.78f, 1f);
                    confirm.interactable = true;
                    GameApp.I.Audio?.Play("ui_toggle");
                };
            }
            Line(panel, L.T("perk.stacking_note"), Theme.FontTiny, Theme.TextMuted);
            confirm = UI.Button(panel, L.T("ui.confirm"), () =>
            {
                if (selected < 0) return;
                Close(m);
                onConfirm(selected);
            }, ButtonStyle.Primary, "icon/check", 52f, Theme.FontH2, "perk_pick");
            confirm.interactable = false;
        }

        private Image PerkCard(RectTransform parent, Battle b, PerkChoice choice)
        {
            var card = UI.Img(parent, "ui/card", new Color(0.7f, 0.68f, 0.78f, 1f), true, "Card");
            card.type = Image.Type.Sliced;
            card.preserveAspect = false;
            UI.Size(card, -1, 104f, -1, -1, 104f);
            var def = choice.perkId != null ? b.C.Perk(choice.perkId) : null;
            string icon, name, desc, meta;
            Color color;
            if (def != null)
            {
                icon = "icon/perk/" + def.id;
                name = L.T("perk." + def.id + ".name");
                desc = TextFormat.Perk(b.C, def);
                color = Theme.Family(def.family);
                string rarity = L.T("perk.rarity." + def.rarity);
                meta = L.T("perk.family." + def.family) + " · " + rarity + (def.maxStacks > 1 ? " · " + L.F("perk.stack", ("n", choice.currentStacks + 1), ("max", def.maxStacks)) : "");
            }
            else
            {
                var fb = b.C.Fallbacks.Find(f => f.id == choice.fallbackId);
                icon = choice.fallbackId == "spark_cache" ? "icon/spark" : choice.fallbackId == "stormheart_mend" ? "icon/heart_plus" : "icon/shield";
                name = L.T("fallback." + choice.fallbackId + ".name");
                float v = fb != null ? fb.value : 0f;
                var args = new Dictionary<string, string>
                {
                    { "n", TextFormat.Number(Mathf.Floor(v * (1f + 0.25f * b.Level))) },
                    { "pct", TextFormat.Percent(v) },
                };
                desc = StringTable.Fill(L.T("fallback." + choice.fallbackId + ".desc"), args);
                color = Theme.Gold;
                meta = L.T("perk.rarity.common");
            }
            var ic = UI.Icon(card.transform, icon, 44f);
            UI.Place(ic.rectTransform, new Vector2(0f, 0.5f), new Vector2(0f, 0.5f), new Vector2(10f, 0f), new Vector2(44f, 44f));
            var n = UI.Text(card.transform, name, Theme.FontH2, color, TextAlignmentOptions.TopLeft, true, "Name");
            UI.Place(n.rectTransform, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(64f, -8f), new Vector2(246f, 22f));
            n.enableAutoSizing = true;
            n.fontSizeMin = 11f;
            n.fontSizeMax = Theme.FontH2;
            var mt = UI.Text(card.transform, meta, Theme.FontTiny, Theme.TextDim, TextAlignmentOptions.TopLeft, false, "Meta");
            UI.Place(mt.rectTransform, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(64f, -30f), new Vector2(246f, 14f));
            var d = UI.Text(card.transform, desc, Theme.FontSmall, Theme.Text, TextAlignmentOptions.TopLeft, false, "Desc");
            d.rectTransform.anchorMin = new Vector2(0f, 0f);
            d.rectTransform.anchorMax = new Vector2(1f, 1f);
            d.rectTransform.offsetMin = new Vector2(64f, 6f);
            d.rectTransform.offsetMax = new Vector2(-8f, -46f);
            d.enableAutoSizing = true;
            d.fontSizeMin = 8f;
            d.fontSizeMax = Theme.FontSmall;
            return card;
        }

        // =========================================================================================
        // New slot: choose a station (shows the real stats it would have in that slot)
        // =========================================================================================
        public void ShowModuleChoice(Battle b, Action<string> onChoose)
        {
            string slot = b.PendingSlot;
            var choices = new List<string>(b.ModuleChoices);
            var m = Open("module", out var panel, 344f);
            m.back = () => true;
            Title(panel, L.F("announce.slot_unlocked", ("slot", L.T("slot." + slot + ".name"))), Theme.Cyan);
            Line(panel, L.T("ui.choose_module") + "\n<color=#b9aed3>" + L.T("slot." + slot + ".name") + ": " + L.T("slot." + slot + ".desc") + "</color>", Theme.FontSmall);
            string selected = null;
            var cards = new Dictionary<string, Image>();
            Button confirm = null;
            var loadout = new Dictionary<string, string>(b.Loadout);
            foreach (var id in choices)
            {
                string mid = id;
                var card = UI.Img(panel, "ui/card", new Color(0.7f, 0.68f, 0.78f, 1f), true, "Card " + id);
                card.type = Image.Type.Sliced;
                card.preserveAspect = false;
                UI.Size(card, -1, 92f, -1, -1, 92f);
                var ic = UI.Icon(card.transform, "icon/module/" + id, 40f);
                UI.Place(ic.rectTransform, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(10f, -10f), new Vector2(40f, 40f));
                var def = b.C.Module(id);
                var name = UI.Text(card.transform, L.T("module." + id + ".name"), Theme.FontH2, Theme.Family(def != null ? def.family : ""), TextAlignmentOptions.TopLeft, true, "Name");
                UI.Place(name.rectTransform, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(58f, -8f), new Vector2(250f, 22f));
                var stats = StatText.Preview(b.C, loadout, slot, id, b.UpgradeLevels, b.PerkStacks, b.Setup.nodeLevels, b.Setup.moduleTiers, b.Setup.ignorePermanent);
                var lines = new List<string>();
                foreach (var (key, label, value) in StatText.Module(stats)) lines.Add(label + " <b>" + value + "</b>");
                var syn = StatText.NewSynergies(b.C, loadout, slot, id);
                string synText = syn.Count > 0 ? "\n<color=#ffd24a>" + L.T("ui.synergy_active") + ": " + L.T("synergy." + syn[0].id + ".name") + "</color>" : "";
                var st = UI.Text(card.transform, string.Join("   ", lines) + synText, Theme.FontTiny, Theme.Text, TextAlignmentOptions.TopLeft, false, "Stats");
                st.rectTransform.anchorMin = Vector2.zero;
                st.rectTransform.anchorMax = Vector2.one;
                st.rectTransform.offsetMin = new Vector2(58f, 6f);
                st.rectTransform.offsetMax = new Vector2(-8f, -32f);
                st.enableAutoSizing = true;
                st.fontSizeMin = 7f;
                st.fontSizeMax = Theme.FontTiny + 1f;
                cards[id] = card;
                var press = card.gameObject.AddComponent<PressHandler>();
                press.OnTap = () =>
                {
                    selected = mid;
                    foreach (var kv in cards) kv.Value.color = kv.Key == mid ? Theme.Gold : new Color(0.7f, 0.68f, 0.78f, 1f);
                    confirm.interactable = true;
                    GameApp.I.Audio?.Play("ui_toggle");
                };
            }
            confirm = UI.Button(panel, L.T("ui.equip"), () =>
            {
                if (selected == null) return;
                Close(m);
                onChoose(selected);
            }, ButtonStyle.Primary, "icon/check", 52f, Theme.FontH2, "unlock");
            confirm.interactable = false;
        }

        // =========================================================================================
        // Boss introduction
        // =========================================================================================
        public void ShowBossIntro(string bossId, Action onDone)
        {
            var m = Open("boss", out var panel, 330f, 0f, new Color(0.08f, 0.01f, 0.03f, 0.85f));
            void Done()
            {
                Close(m);
                onDone?.Invoke();
            }
            m.back = () => { Done(); return true; };
            var warn = UI.Text(panel, L.T("ui.boss_warning"), Theme.FontSmall, Theme.Red, TextAlignmentOptions.Center, true, "Warning");
            UI.Size(warn, -1, 18f);
            var portrait = UI.Img(panel, "portrait/" + bossId, null, false, "Portrait");
            portrait.preserveAspect = true;
            UI.Size(portrait, -1, 150f, -1, -1, 150f);
            Title(panel, L.T("boss." + bossId + ".name"), Theme.Gold);
            Line(panel, L.T("boss." + bossId + ".title"), Theme.FontSmall, Theme.TextDim);
            Line(panel, "<i>" + L.T("boss." + bossId + ".intro") + "</i>", Theme.FontBody, Theme.Text);
            Line(panel, L.T("boss." + bossId + ".hint"), Theme.FontSmall, Theme.Cyan, TextAlignmentOptions.Left);
            UI.Button(panel, L.T("ui.boss_intro_continue"), Done, ButtonStyle.Danger, "icon/sword", 52f);
        }

        // =========================================================================================
        // Pause (+ quick settings)
        // =========================================================================================
        public void ShowPause(Action onResume, Action onQuit)
        {
            var m = Open("pause", out var panel, 330f);
            void Resume()
            {
                Close(m);
                onResume?.Invoke();
            }
            m.back = () => { Resume(); return true; };
            Title(panel, L.T("ui.paused"));
            var app = GameApp.I;
            var s = app.Meta.Data.settings;
            UI.Slider(panel, L.T("ui.settings.music"), s.music, v => { s.music = v; app.ApplySettings(); });
            UI.Slider(panel, L.T("ui.settings.sfx"), s.sfx, v => { s.sfx = v; app.ApplySettings(); });
            UI.Toggle(panel, L.T("ui.settings.shake"), s.screenShake, v => s.screenShake = v);
            UI.Toggle(panel, L.T("ui.settings.flashes"), s.flashes, v => s.flashes = v);
            UI.Toggle(panel, L.T("ui.settings.damage_numbers"), s.damageNumbers, v => s.damageNumbers = v);
            UI.Toggle(panel, L.T("ui.settings.vibration"), s.vibration, v => { s.vibration = v; app.ApplySettings(); });
            UI.Spacer(panel, 4f);
            UI.Button(panel, L.T("ui.resume"), () => { app.SaveNow(); Resume(); }, ButtonStyle.Primary, "icon/play", 52f);
            UI.Button(panel, L.T("ui.quit"), () => Confirm(L.T("ui.quit_confirm"), () =>
            {
                Close(m);
                onQuit?.Invoke();
            }), ButtonStyle.Danger, "icon/flag", 46f, Theme.FontBody);
        }

        public void ClosePause()
        {
            var m = _stack.Find(x => x.kind == "pause");
            if (m != null) Close(m);
        }

        // =========================================================================================
        // Revive
        // =========================================================================================
        public void ShowRevive(Battle b, IAdsService ads, Action onRevive, Action onDecline)
        {
            var m = Open("revive", out var panel, 330f, 0f, new Color(0.12f, 0.0f, 0.02f, 0.82f));
            m.back = () => true;
            Title(panel, L.T("ui.revive_title"), Theme.Red);
            Line(panel, L.F("ui.revive_body", ("pct", b.C.Tuning.economy.reviveHealthPercent + "%")), Theme.FontSmall, Theme.Text);
            bool available = ads != null && ads.IsAvailable;
            string label = L.T("ui.revive") + (ads != null && ads.IsMock ? "  [" + L.T("ui.dev_mock") + "]" : "");
            bool busy = false;
            var revive = UI.Button(panel, label, () =>
            {
                if (!available)
                {
                    Toast.Show(ads != null ? ads.UnavailableReason : L.T("ui.revive_unavailable"), Theme.TextDim);
                    return;
                }
                if (busy) return;
                busy = true;
                ads.ShowRewarded("revive", result =>
                {
                    busy = false;
                    if (result == AdResult.Completed)
                    {
                        Close(m);
                        onRevive?.Invoke();
                    }
                    else Toast.Show(L.T("ui.ad_not_completed"), Theme.TextDim);
                });
            }, ButtonStyle.Primary, "icon/play_ad", 52f, Theme.FontBody);
            if (!available)
            {
                revive.GetComponent<Image>().color = new Color(1f, 1f, 1f, 0.45f);
                Line(panel, ads != null ? ads.UnavailableReason : L.T("ui.revive_unavailable"), Theme.FontTiny, Theme.TextMuted);
            }
            UI.Button(panel, L.T("ui.give_up"), () =>
            {
                Close(m);
                onDecline?.Invoke();
            }, ButtonStyle.Normal, "icon/flag", 46f, Theme.FontBody);
        }

        // =========================================================================================
        // Confirmation
        // =========================================================================================
        public void Confirm(string text, Action onYes, Action onNo = null)
        {
            var m = Open("confirm", out var panel, 310f);
            m.back = () => { Close(m); onNo?.Invoke(); return true; };
            Line(panel, text, Theme.FontBody, Theme.Text);
            var row = UI.Rect(panel, "Buttons");
            UI.Size(row, -1, 50f, -1, -1, 50f);
            UI.HLayout(row, Theme.S2, 0f);
            UI.Button(row, L.T("ui.cancel"), () => { Close(m); onNo?.Invoke(); }, ButtonStyle.Normal, null, 48f, Theme.FontBody, "ui_back");
            UI.Button(row, L.T("ui.confirm"), () => { Close(m); onYes?.Invoke(); }, ButtonStyle.Danger, null, 48f, Theme.FontBody);
        }

        // =========================================================================================
        // Victory / defeat summary
        // =========================================================================================
        public void ShowEnd(GameContent c, RunResult r, RewardSummary rewards, bool canRetry, Action onContinue, Action onRetry)
        {
            var m = Open("end", out var panel, 340f, 0f, new Color(0.02f, 0.01f, 0.05f, 0.86f));
            m.back = () => { Close(m); onContinue?.Invoke(); return true; };
            bool win = r.victory;
            Title(panel, win ? L.T("ui.victory") : L.T("ui.defeat"), win ? Theme.Gold : Theme.Red);
            var hero = UI.Img(panel, "portrait/arc_light_cat", null, false, "Hero");
            hero.preserveAspect = true;
            UI.Size(hero, -1, 84f, -1, -1, 84f);
            if (!win && r.abandoned) Line(panel, L.T("ui.run_abandoned"), Theme.FontTiny, Theme.TextMuted);

            var stats = new List<string>
            {
                r.totalWaves > 0 ? L.F("ui.waves_cleared", ("n", r.wavesCleared), ("total", r.totalWaves)) : L.F("ui.waves_cleared_endless", ("n", r.wavesCleared)),
                L.F("ui.kills", ("n", r.stats.kills)),
                L.F("ui.level_reached", ("n", r.levelReached)),
                L.F("ui.time", ("t", TextFormat.Duration(r.stats.timeSec))),
            };
            Line(panel, string.Join("\n", stats), Theme.FontSmall, Theme.Text);

            if (!win && !string.IsNullOrEmpty(r.principalDamageSource))
            {
                string src = StatText.SourceName(c, r.principalDamageSource);
                Line(panel, L.F("ui.defeat_cause", ("source", src), ("pct", TextFormat.Percent(r.principalDamageShare))), Theme.FontSmall, Theme.Red);
                Line(panel, "<b>" + L.T("ui.defeat_try") + ":</b> " + L.T(StatText.TipKey(c, r.principalDamageSource)), Theme.FontSmall, Theme.Cyan);
            }

            if (rewards != null)
            {
                var lines = new List<string>();
                if (rewards.moonGold > 0) lines.Add("+" + TextFormat.Compact(rewards.moonGold) + " " + L.T("ui.moon_gold"));
                if (rewards.stormShards > 0) lines.Add("+" + rewards.stormShards + " " + L.T("ui.storm_shards"));
                if (rewards.firstClear) lines.Add(L.T("ui.first_clear"));
                if (!string.IsNullOrEmpty(rewards.moduleUnlocked)) lines.Add(L.F("ui.unlocked_module", ("name", L.T("module." + rewards.moduleUnlocked + ".name"))));
                if (rewards.newRecord) lines.Add(L.T("ui.new_record"));
                if (rewards.achievementsReady.Count > 0) lines.Add(L.F("ui.achievements_ready", ("n", rewards.achievementsReady.Count)));
                if (lines.Count == 0) lines.Add(L.T("ui.no_rewards"));
                var head = UI.Text(panel, L.T("ui.rewards"), Theme.FontBody, Theme.Gold, TextAlignmentOptions.Center, true, "RewardsTitle");
                UI.Size(head, -1, 20f);
                Line(panel, string.Join("\n", lines), Theme.FontSmall, Theme.Text);
            }

            var row = UI.Rect(panel, "Buttons");
            UI.Size(row, -1, 54f, -1, -1, 54f);
            UI.HLayout(row, Theme.S2, 0f);
            if (canRetry)
                UI.Button(row, L.T("ui.retry"), () => { Close(m); onRetry?.Invoke(); }, ButtonStyle.Normal, "icon/refresh", 52f, Theme.FontBody);
            UI.Button(row, L.T("ui.continue"), () => { Close(m); onContinue?.Invoke(); }, ButtonStyle.Primary, "icon/home", 52f, Theme.FontBody);
        }
    }
}
