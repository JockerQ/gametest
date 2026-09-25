using System;
using UnityEditor;
using UnityEngine;

namespace EvilCats.EditorTools
{
    /// <summary>
    /// Import settings for the game's generated assets, applied automatically on import:
    /// pixel art stays crisp and exact (point filtering, no compression, no mipmaps, no resizing
    /// to powers of two - the atlas JSON rectangles depend on the exact pixel size). Music streams;
    /// short effects are decompressed on load so they play instantly.
    /// </summary>
    public sealed class ImportRules : AssetPostprocessor
    {
        public const string ArtRoot = "Assets/_EvilCats/Art/";
        public const string UiRoot = "Assets/_EvilCats/UI/";
        public const string AudioRoot = "Assets/_EvilCats/Audio/";

        public static bool IsGameTexture(string path) =>
            path.StartsWith(ArtRoot, StringComparison.Ordinal) || path.StartsWith(UiRoot, StringComparison.Ordinal);

        private void OnPreprocessTexture()
        {
            if (!IsGameTexture(assetPath)) return;
            Apply((TextureImporter)assetImporter);
        }

        public static void Apply(TextureImporter ti)
        {
            ti.textureType = TextureImporterType.Default;
            ti.npotScale = TextureImporterNPOTScale.None;
            ti.mipmapEnabled = false;
            ti.filterMode = FilterMode.Point;
            ti.wrapMode = TextureWrapMode.Clamp;
            ti.textureCompression = TextureImporterCompression.Uncompressed;
            ti.alphaSource = TextureImporterAlphaSource.FromInput;
            ti.alphaIsTransparency = true;
            ti.sRGBTexture = true;
            ti.isReadable = false;
            ti.maxTextureSize = 4096;
        }

        /// <summary>True when an existing importer already has the settings Apply() would give it.</summary>
        public static bool Matches(TextureImporter ti) =>
            ti.textureType == TextureImporterType.Default && ti.npotScale == TextureImporterNPOTScale.None &&
            !ti.mipmapEnabled && ti.filterMode == FilterMode.Point && ti.wrapMode == TextureWrapMode.Clamp &&
            ti.textureCompression == TextureImporterCompression.Uncompressed && ti.maxTextureSize >= 4096;

        private void OnPreprocessAudio()
        {
            if (!assetPath.StartsWith(AudioRoot, StringComparison.Ordinal)) return;
            Apply((AudioImporter)assetImporter, IsMusic(assetPath));
        }

        public static bool IsMusic(string path) => path.Replace('\\', '/').Contains("/music/");

        public static void Apply(AudioImporter ai, bool music)
        {
            var s = ai.defaultSampleSettings;
            s.loadType = music ? AudioClipLoadType.Streaming : AudioClipLoadType.DecompressOnLoad;
            s.compressionFormat = AudioCompressionFormat.Vorbis;
            s.quality = music ? 0.6f : 0.75f;
            s.preloadAudioData = !music;
            ai.defaultSampleSettings = s;
            ai.forceToMono = false;
            ai.loadInBackground = music;
        }

        public static bool Matches(AudioImporter ai, bool music)
        {
            var s = ai.defaultSampleSettings;
            return s.loadType == (music ? AudioClipLoadType.Streaming : AudioClipLoadType.DecompressOnLoad) &&
                   s.compressionFormat == AudioCompressionFormat.Vorbis;
        }
    }
}
