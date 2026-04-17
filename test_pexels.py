import urllib.request, os, json
import dotenv; dotenv.load_dotenv()
key = os.environ.get('PEXELS_API_KEY','')
print('Key present:', bool(key), '| Preview:', key[:12] + '...')
req = urllib.request.Request(
    'https://api.pexels.com/v1/search?query=coffee&per_page=2',
    headers={'Authorization': key}
)
try:
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read())
        print('Pexels OK! Total results:', data.get('total_results'))
        if data.get('photos'):
            print('First photo:', data['photos'][0]['src']['large'][:60])
except urllib.error.HTTPError as e:
    print('HTTP Error:', e.code, e.reason)
    print('Body:', e.read().decode()[:200])
except Exception as e:
    print('Error:', type(e).__name__, e)
