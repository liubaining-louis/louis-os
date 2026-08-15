#!/usr/bin/env python3
from __future__ import annotations
import csv, json, sys
from pathlib import Path

repo = Path(sys.argv[1])
net = repo / 'listings' / 'specific-networks' / 'algorand'
providers_path = repo / 'references' / 'providers' / 'providers.csv'
offers_dir = repo / 'references' / 'offers'

# Build offer slug -> provider from canonical offer files.
offer_provider = {}
for p in offers_dir.glob('*.csv'):
    try:
        with p.open(newline='', encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                slug=(row.get('slug') or '').strip()
                provider=(row.get('provider') or '').strip()
                if slug and provider:
                    offer_provider[slug]=provider
    except Exception:
        pass

used_names=set()
usage=[]
for p in net.glob('*.csv'):
    with p.open(newline='', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            provider=(row.get('provider') or '').strip()
            offer=(row.get('offer') or '').strip()
            if not provider and offer.startswith('!offer:'):
                provider=offer_provider.get(offer.split(':',1)[1], '')
            if provider:
                used_names.add(provider.casefold())
                usage.append({'file':p.name,'slug':row.get('slug'),'provider':provider,'offer':offer})

providers=[]
fields=['description','website','docs','x','github','discord','telegram','linkedin','supportEmail']
with providers_path.open(newline='', encoding='utf-8-sig') as f:
    for row in csv.DictReader(f):
        name=(row.get('name') or '').strip()
        slug=(row.get('slug') or '').strip()
        if name.casefold() in used_names or slug.casefold() in used_names:
            missing=[k for k in fields if not (row.get(k) or '').strip()]
            providers.append({
                'slug':slug,'name':name,'missing_count':len(missing),'missing':missing,
                'current':{k:row.get(k,'') for k in fields},
                'used_in':sorted({x['file'] for x in usage if x['provider'].casefold() in {name.casefold(),slug.casefold()}}),
            })
providers.sort(key=lambda x:(-x['missing_count'],x['slug']))
print(json.dumps({'network':'algorand','used_provider_count':len(providers),'providers':providers},indent=2,ensure_ascii=False))
