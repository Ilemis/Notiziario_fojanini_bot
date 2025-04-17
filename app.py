import os
import json
import requests
from bs4 import BeautifulSoup
from flask import Flask

app = Flask(__name__)

# Variabili d'ambiente da impostare su Render
TOKEN = os.environ['TELEGRAM_TOKEN']
CHAT_ID = os.environ['TELEGRAM_CHAT_ID']
STATE_FILE = 'state.json'
URL = 'https://www.fondazionefojanini.it/blog/notiziaritecnici/'

def load_state():
    """
    Carica lo stato dal file JSON se esiste, altrimenti restituisce uno stato vuoto.
    """
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {'sent': []}

def save_state(state):
    """
    Salva lo stato corrente nel file JSON.
    """
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

def fetch_pdfs():
    """
    Recupera tutti i link ai PDF dalla pagina e restituisce una lista di dizionari con URL e titolo.
    """
    r = requests.get(URL)
    soup = BeautifulSoup(r.text, 'html.parser')
    pdfs = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.lower().endswith('.pdf'):
            full_url = requests.compat.urljoin(URL, href)
            title = a.get_text(strip=True) or os.path.basename(href)
            pdfs.append({'url': full_url, 'title': title})
    # Rimuove duplicati mantenendo l'ordine
    seen = set()
    unique = []
    for p in pdfs:
        if p['url'] not in seen:
            seen.add(p['url'])
            unique.append(p)
    return unique

def send_pdf(pdf):
    """
    Scarica il PDF e lo invia su Telegram con il titolo come didascalia.
    """
    r = requests.get(pdf['url'])
    files = {
        'document': (pdf['title'] + '.pdf', r.content)
    }
    data = {
        'chat_id': CHAT_ID,
        'caption': pdf['title']
    }
    resp = requests.post(
        f'https://api.telegram.org/bot{TOKEN}/sendDocument',
        data=data,
        files=files
    )
    return resp.ok

def send_info_message(message):
    """
    Invia un messaggio di testo su Telegram.
    """
    data = {
        'chat_id': CHAT_ID,
        'text': message
    }
    resp = requests.post(
        f'https://api.telegram.org/bot{TOKEN}/sendMessage',
        data=data
    )
    return resp.ok

@app.route('/', methods=['GET'])
def check_new():
    """
    Endpoint principale che controlla la presenza di nuovi PDF e li invia su Telegram.
    """
    state = load_state()
    sent = state.get('sent', [])
    pdfs = fetch_pdfs()
    new = [p for p in pdfs if p['url'] not in sent]
    if new:
        for pdf in new:
            if send_pdf(pdf):
                sent.append(pdf['url'])
        state['sent'] = sent
        save_state(state)
    else:
        send_info_message("Nessun nuovo PDF trovato negli ultimi 12 ore.")
    return 'OK', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
