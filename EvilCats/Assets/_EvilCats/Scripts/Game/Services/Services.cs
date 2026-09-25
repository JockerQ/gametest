using System;
using System.Collections.Generic;
using UnityEngine;

namespace EvilCats.Game
{
    // ======================================================================================
    // Online/commercial service adapters.
    //
    // The game is fully playable offline with the default "Unconfigured" implementations:
    // they report IsAvailable = false with a reason the UI shows, and they never fake success.
    // DevMock implementations exist ONLY in the Editor and development builds, are labelled
    // "DEV MOCK" in the UI, and are compiled out of release builds (#if DEVELOPMENT_BUILD ||
    // UNITY_EDITOR). Real SDKs (Unity Ads/LevelPlay, Google Play Billing, Play Games, etc.) must
    // be integrated by the owner behind these interfaces; see NEXT_STEPS.md.
    // ======================================================================================

    public enum AdResult { Completed, Skipped, Failed, NoFill, NotAvailable }

    public interface IAdsService
    {
        bool IsAvailable { get; }
        string UnavailableReason { get; }
        bool IsMock { get; }
        /// <summary>Invoke the callback exactly once. Grant a reward ONLY for AdResult.Completed.</summary>
        void ShowRewarded(string placement, Action<AdResult> onDone);
    }

    public sealed class ProductInfo
    {
        public string id;
        public string localizedPrice;   // only ever filled from a real, configured store
        public bool owned;
    }

    public interface IPurchaseService
    {
        bool IsAvailable { get; }
        string UnavailableReason { get; }
        bool IsMock { get; }
        IReadOnlyList<ProductInfo> Products { get; }
        void Purchase(string productId, Action<bool, string> onDone);
        void RestorePurchases(Action<bool, string> onDone);
    }

    public interface IAnalyticsService
    {
        bool IsAvailable { get; }
        void Event(string name, Dictionary<string, object> data = null);
    }

    public interface IAuthService
    {
        bool IsAvailable { get; }
        string UnavailableReason { get; }
        bool IsSignedIn { get; }
        void SignIn(Action<bool, string> onDone);
    }

    public interface ICloudSaveService
    {
        bool IsAvailable { get; }
        string UnavailableReason { get; }
    }

    public interface ILeaderboardService
    {
        bool IsAvailable { get; }
        string UnavailableReason { get; }
    }

    public sealed class ServiceHub
    {
        public IAdsService Ads;
        public IPurchaseService Purchases;
        public IAnalyticsService Analytics;
        public IAuthService Auth;
        public ICloudSaveService Cloud;
        public ILeaderboardService Leaderboards;

        public static ServiceHub CreateDefault()
        {
            var hub = new ServiceHub
            {
                Ads = new UnconfiguredAds(),
                Purchases = new UnconfiguredPurchases(),
                Analytics = new NoAnalytics(),
                Auth = new UnconfiguredAuth(),
                Cloud = new UnconfiguredCloud(),
                Leaderboards = new UnconfiguredLeaderboards(),
            };
#if UNITY_EDITOR || DEVELOPMENT_BUILD
            // Opt-in only (Settings > "Developer: mock services"), never enabled by default.
            if (PlayerPrefs.GetInt("evilcats_dev_mock_services", 0) == 1)
            {
                hub.Ads = new DevMockAds();
                hub.Purchases = new DevMockPurchases();
            }
#endif
            return hub;
        }
    }

    internal static class NotConfigured
    {
        public static string Reason => L.T("ui.service.not_configured");
    }

    public sealed class UnconfiguredAds : IAdsService
    {
        public bool IsAvailable => false;
        public string UnavailableReason => L.T("ui.revive_unavailable");
        public bool IsMock => false;
        public void ShowRewarded(string placement, Action<AdResult> onDone) => onDone?.Invoke(AdResult.NotAvailable);
    }

    public sealed class UnconfiguredPurchases : IPurchaseService
    {
        public bool IsAvailable => false;
        public string UnavailableReason => L.T("ui.shop.store_unavailable");
        public bool IsMock => false;
        public IReadOnlyList<ProductInfo> Products => Array.Empty<ProductInfo>();
        public void Purchase(string productId, Action<bool, string> onDone) => onDone?.Invoke(false, UnavailableReason);
        public void RestorePurchases(Action<bool, string> onDone) => onDone?.Invoke(false, UnavailableReason);
    }

    /// <summary>No analytics are collected in this build.</summary>
    public sealed class NoAnalytics : IAnalyticsService
    {
        public bool IsAvailable => false;
        public void Event(string name, Dictionary<string, object> data = null) { }
    }

    public sealed class UnconfiguredAuth : IAuthService
    {
        public bool IsAvailable => false;
        public string UnavailableReason => L.T("ui.sign_in_unavailable");
        public bool IsSignedIn => false;
        public void SignIn(Action<bool, string> onDone) => onDone?.Invoke(false, UnavailableReason);
    }

    public sealed class UnconfiguredCloud : ICloudSaveService
    {
        public bool IsAvailable => false;
        public string UnavailableReason => L.T("ui.profile.cloud_unavailable");
    }

    public sealed class UnconfiguredLeaderboards : ILeaderboardService
    {
        public bool IsAvailable => false;
        public string UnavailableReason => L.T("ui.records.local_note");
    }

#if UNITY_EDITOR || DEVELOPMENT_BUILD
    /// <summary>DEVELOPMENT ONLY. Simulates a rewarded ad so the revive flow can be tested. Labelled in the UI.</summary>
    public sealed class DevMockAds : IAdsService
    {
        public bool IsAvailable => true;
        public string UnavailableReason => null;
        public bool IsMock => true;
        private bool _showing;

        public void ShowRewarded(string placement, Action<AdResult> onDone)
        {
            if (_showing) return;          // duplicate taps while "showing" are ignored
            _showing = true;
            Debug.Log("[DEV MOCK] Rewarded ad '" + placement + "' completed (no real ad shown).");
            _showing = false;
            onDone?.Invoke(AdResult.Completed);
        }
    }

    /// <summary>DEVELOPMENT ONLY. Never shows a price and never claims a real purchase happened.</summary>
    public sealed class DevMockPurchases : IPurchaseService
    {
        public bool IsAvailable => false;
        public string UnavailableReason => "[DEV MOCK] " + L.T("ui.shop.store_unavailable");
        public bool IsMock => true;
        public IReadOnlyList<ProductInfo> Products => Array.Empty<ProductInfo>();
        public void Purchase(string productId, Action<bool, string> onDone) => onDone?.Invoke(false, UnavailableReason);
        public void RestorePurchases(Action<bool, string> onDone) => onDone?.Invoke(false, UnavailableReason);
    }
#endif
}
