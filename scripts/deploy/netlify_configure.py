"""Configure this one Netlify project using the existing local CLI login.

Never prints the credential or environment values. No unrelated DNS is changed.
"""
import json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / '.netlify' / 'state.json'
DOMAIN = 'nivra.tanishq.work'
ACCOUNT = 'taniagg9910922265'
ZONE = '6a520df3cfd6d9db53df781f'


def credential():
    cfg = json.loads((Path.home()/'Library'/'Preferences'/'netlify'/'config.json').read_text())
    user = cfg['users'][cfg['userId']]
    auth = user['auth']
    return auth['token'] if isinstance(auth, dict) else auth


def api(path, method='GET', data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = Request('https://api.netlify.com/api/v1/'+path, data=body, method=method,
                  headers={'Authorization':'Bearer '+credential(), 'Content-Type':'application/json'})
    with urlopen(req, timeout=40) as response:
        raw = response.read()
        return json.loads(raw) if raw else None


def configure():
    if CONFIG.exists():
        site = api('sites/'+json.loads(CONFIG.read_text())['siteId'])
    else:
        sites = api('sites?per_page=100')
        site = next((s for s in sites if s.get('custom_domain') == DOMAIN), None)
        if site is None:
            site = api(ACCOUNT+'/sites', 'POST', {'name':'nivra-tanishq', 'custom_domain':DOMAIN, 'force_ssl':True})
        CONFIG.parent.mkdir(exist_ok=True)
        CONFIG.write_text(json.dumps({'siteId':site['id']}, indent=2)+'\n')
    if site.get('custom_domain') != DOMAIN:
        raise RuntimeError('Linked Netlify project belongs to another domain. No changes made.')
    records = api('dns_zones/'+ZONE+'/dns_records')
    target = site['name']+'.netlify.app'
    existing = [r for r in records if r.get('hostname','').rstrip('.') == DOMAIN]
    if not existing:
        api('dns_zones/'+ZONE+'/dns_records', 'POST', {'type':'CNAME','hostname':DOMAIN,'value':target,'ttl':300})
    elif not all(r.get('type') in ('NETLIFY','NETLIFYv6') or (r.get('type')=='CNAME' and r.get('value','').rstrip('.')==target) for r in existing):
        raise RuntimeError('Existing NIVRA DNS points elsewhere. No DNS records replaced.')
    print(json.dumps({'siteId':site['id'],'name':site['name'],'domain':DOMAIN,'accountId':site['account_id']}))
    return site


if __name__ == '__main__': configure()
