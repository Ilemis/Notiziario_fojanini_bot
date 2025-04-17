import os, json, requests
from bs4 import BeautifulSoup
from flask import Flask

app = Flask(__name__)

# Parametri da impostare come variabili d’ambiente su Render
TOKEN = os.environ['TELEGRAM_TOKEN']
CHAT_ID = os.environ['TELEGRAM_CHAT_ID']
STATE_FILE = 'state.json'
URL = 'https://www.fondazionefojanini.it/blog/notiziaritecnici/'

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {'sent': []}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

def fetch_pdfs():
    r = requests.get(URL)
    soup = BeautifulSoup(r.text, 'html.parser')
    pdfs = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.lower().endswith('.pdf'):
            full_url = requests.compat.urljoin(URL, href)
            title = a.get_text(strip=True) or os.path.basename(href)
            pdfs.append({'url': full_url, 'title': title})
    # rimuove duplicati mantenendo l’ordine
    seen = set(); unique = []
    for p in pdfs:
        if p['url'] not in seen:
            seen.add(p['url']); unique.append(p)
    return unique

def send_pdf(pdf):
    # Scarica il PDF
    r = requests.get(pdf['url'])
    files = {
        'document': (pdf['title'] + '.pdf', r.content)
    }
    data = {
        'chat_id': CHAT_ID,
        'caption': pdf['title']  # qui mettiamo il titolo come didascalia
    }
    resp = requests.post(
        f'https://api.telegram.org/bot{TOKEN}/sendDocument',
        data=data,
        files=files
    )
    return resp.ok


@app.route('/', methods=['GET'])
def check_new():
    state = load_state()
    sent = state.get('sent', [])
    pdfs = fetch_pdfs()
    new = [p for p in pdfs if p['url'] not in sent]
    for pdf in new:
        if send_pdf(pdf):
            sent.append(pdf['url'])
    state['sent'] = sent
    save_state(state)
    return 'OK', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
