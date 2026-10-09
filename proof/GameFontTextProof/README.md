# GameFontTextProof

Development proof for the HD2Runtime 0.30.4 game-font text in mod windows (docs/ui-overlay.md, "Other scripts").
Needs the game-fonts development runtime built with it. A window at the top left shows:

| line | drawn in | needs the game language |
|---|---|---|
| Latin: HELLDIVERS 2 - Super Earth, café façade | FS Sinclair | any |
| Polski: zażółć gęślą jaźń | FS Sinclair + the game's Latin set (ż ó ł ć ę ś ą ź ń) | a European language (English is fine) |
| 简体中文：模组窗口测试 | the game's Simplified Chinese font | Simplified Chinese |
| 繁體中文：模組視窗測試 | the game's Traditional Chinese font | Traditional Chinese |
| 日本語：モッドのウィンドウ表示テスト | the game's Japanese font | Japanese |
| 한국어: 모드 창 테스트입니다 | the game's Korean font | Korean |
| Русский: окно мода, проверка шрифта | the game's Russian font | Russian |

and a Chinese paragraph wrapped into lines between characters. In any other language a line shows `?` where its
font is not loaded (as before 0.30.4). Ctrl+F7 shows / hides the window, Ctrl+F8 logs its state again. The log lists,
per line, every run and the font it used, `can_draw`, and which game fonts are loaded. Nothing of the game is written.

Report, per language tried: which lines are readable, which show `?`, whether each line sits on one baseline with its
Latin part, and whether switching the language with the window open works without a crash.
