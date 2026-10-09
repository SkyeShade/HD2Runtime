# GameFontTextProof

Development proof for the HD2Runtime 0.30.4 game-font text in mod windows (docs/ui-overlay.md, "Other scripts").
Needs the game-fonts development runtime built with it. A window at the top left shows:

| line | drawn in |
|---|---|
| Latin: HELLDIVERS 2 - Super Earth, café façade | FS Sinclair |
| Polski: zażółć gęślą jaźń | FS Sinclair + the game's Latin set (ż ó ł ć ę ś ą ź ń) |
| 简体中文：模组窗口测试 | the game's Simplified Chinese font |
| 繁體中文：模組視窗測試 | the game's Traditional Chinese font |
| 日本語：モッドのウィンドウ表示テスト | the game's Japanese font |
| 한국어: 모드 창 테스트입니다 | the game's Korean font |
| Русский: окно мода, проверка шрифта | the game's Russian font |

and a Chinese paragraph wrapped into lines between characters. 0.2.0: in ANY game language, every line should draw a
second or two after the window opens (the Runtime loads the font package a line needs; each shows `?` until then;
the log says `ui fonts: loading the game's ... font package` once per font). Ctrl+F7 shows / hides the window, Ctrl+F8
logs its state again. The log lists, per line, every run and the font it used, `can_draw`, and which game fonts are
loaded. Nothing of the game is written.

Report, per language tried: which lines are readable, which show `?`, whether each line sits on one baseline with its
Latin part, and whether switching the language with the window open works without a crash.
