using System.Text.Json;
using HD2RuntimeGUI.Core;
using HD2RuntimeGUI.Core.Generation;
using HD2RuntimeGUI.Core.GitHub;
using HD2RuntimeGUI.Core.Metadata;
using HD2RuntimeGUI.Core.Models;
using HD2RuntimeGUI.Core.Storage;

// usage: Harness <project.hd2mod.json> <output folder>
var projectPath = args[0];
var outDir = Path.GetFullPath(args[1]);
Directory.CreateDirectory(outDir);
var paths = new AppPaths(Path.Combine(outDir, "workspace"));
using var http = new HttpClient();
var cache = new SdkCache(paths, new MetadataReader(), new GitHubReleaseClient(http));
var sdk = await cache.GetCurrentAsync();
Console.WriteLine($"ModBuilder {BuildInfo.Identity}; bundled SDK {sdk.Version} API {sdk.ApiVersion}");
ModProject Load() => JsonSerializer.Deserialize<ModProject>(File.ReadAllBytes(projectPath), JsonStorage.Options)!;
var generator = new LuaGenerator(new ChangeService());
var entities = new EntityChangeService();
var summary = new List<object>();

void Export(string name, Action<ModProject> mutate)
{
    var project = Load();
    mutate(project);
    try
    {
        var lua = generator.Generate(project, sdk);
        File.WriteAllText(Path.Combine(outDir, name + ".lua"), lua);
        File.WriteAllText(Path.Combine(outDir, name + ".wrapped.lua"), ModExporter.Wrap(project, lua));
        summary.Add(new { name, ok = true, chars = lua.Length });
        Console.WriteLine($"{name}: exported {lua.Length} chars");
    }
    catch (Exception e)
    {
        File.WriteAllText(Path.Combine(outDir, name + ".error.txt"), e.ToString());
        summary.Add(new { name, ok = false, error = e.Message });
        Console.WriteLine($"{name}: EXPORT ERROR {e.Message}");
    }
}

void KeepWeapons(ModProject p, params string[] names)
{
    p.WeaponChanges.RemoveAll(c => !names.Contains(c.Weapon));
    p.CompositionChanges.RemoveAll(c => !names.Contains(c.Weapon));
    p.SupportChanges.RemoveAll(c => !names.Contains(c.Weapon));
    p.StratagemChanges.Clear();
    p.EntityChanges.Clear();
    p.ProjectileChanges.Clear();
}

void AddBackpack(ModProject p)
{
    // The report's variant: Maxigun backpack ammunition edited in ModBuilder (not in the supplied project).
    const string key = "backpack:m-1000-maxigun-backpack:m-1000-maxigun-backpack-backpack:deposit.";
    p.EntityChanges.Add(entities.Create(sdk, key + "capacity", "1500"));
    p.EntityChanges.Add(entities.Create(sdk, key + "refill_amount", "750"));
}

Export("A-original", _ => { });
Export("B-no-stratagem", p => p.StratagemChanges.Clear());
Export("B2-no-support", p => p.SupportChanges.Clear());
Export("B3-no-stratagem-no-support", p => { p.StratagemChanges.Clear(); p.SupportChanges.Clear(); });
Export("B4-no-entity", p => p.EntityChanges.Clear());
Export("C-original-plus-maxigun-backpack", AddBackpack);
Export("D-ma5c-only", p => KeepWeapons(p, "MA5C Assault Rifle"));
Export("D2-ma5c-capacity-only", p => { KeepWeapons(p, "MA5C Assault Rifle"); p.WeaponChanges.RemoveAll(c => c.SemanticFieldId != "magazine.capacity"); p.CompositionChanges.Clear(); });
Export("D3-ma5c-plus-stratagem", p => { var s = p.StratagemChanges.ToList(); KeepWeapons(p, "MA5C Assault Rifle"); p.StratagemChanges.AddRange(s); });
Export("D4-ma5c-plus-support", p => { var s = p.SupportChanges.ToList(); KeepWeapons(p, "MA5C Assault Rifle"); p.SupportChanges.AddRange(s); });
Export("E-maxigun-only", p => KeepWeapons(p, "M-1000 Maxigun"));
Export("E2-maxigun-plus-backpack", p => { KeepWeapons(p, "M-1000 Maxigun"); AddBackpack(p); });
Export("E3-backpack-only", p => { KeepWeapons(p); AddBackpack(p); });
Export("G-orbital-precision-strike-only", p => { var s = p.StratagemChanges.ToList(); KeepWeapons(p); p.StratagemChanges.AddRange(s); });
foreach (var weapon in new[] { "SG-20 Halt", "SG-225SP Breaker Spray&Pray", "LAS-12 Sai", "R/40-K Hot-Shot Marksman Rifle", "SMG-32 Reprimand", "LAS-16 Sickle", "M-1000 Maxigun", "MA5C Assault Rifle" })
    Export("F-" + System.Text.RegularExpressions.Regex.Replace(weapon, "[^A-Za-z0-9]+", "-").Trim('-'), p => KeepWeapons(p, weapon));
File.WriteAllText(Path.Combine(outDir, "summary.json"), JsonSerializer.Serialize(summary, new JsonSerializerOptions { WriteIndented = true }));
return 0;
