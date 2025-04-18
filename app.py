import os
import json
import requests
from bs4 import BeautifulSoup
from flask import Flask
import urllib.parse  # Import per gestire correttamente gli URL
from datetime import datetime  # Import per gestire orario e data

# Crea l'applicazione Flask
app = Flask(__name__)

# --- CONFIGURAZIONE ---
# Credenziali e impostazioni lette dalle variabili d'ambiente o valori di fallback
TOKEN = os.environ.get('TELEGRAM_TOKEN', 'YOUR_FALLBACK_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', 'YOUR_FALLBACK_CHAT_ID')
STATE_FILE = 'state.json'  # File per memorizzare gli URL già inviati
URL = 'https://www.fondazionefojanini.it/blog/notiziaritecnici/'  # Pagina da monitorare

# --- GESTIONE STATO (PDF Già Inviati + Ultima info) ---

def load_state():
    """Carica la lista degli URL dei PDF già inviati e l'ultima data di notifica informativa."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)
                # Verifica struttura base
                if isinstance(state, dict) and 'sent' in state and isinstance(state['sent'], list):
                    # Aggiunge last_info_date se manca
                    if 'last_info_date' not in state:
                        state['last_info_date'] = None
                    return state
        except (json.JSONDecodeError, IOError) as e:
            print(f"Errore lettura {STATE_FILE}: {e}. Inizializzo.")
    # Stato di default
    return {'sent': [], 'last_info_date': None}


def save_state(state):
    """Salva lo stato corrente (lista URL inviati + data ultima info) nel file STATE_FILE."""
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=4, ensure_ascii=False)
    except IOError as e:
        print(f"Errore salvataggio {STATE_FILE}: {e}")

# --- LOGICA DI SCRAPING E INVIO ---

def fetch_pdfs():
    """Recupera i link ai PDF dalla pagina URL, estraendo URL e nome file."""
    print(f"Recupero PDF da: {URL}")
    pdfs_found = []
    try:
        response = requests.get(URL, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        for link_tag in soup.find_all('a', href=True):
            href = link_tag['href']
            if href.lower().endswith('.pdf'):
                full_url = urllib.parse.urljoin(URL, href)
                # Estrae il nome file dall'URL (gestisce caratteri speciali)
                file_name = os.path.basename(urllib.parse.unquote(full_url))
                pdf_info = {'url': full_url, 'title': file_name}
                pdfs_found.append(pdf_info)

        # Rimuovi duplicati basati su URL
        seen_urls = set()
        unique_pdfs = [pdf for pdf in pdfs_found if pdf['url'] not in seen_urls and not seen_urls.add(pdf['url'])]

        print(f"Trovati {len(unique_pdfs)} PDF unici.")
        return unique_pdfs

    except requests.exceptions.RequestException as e:
        print(f"Errore durante il recupero della pagina {URL}: {e}")
        return []
    except Exception as e:
        print(f"Errore imprevisto durante analisi pagina: {e}")
        return []


def send_pdf(pdf_info):
    """Scarica un PDF e lo invia a Telegram con il nome file corretto e una didascalia pulita."""
    print(f"Tentativo invio PDF: {pdf_info['title']}")
    try:
        response = requests.get(pdf_info['url'], timeout=60)
        response.raise_for_status()

        file_name_with_ext = pdf_info['title']
        # Prepara didascalia (rimuove estensione, sostituisce underscore)
        caption_text = file_name_with_ext[:-4] if file_name_with_ext.lower().endswith('.pdf') else file_name_with_ext
        caption_text = caption_text.replace('_', ' ')

        files_to_send = {'document': (file_name_with_ext, response.content)}
        message_data = {'chat_id': CHAT_ID, 'caption': caption_text}
        telegram_api_url = f'https://api.telegram.org/bot{TOKEN}/sendDocument'

        api_response = requests.post(telegram_api_url, data=message_data, files=files_to_send, timeout=60)

        if api_response.status_code == 200:
            print(f"PDF '{pdf_info['title']}' inviato con successo.")
            return True
        else:
            print(f"Errore API Telegram ({api_response.status_code}): {api_response.text}")
            return False

    except requests.exceptions.RequestException as e:
        print(f"Errore download/invio PDF {pdf_info['url']}: {e}")
        return False
    except Exception as e:
        print(f"Errore imprevisto invio PDF {pdf_info['title']}: {e}")
        return False


def send_info_message(message):
    """Invia un messaggio di testo semplice a Telegram."""
    print(f"Invio messaggio informativo: '{message}'")
    telegram_api_url = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
    message_data = {'chat_id': CHAT_ID, 'text': message}
    try:
        api_response = requests.post(telegram_api_url, data=message_data, timeout=30)
        if api_response.status_code == 200:
            print("Messaggio informativo inviato.")
            return True
        else:
            print(f"Errore invio messaggio info ({api_response.status_code}): {api_response.text}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"Errore rete invio messaggio info: {e}")
        return False

# --- ENDPOINT FLASK PER CRON JOB ---

@app.route('/', methods=['GET'])
def check_new():
    """Endpoint chiamato dal cron job per verificare e inviare nuovi PDF."""
    print("\n--- Avvio controllo nuovi PDF ---")
    state = load_state()
    sent_urls = set(state.get('sent', []))
    print(f"Caricati {len(sent_urls)} URL già inviati.")

    all_pdfs = fetch_pdfs()
    new_pdfs = [pdf for pdf in all_pdfs if pdf['url'] not in sent_urls]

    if new_pdfs:
        print(f"Trovati {len(new_pdfs)} nuovi PDF. Invio immediato...")
        for pdf in new_pdfs:
            if send_pdf(pdf):
                state['sent'].append(pdf['url'])
        save_state(state)

    else:
        # Controllo notifica informativa solo alle 7 del mattino
        now = datetime.now()
        today_str = now.date().isoformat()
        last_info = state.get('last_info_date')
        if now.hour == 7 and last_info != today_str:
            send_info_message("Nessun nuovo PDF trovato dall'ultimo controllo.")
            state['last_info_date'] = today_str
            save_state(state)
        else:
            print("Nessuna notifica informativa inviata.")

    print("--- Controllo terminato ---")
    return 'Controllo completato', 200

# --- AVVIO APPLICAZIONE (per hosting come Render) ---

if __name__ == '__main__':
    print("Avvio applicazione Flask...")
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
