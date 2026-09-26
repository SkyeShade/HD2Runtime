local matcher=require('hd2runtime/primary_mapper/matcher')
local json=require('hd2runtime/primary_mapper/json')
local M={}
local strength={EXACT=4,STRONG=3,AMBIGUOUS=2,UNMATCHED=1}

local function evidence(match)
    local result={}
    for i,value in ipairs(match.matched)do result[i]=value end
    return result
end

function M.compose(raw,dataset,metadata)
    assert(raw.writes==0 and raw.protectionChanges==0 and raw.fixtureFallback=='disabled',
        'read-only invariant failed')
    local candidates,mapping={},{}
    for _,candidate in ipairs(raw.runtimeCandidates)do
        local ranked=matcher.rank(candidate.matchFields,dataset,5)
        candidate.status=ranked.status
        candidate.scoreMargin=ranked.scoreMargin
        candidate.rankedWikiMatches=ranked.rankedWikiMatches
        candidate.matchFields=nil
        candidate.diagnostics=json.array(candidate.diagnostics)
        candidate.attacks=json.array(candidate.attacks)
        for _,rank in ipairs(candidate.rankedWikiMatches)do
            rank.matched=json.array(rank.matched);rank.mismatched=json.array(rank.mismatched)
        end
        candidate.rankedWikiMatches=json.array(candidate.rankedWikiMatches)
        candidates[#candidates+1]=candidate
        local top=candidate.rankedWikiMatches[1]
        if top and (candidate.status=='EXACT'or candidate.status=='STRONG')then
            local current=mapping[top.name]
            local replacement={resourceHash=candidate.resourceHash,status=candidate.status,
                score=top.score,evidence=json.array(evidence(top))}
            if not current or strength[replacement.status]>strength[current.status]
                or replacement.status==current.status and replacement.score>current.score
                or replacement.status==current.status and replacement.score==current.score
                    and replacement.resourceHash<current.resourceHash then
                mapping[top.name]=replacement
            end
        end
    end
    table.sort(candidates,function(a,b)return a.resourceHash<b.resourceHash end)
    local report={schemaVersion=1,gameFingerprints=raw.fingerprint,
        hd2RuntimeVersion=metadata.version,mapperCommit=metadata.commit,wikiDataset={source=dataset.source,
            importedAt=dataset.imported_at,sourceSha256=dataset.source_sha256,
            summarySha256=dataset.summary_sha256,weaponCount=dataset.weapon_count},
        scanMetrics=raw.metrics,runtimeCandidates=json.array(candidates),
        fieldsCurrentlyUsable=json.array(raw.fieldsCurrentlyUsable),
        fieldsNotRuntimeMapped=json.array(raw.fieldsNotRuntimeMapped),
        stableSnapshot=raw.stableSnapshot,writes=0,protectionChanges=0,
        fixtureFallback='disabled',mode=raw.mode}
    return report,mapping
end

function M.log_lines(report)
    local lines={string.format('PRIMARY_WEAPON_MAP start wiki_weapons=%d runtime_candidates=%d',
        report.wikiDataset.weaponCount,report.scanMetrics.candidateCount)}
    for _,candidate in ipairs(report.runtimeCandidates)do
        lines[#lines+1]=string.format('PRIMARY_WEAPON_MAP resource=%s entity_row=%s status=%s resolution=%s',
            candidate.resourceHash,tostring(candidate.entityRow),candidate.status,candidate.resolutionStatus)
        for rank,match in ipairs(candidate.rankedWikiMatches)do
            lines[#lines+1]=string.format('PRIMARY_WEAPON_MAP resource=%s rank=%d wiki="%s" score=%d matched=%d mismatched=%d',
                candidate.resourceHash,rank,match.name,match.score,#match.matched,#match.mismatched)
        end
        for _,diagnostic in ipairs(candidate.diagnostics)do
            lines[#lines+1]='PRIMARY_WEAPON_MAP resource='..candidate.resourceHash..' diagnostic='..tostring(diagnostic):gsub('[\r\n]',' ')
        end
    end
    lines[#lines+1]=string.format('PRIMARY_WEAPON_MAP complete candidates=%d failures=%d writes=0 protection_changes=0 fixture_fallback=disabled',
        report.scanMetrics.candidateCount,report.scanMetrics.candidateFailures)
    return lines
end
return M
