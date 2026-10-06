"""Can the Runtime show its own custom-stratagem selector while the player prepares the loadout, and turn a pick into
a normal vanilla token in one of the four slots, with no native game-function call, hook or patch
(docs/custom-stratagems.md, "A Runtime-owned custom stratagem selector: research")? Read-only, offline: the game.dll
and helldivers2.exe images and the seven retained snapshots of build F5FEE03DCFDB. Nothing is written. The third-party
Mod Options Menu and Stratagem MultiSelect mods are leads only: every claim here is proven in game code.

Proves:

1. Drawing. The engine registers its Stingray Lua scripting API when the Lua state starts (exe 0x2D3590): World
   (create_screen_gui, destroy_gui), Gui (rect, bitmap, text with update_/destroy_ variants, set_visible) and
   Application.main_world, the world the game rendered last (0x317DE0 picks the largest render timestamp
   world+0x230960). A normal GUI resolves a bitmap material by resource name through the same lookup the game's GUIs
   use (0x264620, the material type, "Material not found."), which Runtime's custom icon materials were already proven
   against. The engine's own font core/performance_hud/monaco (font and material) is resident in every snapshot. The
   bindings check no arguments (a wrong value crashes rather than raising a Lua error), so the Runtime must validate
   everything it passes. XAML (Noesis) is reachable from C++ only.
2. Input. The game evaluates its input actions every frame into [game+0x347CF18] + 0x328 + (group * 97 + action) * 32,
   byte 0 = triggered, on any device or binding (0x12F65E0). Menu group 0: Up 1, Down 2, Right 3, Left 4, Back 9,
   Select 10 (the action table, 0xAE6360). Reading them is a data read; the native screen reacts to them too.
3. The loadout screen (ui = [[game+0x347CE38]+0xB0], 0 when closed): the local record is ui+0x10+[ui+0x27D0]*0x9F0
   (+0x188 entries of 0x30, +0x788 count, +0x9E8 owner); ui+0x2818 = 10 while the stratagem grid is open for slot
   ui+0x281C (set when the grid opens, 0x146EB9C); ui+0x27FC = ready; ui+0x2808 = launched.
4. A pick (0x146E0A0): the slot widget takes the type (0x189D050 -> 0x1893600, widget +0x128C; a per-slot message to
   peers), the record is rebuilt from the four widgets (0x18966A0: cleared, then one entry per filled widget), the grid
   closes, the save store is written (0x1751350, also from sync_loadout 0x1467808 at launch and on_exit 0x1467CD9);
   no ownership check on any of them.
5. The record drives the slots: every frame the panel bind (0x146CB58 -> 0x189CA20 -> 0x189C900) passes the record to
   0x1895A20, which returns early while its cached record pointer (+0xD960) and local flag (+0xD978) are unchanged,
   and otherwise repaints the four slot widgets from the record's entries (0x18962CE..0x1896347), for the local panel
   too (0x18962C3).

6. Render order (docs/custom-stratagems.md, "Render order"). A screen GUI's primitives are drawn in its world's
   transparent passes; Gui.rect keeps the Vector3 z as an int32 layer that orders primitives inside the GUI (0x3E1CBD).
   create_screen_gui takes only scale, immediate, dock_right, dock_top, material and shadow_caster options: none picks
   a render stage. The game renders its UI world through the render config viewport hud_world_ui_and_composite_layer
   (game.dll 0xAB1BF0), whose layer config draws the transparent passes, then the Noesis UI (generator "noesis") into the
   same ui_target, then composites ui_target over the game image into the back buffer (copy_and_blend_ui). Each frame the
   engine calls the Lua update callback, then the Lua render callback and right after it the game plugin's render
   callback (0x689BC0 -> plugin +0x90 = game.dll 0x4EE7E0 -> 0xAB7680), which renders the game world, the UI world and
   an offscreen ui_3d world. Render commands are queued in order (0x10788C). The render config's 'overlay' viewport draws
   its transparent pass straight into the back buffer, but no game code creates it; a world a script renders from the
   Lua callbacks is queued before the game's UI world, whose composite then rewrites the whole back buffer. The engine's
   own debug world, rendered after the game behind a setting (0x8A1EC), is not in Application.worlds.

7. The native card's look (the Runtime custom stratagems panel). The stratagem card style only sizes the card's
   elements (card 80, inner frame 68, icon 51 units); the one image it binds (0x1450160) is element +0x1800's: the focus
   bracket, 92 units, an atlas sprite (0x270930A62555EBEF; the other card styles' brackets 0xF78DB8F1CC821769,
   0x7D698BF20161DE2B) on a 1024 x 512 single-channel (BC4) UI atlas page, after a material set on the element
   (0xF6978E86E4F4B0D5). No texture or GUI material carries the card's background, border or inner frame. Gui.bitmap
   takes a material by name or IdString64, and Gui.bitmap_uv exists, but no GUI material that samples that atlas page
   can be named, so the Runtime tile is drawn with rectangles in the native proportions.

8. The selection lifecycle. ui+0x273990 is the selection-open byte: set to 1 only when a selection opens (0x146EA57,
   the open handler 0x146E9D0, reached from one input handler), 0 only when it closes (0x146F3DA, the close handler
   0x146F3B0, also called after a pick that leaves no empty slot, 0x146E672) and at screen init (0x1466FA6). The
   sub-state ui+0x2818 is NOT the open grid: every frame the screen update recomputes it from the panel's FOCUSED slot
   (panel +0xD96C, set by 0x189578D): 10 for a focused stratagem slot 0-3, 5 for slot 4, 0 for none (0x1468748,
   0x14686BB), whether or not a selection is open; the edited slot ui+0x281C is -1 until the first selection (0x1465931).
   After a pick with an empty slot left, the selection stays open on the next empty slot (0x146E6D4). The custom panel
   is shown only while the selection byte is set, the sub-state is 10 and the edited slot is 0-3.

9. The native details panel. The selection's per-frame update fills the details panel at ui+0x24B520 (0x1468773 ->
   0x189FA80), a GUI element like the list frame: for a stratagem it sets its size to 1024 x 400 units (0x189FC39,
   0x189FC44 read 1024.0 and 400.0; mode 0xB at +0x157E0) and the close handler fades it (0x146F3E1). Its laid-out size
   (+0x24) and world transform give its screen rectangle as for the cards; the custom panel sits to its right.
10. The Gui.bitmap contract. Gui.bitmap and Gui.bitmap_uv (0x3E323A) read their first argument through one parser
   (0x3E0FA0): in a legacy-mode GUI (+0x89 set) a 32-bit id into the GUI's own material set (0x3E10D3, 0x3E10DB);
   otherwise a MATERIAL resource by 64-bit name, from a string (MurmurHash64) or an IdString64 (tag 0x6F6F4D64, built by
   IdString64.from_hex with "%llx", 0x3D3437), resolved by 0x264620 (0x3E117D): refused for legacy GUIs (0x264651),
   "Material not found." when no material of that name is resident, "Material sets are not supported for GUIs."
   (0x26474C) when the resource's +4 field is 0; otherwise a per-GUI instance of that material is drawn. A texture or an
   atlas sprite is never accepted: the Runtime image's own GUI icon material (same name as its texture, +4 = 1) is the
   resource Gui.bitmap needs.

11. The mouse. The engine registers a Win32 mouse device ("WindowsMouse", buttons left/right/middle, 0x5A8108,
   0x5A826F) whose cursor axis is the device's stored integer x and y converted to floats (0x5A8E81, 0x5A8E8C, axis +0x18,
   0x5A8EA0); the y it stores is the y it is given (0x5A94F6). Its callers are indirect and the executable's imports are
   hidden, so whether that y is flipped to the GUI's bottom-left origin is not established offline; stingray.Mouse.axis /
   button are logged beside the Runtime's own reading. The custom panel reads the OS cursor through the Runtime input
   module (GetCursorPos, ScreenToClient, GetClientRect, GetAsyncKeyState: client pixels, top-left origin) and converts
   to the GUI's pixels and bottom-left origin itself.
12. The icon material's shader. The template 0x3461FF0D is in shader library 0x8CDE642487327D4E: its compiled code is in
   the library's GPU part (an earlier search read only the 4-byte main parts). Its pixel shader samples diffuse_map
   (the material's one slot, 0x3AA8B87E = IdString32("diffuse_map")) and treats the texture's R, G, B and A as masks:
   each is multiplied by the strength c0.x, c1.x, c2.x, c3.x and coloured c0.yzw .. c3.yzw (a cbuffer of the material
   instance), the layers stacked R over G over B over A, times the vertex colour. The icon material declares no
   variables, so with c0-c3 at zero every texel is transparent: Gui.bitmap draws the quad, but nothing is visible. The
   native loadout slot sets them on its element's own material copy (0x1893669..0x18936BF): c0 = the category colour of
   the type's colour set (StratagemInfo +0xB8, the table at game+0x331B610), c1 = (1, 1, 1, 0.933), c2 = (0.2, 0, 0, 0);
   c3 is never set. The exposed Lua API reaches the same setter: Gui.material(gui, name) returns the GUI's own instance
   (the same per-GUI lookup as Gui.bitmap) and Material.set_vector4(instance, 'c0', Quaternion.from_elements(..)) sets a
   variable through the function the game uses (exe 0x49E09F -> 0x4F3730). Gui.bitmap returns an id even when the
   material was not found (a null material, handle 0xFFFFFF): the Runtime's own residency check is the guard.
13. Moving the selection on. After a pick, the native pick handler searches the four slot WIDGETS from slot 0 (one whose
   flags +0x1288 have bit 2 is skipped; empty = type 0 or above 149) and, when one is empty, moves the panel focus
   through the native setter 0x1895770 (its highlight is applied inside it) and writes the edited slot ui+0x281C
   (0x146E6D4); otherwise it calls the close handler. Nothing reads ui+0x281C each frame: only a pick and the open
   handler. One u32 write of ui+0x281C therefore moves the open selection on (the next pick, native or Runtime, lands
   there) while the highlight and the grid's greying stay as they were. The close handler hides the grid, the details
   panel and the slot highlight through element calls only, and the input action states are cleared and recomputed
   from the devices every frame before the screen reads them (0x12FA0A6): the selection cannot be closed by data. The
   Runtime's cleared cached record pointer makes the repaint take its first-bind branch, which moves the local panel's
   focus to slot 0 (0x18963EF). A pick in panel mode 1 (ui+0x6F290) always closes.
14. Slot-local icons. Each slot widget's icon element (widget + 0x380, an image element) gets the type's icon every
   time the widget takes a type (0x1893650 -> 0x1450160, no early return), so every repaint resets all four. The image
   setter copies the atlas sprite's rectangle into the element (+0x134), stores the name (+0x150), binds the sprite's
   page texture into the element's own material through an engine call (a render command), and computes the UV
   (+0x124) from the rectangle; the scene update then pushes the material and UV of an element marked dirty (bit 1,
   ancestors bit 3 through +0xF0) to its GUI primitive. A different icon on the SAME atlas page can therefore be shown
   in one slot by data: its rectangle and UV, and the dirty bits the setter itself sets. A custom image (a texture of
   its own) needs the texture bind, an engine call: not by data.
15. The native slot highlight. The local panel P = ui+0x595F0 holds the focused slot (P+0xD96C) and the previous one
   (P+0xD970); each slot widget's flags (+0x1288) carry bit 1 = focused (bit 2 disabled, bit 3 selection open). The
   focus setter 0x1895770 stores both, moves bit 1 and calls the widget visual update 0x18932F0 on both widgets, a pure
   function of the flags (frame colour, opacity, thickness and gap, the frame bars); nothing redraws them per frame.
   The repaint's first-bind branch (after the Runtime's cleared cached record pointer) forces slot 0. But the panel
   update reaches, every frame in panel mode 0 (0x189B9CB -> 0x18999F0 -> 0x1899CD0), the end of a frame flash:
   for each slot widget whose byte +0x12A0 is set and whose frame has no colour tween running, it clears the byte and
   calls 0x18932F0 itself (0x1894C30..0x1894C57). The focus can therefore be moved by data: the focus and previous
   focus, bit 1 on both widgets, then that byte on both: the game's own code redraws both widgets from their flags.
   ui+0x2739C8 is the active panel group (0: the local one). While the selection is open the panel's own navigation is
   skipped (0x189BDEC), so a direction input would not move the focus there.
16. A custom texture in a native slot. The texture a slot icon shows is NOT in any main-thread field: binding it
   (material API +0x78 -> exe 0x4F3230) stores {property, resource} in the material's CPU list and queues render command
   7, which the render thread applies to the material's render-side object R by storing u32 [resource+0] into R+0x48[k]
   (0x4F4713, no dirty flag); every GUI draw reads that handle (0x4FD555/0x4FD559). R is found from the element's own
   material clone M (+0x148): its render handle (M+4) indexes the render world's tables (RW+0x1C0 -> RW+0x170, mask
   [WRI+0x40]; 0x1E87A9..0x1E87BD), RW reached through M+8 = WRI+0x10, [WRI+0x10] = RI, [RI+0x80] = RW+0x10. A data-only
   custom slot icon would therefore be a write into render-thread memory read concurrently: researched read-only.
17. Closing the selection (the full-loadout case) is not possible by data: the close handler's panel slide-back
   0x189E2F0(P, 0) starts pool tweens, the list clear releases handles and the grid fade is a tween, none with a per-frame
   consumer; the only per-frame paths that close it are launch and deploy (forbidden). The close handler itself,
   0x146F3B0(ui), is the game's one close: Back on a focused stratagem slot (sub-state 10: 0x146E963) posts the
   picker-close sound and calls it with the loadout UI (rcx = rdi, the handler's first argument, 0x146E0B6), and so does
   a pick that leaves no empty slot (0x146E665..0x146E672). Its one argument is the UI (kept in rsi); it returns nothing.
   It sets ui+0x273991 from ui+0x273992, clears the selection-open byte ui+0x273990 and the sub-state ui+0x2818, hides
   the grid (0x18DBFF0(ui+0xD2850, 1)), clears the card list (0x18D27B0(ui+0xD2F20): its row count +0x91F14 and card
   count +0x92984 become 0), clears widget flag bit 3 on the four slot widgets and redraws them (0x18932F0), and slides
   each panel back (0x189E2F0, 0x189CEB0, 0x1898AB0). The Runtime calls it (a typed native UI call; no patch, no hook)
   only to close the selection its own selection filled, exactly as Back does: the picker-close sound, then the call.
18. UI sounds. The loadout screen posts its sounds through 0x1327F50(key): the key is remapped through the hash_lookup
   resource to a Wwise event id and posted on the WwiseWorld of the "Game World" ([[game+0x3326340]+0x10F8]; the world
   itself at +0x10E8, the first of Application.worlds in every snapshot), with its default source. A pick that fills the
   last slot posts 0x97753411 (event 0x0DBB2A14) before closing; Back on a stratagem slot posts the same; selecting a
   loadout slot (the grid opening) posts 0xA31D0645 (event 0x3C38FC71); a pick with an empty slot left posts none of
   its own. The Wwise plugin registers stingray.Wwise.wwise_world, stingray.Wwise.has_event and
   stingray.WwiseWorld.trigger_event(wwise_world, name), which posts the FNV-1 (lower-case) hash of the name exactly as
   the game posts its ids; a name whose hash equals a native event id posts that very event. Every pick posts one
   more sound before any of these: the card list accepting a card posts 0xBE9303B7 (event 0x6A84A787; 0x18CFDD3), then
   reports the pick (4) that the pick handler acts on. The keys are remapped through the hash table the remap reads
   (game+0x346C9F8 slots, +0x346CA00 capacity, +0x346CA04 the empty key, +0x346CA08 the multiplier), read in every
   snapshot (snapshots uiSoundRemap).
19. Slot icon overlays (correcting 1 and 6). Application.main_world picks the largest render stamp, but every world
   rendered in a frame carries the same stamp (frame time), so the tie goes to the world with the most units
   (0x317E65): the Game World, worlds()[1]. A Runtime screen GUI there is drawn in the game world's passes, under the
   whole UI composite. The four ship loadout slots (scene 3, icon layer 14), the picker grid, the details panel and the
   mission HUD's stratagem list (scene 5, icon layer 557) are the game's own element primitives in screen GUIs of the
   Ui World ([[game+0x3326340]+0x1118], worlds()[2]), not Noesis. Inside one world every GUI's primitives are sorted
   together by a depth computed from their layer (0x2693E3: 0.1 * (1023 - layer) / 1023; screen GUIs above world GUIs),
   not per GUI. A Runtime screen GUI created in the Ui World at a layer above the native slot parts (17..1023, avoiding
   the HUD's 950-953 and the native 991-1018) therefore draws over the slot icons, under Noesis. Application.worlds
   lists the engine's world array in order (0x3F821F..0x3F8277), so the Ui World's Lua value is found by its index in
   that array. The slot icon's on-screen quad is its element's size and transform (ship: the slot widget + 0x380;
   mission: [game+0x346D538] + 0x395100 + 0x1150 + k * 0x3760 + 0x7C0 + 0x518, entry k showing record entry
   [entry + 0x3748]), shown while its primitive (+0x110) exists, with alpha +0x54.
20. The native slot's icon background (the overlay's backing plate). The slot widget build (0x1892DB0) lays out, in
   its 80-unit widget, under the icon (+0x380, layer 14): +0x110, an element of kind 5 (0x1892EBA), placed at 5, 5
   (0x1892F01), 70 units square (the icon's own area), grey 36/255 (0x1892F2F) at layer 12; and +0x228, an image
   element at layer 13 whose sprite (0x6E6A67B944661E66, set by the local panel repaint 0x1895E12 through 0x1893870)
   is tinted from the colour-set tables 0x331A9B0 (c0) and 0x331B4E0 (c1). Kind 5 is pushed by 0x1444030 (the kind
   dispatch 0x144DF3B: flags >> 18) as a filled rectangle with a transform and a colour and no material (GUI interface
   +0x108). An element's effective colour is (a, r, g, b) at +0x54 (0x144BEA7). A plate in that grey, opaque, under
   the overlay hides the native icon; the tint sprite is on a UI atlas page no GUI material can name (finding 7), so
   the plate reproduces the grey box, not the tint.

Output: research/runtime-stratagem-ui-F5FEE03DCFDB.json.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import hd2_game_data  # noqa: E402
import hd2_archive  # noqa: E402
import research_event_state as base  # noqa: E402
import research_image_resources as resources  # noqa: E402
import snapshot_image  # noqa: E402
from research_stratagem_calldown import SNAPSHOTS  # noqa: E402

OUTPUT = ROOT / 'research/runtime-stratagem-ui-F5FEE03DCFDB.json'
FONT_TYPE, MATERIAL_TYPE = hd2_archive.resource_hash('font'), hd2_archive.resource_hash('material')
FONT = 'core/performance_hud/monaco'
G_LOADOUT_UI_OWNER, G_INPUT_OWNER = 0x347CE38, 0x347CF18
TABLE, PRECISION = 0x37CB600, 118

EXE = {
    'luaApi': [
        (0x2D3AB6, 'call 0x3e8710', None, 'Lua state start: the Gui module is registered'),
        (0x3E8839, 'lea rdx, [rip + {rip}]', 0x167995C, 'Gui.bitmap'),
        (0x3E888E, 'lea rdx, [rip + {rip}]', 0x1680260, 'Gui.update_bitmap'),
        (0x3E88E3, 'lea rdx, [rip + {rip}]', 0x1680250, 'Gui.destroy_bitmap'),
        (0x3E8D89, 'lea rdx, [rip + {rip}]', 0x1680400, 'Gui.text'),
        (0x3E8DDE, 'lea rdx, [rip + {rip}]', 0x1680330, 'Gui.update_text'),
        (0x3E8E33, 'lea rdx, [rip + {rip}]', 0x1680320, 'Gui.destroy_text'),
        (0x3E9031, 'lea rdx, [rip + {rip}]', 0x1680358, 'Gui.set_visible'),
        (0x3E1982, 'lea rdx, [rip + {rip}]', 0x166BB9C, 'Gui.rect'),
        (0x3F5390, 'lea rdx, [rip + {rip}]', 0x1680918, 'World.create_screen_gui'),
        (0x3F543A, 'lea rdx, [rip + {rip}]', 0x1680B18, 'World.destroy_gui'),
    ],
    'mainWorld': [
        (0x3F8326, 'call 0x317de0', None, 'Application.main_world: the world ...'),
        (0x317E44, 'movsd xmm1, qword ptr [rax + 0x230960]', None, '... with the latest render timestamp'),
    ],
    'engineTypes': [
        (0x430F3E, 'lea rdx, [rip + {rip}]', 0x167FA54, 'stingray.Vector2 is a table whose __call ...'),
        (0x430F4E, 'lea rdx, [rip + {rip}]', 0x431110, '... is its constructor (callable, not of type function)'),
        (0x43517E, 'lea rdx, [rip + {rip}]', 0x167FA54, 'stingray.Vector3 is a table whose __call ...'),
        (0x43518E, 'lea rdx, [rip + {rip}]', 0x435370, '... is its constructor (callable, not of type function)'),
        (0x3E72CA, 'lea rdx, [rip + {rip}]', 0x168045C, 'stingray.Color: a plain C function ...'),
        (0x3E72D1, 'call 0x1c43b0', None, '... bound directly into stingray'),
        (0x3E7091, 'lea rdx, [rip + {rip}]', 0x16804F0, 'Gui.resolution'),
    ],
    'engineReturns': [
        (0x3F09D3, 'mov eax, 1', None, 'World.create_screen_gui returns one value (the GUI)'),
        (0x3E1D4E, 'call qword ptr [rip + {rip}]', 0x13F7880, 'Gui.rect pushes its id (lua_pushinteger) ...'),
        (0x3E1D5C, 'mov eax, 1', None, '... and returns one value'),
        (0x3E2BA7, 'mov eax, 1', None, 'Gui.bitmap returns one value (its id)'),
        (0x3E5491, 'mov eax, 1', None, 'Gui.text returns one value (its id)'),
        (0x3E1F90, 'xor eax, eax', None, 'Gui.update_rect returns NOTHING'),
        (0x3E2DF7, 'xor eax, eax', None, 'Gui.update_bitmap returns nothing'),
        (0x3F105D, 'xor eax, eax', None, 'World.destroy_gui returns nothing'),
    ],
    'guiMaterial': [
        (0x3E0FCC, 'cmp byte ptr [rsi + 0x89], 0', None, 'a bitmap material by name: legacy GUI or normal GUI'),
        (0x264638, 'cmp byte ptr [rcx + 0x89], 0', None, 'normal GUI: the material by resource name ...'),
        (0x2646C5, 'movabs rax, 0xeac0b497876adedf', None, '... of the material type (the custom icon\'s path)'),
        (0x2646E8, 'lea rax, [rip + {rip}]', 0x1675000, 'absent: "Material not found." (null material)'),
    ],
    'mouse': [
        (0x5A8108, 'lea rax, [rip + {rip}]', 0x168A628, 'the engine\'s Win32 mouse device ("WindowsMouse")'),
        (0x5A826F, 'lea rcx, [rip + {rip}]', 0x1670430, 'its "left" button'),
        (0x5A8E81, 'cvtsi2ss xmm0, rax', None, 'its cursor axis: the stored integer x ...'),
        (0x5A8E8C, 'cvtsi2ss xmm1, rax', None, '... and y, as floats ...'),
        (0x5A8EA0, 'movsd qword ptr [rcx + 0x18], xmm0', None, '... into the cursor axis'),
        (0x5A94F6, 'mov dword ptr [rsi + 0x204], ebp', None, 'the y stored is the y given (its callers are indirect)'),
    ],
    'bitmapContract': [
        (0x3E10D3, 'mov rcx, qword ptr [rsi + 0x78]', None, 'legacy-mode GUI: a 32-bit id in the GUI\'s material set ...'),
        (0x3E10DB, 'call 0xce480', None, '(looked up there)'),
        (0x3E1123, 'cmp dword ptr [rax], 0x6f6f4d64', None, 'otherwise a string or an IdString64 (64-bit name) ...'),
        (0x3E117D, 'call 0x264620', None, '... resolved as a MATERIAL resource'),
        (0x264651, 'lea rax, [rip + {rip}]', 0x1674ED0, 'refused for legacy-mode GUIs'),
        (0x26474C, 'lea rax, [rip + {rip}]', 0x1675018, 'refused when the resource\'s +4 is 0 (a material set)'),
        (0x3E323A, 'call 0x3e0fa0', None, 'Gui.bitmap_uv reads its material the same way'),
        (0x3D3437, 'lea rdx, [rip + {rip}]', 0x166BB80, 'IdString64.from_hex parses "%llx"'),
    ],
    'slotIconAtlas': [
        (0x343966, 'mov rax, qword ptr [rcx + 8]', None, 'an atlas sprite record: its page (+8) ...'),
        (0x34396D, 'mov eax, dword ptr [rcx + 0x18]', None, '... and its rectangle (+0x18: offset u, v, scale u, v) ...'),
        (0x34397F, 'mov dword ptr [r9], eax', None, '... copied into the image element (+0x134)'),
        (0x3439B0, 'mov dword ptr [r9 + 8], 0x3f800000', None, 'no sprite: the full rectangle'),
    ],
    'iconMaterialApi': [
        (0x3E71E5, 'lea rdx, [rip + {rip}]', 0x1666660, 'Gui.material ...'),
        (0x3E7ED9, 'call 0x264620', None, '... resolves through the same per-GUI material lookup as Gui.bitmap'),
        (0x49D591, 'lea rdx, [rip + {rip}]', 0x1683C58, 'Material.set_vector4 ...'),
        (0x49E09F, 'call 0x4f3730', None, '... sets a float4 variable through the engine setter ...'),
        (0x30EFB0, 'jmp 0x4f3730', None, '... the one the game\'s UI calls (material API +0x18)'),
        (0x442872, 'lea rdx, [rip + {rip}]', 0x1683410, 'Quaternion.from_elements (a 4-float box)'),
        (0x3E1182, 'mov rax, qword ptr [rsp + 0x20]', None, 'Gui.bitmap keeps going with a material not found ...'),
        (0x267A74, 'mov eax, 0xffffff', None, '... (a null material handle): an id does not prove the material'),
    ],
    'slotTexture': [
        (0x4F32AE, 'mov qword ptr [r10 + rdx*8 + 8], r14', None, 'a texture bind stores {property, resource} in the CPU list'),
        (0x4F3358, 'mov dword ptr [rcx], 7', None, '... and queues render command 7 ...'),
        (0x4F336C, 'mov esi, dword ptr [r14]', None, '... carrying the texture render handle u32 [resource+0]'),
        (0x1D9ADC, 'mov dword ptr [r14 + 4], eax', None, 'a material instance: its render handle (+4) ...'),
        (0x1D9AE0, 'mov qword ptr [r14 + 8], r13', None, '... its world interface (+8 = WRI + 0x10) ...'),
        (0x1D9B29, 'lea rax, [rip + {rip}]', 0x1688200, '... its render-side object (this vtable) ...'),
        (0x1D9B8C, 'mov dword ptr [rsi + 8], 7', None, '... of kind 7 ...'),
        (0x1D9C59, 'mov dword ptr [r8 + rax], ecx', None, '... holding the texture handles (+0x48)'),
        (0x1E87A9, 'mov ecx, dword ptr [rax + 0x40]', None, 'the render world: the handle mask [WRI+0x40] ...'),
        (0x1E87B2, 'mov rax, qword ptr [rsi + 0x1c0]', None, '... the index array (RW+0x1C0) ...'),
        (0x1E87BD, 'mov rcx, qword ptr [rsi + 0x170]', None, '... the object array (RW+0x170)'),
        (0x4F4713, 'mov dword ptr [rax + rdi*4], ebp', None, 'command 7 on the render thread: the handle stored, nothing else'),
        (0x4FD555, 'mov rax, qword ptr [r9 + 0x48]', None, 'every GUI draw reads the handles ...'),
        (0x4FD559, 'mov edi, dword ptr [rax + rcx*4]', None, '... at draw time'),
        (0x10CF20, 'mov qword ptr [rbx + 0x10], rax', None, 'WRI+0x10: the render interface'),
        (0x10CF56, 'mov qword ptr [rcx + 0x150], rdx', None, 'RW+0x150: its WRI'),
        (0x1E61A1, 'mov qword ptr [rsi + 0x80], rbx', None, 'RI+0x80: RW + 0x10'),
        (0x1E409F, 'lea rax, [rip + {rip}]', 0x1672E70, 'the render world\'s vtable'),
        (0x267A6F, 'mov eax, dword ptr [rax + 4]', None, 'a GUI primitive takes only the material\'s render handle'),
    ],
    'worldOrder': [
        (0x3F821F, 'mov rax, qword ptr [rip + {rip}]', 0x1A10208, 'Application.worlds: the application ...'),
        (0x3F823D, 'mov ebp, dword ptr [rax + 0x590]', None, '... its world count ...'),
        (0x3F826C, 'mov rdx, qword ptr [rax + 0x598]', None, '... its world array, in order ...'),
        (0x3F8277, 'call 0x404f80', None, '... each world wrapped (full userdata) into the list'),
        (0x317E65, 'mov r8d, dword ptr [rax + 0x2305b8]', None, 'main_world ties broken by unit count (the Game World)'),
        (0x2693E3, 'movss dword ptr [r14 + 0x70], xmm0', None, 'a GUI batch depth from its layer ...'),
        (0x4BF4D3, 'cvttss2si rcx, xmm0', None, '... into the sort key ...'),
        (0x4BF4E2, 'shl rax, 4', None, '... with no GUI identity in the key'),
    ],
    'renderOrder': [
        (0x3E1CBD, 'cvttss2si rax, xmm8', None, 'Gui.rect: the Vector3 z becomes an int32 layer (inside the GUI)'),
        (0x3F04E2, 'lea rdx, [rip + {rip}]', 0x167877C, 'create_screen_gui options: scale ...'),
        (0x3F0545, 'lea rdx, [rip + {rip}]', 0x1680870, '... immediate ...'),
        (0x3F056D, 'lea rdx, [rip + {rip}]', 0x1680860, '... dock_right ...'),
        (0x3F05A2, 'lea rdx, [rip + {rip}]', 0x16808F0, '... dock_top ...'),
        (0x3F05D3, 'lea rdx, [rip + {rip}]', 0x1666660, '... material ...'),
        (0x3F0736, 'lea rdx, [rip + {rip}]', 0x1672498, '... shadow_caster (no stage or order option)'),
        (0x89F81, 'call qword ptr [rax + 0x18]', None, 'frame: the script game update (Lua update, then plugins)'),
        (0x689B7E, 'lea r8, [rip + {rip}]', 0x1678150, '(the Lua update callback)'),
        (0x8A1E2, 'call qword ptr [rax + 0x20]', None, 'frame: the script game render ...'),
        (0x689BC6, 'lea r8, [rip + {rip}]', 0x1690DB8, '... calls the Lua render callback ...'),
        (0x689C14, 'jmp qword ptr [rax + 0x90]', None, '... then the game plugin\'s render callback'),
        (0x8A1EC, 'cmp byte ptr [rax + 0x167], r13b', None, 'then the engine debug world, behind a setting'),
        (0x3F7A22, 'lea rdx, [rip + {rip}]', 0x1680CB8, 'Application.new_world'),
        (0x3F7A77, 'lea rdx, [rip + {rip}]', 0x1680CF0, 'Application.render_world'),
        (0x3F7ACC, 'lea rdx, [rip + {rip}]', 0x1680CE0, 'Application.release_world'),
        (0x3F96A2, 'lea rdx, [rip + {rip}]', 0x1680DC8, 'Application.create_viewport'),
        (0x318216, 'mov qword ptr [rsi + 0x230960], rax', None, 'render_world stamps the world (main_world reads it)'),
        (0x10788C, 'xchg qword ptr [rdi + rcx*8 + 8], rax', None, 'the world render is queued in order'),
    ],
}
GAME = {
    'inputActions': [
        (0x12F65F8, 'imul r8, rdx, 0x61', None, 'an action\'s state: (group * 97 + action) ...'),
        (0x12F6603, 'movzx eax, byte ptr [r10 + r11 + 0x328]', None, '... * 32 + 0x328, byte 0: triggered'),
        (0x12F67B9, 'mov rax, qword ptr [rip + {rip}]', G_INPUT_OWNER, 'the input owner'),
        (0xAE6518, 'mov dword ptr [r14 + 0xc], 1', None, 'Menu.Up = 1'),
        (0xAE65CC, 'mov dword ptr [r14 + 0x14], 2', None, 'Menu.Down = 2'),
        (0xAE6680, 'mov dword ptr [r14 + 0x1c], 3', None, 'Menu.Right = 3'),
        (0xAE6734, 'mov dword ptr [r14 + 0x24], 4', None, 'Menu.Left = 4'),
        (0xAE6AB8, 'mov dword ptr [r14 + 0x4c], 9', None, 'Menu.Back = 9'),
        (0xAE6B6C, 'mov dword ptr [r14 + 0x54], 0xa', None, 'Menu.Select = 10'),
    ],
    'loadoutScreen': [
        (0x8745B9, 'mov rax, qword ptr [rip + {rip}]', G_LOADOUT_UI_OWNER, 'the loadout UI owner'),
        (0x8745C0, 'mov rcx, qword ptr [rax + 0xb0]', None, 'its UI object (0 while no loadout screen exists)'),
        (0x146E0C8, 'mov ebx, dword ptr [rdi + 0x2818]', None, 'the screen\'s sub-state (10: stratagem grid)'),
        (0x146E109, 'mov r10d, dword ptr [rdi + 0x27d0]', None, 'the local record\'s index'),
        (0x146E1B9, 'imul rcx, r10, 0x9f0', None, 'records of 0x9F0 bytes'),
        (0x146EB9C, 'mov dword ptr [rdi + 0x281c], edx', None, 'grid open: the edited slot'),
        (0x146E5E4, 'mov edx, dword ptr [rdi + 0x281c]', None, 'the pick goes into the edited slot'),
        (0x14706AF, 'lea rcx, [rsi + 0x9f8]', None, 'each record\'s owner (+0x9E8)'),
        (0x147074B, 'mov byte ptr [rcx + 0x27fc], 1', None, 'ready'),
        (0x1470C53, 'mov byte ptr [rsi + 0x2808], 1', None, 'launched'),
    ],
    'pick': [
        (0x189D07B, 'imul rcx, rsi, 0x12a8', None, 'the slot widget ...'),
        (0x189D084, 'add rcx, 0x8ec0', None, '... of the panel'),
        (0x189D08E, 'call 0x1893600', None, 'takes the type (and its icon)'),
        (0x1893613, 'mov dword ptr [rcx + 0x128c], edi', None, 'widget +0x128C: the type'),
        (0x189D0D2, 'call 0xbe0800', None, 'a per-slot message to peers'),
        (0x18966DD, 'mov r8d, 0x600', None, 'the record rebuilt from the widgets: cleared ...'),
        (0x18966EF, 'mov dword ptr [r14 + 0x788], 0', None, '... count 0, then one entry per filled widget'),
    ],
    'gridGeometry': [
        (0x18D887E, 'mov dword ptr [rsp + 0x30], 0x43c58000', None, 'the card list is itself a GUI element ...'),
        (0x18D8886, 'mov rcx, r15', None, '... (the list frame, 395 x 528 local units)'),
        (0x18D8896, 'call 0x1447160', None, 'its size is set'),
        (0x18D44D2, 'cmp dword ptr [rbx + rcx*4 + 0x92318], 0', None, 'layout: a non-empty last row ...'),
        (0x18D44DF, 'mov dword ptr [rbx + 0x91f14], edx', None, '... is counted: +0x91F14 = the row count'),
        (0x18D2C77, 'mov dword ptr [rsi + 0x928d8], r15d', None, 'realize: the first realized row'),
        (0x18D0704, 'imul rsi, rax, 0xaed0', None, 'hover: each realized row widget ...'),
        (0x18D071B, 'cmp dword ptr [rsi + 0xb9b4], edi', None, '... and its realized card count'),
        (0x18D073F, 'add rbx, 0xc10', None, 'each card widget (stride 0x2B68) ...'),
        (0x18D074C, 'call 0x178f970', None, '... hit-tested against the cursor'),
        (0x178F9F9, 'jmp 0x144d320', None, 'the element contains-point test'),
        (0x144D33F, 'mov rax, qword ptr [rcx + 0x24]', None, 'element +0x24: its size (w, h)'),
        (0x144D362, 'movss xmm9, dword ptr [rcx + 0x64]', None, 'world transform m00 (x per unit of w)'),
        (0x144D36E, 'movss xmm10, dword ptr [rcx + 0x6c]', None, 'm02 (y per unit of w)'),
        (0x144D324, 'movss xmm5, dword ptr [rcx + 0x84]', None, 'm20 (x per unit of h)'),
        (0x144D32C, 'movss xmm2, dword ptr [rcx + 0x8c]', None, 'm22 (y per unit of h)'),
        (0x144D3EF, 'addss xmm12, dword ptr [rcx + 0x94]', None, 'translation x'),
        (0x144D337, 'movss xmm4, dword ptr [rcx + 0x9c]', None, 'translation y (screen space, bottom-left origin)'),
        (0x18CAD67, 'mov dword ptr [rsp + 0x30], 0x42a00000', None, 'stratagem card style: the card 80 x 80 units'),
        (0x18CAD84, 'mov dword ptr [rsp + 0x30], 0x42880000', None, 'its inner frame 68 x 68'),
        (0x18CAD23, 'mov dword ptr [rsp + 0x30], 0x424c0000', None, 'its icon 51 x 51'),
    ],
    'gridScroll': [
        (0x18D294D, 'mov dword ptr [rdi + 0x92968], ebp', None, 'clear: the content height starts at 0'),
        (0x18CC72B, 'mov dword ptr [rsp + 0x18], 0x42a00000', None, 'list mode 3 cell: 80 x 80 units'),
        (0x18D2579, 'movss xmm0, dword ptr [rip + {rip}]', 0x23C74A4, 'the grid gap: 5 units (row pitch 85)'),
        (0x18D4518, 'movss dword ptr [rbx + r9*4 + 0x91f18], xmm0', None, 'layout: each row height (cell + gap) ...'),
        (0x18D4522, 'cmp r9d, dword ptr [rbx + r10*4 + 0x9274c]', None, '... the first row of a section ...'),
        (0x18D4552, 'movss dword ptr [rbx + r9*4 + 0x91f18], xmm1', None, '... also holds its header height'),
        (0x18D455F, 'addss xmm0, dword ptr [rbx + 0x92968]', None, 'the content height: the sum of the row heights'),
        (0x18D456A, 'movss dword ptr [rbx + 0x92968], xmm0', None, '(stored)'),
        (0x18D4592, 'movss xmm7, dword ptr [rip + {rip}]', 0x23C7B98, 'the viewport: 528 units (four cards per row)'),
        (0x18D45A4, 'comiss xmm0, xmm7', None, 'content taller than the viewport ...'),
        (0x18D45B8, 'mov byte ptr [rbx + 0x928f9], 1', None, '... the list scrolls'),
        (0x18D45F6, 'addss xmm1, dword ptr [rip + {rip}]', 0x23C75E8, 'the scroll limit: content + 20 - viewport ...'),
        (0x18D4602, 'call 0x1794600', None, '... set on the scrollbar (list + 0x110)'),
        (0x1794600, 'movss xmm4, dword ptr [rcx + 0x7b0]', None, 'scrollbar +0x7B0: the limit (list + 0x8C0)'),
        (0x18CF84F, 'movss xmm0, dword ptr [rcx + 0x92960]', None, 'the scroll offset (units from the content top)'),
        (0x18CF874, 'movss xmm1, dword ptr [rcx + 0x8c0]', None, 'clamped to the limit ...'),
        (0x18CF881, 'movss dword ptr [rcx + 0x92960], xmm1', None, '... at the bottom'),
        (0x18D2BBA, 'movss xmm6, dword ptr [rcx + 0x92960]', None, 'realize: from the scroll offset ...'),
        (0x18D2C00, 'movss xmm0, dword ptr [rsi + r15*4 + 0x91f18]', None, '... rows are skipped by their heights'),
    ],
    'save': [
        (0x146E6B7, 'call 0x1751350', None, 'a pick saves'),
        (0x1467808, 'call 0x1751350', None, 'sync_loadout (launch) saves the record first'),
        (0x1467CD9, 'call 0x1751350', None, 'on_exit saves (after ready)'),
    ],
    'repaint': [
        (0x146CB58, 'call 0x189ca20', None, 'every frame: each panel is bound to its record'),
        (0x189C8FD, 'mov rdx, r12', None, 'the record ...'),
        (0x189C900, 'call 0x1895a20', None, '... into the slot repaint'),
        (0x1895A6B, 'cmp qword ptr [rcx + 0xd960], rdx', None, 'unchanged cached record pointer ...'),
        (0x1895A74, 'cmp byte ptr [rcx + 0xd978], r8b', None, '... and local flag: no repaint'),
        (0x1895A8D, 'mov qword ptr [rcx + 0xd960], rsi', None, 'otherwise the pointer is cached and ...'),
        (0x1895B0D, 'je 0x18962c5', None, '(a remote panel goes straight to the slots)'),
        (0x18962C3, 'jmp 0x18962cc', None, '(the local panel too, after its own extras)'),
        (0x18962CE, 'lea r15, [rsi + 0x188]', None, '... the slots are repainted from the record\'s entries'),
        (0x18962E0, 'cmp r14d, dword ptr [rsi + 0x788]', None, 'up to its count'),
        (0x1896329, 'test byte ptr [rax + 0x80], 2', None, 'selectable types only'),
        (0x1896347, 'call 0x1893600', None, 'each into the next widget (type and icon)'),
    ],
    'selectionLifecycle': [
        (0x146EA57, 'mov byte ptr [rcx + 0x273990], 1', None, 'a selection opens: the selection-open byte ...'),
        (0x146F3DA, 'mov byte ptr [rcx + 0x273990], 0', None, '... and closes'),
        (0x1466FA6, 'mov dword ptr [rdi + 0x273990], 0x1000000', None, '(cleared when the screen is built)'),
        (0x146E672, 'call 0x146f3b0', None, 'a pick with no empty slot left closes the selection'),
        (0x146E6D4, 'mov dword ptr [rdi + 0x281c], esi', None, 'a pick with an empty slot left moves on to it'),
        (0x1465931, 'mov dword ptr [rdi + 0x281c], 0xffffffff', None, 'the edited slot starts at -1'),
        (0x1468748, 'mov edx, dword ptr [rcx + rsi + 0x66f5c]', None, 'every frame: the FOCUSED slot ...'),
        (0x14686BB, 'mov dword ptr [rsi + 0x2818], eax', None, '... sets the sub-state (10: a stratagem slot focused)'),
        (0x189578D, 'mov dword ptr [rcx + 0xd96c], ebx', None, 'the panel\'s focused slot'),
    ],
    'iconColours': [
        (0x1893669, 'mov r8d, dword ptr [rdi + 0xb8]', None, 'a slot icon\'s colours: the type\'s colour set ...'),
        (0x1893670, 'lea rax, [rip + {rip}]', 0x331B610, '... indexes the category colour table ...'),
        (0x1893677, 'shl r8, 4', None, '... of 16-byte entries ...'),
        (0x189367B, 'mov edx, 0x28723f4d', None, '... set as c0 (the R mask layer: strength, r, g, b)'),
        (0x1893683, 'call 0x14498c0', None, '(the element material\'s vector setter)'),
        (0x1893695, 'lea r8, [rip + {rip}]', 0x21E89E0, 'c1 (the G mask layer) ...'),
        (0x189369C, 'mov edx, 0x851fd4fd', None, '... is this constant'),
        (0x18936B3, 'lea r8, [rip + {rip}]', 0x21E8A10, 'c2 (the B mask layer) ...'),
        (0x18936BA, 'mov edx, 0x10c353af', None, '... is this constant (c3, the A layer, is never set)'),
    ],
    'selectionAdvance': [
        (0x146E609, 'cmp dword ptr [rdi + 0x6f290], 1', None, 'a pick in panel mode 1 always closes the selection'),
        (0x146E619, 'lea r11, [rdi + 0x6373c]', None, 'the next empty slot: the widgets from slot 0 ...'),
        (0x146E620, 'movzx eax, byte ptr [r11 - 4]', None, '... skipping one whose flags (+0x1288) have bit 2 ...'),
        (0x146E632, 'cmp eax, 0x94', None, '... empty: the widget type is 0 or above 149 ...'),
        (0x146E660, 'cmp esi, 4', None, '... up to slot 3 (no wrap)'),
        (0x146E6CF, 'call 0x1895770', None, 'found: the focus and its highlight move inside the native setter'),
        (0x146E692, 'call 0x18d1890', None, 'either way the native grid is re-greyed from the record'),
        (0x146D56E, 'cmp byte ptr [rdi + 0x273990], 0', None, 'per frame the selection byte only routes input'),
        (0x146F424, 'call 0x18dbff0', None, 'the close handler hides the grid through element calls'),
        (0x12FA0A6, 'lea rcx, [rsi + 0x328]', None, 'every frame the input action states are cleared ...'),
        (0x12FA0AF, 'mov r8d, 0x9da0', None, '... (13 x 97 x 32 bytes), then recomputed from the devices'),
        (0x1895A88, 'mov qword ptr [rsp + 0x48], rax', None, 'the repaint keeps the old cached record pointer ...'),
        (0x18963B5, 'cmp qword ptr [rsp + 0x48], 0', None, '... and when it was 0 (the Runtime write) ...'),
        (0x18963EF, 'mov dword ptr [r13 + 0xd96c], 0', None, '... the local panel focus moves to slot 0'),
    ],
    'slotIcon': [
        (0x189302E, 'lea rdi, [rsi + 0x380]', None, 'each slot widget\'s icon element: widget + 0x380 ...'),
        (0x1893038, 'call 0x143eab0', None, '... built as an image element'),
        (0x189360C, 'lea rbx, [rcx + 0x380]', None, 'the widget taking a type: its icon element ...'),
        (0x1893650, 'mov rdx, qword ptr [rdi + 0xb0]', None, '... gets the type\'s icon (StratagemInfo +0xB0) ...'),
        (0x1893657, 'call 0x1450160', None, '... every time (no early return): each repaint resets every slot icon'),
        (0x1450177, 'cmp eax, 0xc0000', None, 'the image setter: an image element (kind 3) ...'),
        (0x14501BB, 'lea r8, [rdi + 0x134]', None, '... its sprite rectangle (+0x134) from the atlas map ...'),
        (0x14501C2, 'mov qword ptr [rcx + 0x150], rbx', None, '... its name (+0x150) ...'),
        (0x1450213, 'call 0x143f3c0', None, '... then its UV'),
        (0x143F464, 'movss dword ptr [rcx + 0x124], xmm0', None, 'UV (+0x124) = base (+0x114) x scale + offset'),
        (0x143F48F, 'movss dword ptr [rcx + 0x130], xmm2', None, '(its last corner)'),
        (0x1449B4C, 'call qword ptr [rax + 0x78]', None, 'binding a texture is an engine call (a render command)'),
        (0x1449B7D, 'or ecx, 2', None, 'the element is marked dirty (bit 1) ...'),
        (0x1449BA0, 'or edx, 8', None, '... and each ancestor child-dirty (bit 3) ...'),
        (0x1449BA5, 'mov rax, qword ptr [rax + 0xf0]', None, '... up the parent chain (+0xF0)'),
        (0x12F436E, 'test byte ptr [rdi + 8], 0xa', None, 'the scene update visits dirty elements ...'),
        (0x144E0B0, 'jmp 0x143ec80', None, '... an image element ...'),
        (0x143ED88, 'lea r9, [rdi + 0x124]', None, '... pushes its UV ...'),
        (0x143EE16, 'mov r9, qword ptr [rdi + 0x148]', None, '... and its own material to its GUI primitive ...'),
        (0x143EE7B, 'and ecx, 0xfffffff5', None, '... and clears both dirty bits'),
    ],
    'slotFocus': [
        (0x189577A, 'mov eax, dword ptr [rcx + 0xd96c]', None, 'the focus setter: the panel focus (+0xD96C) ...'),
        (0x1895798, 'mov dword ptr [rcx + 0xd970], eax', None, '... the previous focus (+0xD970) ...'),
        (0x1895826, 'mov word ptr [rcx + 0x1288], dx', None, '... the old widget loses flag bit 1 ...'),
        (0x18958B0, 'mov word ptr [rcx + 0x1288], dx', None, '... the new widget gains it ...'),
        (0x18958B7, 'call 0x18932f0', None, '... and each widget\'s visuals are updated'),
        (0x189330E, 'movzx eax, byte ptr [rcx + 0x1288]', None, 'the widget visual update reads only the flags ...'),
        (0x1893356, 'shr al, 1', None, '... bit 1: focused ...'),
        (0x189341C, 'mov qword ptr [rbx + 0x1118], 0x40400000', None, '... the focused frame: 3 units, no gap ...'),
        (0x189351E, 'mov dword ptr [rbx + 0x111c], 0x41800000', None, '... an unfocused frame: a 16-unit gap'),
        (0x18939B9, 'cmp byte ptr [rcx + 0x12a0], 0', None, 'a frame flash (a colour tween) ...'),
        (0x1893A4B, 'mov byte ptr [rbx + 0x12a0], 1', None, '... sets the widget byte +0x12A0'),
        (0x1894C20, 'lea rbx, [rsi + 0xa160]', None, 'every frame, for the four slot widgets\' bytes ...'),
        (0x1894C30, 'cmp byte ptr [rbx], 0', None, '... a set byte ...'),
        (0x1894C35, 'test dword ptr [rbx - 0xb08], 0x4000000', None, '... with no colour tween on the frame ...'),
        (0x1894C41, 'test dword ptr [rbx - 0xa58], 0x7ff', None, '... (its tween index) ...'),
        (0x1894C54, 'mov byte ptr [rbx], 0', None, '... is cleared ...'),
        (0x1894C57, 'call 0x18932f0', None, '... and the widget\'s visuals are updated from its flags'),
        (0x1899CC1, 'test eax, eax', None, 'the panel update runs it in panel mode 0 ...'),
        (0x1899CD0, 'call 0x1894bc0', None, '... for the local panel ...'),
        (0x189B9CB, 'cmp qword ptr [rdi + 0x1ee00], 0', None, '... while its container is bound (ui+0x72878)'),
        (0x189B9E8, 'call 0x18999f0', None, '(the panel update)'),
        (0x146C69A, 'call 0x189b920', None, '(from the loadout screen update)'),
        (0x1468671, 'mov eax, dword ptr [rsi + 0x2739c8]', None, 'the active panel group (ui+0x2739C8) ...'),
        (0x1468677, 'imul rcx, rax, 0x1ee18', None, '... of 0x1EE18 bytes (0: the local one)'),
        (0x18963E0, 'mov eax, dword ptr [r13 + 0xd96c]', None, 'the repaint\'s first bind reads the focus, then forces 0'),
        (0x146EC9D, 'or cx, 8', None, 'the open handler sets flag bit 3 on the widgets ...'),
        (0x146F45D, 'and cx, r14w', None, '... the close handler clears it'),
        (0x18950D6, 'call 0x178e020', None, 'the panel navigation decodes the direction actions ...'),
        (0x189BDEC, 'test r9b, r9b', None, '... and is skipped while a selection is open'),
    ],
    'selectionCloseBlockers': [
        (0x146F495, 'call 0x189e2f0', None, 'the close handler slides each panel back (pool tweens) ...'),
        (0x189E31B, 'cmp byte ptr [rcx + 0x1ee11], dl', None, '... behind a latch (P+0x1EE11) ...'),
        (0x189B9D5, 'movzx r8d, byte ptr [rdi + 0x1ee11]', None, '... read per frame only as a parameter, never re-run'),
        (0x18DC0ED, 'call 0x1448870', None, 'the grid fade is a pool tween'),
        (0x18D285F, 'call 0x13918e0', None, 'the list clear releases resource handles'),
        (0x146E975, 'call 0x146f3b0', None, 'Back with the grid open runs the full close (input only)'),
        (0x146ED6A, 'cmp dword ptr [rdi + 0x164e2c], 0', None, 'an empty grid closes only inside the open handler'),
    ],
    'slotIconMaterial': [
        (0x1893046, 'call 0x144f800', None, 'the slot icon element is built with its material once'),
        (0x1449421, 'test r8b, 1', None, 'a material marked external (bit 16) is never cloned ...'),
        (0x1446AA9, 'shr eax, 0x10', None, '... nor destroyed with the element'),
    ],
    'uiSound': [
        (0x1327F68, 'mov rcx, qword ptr [rip + {rip}]', 0x3326340, 'UI sounds: the game\'s world context ...'),
        (0x1327F76, 'mov rcx, qword ptr [rcx + 0x10f8]', None, '... its Game World\'s WwiseWorld (+0x10F8) ...'),
        (0x1327F8B, 'call 0x12556e0', None, '... the key remapped to the Wwise event id ...'),
        (0x1327F9F, 'mov rcx, qword ptr [rcx + 0x10f8]', None, '... and posted there'),
        (0xAB18B7, 'mov qword ptr [rsi + 0x10e8], rax', None, 'the Game World itself (+0x10E8)'),
        (0x146E665, 'mov edx, 0x97753411', None, 'a pick filling the last slot: the picker-close sound ...'),
        (0x146E968, 'mov edx, 0x97753411', None, '... also Back on a stratagem slot'),
        (0x146DC94, 'mov edx, 0xa31d0645', None, 'a loadout slot selected (the grid opening) ...'),
        (0x146DC99, 'call 0x1327f50', None, '(posted)'),
        (0x18CFDD3, 'mov edx, 0xbe9303b7', None, 'a card accepted in the stratagem grid: the pick sound ...'),
        (0x18CFDD8, 'call 0x1327f50', None, '... posted for every pick ...'),
        (0x18CFDE7, 'mov eax, 4', None, '... before the card list reports the pick'),
    ],
    # The game's own selection close (research selectorClose): its one argument, its effects, and its two callers.
    'selectorClose': [
        (0x146F3B0, 'mov qword ptr [rsp + 8], rbx', None, 'the close handler (ui) ...'),
        (0x146F3D1, 'mov rsi, rcx', None, '... keeps its one argument, the loadout UI ...'),
        (0x146F3D4, 'mov byte ptr [rcx + 0x273991], al', None, '... copies ui+0x273992 to ui+0x273991 ...'),
        (0x146F3DA, 'mov byte ptr [rcx + 0x273990], 0', None, '... clears the selection-open byte ...'),
        (0x146F418, 'mov dword ptr [rsi + 0x2818], 0', None, '... and the sub-state ...'),
        (0x146F424, 'call 0x18dbff0', None, '... hides the grid ...'),
        (0x146F429, 'lea rcx, [rsi + 0xd2f20]', None, '... clears the card list ...'),
        (0x146F430, 'call 0x18d27b0', None, '(the list clear)'),
        (0x18D28E5, 'mov dword ptr [rdi + 0x91f14], ebp', None, 'the list clear: row count 0 ...'),
        (0x18D296F, 'mov qword ptr [rdi + 0x92984], rbp', None, '... card count 0'),
        (0x146F46B, 'call 0x18932f0', None, 'redraws each slot widget it clears bit 3 on'),
        (0x146F503, 'ret', None, 'returns nothing'),
        (0x146E0B6, 'mov rdi, rcx', None, 'the pick handler keeps the loadout UI (its first argument) in rdi ...'),
        (0x146E665, 'mov edx, 0x97753411', None, '... a pick that leaves no empty slot: the picker-close sound ...'),
        (0x146E66F, 'mov rcx, rdi', None, '... then the UI ...'),
        (0x146E672, 'call 0x146f3b0', None, '... to the close handler'),
        (0x146E94E, 'mov ecx, dword ptr [rdi + 0x2818]', None, 'Back: by the sub-state ...'),
        (0x146E963, 'cmp ecx, 5', None, '... 10 (a stratagem slot): ...'),
        (0x146E972, 'mov rcx, rdi', None, '... the picker-close sound, then the UI to the close handler'),
    ],
    'slotOverlay': [
        (0x14469AE, 'mov qword ptr [rbx + 0xf8], rcx', None, 'an element\'s scene (scene 3: the loadout; 5: the HUD) ...'),
        (0x12EDFDC, 'mov rax, qword ptr [rcx + 0x4b8]', None, '... whose GUI is a screen GUI ...'),
        (0x143EDD2, 'mov rcx, qword ptr [rax + 8]', None, '... that the scene push draws into ...'),
        (0x143ED9F, 'movzx edx, word ptr [rdi + 0xbc]', None, '... at the element\'s layer (+0xBC)'),
        (0x143EDE6, 'mov dword ptr [rdi + 0x110], eax', None, 'the element\'s primitive id (+0x110)'),
        (0x144BEA7, 'movups xmmword ptr [rcx + 0x54], xmm3', None, 'its effective colour and alpha (+0x54)'),
        (0x1893095, 'mov edx, 0xe', None, 'the ship slot icon: layer 14'),
        (0xAB7B18, 'mov rcx, qword ptr [rbx + 0x1118]', None, 'the Ui World rendered through its viewport'),
        (0x12F0BEF, 'mov eax, dword ptr [r10 + 0xac21c]', None, 'the game mode ...'),
        (0x12F0C12, 'cmp eax, 4', None, '... 4: the mission HUD ...'),
        (0x12F0C17, 'lea rcx, [rdi + 0x24e340]', None, '... at the UI root + 0x24E340 ...'),
        (0x12EA0E3, 'lea rcx, [r15 + 0x146dc0]', None, '... its stratagem list + 0x146DC0 ...'),
        (0x1833436, 'lea rsi, [r15 + 0x1150]', None, '... entries from + 0x1150 ...'),
        (0x18334D4, 'add rsi, 0x3760', None, '... of 0x3760 bytes ...'),
        (0x183599A, 'mov dword ptr [rcx + 0x3748], r12d', None, '... each holding the record entry it shows ...'),
        (0x1835DAE, 'lea rcx, [r15 + 0x7c0]', None, '... and its widget (+0x7C0) ...'),
        (0x18398B4, 'lea rdi, [r14 + 0x518]', None, '... whose icon element is + 0x518 ...'),
        (0x183A352, 'mov dword ptr [rsi + 0x14c8], eax', None, '... showing the type cached at + 0x14C8'),
        (0xAC6397, 'mov rcx, qword ptr [rip + {rip}]', 0x346D538, 'the UI root'),
    ],
    'slotBackground': [
        (0x1892EBA, 'mov edx, 5', None, 'the slot widget\'s +0x110: an element of kind 5 ...'),
        (0x1892EC2, 'call 0x1446840', None, '... (the element init: kind = edx << 18) ...'),
        (0x1892F01, 'mov dword ptr [rbp - 0x50], 0x40a00000', None, '... placed at 5, 5 units ...'),
        (0x1892F2F, 'mov dword ptr [rbp - 0x50], 0x3e109091', None, '... grey 36/255 ...'),
        (0x1892F4C, 'mov edx, 0xc', None, '... at layer 12, under the icon'),
        (0x1892F6C, 'lea rdi, [rsi + 0x228]', None, 'the tint sprite element (+0x228) ...'),
        (0x189300E, 'mov edx, 0xd', None, '... at layer 13 ...'),
        (0x1895E12, 'movabs rbx, 0x6e6a67b944661e66', None, '... its sprite, set by the local panel repaint ...'),
        (0x18938C6, 'lea rax, [rip + {rip}]', 0x331A9B0, '... tinted c0 from this colour-set table ...'),
        (0x18938F2, 'lea rax, [rip + {rip}]', 0x331B4E0, '... and c1 from this one'),
        (0x144DF3B, 'shr eax, 0x12', None, 'the element push dispatch by kind (flags >> 18) ...'),
        (0x144E0D4, 'jmp 0x1444030', None, '... kind 5 pushed by 0x1444030 ...'),
        (0x1444144, 'mov r10, qword ptr [rcx + 0x108]', None, '... as a filled rectangle: no material, a colour'),
    ],
    'detailsPanel': [
        (0x1468773, 'lea rcx, [rsi + 0x24b520]', None, 'while selecting: the details panel (ui+0x24B520) ...'),
        (0x1468783, 'call 0x189fa80', None, '... is filled'),
        (0x189FC39, 'movss xmm0, dword ptr [rip + {rip}]', 0x23C7D58, 'its size for a stratagem: 1024 ...'),
        (0x189FC44, 'movss xmm2, dword ptr [rip + {rip}]', 0x23C7AC8, '... x 400 units'),
        (0x189FC5D, 'mov dword ptr [rdi + 0x157e0], 0xb', None, '(the stratagem mode)'),
        (0x189FC67, 'call 0x1447160', None, '(the element size setter)'),
        (0x146F3E1, 'add rcx, 0x24b520', None, 'the close handler fades it'),
    ],
    'cardLook': [
        (0x18CADD2, 'movabs rdx, 0xf6978e86e4f4b0d5', None, 'the card\'s element +0x1800: a material ...'),
        (0x18CADEB, 'movabs rdx, 0x270930a62555ebef', None, '... and an image: the focus bracket sprite ...'),
        (0x18CADFC, 'call 0x1450160', None, '... bound by the image setter (atlas sprite first)'),
        (0x18CAE01, 'mov dword ptr [rsp + 0x30], 0x42b80000', None, 'the bracket element: 92 units'),
        (0x18CAAA7, 'movabs rdx, 0xf78db8f1cc821769', None, 'another card style\'s bracket sprite'),
        (0x18CABB5, 'movabs rdx, 0x7d698bf20161de2b', None, 'another card style\'s bracket sprite'),
    ],
    'renderOrder': [
        (0x4EE7E0, 'jmp 0xab7680', None, 'the game plugin\'s render callback'),
        (0xAB1BA4, 'mov edx, 0xf2760503', None, 'the game world\'s viewport: default'),
        (0xAB1BF0, 'mov edx, 0x1c714a8c', None, 'the UI world\'s viewport: hud_world_ui_and_composite_layer'),
        (0xAB7AFC, 'call qword ptr [r10 + 0x28]', None, 'render: the game world ...'),
        (0xAB7B0A, 'mov r8, qword ptr [rbx + 0x1128]', None, '... then the UI world through its viewport ...'),
        (0xAB7B40, 'call qword ptr [r10 + 0x28]', None, '(render_world)'),
        (0xAB7CBD, 'mov dword ptr [rsp + 0x38], 0x1a43b7a8', None, '... then an offscreen ui_3d world'),
    ],
}


GAME_FONTS = 0x3772260             # the game's own font table: eight resource name hashes (game.dll .data)
# The game's own selection close (research selectorClose): its entry and the bytes re-proved before each call.
PROLOGUE_RVA = 0x146F3B0
PROLOGUE_CLOSE = ('48895c240848896c24104889742418' '48897c242041564883ec20' '0fb68192392700488bf1888191392700'
    'c6819039270000')
PLUGIN_GAME = 0x1A0F770            # exe .data: the game plugin's API (its +0x90: the render callback)
RENDER_CONFIG = 0xEE6B1BA7E22D71ED  # the game's render config resource (name hash), type render_config
CAMERA_UNIT, SHADING = 'core/units/camera', 'core/stingray_renderer/environments/midday/midday'
UNIT_TYPE, SHADING_TYPE = hd2_archive.resource_hash('unit'), hd2_archive.resource_hash('shading_environment')
TEXTURE_TYPE = hd2_archive.resource_hash('texture')
CARD_IMAGES = {'focusBracket': 0x270930A62555EBEF, 'focusBracketStyleA': 0xF78DB8F1CC821769,
    'focusBracketStyleB': 0x7D698BF20161DE2B, 'elementMaterial': 0xF6978E86E4F4B0D5}


def card_look(mem, manager):
    """The card images: each hash as a texture, a material and an atlas sprite (with the sprite's page, size and UV)."""
    atlas = mem.ptr(manager.rm + 0x2A0)
    buckets = mem.u32(manager.rm + 0x2B4)
    out = {}
    for label, name in CARD_IMAGES.items():
        index = resources.resolve(mem, atlas, buckets, 24, 0x10, 0, name) if atlas else None
        sprite = None
        if index is not None:
            record = mem.ptr(atlas + index * 24 + 8)
            raw = mem.read(record, 0x28)
            page, width, height = struct.unpack_from('<QII', raw, 8)
            sprite = {'page': '0x%016X' % page, 'size': [width, height],
                'uv': [round(v, 5) for v in struct.unpack_from('<4f', raw, 0x18)] if len(raw) >= 0x28 else
                    [round(v, 5) for v in struct.unpack('<4f', mem.read(record + 0x18, 16))]}
        out[label] = {'texture': manager.lookup(TEXTURE_TYPE, name)[0], 'material': manager.lookup(MATERIAL_TYPE, name)[0],
            'sprite': sprite}
    return out


ICON_SHADER_LIBRARY = 0x8CDE642487327D4E   # the shader library holding the icon material template 0x3461FF0D
ICON_TEMPLATE = 0x3461FF0D
COLOUR_TABLE, COLOUR_WHITE, COLOUR_SHADOW = 0x331B610, 0x21E89E0, 0x21E8A10   # game.dll: c0 table, c1, c2


def icon_shader():
    """The icon material template's shader library from the installed data: the template id, its pass layer and the
    pixel shader's constant buffer: the four mask layers c0-c3 and the one texture, diffuse_map."""
    data = hd2_game_data.Data()
    wanted = (ICON_SHADER_LIBRARY, hd2_archive.resource_hash('shader_library'))
    found = data.find({wanted})
    if wanted not in found:
        raise ValueError('the icon shader library is not in the installed game data')
    archive, _main, _stream, gpu = found[wanted]
    raw = data.read(archive, gpu, '.gpu_resources')
    template, layer = struct.unpack_from('<I', raw, 0xE0)[0], struct.unpack_from('<I', raw, 0x158)[0]
    if template != ICON_TEMPLATE:
        raise ValueError('the icon shader library no longer holds the icon template')
    names = {name: raw.find(name.encode() + b'\0') for name in ('c0', 'c1', 'c2', 'c3', '__tex_diffuse_map',
        'scissor_mode')}
    if min(names.values()) < 0 or raw.count(b'DXBC') < 1:
        raise ValueError('the icon pixel shader no longer declares c0-c3 and diffuse_map')
    ids = {name: '0x%08X' % (hd2_archive.resource_hash(name) >> 32) for name in ('c0', 'c1', 'c2', 'c3', 'diffuse_map')}
    if ids['diffuse_map'] != '0x3AA8B87E' or ids['c0'] != '0x28723F4D' or ids['c1'] != '0x851FD4FD' \
            or ids['c2'] != '0x10C353AF':
        raise ValueError('the variable ids no longer match the game\'s')
    return {'library': '0x%016X' % ICON_SHADER_LIBRARY, 'archive': archive, 'gpuBytes': len(raw),
        'sha256': hashlib.sha256(raw).hexdigest().upper(), 'template': '0x%08X' % template,
        'passLayer': '0x%08X' % layer, 'transparentLayer': '0x%08X' % (hd2_archive.resource_hash('transparent') >> 32),
        'declares': sorted(names), 'variableIds': ids}


GAS_STRIKE_ID = 3193297673         # Orbital Gas Strike's stable id (StratagemInfo +4): the slot icon example


def row_by_id(mem, stable_id):
    for kind in range(1, 150):
        row = mem.ptr(mem.game + TABLE + kind * 8)
        if row and mem.u32(row + 4) == stable_id:
            return kind, row
    return None, None


def slot_icon_atlas(mem, manager):
    """The token's (Orbital Precision Strike) and the example borrowed icon's (Orbital Gas Strike) atlas sprites: page,
    rectangle and the rows' colour sets, read as the image setter reads them."""
    atlas = mem.ptr(manager.rm + 0x2A0)
    buckets = mem.u32(manager.rm + 0x2B4)
    out = {}
    for label, kind, row in (('token', PRECISION, mem.ptr(mem.game + TABLE + PRECISION * 8)),
            ('borrowed', *row_by_id(mem, GAS_STRIKE_ID))):
        icon = mem.u64(row + 0xB0)
        index = resources.resolve(mem, atlas, buckets, 24, 0x10, 0, icon) if atlas else None
        sprite = None
        if index is not None:
            record = mem.ptr(atlas + index * 24 + 8)
            page = mem.u64(record + 8)
            sprite = {'page': '0x%016X' % page, 'rect': list(struct.unpack('<4f', mem.read(record + 0x18, 16)))}
        out[label] = {'type': kind, 'stableId': mem.u32(row + 4), 'icon': '0x%016X' % icon,
            'colourSet': mem.u32(row + 0xB8), 'sprite': sprite}
    out['samePage'] = bool(out['token']['sprite'] and out['borrowed']['sprite']
        and out['token']['sprite']['page'] == out['borrowed']['sprite']['page'])
    return out


def sjson(data):
    """The compiled render config: typed nodes {u32 type, u32 value}; 1 bool, 2 int, 3 float, 4 string offset,
    5 array {element type, count, values}, 6 object {count, (key offset, type, value)}."""
    def text(at):
        return data[at:data.index(b'\0', at)].decode('latin-1')

    def node(kind, value):
        if kind == 1:
            return bool(value)
        if kind == 2:
            return struct.unpack('<i', struct.pack('<I', value))[0]
        if kind == 3:
            return struct.unpack('<f', struct.pack('<I', value))[0]
        if kind == 4:
            return text(value)
        if kind == 5:
            element, count = struct.unpack_from('<II', data, value)
            return [node(element, struct.unpack_from('<I', data, value + 8 + 4 * i)[0]) for i in range(count)]
        if kind == 6:
            count = struct.unpack_from('<I', data, value)[0]
            out = {}
            for i in range(count):
                key, sub, sub_value = struct.unpack_from('<III', data, value + 4 + 12 * i)
                out[text(key)] = node(sub, sub_value)
            return out
        raise ValueError('unknown render config node %d' % kind)
    return node(*struct.unpack_from('<II', data, 0))


def render_config():
    """The game's render config from the installed data: how the UI world, the Noesis UI and the overlay viewport are
    ordered."""
    data = hd2_game_data.Data()
    wanted = (RENDER_CONFIG, hd2_archive.resource_hash('render_config'))
    found = data.find({wanted})
    if wanted not in found:
        raise ValueError('the render config is not in the installed game data')
    archive, main, _stream, _gpu = found[wanted]
    raw = data.read(archive, main)
    config = sjson(raw)
    def passes(name):
        out = []
        for step in config['layer_configs'][name]:
            if 'resource_generator' in step:
                out.append('generator ' + step['resource_generator'])
            elif 'name' in step:
                out.append('layer %s -> %s' % (step['name'], ', '.join(step.get('render_targets', []))))
            elif 'clear_flags' in step:
                out.append('clear ' + ', '.join(step.get('render_targets', [])))
            else:
                out.append('(%s)' % step.get('type', 'step'))
        return out
    def outputs(generator):
        found_out = []
        def walk(item):
            if isinstance(item, dict):
                if item.get('type') in ('fullscreen_pass', 'noesis') and 'output' in item:
                    found_out.append({'type': item['type'], 'output': item['output'],
                        'input': item.get('input', []), 'shader': item.get('shader')})
                for value in item.values():
                    walk(value)
            elif isinstance(item, list):
                for value in item:
                    walk(value)
        walk(config['resource_generators'][generator])
        return found_out
    viewports = config['viewports']
    return {'resource': '0x%016X' % RENDER_CONFIG, 'archive': archive, 'sha256': hashlib.sha256(raw).hexdigest().upper(),
        'uiWorldViewport': {'name': 'hud_world_ui_and_composite_layer',
            'outputRt': viewports['hud_world_ui_and_composite_layer']['output_rt'],
            'passes': passes('hud_world_ui_and_composite_layer')},
        'overlayViewport': {'name': 'overlay', 'outputRt': viewports['overlay']['output_rt'],
            'passes': passes('overlay')},
        'noesis': outputs('noesis'), 'copyAndBlendUi': outputs('copy_and_blend_ui')[:1],
        'defaultViewportOutputRt': viewports['default']['output_rt']}
MONACO_SHADER = 0x51C11754          # core/performance_hud/monaco's material shader (a bitmap-font shader)
REFERENCE = {'mod': 'Know Your Constellation v4.0 (mods/cowboybingus/enemy_intelligence), Vanilla Plus Megapack v36',
    'source': 'LuaJIT bytecode embedded in its addon (loadstring), listed offline through jit.util in lua51.dll; a lead '
        'only',
    'calls': ['the global stingray (the table Runtime reads)', 'Application.main_world, checked against Application.worlds',
        "World.create_screen_gui(world, 'scale', 1, 1)", 'World.destroy_gui only while the world is listed',
        'Gui.resolution()', 'Gui.rect / Gui.update_rect (retained ids)', 'Gui.text / Gui.update_text (retained ids)',
        'Gui.text_extents', 'Gui.material + Material.set_scalar / set_vector2 / set_vector4 / set_texture',
        'IdString64.from_hex'],
    'values': {'position': 'stingray.Vector3(x, y, layer or 0)', 'size': 'stingray.Vector2(w, h)',
        'color': 'stingray.Color(a, r, g, b)'},
    'font': ('the native game font: its name, its material and the runtime font atlas read from game.dll memory, '
        'passed as IdString64, the atlas set on the material instance of its own GUI'),
    'screens': 'the map and briefing screens, detected by reading game memory',
    'bitmaps': 'none'}


def font_table(mem, manager):
    """The game's font table: each font hash, whether the font and a material of that name are loaded, and that
    material's shader."""
    out = []
    for k in range(8):
        name = mem.u64(mem.game + GAME_FONTS + 8 * k)
        state, pointer = manager.lookup(MATERIAL_TYPE, name)
        shader = None
        if state == 'present' and pointer:
            obj = mem.u64(pointer + 0x20)
            shader = mem.u32(obj + 0x30) if obj else None
        out.append({'font': '0x%016X' % name, 'loaded': manager.lookup(FONT_TYPE, name)[0], 'material': state,
            'shader': '0x%08X' % shader if shader is not None else None})
    return out


# The UI sound keys the loadout screen posts (0x1327F50) and the hash table that remaps each to its Wwise event id.
UI_SOUND_KEYS = (0xBE9303B7, 0x97753411, 0xA31D0645)
SOUND_REMAP = {'slots': 0x346C9F8, 'capacity': 0x346CA00, 'empty': 0x346CA04, 'multiplier': 0x346CA08}


def sound_remap(mem):
    """Each UI sound key's Wwise event id, read from the game's remap table (open addressing from key * multiplier)."""
    slots = mem.ptr(mem.game + SOUND_REMAP['slots'])
    capacity, empty = mem.u32(mem.game + SOUND_REMAP['capacity']), mem.u32(mem.game + SOUND_REMAP['empty'])
    multiplier = mem.u32(mem.game + SOUND_REMAP['multiplier'])
    out = {}
    for key in UI_SOUND_KEYS:
        found, start = None, (key * multiplier) & 0xFFFFFFFF
        for i in range(capacity):
            at = slots + ((start + i) & (capacity - 1)) * 8
            k = mem.u32(at)
            if k == key:
                found = mem.u32(at + 4)
            if k in (key, empty):
                break
        out['0x%08X' % key] = '0x%08X' % found if found is not None else None
    return out


def snapshot_evidence():
    out = {}
    font_hash = hd2_archive.resource_hash(FONT)
    for name in SNAPSHOTS:
        mem = base.Mem(name)
        manager = resources.Manager(mem)
        owner = mem.ptr(mem.game + G_LOADOUT_UI_OWNER)
        input_owner = mem.ptr(mem.game + G_INPUT_OWNER)
        actions = mem.read(input_owner + 0x328, 13 * 97 * 32) if input_owner else None
        precision = mem.ptr(mem.game + TABLE + PRECISION * 8)
        max_uses = struct.unpack('<i', mem.read(precision + 0x50, 4))[0]
        plugin = mem.ptr(mem.exe + PLUGIN_GAME)
        render = mem.u64(plugin + 0x90) if plugin else None
        out[name] = {'loadoutUi': bool(owner and mem.u64(owner + 0xB0)),
            'pluginRenderCallback': '0x%X' % (render - mem.game) if render else None,
            'cameraUnit': manager.lookup(UNIT_TYPE, hd2_archive.resource_hash(CAMERA_UNIT))[0],
            'shadingEnvironment': manager.lookup(SHADING_TYPE, hd2_archive.resource_hash(SHADING))[0],
            'cardLook': card_look(mem, manager),
            'slotIconAtlas': slot_icon_atlas(mem, manager),
            'iconColours': {'table': [list(struct.unpack('<4f', mem.read(mem.game + COLOUR_TABLE + 16 * k, 16)))
                for k in range(5)], 'c1': list(struct.unpack('<4f', mem.read(mem.game + COLOUR_WHITE, 16))),
                'c2': list(struct.unpack('<4f', mem.read(mem.game + COLOUR_SHADOW, 16)))},
            'font': manager.lookup(FONT_TYPE, font_hash)[0], 'fontMaterial': manager.lookup(MATERIAL_TYPE, font_hash)[0],
            'inputActionsReadable': actions is not None, 'precisionMaxUses': max_uses,
            'gameFonts': font_table(mem, manager), 'uiSoundRemap': sound_remap(mem)}
        mem.close()
    return out


def main():
    snap = snapshot_image.Snapshot(build_profile.snapshot_directory() / SNAPSHOTS[0])
    game_base, game_data = snap.module_image('game.dll')
    exe_name = [k for k in snap.modules if k.endswith('.exe')][0]
    exe_base, exe_data = snap.module_image(exe_name)
    snap.close()
    exe, game = base.Image(exe_data, exe_base, base.EXE_TEXT), base.Image(game_data, game_base, base.TEXT)
    exe_pins = {group: [exe.prove(*row) for row in rows] for group, rows in EXE.items()}
    game_pins = {group: [game.prove(*row) for row in rows] for group, rows in GAME.items()}
    flat_exe = [p for rows in exe_pins.values() for p in rows]
    flat_game = [p for rows in game_pins.values() for p in rows]
    relocation = {name: base.verify_pins_live(name, flat_game, flat_exe) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('pinned bytes differ in a snapshot: %r' % relocation)
    evidence = snapshot_evidence()
    if any(v['pluginRenderCallback'] != '0x4EE7E0' for v in evidence.values()):
        raise ValueError('the game plugin render callback differs: %r' % evidence)
    config = render_config()
    result = {'build': 'F5FEE03DCFDB', 'gameDllSha256': base.PROFILE_DLL_SHA, 'exeSha256': base.PROFILE_EXE_SHA,
        'writes': 0, 'protectionChanges': 0,
        'pins': {'exe': exe_pins, 'game': game_pins}, 'pinnedBytesMismatchPerSnapshot': relocation,
        'snapshots': evidence, 'reference': REFERENCE,
        'monacoShader': '0x%08X' % MONACO_SHADER,
        'layout': {
            'loadoutUi': {'ownerGlobal': G_LOADOUT_UI_OWNER, 'root': 0xB0, 'subState': 0x2818, 'gridSubState': 10,
                'editedSlot': 0x281C, 'localRecordIndex': 0x27D0, 'ready': 0x27FC, 'launched': 0x2808,
                'records': 0x10, 'recordStride': 0x9F0, 'recordCount': 4, 'entries': 0x188, 'entryStride': 0x30,
                'entryType': 0, 'entryUses': 4, 'count': 0x788, 'owner': 0x9E8, 'maxLoadoutEntries': 4,
                'panel0BoundRecord': 0x53A78 + 0x5B78 + 0xD960, 'panel0Widgets': 0x53A78 + 0x5B78 + 0x8EC0,
                'widgetStride': 0x12A8, 'widgetType': 0x128C, 'selectionOpen': 0x273990, 'details': 0x24B520,
                'detailsUnits': [1024, 400], 'panelMode': 0x6F290, 'widgetFlags': 0x1288, 'widgetSkipBit': 4,
                'maxType': 149},
            # The native slot highlight: the local panel P = ui + panel, its focus and previous focus, the widget flag
            # bits, the frame flash byte the panel update consumes (0x1894C30), the frame element and its colour tween,
            # the frame's thickness and gap, the active panel group and the container the panel update needs.
            'slotFocus': {'panel': 0x53A78 + 0x5B78, 'focus': 0xD96C, 'previous': 0xD970, 'boundRecord': 0xD960,
                'localFlag': 0xD978, 'widgetFlags': 0x1288, 'focusedBit': 2, 'disabledBit': 4, 'selectionBit': 8,
                'flash': 0x12A0, 'frame': 0x798, 'colourTweenFlag': 0x4000000, 'colourTween': 0xB0, 'tweenMask': 0x7FF,
                'thickness': 0x1118, 'gap': 0x111C, 'opacity': 0x44, 'selectedElement': 0x1130,
                'focusedThickness': 3.0, 'focusedGap': 0.0, 'unfocusedGap': 16.0, 'activeGroup': 0x2739C8,
                'containerBound': 0x72878},
            # The render-side copy of a slot icon element's material (research slotTexture; READ ONLY): M = [element +
            # material]; M+4 its render handle, M+8 its world interface (WRI + 0x10); RI = [WRI + 0x10]; RW = [RI + 0x80]
            # - 0x10, checked by its vtable and RW+0x150 == WRI; R = [[RW+0x170] + 8 * u32 [[RW+0x1C0] + 4 * (handle &
            # [WRI+0x40])]], checked by its vtable, kind 7, shader and template; its texture properties (+0x30, count
            # +0x28) and handles (+0x48, count +0x40); a texture's render handle is u32 [resource + 0].
            'slotTexture': {'elementOwns': 0x40, 'elementExternal': 0x10000, 'materialHandle': 4, 'materialWorld': 8,
                'materialShader': 0x30, 'materialTemplate': 0x38, 'worldOffset': 0x10, 'wriRenderInterface': 0x10,
                'wriMask': 0x40, 'riRenderWorld': 0x80, 'rwVtable': 0x1672E70, 'rwWri': 0x150, 'rwIndex': 0x1C0,
                'rwObjects': 0x170, 'rmVtable': 0x1688200, 'rmKind': 8, 'rmKindMaterial': 7, 'rmPropCount': 0x28,
                'rmProps': 0x30, 'rmHandleCount': 0x40, 'rmHandles': 0x48, 'rmShader': 0x58, 'rmTemplate': 0x60,
                'imageProperty': 0x3AA8B87E, 'maxProps': 16},
            # UI sounds (research uiSound): the game's world context, its Game World and that world's WwiseWorld; the
            # native events by key, Wwise id, and a name whose FNV-1 hash is that id (the event's own name is not in the
            # game data) or the event's real name.
            'uiSound': {'context': 0x3326340, 'world': 0x10E8, 'wwiseWorld': 0x10F8, 'events': {
                'stratagem_pick': {'key': 0xBE9303B7, 'id': 0x6A84A787, 'name': 'hd2runtime_u64dawv',
                    'label': 'a stratagem picked (a card accepted in the stratagem grid)'},
                'picker_close': {'key': 0x97753411, 'id': 0x0DBB2A14, 'name': 'hd2runtime_bci6lee',
                    'label': 'the picker closing (a pick filling the last slot; Back)'},
                'slot_select': {'key': 0xA31D0645, 'id': 0x3C38FC71, 'name': 'hd2runtime_bgj4s6o',
                    'label': 'a loadout slot selected (the stratagem grid opening)'},
                'generic_select': {'name': 'ui_generic_select', 'label': 'ui_generic_select (by its real name)'},
                'item_hover_select': {'name': 'ui_armory_item_hover_select',
                    'label': 'ui_armory_item_hover_select (by its real name)'}}},
            # The game's own selection close (research selectorClose): the close handler (ui), the exact bytes re-proved
            # right before the call (its prologue through the selection-open byte cleared), and what it leaves at once.
            'selectorClose': {'rva': 0x146F3B0, 'prologue': PROLOGUE_CLOSE, 'subStateAfter': 0, 'rowCountAfter': 0,
                'cardCountAfter': 0},
            # Slot icon overlays (research slotOverlay, worldOrder): an element's primitive id and effective alpha; the
            # game context's Ui World; the engine's world array (Application.worlds' order); the mission HUD chain; the
            # overlay layer (above the native slot parts 12-16 and the HUD's 557, below 950).
            'slotOverlay': {'primitive': 0x110, 'alpha': 0x54, 'layer': 0xBC, 'gameContext': 0x3326340, 'uiWorld': 0x1118,
                'gameMode': 0xAC21C, 'missionHudMode': 4, 'hudRoot': 0x346D538, 'hudList': 0x24E340 + 0x146DC0,
                'entries': 0x1150, 'entryStride': 0x3760, 'entrySlot': 0x3748, 'widget': 0x7C0, 'widgetType': 0x14C8,
                'hudIcon': 0x518, 'hudEntries': 16, 'application': 0x1A10208, 'worldCount': 0x590,
                'worldArray': 0x598, 'shipIconLayer': 14, 'hudIconLayer': 557, 'overlayLayer': 940, 'maxLayer': 1023,
                # The native slot's icon background (research slotBackground): the grey box (widget + background, kind
                # 5, layer 12) and its effective colour (+0x54: a, r, g, b); the tint sprite element above it (layer 13).
                'background': 0x110, 'backgroundLayer': 12, 'backgroundGrey': 36, 'effectiveColour': 0x54,
                'tint': 0x228, 'tintLayer': 13, 'tintSprite': '0x6E6A67B944661E66', 'hudOverlayLayer': 940},
            # A slot widget's icon element (widget + element) and the image-element fields the image setter writes.
            # The icon shader's mask colours as the native loadout slot sets them (c0 from the colour set table, c1 and
            # c2 constants; c3 is never set), and the shader variable names.
            'iconColours': {'table': COLOUR_TABLE, 'stride': 16, 'sets': 5, 'c1': COLOUR_WHITE, 'c2': COLOUR_SHADOW,
                'variables': ['c0', 'c1', 'c2', 'c3']},
            'slotIcon': {'element': 0x380, 'flags': 0, 'kindShift': 18, 'kindMask': 0xF, 'imageKind': 3, 'dirty': 2,
                'childDirty': 8, 'parent': 0xF0, 'scene': 0xF8, 'primitive': 0x110, 'base': 0x114, 'uv': 0x124,
                'rect': 0x134, 'material': 0x148, 'name': 0x150, 'spritePage': 8, 'spriteRect': 0x18,
                'maxAncestors': 32},
            'grid': {'list': 0xD2F20, 'rowCount': 0x91F14, 'rowCards': 0x92318, 'cardCount': 0x92984,
                'sections': 0x92748, 'sectionFirstRow': 0x9274C, 'firstRealizedRow': 0x928D8, 'realizedRows': 0x91F0C,
                'rowWidgetStride': 0xAED0, 'rowRealizedCards': 0xB9B4, 'cardWidget': 0xC10, 'cardWidgetStride': 0x2B68,
                'cardsPerRow': 4, 'element': {'size': 0x24, 'm00': 0x64, 'm02': 0x6C, 'm20': 0x84, 'm22': 0x8C,
                    'tx': 0x94, 'ty': 0x9C},
                'card': {'size': 80, 'inner': 68, 'icon': 51},
                'scroll': {'rowHeights': 0x91F18, 'content': 0x92968, 'offset': 0x92960, 'limit': 0x8C0,
                    'scrolls': 0x928F9, 'sectionIds': 0x92854, 'viewport': 528, 'padding': 20, 'cell': 80, 'gap': 5,
                    'frame': [395, 528]}},
            'inputActions': {'ownerGlobal': G_INPUT_OWNER, 'states': 0x328, 'stride': 32, 'groupActions': 97,
                'groups': 13, 'menu': {'group': 0, 'up': 1, 'down': 2, 'right': 3, 'left': 4, 'back': 9, 'select': 10}},
            'font': FONT,
            'render': {'cameraUnit': CAMERA_UNIT, 'unitType': '0x%016X' % UNIT_TYPE, 'shading': SHADING,
                'shadingType': '0x%016X' % SHADING_TYPE, 'overlayViewport': 'overlay', 'provenLayers': 999,
                'experimentalLayers': [2000, 10000]}},
        'renderConfig': config,
        'iconShader': icon_shader(),
        'determinations': {
            'runtimeUi': ('Possible only through the engine\'s own Lua scripting API (World.create_screen_gui, '
                'Gui.rect/bitmap/text, Application.main_world): no data-only path puts pixels on screen. The native '
                'cards bind their materials in native code, and XAML is reachable from C++ only. Whether that API '
                'counts as a native call is the user\'s decision; it is not an FFI call into game code.'),
            'whereItAppears': ('Application.main_world is the Game World (all worlds rendered in a frame tie on the render '
                'stamp; the most units wins): a screen GUI there is under the whole UI composite and visible only where '
                'the UI target is transparent (the custom panel beside the details panel). The loadout screen and the '
                'mission HUD are screen GUIs of the Ui World (worlds()[2]).'),
            'customResources': ('The card\'s icon is the Runtime image\'s own GUI material, by name (the lookup it '
                'was proven against); the name and description are the Runtime text\'s strings, drawn in the engine '
                'font core/performance_hud/monaco (resident in every snapshot).'),
            'input': ('Device-independent menu actions are readable as data, but the native grid reacts to the same '
                'actions and no input can be consumed without a hook: the first proof uses Runtime keybinds on keys '
                'the loadout screen leaves unbound.'),
            'selectionState': ('The local record (ui+0x10+[ui+0x27D0]*0x9F0) is what the save, sync_loadout and the '
                'mission record read; the slot widgets mirror it and are rebuilt into it on every pick.'),
            'selectionWrite': ('One entry {type, uses} in the record (plus the count for a new slot) and the panel\'s '
                'cached record pointer cleared: the game\'s own per-frame bind then repaints the four widgets from the '
                'record, so a later rebuild from the widgets keeps the entry. No native call.'),
            'persistence': ('sync_loadout (launch) and on_exit (after ready) save the record into the save store as '
                '{stable id, uses} pairs in order; no ownership check at save, sync or restore.'),
            'network': ('A pick also sends a per-slot message to peers; a direct write does not. sync_loadout sends '
                'the whole loadout at launch. Solo only.'),
            'renderOrder': ('A screen GUI is drawn in its world\'s transparent passes; its z layer orders primitives '
                'inside that GUI only. The game draws its UI world through hud_world_ui_and_composite_layer: the '
                'transparent passes, then the Noesis UI into the same ui_target, then the composite over the game image '
                'into the back buffer. A GUI in the UI world is therefore always under the Noesis UI, and a GUI in the '
                'game world is under the whole UI target. The overlay viewport draws into the back buffer directly, but '
                'a script world is rendered from the Lua callbacks, which the engine runs before the game\'s render '
                'callback in the same frame, so the UI composite then rewrites the back buffer. No create_screen_gui '
                'option selects a stage. Unproven offline: what the composite shader does with last_back_buffer.'),
            'selectionLifecycle': ('The selection is open exactly while ui+0x273990 is set (open and close '
                'handlers only). The sub-state 10 means a stratagem slot is FOCUSED: it stays 10 after a pick or Back '
                'while the slot keeps the focus, and the edited slot is -1 before the first selection. A Runtime UI for '
                'choosing a stratagem must require the selection byte, sub-state 10 and an edited slot of 0-3.'),
            'detailsPanel': ('The native details panel is the GUI element at ui+0x24B520, 1024 x 400 units for a '
                'stratagem; its screen rectangle is read like a card\'s. The custom panel goes to its right.'),
            'bitmapContract': ('Gui.bitmap / bitmap_uv draw a MATERIAL resource named by a string or IdString64 (never a '
                'texture or sprite), through a per-GUI material instance; a Runtime image provides exactly that (its GUI '
                'icon material). Whether that material\'s shader draws the picture visibly in a screen GUI is not '
                'decidable offline: the 0.3.0 card drew one visibly; the 0.1.0 and 0.2.0 tiles drew theirs blank.'),
            'mouse': ('The engine Mouse cursor axis is the device\'s stored integer position; whether its y is flipped is '
                'not established offline. The Runtime input module reads the OS cursor (client pixels, top-left origin) '
                'and the left button; the panel converts to GUI pixels (bottom-left origin) itself. Nothing is consumed: '
                'the game still receives every click.'),
            'iconShader': ('The icon material\'s shader (template 0x3461FF0D, library 0x8CDE642487327D4E) treats the '
                'texture\'s R, G, B and A as masks coloured by four material variables c0-c3 (strength, r, g, b). The '
                'material declares none, so they are zero and every texel is transparent: Gui.bitmap draws the quad but '
                'no pixel shows. The native loadout slot sets c0 (the category colour), c1 (white) and c2 (a 20 % '
                'shadow) on its own material copy; a Runtime GUI does the same through Gui.material and '
                'Material.set_vector4, the exposed Lua API. A picture keeps its shapes but is drawn as masks in those '
                'colours (red parts in the category colour, green parts white, blue parts shadow); a true-colour picture '
                'would need another material template (a separate Runtime resource type).'),
            'cardLook': ('The native card\'s background, border and inner frame are sized elements with no image; its one '
                'image is the focus bracket, an atlas sprite on a single-channel UI page that no nameable GUI material '
                'samples. The Runtime tile is drawn with rectangles in the native proportions (80 / 68 / 51 units) and '
                'its focus with four corner brackets measured from that sprite (arms 15/80, 3/80 thick).'),
            'selectionAdvance': ('One u32 write of the edited slot ui+0x281C moves the open selection on to the next '
                'empty slot (the next pick lands there; nothing reads it each frame). The native focus highlight and '
                'the grid\'s greying are applied only inside native calls and stay as they were; the Runtime\'s cleared '
                'cached record pointer moves the focus to slot 0 (the repaint\'s first-bind branch).'),
            'selectionClose': ('Not possible by data: the close handler slides the panels back with pool tweens '
                '(0x189E2F0, its latch read per frame only as a parameter), clears the list (releasing handles) and fades '
                'the grid with a tween; none has a per-frame consumer, and the only per-frame paths that close it are '
                'launch and deploy. A partial data close leaves the grid drawn and frozen, and Back would then leave the '
                'screen. The Back action cannot be injected as data (rebuilt from the devices every frame). The game\'s '
                'own close handler 0x146F3B0(ui) is what Back on a stratagem slot and a pick filling the last slot call, '
                'each after the picker-close sound: one argument (the loadout UI), no result. A narrow typed call of it '
                'from the main thread closes the selection exactly as Back does (selectorClose); its effect on screen '
                'needs a live test.'),
            'uiSound': ('The native selection flow posts the picker-close event when a pick fills the last slot (and on '
                'Back) and the slot-select event when the grid opens; the card list posts the pick event (key '
                '0xBE9303B7, event 0x6A84A787) for every pick, before the pick is applied; a pick that leaves an empty '
                'slot posts no other sound of its own (the panel transition after it may: its ids are data-driven and not '
                'read offline). The '
                'exposed Wwise Lua API posts any of these exactly, by a name whose FNV-1 hash is the event id, on the '
                'Game World\'s WwiseWorld. Which event the player hears as the selection sound needs a listening test.'),
            'slotOverlay': ('A Runtime screen GUI created in the Ui World (found by its index in the engine\'s world '
                'array) at a layer above the native slot parts draws over the native slot icons, ship and mission: all '
                'GUIs of a world are depth-sorted together by layer; Noesis stays above. Its quad follows the slot icon '
                'element\'s own size and transform and alpha. The native icon, material and texture are untouched. '
                'The backing plate is the native icon background\'s grey box (widget + 0x110, kind 5: a filled '
                'rectangle, layer 12) in its live effective colour, opaque, on the icon\'s quad; the category tint '
                'sprite above it (layer 13) is on a UI atlas page no GUI material can name and is not reproduced.'),
            'slotTexture': ('A custom texture in one native slot is not reachable through main-thread data: the texture '
                'a draw uses is the render-side material object\'s handle (R+0x48[k]), set only by render command 7 '
                'from a native bind. Writing it would be a write into render-thread memory read concurrently on every '
                'draw: not proven safe; the chain is probed read-only. The borrowed same-page icon stays the data-only '
                'option.'),
            'slotFocus': ('The native slot highlight follows the panel focus (P+0xD96C) and widget flag bit 1, drawn only '
                'when the widget visual update 0x18932F0 runs. Its data path: the focus and previous focus, bit 1 on '
                'both widgets, then the frame-flash byte +0x12A0 on both, which the panel update consumes every frame in '
                'panel mode 0 by calling 0x18932F0 itself when the frame has no colour tween. No native call by the '
                'Runtime; the game redraws both widgets from their flags.'),
            'slotIcon': ('Every repaint resets every slot\'s icon from its type. One slot can show another icon ON THE '
                'SAME ATLAS PAGE by data, as the image setter leaves it: the sprite rectangle (+0x134), the UV (+0x124) '
                'and the dirty bits (element bit 1, ancestors bit 3); it must be re-applied after each repaint. A '
                'custom image (a texture of its own) needs the texture bind, an engine call: blocked under the '
                'no-native-call rule. No StratagemInfo field changes; another slot of the same type keeps its icon.'),
            'identity': ('The save keeps only {stable id, uses} in order: the virtual entry is reconstructed from a '
                'Runtime-owned local record (definition id, slot index, the token\'s stable id and the loadout\'s '
                'pairs at the time), checked against the saved order; no save-format extension.')},
        'conclusion': ('A Runtime-owned selector is possible if the engine\'s Lua GUI API is acceptable: a screen GUI '
            'card with the Runtime icon and text, shown while the grid is open, selected by Runtime keybinds. A pick '
            'can be written as data into the record the game itself saves, with the game\'s own per-frame repaint '
            'updating the slots. Unproven offline: that the screen GUI is drawn over the loadout screen, and the '
            'repaint\'s side effects. Solo only. Render order: through the exposed Lua API a Runtime screen GUI '
            'cannot be drawn above the native Noesis UI (the UI world draws Noesis after every world GUI, and no script '
            'world can be rendered after the UI composite); the development render-order probe tests this live.')}
    events = {'0x%08X' % e['key']: '0x%08X' % e['id'] for e in result['layout']['uiSound']['events'].values()
        if 'key' in e}
    if set(events) != {'0x%08X' % k for k in UI_SOUND_KEYS} or any(v['uiSoundRemap'] != events
            for v in evidence.values()):
        raise ValueError('a UI sound key does not remap to its event id: %r' % {k: v['uiSoundRemap']
            for k, v in evidence.items()})
    if game.data[PROLOGUE_RVA:PROLOGUE_RVA + len(bytes.fromhex(PROLOGUE_CLOSE))].hex() != PROLOGUE_CLOSE:
        raise ValueError('the close handler prologue changed')
    OUTPUT.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('wrote', OUTPUT.relative_to(ROOT), '; pins', len(flat_exe) + len(flat_game), '; snapshots with mismatches',
        sum(1 for v in relocation.values() if v), '; font resident in',
        sum(1 for v in evidence.values() if v['font'] == 'present' and v['fontMaterial'] == 'present'))


if __name__ == '__main__':
    main()
