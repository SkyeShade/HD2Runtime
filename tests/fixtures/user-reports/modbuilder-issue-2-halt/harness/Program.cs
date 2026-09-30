using System.Text.Json;
using HD2RuntimeGUI.Core;
using HD2RuntimeGUI.Core.Generation;
using HD2RuntimeGUI.Core.GitHub;
using HD2RuntimeGUI.Core.Metadata;
using HD2RuntimeGUI.Core.Models;
using HD2RuntimeGUI.Core.Storage;

var outDir = Path.GetFullPath(args[0]);
Directory.CreateDirectory(outDir);
var paths = new AppPaths(Path.Combine(outDir, "workspace"));
using var http = new HttpClient();
var cache = new SdkCache(paths, new MetadataReader(), new GitHubReleaseClient(http));
var sdk = await cache.GetCurrentAsync();
Console.WriteLine($"ModBuilder {BuildInfo.Identity}; bundled SDK {sdk.Version} API {sdk.ApiVersion}");
var weapons = new WeaponChangeService();
var generator = new LuaGenerator(new ChangeService());
var catalog = WeaponChangeService.Catalog(sdk);
var log = new List<string>();

string Perturb(WeaponCapability f)
{
    var v = f.CurrentDefault;
    if (f.Type == "boolean") return v.ValueKind == JsonValueKind.True ? "false" : "true";
    if (v.ValueKind != JsonValueKind.Number) return "";
    var d = v.GetDouble();
    if (f.Type == "integer") { var n = (long)d + 1; if (f.Max is double mx && n > mx) n = (long)d - 1; return n.ToString(); }
    var x = d == 0 ? 0.5 : d * 1.1;
    if (f.Max is double max && x > max) x = d * 0.9;
    if (f.Min is double min && x < min) x = min;
    return x.ToString("R", System.Globalization.CultureInfo.InvariantCulture);
}
List<WeaponChange> Changes(string weapon, Func<WeaponCapability, bool> keep)
{
    var list = new List<WeaponChange>();
    foreach (var f in catalog.Weapon(weapon).Fields.Where(f => f.Editable && !f.DerivedReadOnly && f.AliasOf == null && keep(f)))
    {
        var value = Perturb(f);
        if (value == "") continue;
        try
        {
            var c = weapons.Create(sdk, weapon, f.SemanticFieldId, value, true);
            if (f.Acknowledgement == "allow_unverified_effect") c.EffectAcknowledgement = WeaponChangeService.EffectEvidence(weapon, f);
            list.Add(c);
        }
        catch (Exception e) { log.Add($"{weapon} {f.SemanticFieldId}: create refused: {e.Message}"); }
    }
    return list;
}
bool IsDamage(WeaponCapability f) => f.SemanticFieldId.StartsWith("damage.");
ModProject Project(string name, IEnumerable<WeaponChange> changes)
{
    var resource = "mods/harness/" + System.Text.RegularExpressions.Regex.Replace(name.ToLowerInvariant(), "[^a-z0-9]+", "_");
    var p = new ModProject { DisplayName = name, Author = "harness", ResourceId = resource, ManagerGuid = HD2RuntimeGUI.Core.Projects.ProjectIdentity.ManagerGuid(resource), SdkVersion = sdk.Version, ExportDirectory = Path.Combine(outDir, "export") };
    p.WeaponChanges.AddRange(changes);
    return p;
}
// Unrelated edits on other weapons, before and after the Halt edits in project order.
List<WeaponChange> Others(string weapon, params string[] fields) => Changes(weapon, f => fields.Contains(f.SemanticFieldId));
var before = Others("AR-23 Liberator", "weapon.sway", "weapon.ergonomics", "magazine.capacity", "damage.player_standard_damage");
var after = Others("SMG-32 Reprimand", "weapon.sway", "weapon.fire_rate", "damage.player_standard_damage");
var haltAll = Changes("SG-20 Halt", _ => true);
var haltDamage = Changes("SG-20 Halt", IsDamage);
var haltSway = Changes("SG-20 Halt", f => f.SemanticFieldId == "weapon.sway");
var variants = new Dictionary<string, List<WeaponChange>>
{
    ["H0-control-no-halt"] = [.. before, .. after],
    ["H1-halt-all"] = [.. before, .. haltAll, .. after],
    ["H2-halt-damage-only"] = [.. before, .. haltDamage, .. after],
    ["H3-halt-sway-only"] = [.. before, .. haltSway, .. after],
};
var summary = new List<object>();
foreach (var (name, changes) in variants)
{
    var project = Project(name, changes);
    try
    {
        var lua = generator.Generate(project, sdk);
        File.WriteAllText(Path.Combine(outDir, name + ".lua"), lua);
        File.WriteAllText(Path.Combine(outDir, name + ".wrapped.lua"), ModExporter.Wrap(project, lua));
        summary.Add(new { name, ok = true, changes = changes.Count, fields = changes.Select(c => c.Weapon + " " + c.SemanticFieldId).ToList() });
    }
    catch (Exception e) { summary.Add(new { name, ok = false, error = e.Message }); }
}
File.WriteAllText(Path.Combine(outDir, "summary.json"), JsonSerializer.Serialize(new { sdk = sdk.Version, identity = BuildInfo.Identity, summary, log }, new JsonSerializerOptions { WriteIndented = true }));
Console.WriteLine(string.Join("\n", log));
return 0;
