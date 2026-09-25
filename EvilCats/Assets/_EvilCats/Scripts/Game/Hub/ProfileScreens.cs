using System.Collections.Generic;
using EvilCats.Content;
using EvilCats.Meta;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

namespace EvilCats.Game
{
    // =============================================================================================
    // Shop: cosmetics only (never combat power). Real-money items stay visibly "not configured".
    // =============================================================================================
    public sealed class ShopScreen : HubScreen
    {
        public override string TitleKey => "ui.shop.title";
        public override string Tab => "more";

        public override void Build(RectTransform content)
        {
            var list = UI.ScrollList(content, out _, Theme.S2, Theme.S3);
            UI.Stretch((RectTransform)list.parent.parent);
            HubKit.Wrap(list, L.T("ui.shop.note"), Theme.FontSmall, Theme.TextDim, TextAlignmentOptions.Top);

            // Supporter pack: shown, but honest that the store is not configured in this build
            var store = App.Services.Purchases;
            var sp = HubKit.Card(list, 0f, "ui/card", Theme.Gold);
            HubKit.Label(sp, L.T("ui.shop.supporter"), Theme.FontH2, Theme.Gold, true);
            HubKit.Wrap(sp, L.T("ui.shop.supporter_desc"), Theme.FontSmall, Theme.Text);
            string reason = store.IsAvailable ? null : store.UnavailableReason;
            if (reason != null) HubKit.Wrap(sp, reason + (store.IsMock ? "  [" + L.T("ui.dev_mock") + "]" : ""), Theme.FontTiny, Theme.Red);
            var buy = UI.Button(sp, L.T("ui.buy"), () =>
            {
                if (!store.IsAvailable) { App.Audio?.Play("ui_denied"); Toast.Show(store.UnavailableReason); return; }
                store.Purchase("supporter_pack", (ok, msg) => Toast.Show(msg ?? "", ok ? Theme.Gold : Theme.Red));
            }, ButtonStyle.Normal, "icon/shop", 44f, Theme.FontBody);
            if (!store.IsAvailable) buy.GetComponent<Image>().color = new Color(1f, 1f, 1f, 0.5f);
            UI.Button(sp, L.T("ui.shop.restore"), () =>
                store.RestorePurchases((ok, msg) => Toast.Show(msg ?? "", ok ? Theme.Gold : Theme.TextDim)), ButtonStyle.Ghost, null, 36f, Theme.FontSmall);

            var cos = new List<CosmeticDef>(C.Progression.cosmetics);
            cos.Sort((a, b) => a.order.CompareTo(b.order));
            HubKit.Section(list, L.T("ui.shop.skins"));
            foreach (var c in cos) if (c.kind == "hero_skin") Item(list, c);
            HubKit.Section(list, L.T("ui.shop.banners"));
            foreach (var c in cos) if (c.kind == "banner") Item(list, c);
        }

        private void Item(RectTransform list, CosmeticDef c)
        {
            bool owned = Data.cosmeticsOwned.Contains(c.id);
            bool equipped = c.kind == "hero_skin" ? Data.heroSkin == c.id : Data.banner == c.id;
            var card = HubKit.Card(list, 0f, "ui/card", equipped ? Theme.Gold : (Color?)null);
            var row = HubKit.Row(card, 64f);
            if (c.kind == "hero_skin")
            {
                var preview = UI.Img(row, null, null, false, "Preview");
                preview.sprite = App.Sprites.GetForUi("hero/" + c.id + "/idle/0", 1.5f);
                preview.preserveAspect = true;
                UI.Size(preview, 60f, 60f);
            }
            else
            {
                var flag = UI.Icon(row, "icon/flag", 44f, HubKit.BannerColor(c.id));
                UI.Size(flag, 60f, 60f);
            }
            var col = UI.Rect(row, "Text");
            UI.Size(col, -1, 64f, 1);
            UI.VLayout(col, 2f, 0f, TextAnchor.MiddleLeft);
            HubKit.Label(col, L.T("cosmetic." + c.id + ".name"), Theme.FontBody, Theme.Text, true);
            string price;
            if (owned) price = equipped ? L.T("ui.equipped") : L.T("ui.owned");
            else if (c.supporterOnly) price = L.T("ui.shop.supporter");
            else if (!string.IsNullOrEmpty(c.achievement)) price = L.F("ui.shop.achievement_unlock", ("name", L.T("achievement." + c.achievement + ".name")));
            else if (c.moonGold <= 0 && c.stormShards <= 0) price = L.T("ui.free");
            else price = c.moonGold > 0 ? c.moonGold + " " + L.T("ui.moon_gold") : c.stormShards + " " + L.T("ui.storm_shards");
            HubKit.Label(col, price, Theme.FontSmall, owned ? Theme.Green : Theme.Gold);
            if (owned && !equipped)
            {
                var b = UI.Button(row, L.T("ui.equip"), () => Hub.Explain(Meta.EquipCosmetic(c.id, GameApp.UtcNow)), ButtonStyle.Primary, null, 42f, Theme.FontSmall);
                UI.Size(b, 88f, 42f);
            }
            else if (!owned && !c.supporterOnly && string.IsNullOrEmpty(c.achievement))
            {
                var b = UI.Button(row, L.T("ui.buy"), () =>
                {
                    var r = Meta.BuyCosmetic(c.id, GameApp.UtcNow);
                    if (r == MetaResult.Ok) { App.Audio?.Play("purchase"); Meta.EquipCosmetic(c.id, GameApp.UtcNow); }
                    else Hub.Explain(r);
                }, ButtonStyle.Primary, c.moonGold > 0 ? "icon/moon_gold" : "icon/storm_shard", 42f, Theme.FontSmall);
                UI.Size(b, 88f, 42f);
            }
        }
    }

    // =============================================================================================
    // Profile: local guest profile. No fake login: sign-in and cloud save say they are not configured.
    // =============================================================================================
    public sealed class ProfileScreen : HubScreen
    {
        public override string TitleKey => "ui.profile.title";
        public override string Tab => "more";

        public override void Build(RectTransform content)
        {
            var list = UI.ScrollList(content, out _, Theme.S3, Theme.S4);
            UI.Stretch((RectTransform)list.parent.parent);
            var avatar = UI.Img(list, "avatar/" + Data.avatar, null, false, "Avatar");
            avatar.preserveAspect = true;
            UI.Size(avatar, -1, 96f, -1, -1, 96f);
            HubKit.Label(list, L.T("ui.profile.name"), Theme.FontSmall, Theme.TextDim);
            UI.Input(list, Data.displayName, L.T("ui.profile.name_rules"), name =>
            {
                if (name == Data.displayName) return;
                var r = Meta.SetDisplayName(name, GameApp.UtcNow);
                if (r == MetaResult.Ok) Toast.Show(L.T("ui.saved"), Theme.Green);
                else Hub.Explain(r);
            });
            HubKit.Wrap(list, L.T("ui.profile.name_rules"), Theme.FontTiny, Theme.TextMuted);

            HubKit.Section(list, L.T("ui.profile.avatar"));
            var grid = UI.Rect(list, "Avatars");
            var g = grid.gameObject.AddComponent<GridLayoutGroup>();
            g.cellSize = new Vector2(72f, 72f);
            g.spacing = new Vector2(8f, 8f);
            g.childAlignment = TextAnchor.UpperCenter;
            int rows = Mathf.CeilToInt(C.Progression.avatars.Count / 4f);
            UI.Size(grid, -1, rows * 80f, -1, -1, rows * 80f);
            foreach (var a in C.Progression.avatars)
            {
                string id = a;
                var frame = UI.Img(grid, "ui/slot_frame", Data.avatar == id ? Theme.Gold : Color.white, true, "Avatar " + id);
                frame.type = Image.Type.Sliced;
                var pic = UI.Img(frame.transform, "avatar/" + id, null, false, "Pic");
                pic.preserveAspect = true;
                UI.Stretch(pic.rectTransform, 6, 6, 6, 6);
                frame.gameObject.AddComponent<PressHandler>().OnTap = () =>
                {
                    App.Audio?.Play("ui_toggle");
                    Hub.Explain(Meta.SetAvatar(id, GameApp.UtcNow));
                };
            }

            HubKit.Section(list, L.T("ui.profile.account"));
            var acc = HubKit.Card(list);
            HubKit.Label(acc, L.T("ui.profile.guest"), Theme.FontBody, Theme.Text, true);
            HubKit.Wrap(acc, L.T("ui.sign_in_unavailable"), Theme.FontSmall, Theme.TextDim);
            var auth = App.Services.Auth;
            var sign = UI.Button(acc, L.T("ui.sign_in"), () => Toast.Show(auth.UnavailableReason), ButtonStyle.Normal, "icon/cloud", 44f, Theme.FontBody);
            if (!auth.IsAvailable) sign.GetComponent<Image>().color = new Color(1f, 1f, 1f, 0.5f);
            HubKit.Label(acc, L.T("ui.profile.cloud"), Theme.FontBody, Theme.Text, true);
            HubKit.Wrap(acc, App.Services.Cloud.UnavailableReason, Theme.FontSmall, Theme.TextDim);
            HubKit.Wrap(list, "ID: " + Data.profileId.Substring(0, System.Math.Min(8, Data.profileId.Length)), Theme.FontTiny, Theme.TextMuted, TextAlignmentOptions.Top);
        }
    }

    // =============================================================================================
    // Settings
    // =============================================================================================
    public sealed class SettingsScreen : HubScreen
    {
        public override string TitleKey => "ui.settings";
        public override string Tab => "more";

        public override void Build(RectTransform content)
        {
            var list = UI.ScrollList(content, out _, Theme.S1, Theme.S4);
            UI.Stretch((RectTransform)list.parent.parent);
            var s = Data.settings;
            HubKit.Section(list, L.T("ui.settings.audio"));
            UI.Slider(list, L.T("ui.settings.music"), s.music, v => { s.music = v; App.ApplySettings(); });
            UI.Slider(list, L.T("ui.settings.sfx"), s.sfx, v => { s.sfx = v; App.ApplySettings(); });

            HubKit.Section(list, L.T("ui.settings.comfort"));
            UI.Toggle(list, L.T("ui.settings.vibration"), s.vibration, v => { s.vibration = v; App.ApplySettings(); App.SaveNow(); });
            UI.Toggle(list, L.T("ui.settings.shake"), s.screenShake, v => { s.screenShake = v; App.SaveNow(); });
            UI.Toggle(list, L.T("ui.settings.flashes"), s.flashes, v => { s.flashes = v; App.SaveNow(); });
            UI.Toggle(list, L.T("ui.settings.damage_numbers"), s.damageNumbers, v => { s.damageNumbers = v; App.SaveNow(); });

            HubKit.Section(list, L.T("ui.settings.gameplay"));
            UI.Toggle(list, L.T("ui.settings.default_speed"), s.startAt2x, v => { s.startAt2x = v; App.SaveNow(); });
            HubKit.Label(list, L.T("ui.settings.route_layout"), Theme.FontBody, Theme.Text);
            var routes = HubKit.Row(list, 46f, Theme.S2);
            routes.GetComponent<HorizontalLayoutGroup>().childForceExpandWidth = true;
            foreach (var layout in new[] { "routes_5", "routes_3" })
            {
                string id = layout;
                var b = UI.Button(routes, L.T("ui.settings.route_layout." + id), () =>
                {
                    s.routeLayout = id;
                    App.SaveNow();
                    Hub.Rebuild();
                }, s.routeLayout == id ? ButtonStyle.Primary : ButtonStyle.Normal, null, 44f, Theme.FontSmall);
                UI.Size(b, -1, 44f, 1);
            }
            HubKit.Wrap(list, L.T("ui.settings.route_layout_note"), Theme.FontTiny, Theme.TextDim);
            var lang = HubKit.Row(list, 40f);
            HubKit.Label(lang, L.T("ui.settings.language"), Theme.FontBody, Theme.Text, false, -1, 1);
            HubKit.Label(lang, L.T("ui.settings.language_value"), Theme.FontBody, Theme.TextDim, false, 100f);

#if UNITY_EDITOR || DEVELOPMENT_BUILD
            HubKit.Section(list, "Developer");
            bool mock = PlayerPrefs.GetInt("evilcats_dev_mock_services", 0) == 1;
            UI.Toggle(list, "[" + L.T("ui.dev_mock") + "] Ads", mock, v =>
            {
                PlayerPrefs.SetInt("evilcats_dev_mock_services", v ? 1 : 0);
                PlayerPrefs.Save();
                App.ReloadServices();
            });
#endif
            UI.Spacer(list, 8f);
            HubKit.Wrap(list, L.T("ui.settings.save_note"), Theme.FontTiny, Theme.TextDim, TextAlignmentOptions.Top);
            UI.Button(list, L.T("ui.credits"), () => Hub.Open(new CreditsScreen()), ButtonStyle.Normal, "icon/info", 46f, Theme.FontBody);
            UI.Button(list, L.T("ui.settings.reset"), () => Hub.Confirm(L.T("ui.settings.reset_confirm"), () =>
                Hub.Confirm(L.T("ui.settings.reset_confirm2"), App.ResetProgress, L.T("ui.settings.reset"))), ButtonStyle.Danger, "icon/warning", 46f, Theme.FontBody);
        }

        public override void Refresh() { }   // sliders would lose their drag if rebuilt mid-change

        public override void OnHide() => App.SaveNow();
    }
}
