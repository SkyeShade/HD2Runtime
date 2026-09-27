local matcher=require('hd2runtime/primary_mapper/matcher')
local json=require('hd2runtime/primary_mapper/json')
local M={}
local strength={EXACT=4,STRONG=3,AMBIGUOUS=2,UNMATCHED=1}

local function copy_array(values)
    local result={};for index,value in ipairs(values or{})do result[index]=value end
    return json.array(result)
end
local function public_match(match)
    return {name=match.name,slot=match.slot,category=match.category,score=match.score,
        matched=copy_array(match.matched),mismatched=copy_array(match.mismatched),
        unresolvedFields=copy_array(match.unresolvedFields),compared=match.compared,
        highValueMatches=match.highValueMatches,highValueMismatches=match.highValueMismatches,
        structurallyCompatible=match.structurallyCompatible,compatibleAttackKind=match.compatibleAttackKind,
        compatibleWeaponSlot=match.compatibleWeaponSlot,
        matchedAttackBranch=match.matchedAttackBranch,matchedDamageBranch=match.matchedDamageBranch,
        matchedProjectileBranch=match.matchedProjectileBranch,branchMode=match.branchMode,
        runtimeAttackIndex=match.runtimeAttackIndex,runtimeAttackRole=match.runtimeAttackRole,
        incompatibility=match.incompatibility,credible=match.credible==true}
end
local function candidate_match(candidate,match)
    return {resourceHash=candidate.resourceHash,entityRow=candidate.entityRow,
        candidateStatus=candidate.status,score=match.score,
        matchedAttackBranch=match.matchedAttackBranch,
        matchedDamageBranch=match.matchedDamageBranch,
        matchedProjectileBranch=match.matchedProjectileBranch,branchMode=match.branchMode,
        runtimeAttackIndex=match.runtimeAttackIndex,runtimeAttackRole=match.runtimeAttackRole,
        matched=copy_array(match.matched),mismatched=copy_array(match.mismatched),
        unresolvedFields=copy_array(match.unresolvedFields),
        projectileType=candidate.resolvedFields.projectile_type and candidate.resolvedFields.projectile_type.value,
        damageType=candidate.resolvedFields.damage_type and candidate.resolvedFields.damage_type.value,
        crosshairType=candidate.resolvedFields.crosshair_type and candidate.resolvedFields.crosshair_type.value,
        weaponSlot=candidate.resolvedFields.weapon_slot and candidate.resolvedFields.weapon_slot.value,
        capacity=candidate.resolvedFields.capacity and candidate.resolvedFields.capacity.value,
        implementationFamilies=copy_array(candidate.implementationFamilies)}
end
local function catalog_families(weapon)
    local found,result={},{}
    local function add(value)if not found[value]then found[value]=true;result[#result+1]=value end end
    if tostring(weapon.category):lower():find('shotgun',1,true)then add('shotgun/feed_variants')end
    for _,attack in ipairs(weapon.attacks or{})do
        local family=({Beam='beam',Arc='arc',Spray='spray/flame',Melee='melee',
            Projectile='conventional_projectile'})[attack.kind]
        if family then add(family)end
    end
    if #result==0 then add('special/non_damaging')end
    return result
end
local function candidate_before(a,b)
    if a.score~=b.score then return a.score>b.score end
    if strength[a.candidateStatus]~=strength[b.candidateStatus]then
        return strength[a.candidateStatus]>strength[b.candidateStatus]
    end
    return a.resourceHash<b.resourceHash
end
local function catalog_entry(weapon,matches,partials)
    table.sort(matches,candidate_before)
    table.sort(partials,candidate_before)
    local best=matches[1];local competing={}
    for index=2,#matches do competing[#competing+1]=matches[index]end
    local resolution,status='UNRESOLVED','UNMATCHED'
    if #matches==1 then
        status=best.candidateStatus
        resolution=(status=='EXACT'or status=='STRONG')and'UNIQUE'or'AMBIGUOUS'
    elseif #matches>1 then resolution='DUPLICATE';status='AMBIGUOUS'
    elseif #partials>0 then resolution='AMBIGUOUS';status='AMBIGUOUS';best=partials[1]end
    return {name=weapon.name,slot=weapon.slot or'primary',category=weapon.category,
        runtimeCandidateMatches=#matches,resolution=resolution,status=status,
        bestCandidate=best,competingCandidates=json.array(competing),
        partialCandidates=json.array(partials),partialRuntimeCandidateMatches=#partials,
        scoreMargin=best and best.score-(competing[1]and competing[1].score or 0)or 0,
        duplicateRuntimeResources=#matches>1}
end
local function summary(dataset,catalog,candidates,status_counts)
    local unique_primary,unique_secondary=0,0
    local identified_primary,identified_secondary=0,0
    local duplicates,unresolved,multiple,partial,plasma={},{},{},{},{}
    local unresolved_families={}
    for _,candidate in ipairs(candidates)do
        if candidate.status=='AMBIGUOUS'then partial[#partial+1]=candidate.resourceHash end
        if #candidate.credibleWikiIdentities>1 then
            multiple[#multiple+1]={resourceHash=candidate.resourceHash,
                identities=copy_array(candidate.credibleWikiIdentities),scoreMargin=candidate.scoreMargin}
        end
    end
    for _,weapon in ipairs(dataset.weapons)do
        local entry=catalog[weapon.name]
        if entry.resolution=='UNIQUE'then
            if entry.slot=='secondary'then unique_secondary=unique_secondary+1 else unique_primary=unique_primary+1 end
            if entry.slot=='secondary'then identified_secondary=identified_secondary+1 else identified_primary=identified_primary+1 end
        elseif entry.resolution=='DUPLICATE'then
            if entry.slot=='secondary'then identified_secondary=identified_secondary+1 else identified_primary=identified_primary+1 end
            local resources={entry.bestCandidate.resourceHash}
            for _,value in ipairs(entry.competingCandidates)do resources[#resources+1]=value.resourceHash end
            duplicates[#duplicates+1]={name=entry.name,slot=entry.slot,resources=json.array(resources)}
        elseif entry.resolution=='UNRESOLVED'or entry.resolution=='AMBIGUOUS'then
            local families=catalog_families(weapon)
            unresolved[#unresolved+1]={name=entry.name,slot=entry.slot,category=entry.category,
                likelyImplementationFamilies=copy_array(families),
                reason=entry.resolution=='AMBIGUOUS'and'partial candidates exist but none is uniquely credible'
                    or'no credible structurally compatible runtime candidate'}
            for _,family in ipairs(families)do
                local values=unresolved_families[family]or{};values[#values+1]=entry.name
                unresolved_families[family]=values
            end
        end
        if entry.name:match('^PLAS%-')then
            plasma[#plasma+1]={name=entry.name,slot=entry.slot,resolution=entry.resolution,
                runtimeCandidateMatches=entry.runtimeCandidateMatches,bestCandidate=entry.bestCandidate}
        end
    end
    table.sort(duplicates,function(a,b)return a.name<b.name end)
    table.sort(unresolved,function(a,b)return a.name<b.name end)
    table.sort(multiple,function(a,b)return a.resourceHash<b.resourceHash end)
    table.sort(partial);table.sort(plasma,function(a,b)return a.name<b.name end)
    return {catalogWeapons=dataset.weapon_count,
        primaryCatalogWeapons=dataset.slot_counts and dataset.slot_counts.primary or dataset.weapon_count,
        secondaryCatalogWeapons=dataset.slot_counts and dataset.slot_counts.secondary or 0,
        primariesResolvedUnique=unique_primary,secondariesResolvedUnique=unique_secondary,
        totalUniqueResolved=unique_primary+unique_secondary,statusCounts=status_counts,
        primaryIdentitiesResolved=identified_primary,secondaryIdentitiesResolved=identified_secondary,
        totalIdentitiesResolved=identified_primary+identified_secondary,
        partialRuntimeCandidateCount=#partial,partialRuntimeCandidates=json.array(partial),
        duplicateIdentityGroups=json.array(duplicates),unresolvedCatalogWeapons=json.array(unresolved),
        unresolvedImplementationFamilies=unresolved_families,
        runtimeCandidatesMatchingMultipleCatalogWeapons=json.array(multiple),
        plasmaFamilySpecificFindings=json.array(plasma),writes=0,protectionChanges=0,
        fixtureFallback='disabled'}
end

function M.compose(raw,dataset,metadata)
    assert(raw.writes==0 and raw.protectionChanges==0 and raw.fixtureFallback=='disabled',
        'read-only invariant failed')
    local candidates,by_weapon,partial_by_weapon={},{},{}
    for _,weapon in ipairs(dataset.weapons)do by_weapon[weapon.name]={};partial_by_weapon[weapon.name]={}end
    local status_counts={EXACT=0,STRONG=0,AMBIGUOUS=0,UNMATCHED=0}
    for _,candidate in ipairs(raw.runtimeCandidates)do
        candidate.matchFields.runtime_attacks=candidate.attacks
        candidate.matchFields.weapon_data_only=#candidate.attacks==0 and candidate.weaponData~=nil
        local ranked=matcher.rank(candidate.matchFields,dataset,8)
        candidate.status=ranked.status;candidate.scoreMargin=ranked.scoreMargin
        candidate.credibleWikiIdentities=copy_array(ranked.credibleWikiIdentities)
        status_counts[candidate.status]=status_counts[candidate.status]+1
        local visible={}
        for index,match in ipairs(ranked.rankedWikiMatches)do visible[index]=public_match(match)end
        candidate.rankedWikiMatches=json.array(visible)
        for _,match in ipairs(ranked.allWikiMatches)do
            if match.credible then
                local bucket=(candidate.status=='EXACT'or candidate.status=='STRONG')
                    and by_weapon[match.name]or partial_by_weapon[match.name]
                bucket[#bucket+1]=candidate_match(candidate,match)
            end
        end
        candidate.matchFields=nil
        candidate.diagnostics=copy_array(candidate.diagnostics);candidate.attacks=copy_array(candidate.attacks)
        candidate.playerWeaponEvidence=candidate.status=='EXACT'or candidate.status=='STRONG'
            and'LIKELY_PLAYER'or candidate.status=='AMBIGUOUS'and'PARTIAL'or'UNRESOLVED'
        candidates[#candidates+1]=candidate
    end
    table.sort(candidates,function(a,b)return a.resourceHash<b.resourceHash end)
    local mapping,catalog_list={},{}
    for _,weapon in ipairs(dataset.weapons)do
        local entry=catalog_entry(weapon,by_weapon[weapon.name],partial_by_weapon[weapon.name])
        mapping[weapon.name]=entry
        catalog_list[#catalog_list+1]=entry
    end
    table.sort(catalog_list,function(a,b)return a.name<b.name end)
    local identity_summary=summary(dataset,mapping,candidates,status_counts)
    identity_summary.gameFingerprints=raw.fingerprint
    identity_summary.hd2RuntimeVersion=metadata.version
    identity_summary.mapperCommit=metadata.commit
    identity_summary.mode=raw.mode
    identity_summary.runtimeCandidateCount=raw.metrics.candidateCount
    identity_summary.failedCandidateCount=raw.metrics.candidateFailures
    local report={schemaVersion=2,gameFingerprints=raw.fingerprint,
        hd2RuntimeVersion=metadata.version,mapperCommit=metadata.commit,wikiDataset={source=dataset.source,
            importedAt=dataset.imported_at,sourceSha256=dataset.source_sha256,
            summarySha256=dataset.summary_sha256,weaponCount=dataset.weapon_count,
            slotCounts=dataset.slot_counts,multiAttackWeaponCount=dataset.multi_attack_weapon_count},
        scanMetrics=raw.metrics,runtimeCandidates=json.array(candidates),
        catalogIdentities=json.array(catalog_list),identitySummary=identity_summary,
        fieldsCurrentlyUsable=copy_array(raw.fieldsCurrentlyUsable),
        fieldsNotRuntimeMapped=copy_array(raw.fieldsNotRuntimeMapped),
        stableSnapshot=raw.stableSnapshot,writes=0,protectionChanges=0,
        fixtureFallback='disabled',mode=raw.mode}
    return report,mapping,identity_summary
end

function M.log_lines(report)
    local lines={string.format('PLAYER_WEAPON_MAP start catalog_weapons=%d runtime_candidates=%d',
        report.wikiDataset.weaponCount,report.scanMetrics.candidateCount)}
    for _,candidate in ipairs(report.runtimeCandidates)do
        lines[#lines+1]=string.format('PLAYER_WEAPON_MAP resource=%s entity_row=%s status=%s resolution=%s',
            candidate.resourceHash,tostring(candidate.entityRow),candidate.status,candidate.resolutionStatus)
        for rank,match in ipairs(candidate.rankedWikiMatches)do
            lines[#lines+1]=string.format('PLAYER_WEAPON_MAP resource=%s rank=%d wiki="%s" score=%d damage_branch="%s" projectile_branch="%s" matched=%d mismatched=%d',
                candidate.resourceHash,rank,match.name,match.score,tostring(match.matchedDamageBranch),
                tostring(match.matchedProjectileBranch),#match.matched,#match.mismatched)
        end
        for _,diagnostic in ipairs(candidate.diagnostics)do
            lines[#lines+1]='PLAYER_WEAPON_MAP resource='..candidate.resourceHash..' diagnostic='..tostring(diagnostic):gsub('[\r\n]',' ')
        end
    end
    lines[#lines+1]=string.format('PLAYER_WEAPON_MAP complete candidates=%d failures=%d writes=0 protection_changes=0 fixture_fallback=disabled',
        report.scanMetrics.candidateCount,report.scanMetrics.candidateFailures)
    return lines
end
return M
