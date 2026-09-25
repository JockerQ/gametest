using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Text;

namespace EvilCats.EditorTools
{
    /// <summary>
    /// Unpacks a .unitypackage straight into the project folder. Used only in batch mode (CI):
    /// there, AssetDatabase.ImportPackage finishes on a later editor update, which never comes
    /// before the process quits.
    ///
    /// A .unitypackage is a gzipped tar with one folder per asset GUID, holding "asset" (the file,
    /// missing for folders), "asset.meta" (its GUID and import settings) and "pathname" (where it
    /// goes). Writing those files gives the same files and GUIDs as Unity's own import. Only paths
    /// inside Assets/ are written, and existing files are never overwritten.
    /// </summary>
    public static class UnityPackageUnpacker
    {
        /// <returns>The number of asset files written.</returns>
        public static int Unpack(string packagePath, string projectRoot)
        {
            var byGuid = new Dictionary<string, Dictionary<string, byte[]>>();
            using (var file = File.OpenRead(packagePath))
            using (var gz = new GZipStream(file, CompressionMode.Decompress))
            {
                var header = new byte[512];
                string longName = null;
                while (ReadExactly(gz, header, 512))
                {
                    if (IsZero(header)) break;   // end-of-archive marker
                    string shortName = Field(header, 0, 100);
                    string prefix = Field(header, 345, 155);   // ustar: long paths are split
                    string name = longName ?? (prefix.Length > 0 ? prefix + "/" + shortName : shortName);
                    longName = null;
                    byte type = header[156];
                    byte[] data = ReadEntry(gz, Size(header));
                    if (type == (byte)'L') { longName = Encoding.UTF8.GetString(data).TrimEnd('\0'); continue; }   // GNU long name
                    if (type != (byte)'0' && type != 0) continue;   // folders, links, pax headers
                    name = name.Replace('\\', '/');
                    if (name.StartsWith("./", StringComparison.Ordinal)) name = name.Substring(2);
                    int slash = name.IndexOf('/');
                    if (slash <= 0 || slash == name.Length - 1) continue;
                    string guid = name.Substring(0, slash), part = name.Substring(slash + 1);
                    if (!byGuid.TryGetValue(guid, out var parts)) byGuid[guid] = parts = new Dictionary<string, byte[]>();
                    parts[part] = data;
                }
            }

            int written = 0;
            foreach (var parts in byGuid.Values)
            {
                if (!parts.TryGetValue("pathname", out var pn)) continue;
                // "pathname" is the target path, sometimes followed by a second line (e.g. "00")
                string rel = Encoding.UTF8.GetString(pn).Split('\n')[0].Trim().Replace('\\', '/');
                if (!IsSafeAssetPath(rel)) continue;
                string full = Path.Combine(projectRoot, rel);
                if (parts.TryGetValue("asset", out var asset))
                {
                    Directory.CreateDirectory(Path.GetDirectoryName(full));
                    if (!File.Exists(full))
                    {
                        File.WriteAllBytes(full, asset);
                        written++;
                    }
                }
                else Directory.CreateDirectory(full);   // a folder: only its .meta is stored
                if (parts.TryGetValue("asset.meta", out var meta) && !File.Exists(full + ".meta"))
                    File.WriteAllBytes(full + ".meta", meta);
            }
            return written;
        }

        private static bool IsSafeAssetPath(string rel)
        {
            if (!rel.StartsWith("Assets/", StringComparison.Ordinal)) return false;
            foreach (var segment in rel.Split('/'))
                if (segment.Length == 0 || segment == "." || segment == "..") return false;
            return rel.IndexOf(':') < 0;
        }

        private static string Field(byte[] h, int offset, int length)
        {
            int end = offset;
            while (end < offset + length && h[end] != 0) end++;
            return Encoding.UTF8.GetString(h, offset, end - offset);
        }

        private static long Size(byte[] h)
        {
            if ((h[124] & 0x80) != 0)
            {
                // base-256 (very large files)
                long big = h[124] & 0x7F;
                for (int i = 125; i < 136; i++) big = (big << 8) | h[i];
                return big;
            }
            long v = 0;
            for (int i = 124; i < 136; i++)
            {
                byte c = h[i];
                if (c == 0 || c == (byte)' ')
                {
                    if (v > 0) break;
                    continue;
                }
                if (c < (byte)'0' || c > (byte)'7') throw new InvalidDataException("Bad tar size field");
                v = v * 8 + (c - (byte)'0');
            }
            return v;
        }

        private static byte[] ReadEntry(Stream s, long size)
        {
            if (size < 0 || size > int.MaxValue) throw new InvalidDataException("Unsupported tar entry size " + size);
            var data = new byte[size];
            if (!ReadExactly(s, data, (int)size)) throw new EndOfStreamException("Truncated package");
            int pad = (int)((512 - size % 512) % 512);
            if (pad > 0 && !ReadExactly(s, new byte[pad], pad)) throw new EndOfStreamException("Truncated package");
            return data;
        }

        private static bool ReadExactly(Stream s, byte[] buffer, int count)
        {
            int read = 0;
            while (read < count)
            {
                int n = s.Read(buffer, read, count - read);
                if (n <= 0) return false;
                read += n;
            }
            return true;
        }

        private static bool IsZero(byte[] b)
        {
            foreach (var x in b) if (x != 0) return false;
            return true;
        }
    }
}
