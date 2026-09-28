local hd2=require('mods/skyeshade/hd2runtime')
-- Recreates Exosuit Unlimited Uses v2: every Exosuit call-in keeps its cooldown but loses the
-- three-use mission limit. 'unlimited' is the game's own unlimited value (the one the FRVs use).
local operations={}
for _,name in ipairs({'EXO-45 Patriot Exosuit','EXO-49 Emancipator Exosuit','EXO-55 Breakthrough Exosuit',
    'EXO-51 Lumberer Exosuit'})do
    operations[#operations+1]={id=name:match('^(EXO%-%d+)'):lower(),target=hd2.stratagem(name),
        field=hd2.fields.stratagem.max_uses,expect=3,value='unlimited'}
end
return hd2.ensure({plan={id='exosuit-unlimited-uses',operations=operations}})
