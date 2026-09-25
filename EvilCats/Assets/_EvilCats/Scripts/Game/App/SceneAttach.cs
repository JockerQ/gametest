using UnityEngine;
using UnityEngine.SceneManagement;

namespace EvilCats.Game
{
    /// <summary>Base for the three scene controllers (Boot, Hub, Battle).</summary>
    public abstract class SceneController : MonoBehaviour
    {
        public static SceneController Current { get; private set; }

        protected virtual void Awake()
        {
            Current = this;
            GameApp.Ensure();
        }

        protected virtual void OnDestroy()
        {
            if (Current == this) Current = null;
        }

        /// <summary>Android back button / Escape. Return true when handled.</summary>
        public virtual bool OnBack() => false;
    }

    /// <summary>
    /// Makes every scene self-starting: after a scene loads, the matching controller is added if
    /// the scene does not already contain one. Pressing Play in any scene (even an empty one)
    /// therefore starts the game; the setup script's scenes simply make the structure explicit.
    /// </summary>
    public static class SceneAttach
    {
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void OnFirstSceneLoaded()
        {
            SceneManager.sceneLoaded -= OnSceneLoaded;
            SceneManager.sceneLoaded += OnSceneLoaded;
            Attach(SceneManager.GetActiveScene().name);
        }

        private static void OnSceneLoaded(Scene scene, LoadSceneMode mode)
        {
            if (mode == LoadSceneMode.Single) Attach(scene.name);
        }

        /// <summary>The Unity Test Framework runs Play Mode tests in its own scene with this object;
        /// tests create the controllers they need themselves.</summary>
        private static bool InsideTestRunner() => GameObject.Find("Code-based tests runner") != null;

        private static void Attach(string sceneName)
        {
            if (InsideTestRunner()) return;
            GameApp.Ensure();
            if (SceneController.Current != null) return;
            switch (sceneName)
            {
                case GameApp.HubScene:
                    new GameObject("HubController").AddComponent<HubController>();
                    break;
                case GameApp.BattleScene:
                    new GameObject("BattleController").AddComponent<BattleController>();
                    break;
                default:
                    new GameObject("BootController").AddComponent<BootController>();
                    break;
            }
        }

        /// <summary>Fallback when scenes are not in Build Settings: swap controllers inside the current scene.</summary>
        public static void SwapInPlace(string sceneName)
        {
            var current = SceneController.Current;
            if (current != null) Object.Destroy(current.gameObject);
            // destroy any other root objects created by the previous controller (cameras, canvases)
            foreach (var root in SceneManager.GetActiveScene().GetRootGameObjects())
                if (root.GetComponent<GameApp>() == null) Object.Destroy(root);
            switch (sceneName)
            {
                case GameApp.HubScene: new GameObject("HubController").AddComponent<HubController>(); break;
                case GameApp.BattleScene: new GameObject("BattleController").AddComponent<BattleController>(); break;
                default: new GameObject("BootController").AddComponent<BootController>(); break;
            }
        }
    }
}
