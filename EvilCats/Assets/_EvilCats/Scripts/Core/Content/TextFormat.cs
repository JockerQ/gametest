using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace EvilCats.Content
{
    /// <summary>
    /// Fills description templates from data so every number shown to the player is the
    /// real value. Tokens:
    ///   {p:key}   perk/ability parameter            {p%:key}  parameter as percent (0.12 -> 12%)
    ///   {m:i}     i-th stat modifier value          {m%:i}    modifier value as percent
    ///   {mx%:i}   multiplier as signed change       (1.3 -> +30%, 0.85 -> -15%)
    ///   {mr%:i}   rate multiplier as signed change  (0.7 -> -30%)
    ///   {mc%:i}   cooldown change of a rate mult    (0.7407 -> +35%)
    ///   {ma:i}    absolute value of a modifier      (-1 -> 1)
    /// Any other {name} is filled from the optional args dictionary.
    /// </summary>
    public static class TextFormat
    {
        private static readonly CultureInfo Inv = CultureInfo.InvariantCulture;

        public static string Number(double v)
        {
            if (Math.Abs(v - Math.Round(v)) < 1e-4) return Math.Round(v).ToString("0", Inv);
            return v.ToString("0.##", Inv);
        }

        public static string Percent(double v) => Number(Math.Round(v * 1000.0) / 10.0) + "%";

        public static string SignedPercent(double v)
        {
            double pct = Math.Round(v * 1000.0) / 10.0;
            return (pct >= 0 ? "+" : "-") + Number(Math.Abs(pct)) + "%";
        }

        public static string Compact(long v)
        {
            if (v >= 1_000_000) return (v / 1_000_000.0).ToString("0.#", Inv) + "M";
            if (v >= 10_000) return (v / 1_000.0).ToString("0.#", Inv) + "K";
            return v.ToString("N0", Inv);
        }

        public static string Duration(float seconds)
        {
            int s = Math.Max(0, (int)Math.Round(seconds));
            return (s / 60).ToString(Inv) + ":" + (s % 60).ToString("00", Inv);
        }

        public static string Perk(GameContent c, PerkDef p)
        {
            if (p == null) return "";
            return Fill(c.Strings.Get("perk." + p.id + ".desc"), p.p, p.mods, null);
        }

        public static string Fill(string template, Dictionary<string, float> p, List<StatModDef> mods, IDictionary<string, string> args)
        {
            if (string.IsNullOrEmpty(template) || template.IndexOf('{') < 0) return template ?? "";
            var sb = new StringBuilder(template.Length + 16);
            int i = 0;
            while (i < template.Length)
            {
                char ch = template[i];
                int end = ch == '{' ? template.IndexOf('}', i + 1) : -1;
                if (end < 0)
                {
                    sb.Append(ch);
                    i++;
                    continue;
                }
                string token = template.Substring(i + 1, end - i - 1);
                string value = Resolve(token, p, mods, args);
                if (value == null) sb.Append('{').Append(token).Append('}');
                else sb.Append(value);
                i = end + 1;
            }
            return sb.ToString();
        }

        /// <summary>Returns null when the token cannot be resolved (the validator reports those).</summary>
        public static string Resolve(string token, Dictionary<string, float> p, List<StatModDef> mods, IDictionary<string, string> args)
        {
            int colon = token.IndexOf(':');
            if (colon < 0) return args != null && args.TryGetValue(token, out var a) ? a : null;
            string kind = token.Substring(0, colon);
            string key = token.Substring(colon + 1);
            switch (kind)
            {
                case "p":
                    return p != null && p.TryGetValue(key, out var pv) ? Number(pv) : null;
                case "p%":
                    return p != null && p.TryGetValue(key, out var pp) ? Percent(pp) : null;
            }
            if (mods == null || !int.TryParse(key, NumberStyles.Integer, Inv, out int idx) || idx < 0 || idx >= mods.Count) return null;
            float v = mods[idx].value;
            switch (kind)
            {
                case "m": return Number(v);
                case "m%": return Percent(v);
                case "mx%": return SignedPercent(v - 1f);
                case "mr%": return SignedPercent(v - 1f);
                case "mc%": return SignedPercent(v > 1e-6f ? 1f / v - 1f : 0f);
                case "ma": return Number(Math.Abs(v));
                default: return null;
            }
        }
    }
}
