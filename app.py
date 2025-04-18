# -*- coding: utf-8 -*-
import os
import json
import requests
from bs4 import BeautifulSoup
from flask import Flask
import urllib.parse
from datetime import date, datetime # Importa le classi per gestire date e ore

# Crea l'applicazione Flask
app = Flask(__name__)

# --- CONFIGURAZIONE ---
TOKEN = os.environ.get('TELEGRAM_TOKEN', 'YOUR_FALLBACK_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', 'YOUR_FALLBACK_CHAT_ID')
STATE_FILE = 'state.json'  # File per memorizzare lo stato (URL inviati e data ultimo health check)
URL = 'https://www.fondazionefojanini.it/blog/notiziaritecnici/' # Pagina da monitorare

# --- GESTIONE STATO (PDF Già Inviati e Ultimo Health Check) ---

def load_state():
    """
    Carica lo stato dal file STATE_FILE.
    Lo stato contiene 'sent' (lista URL PDF) e 'last_healthcheck_date' (stringa YYYY-MM-DD).
    Restituisce uno stato di default se il file non esiste o è invalido.
    """
    # Stato di default all'avvio o in caso di errore
    default_state = {'sent': [], 'last_healthcheck_date': None}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)
                # Verifica base della struttura del file
                if isinstance(state, dict) and isinstance(state.get('sent'), list):
                    # Assicura che la chiave per la data esista, altrimenti usa None
                    if 'last_healthcheck_date' not in state:
                        state['last_healthcheck_date'] = None
                    # Rinominiamo per coerenza se troviamo la vecchia chiave (gestione transitoria)
                    if 'last_notification_date' in state:
                         if state['last_healthcheck_date'] is None: # Dai priorità alla nuova se esiste
                              state['last_healthcheck_date'] = state.pop('last_notification_date')
                         else:
                              state.pop('last_notification_date') # Rimuovi la vecchia se la nuova esiste già
                    return state
                else:
                    print(f"Attenzione: Struttura non valida in {STATE_FILE}. Inizializzo con default.")
                    return default_state
        except (json.JSONDecodeError, IOError) as e:
            print(f"Errore durante lettura/decodifica di {STATE_FILE}: {e}. Inizializzo con default.")
            return default_state
    return default_state # Se il file non esiste, ritorna lo stato di default

def save_state(state):
    """Salva lo stato corrente (incluso 'last_healthcheck_date') nel file STATE_FILE."""
    try:
        # Rimuovi la vecchia chiave se presente, prima di salvare
        state.pop('last_notification_date', None)
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=4, ensure_ascii=False)
        print("Stato salvato correttamente.")
    except IOError as e:
        print(f"Errore durante il salvataggio di {STATE_FILE}: {e}")

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
                file_name = os.path.basename(urllib.parse.unquote(full_url))
                pdf_info = {'url': full_url, 'title': file_name}
                pdfs_found.append(pdf_info)

        # Rimuovi duplicati basati su URL
        seen_urls = set()
        unique_pdfs = [pdf for pdf in pdfs_found if pdf['url'] not in seen_urls and seen_urls.add(pdf['url']) is None]

        print(f"Trovati {len(unique_pdfs)} PDF unici.")
        return unique_pdfs

    except requests.exceptions.RequestException as e:
        print(f"Errore durante il recupero della pagina {URL}: {e}")
        return []
    except Exception as e:
        print(f"Errore imprevisto durante l'analisi della pagina: {e}")
        return []

def send_pdf(pdf_info):
    """Scarica un PDF e lo invia a Telegram."""
    print(f"Tentativo di invio PDF: {pdf_info['title']}")
    try:
        response = requests.get(pdf_info['url'], timeout=60)
        response.raise_for_status()

        file_name_with_ext = pdf_info['title']
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
            print(f"Errore da API Telegram ({api_response.status_code}): {api_response.text}")
            return False

    except requests.exceptions.RequestException as e:
        print(f"Errore durante il download/invio del PDF {pdf_info['url']}: {e}")
        return False
    except Exception as e:
        print(f"Errore imprevisto durante l'invio del PDF {pdf_info['title']}: {e}")
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
            return True # Importante restituire True se l'invio va a buon fine
        else:
            print(f"Errore invio messaggio informativo ({api_response.status_code}): {api_response.text}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"Errore di rete durante invio messaggio informativo: {e}")
        return False
    except Exception as e:
        print(f"Errore imprevisto durante invio messaggio informativo: {e}")
        return False

# --- ENDPOINT FLASK PER CRON JOB ---

@app.route('/', methods=['GET'])
def check_new():
    """
    Endpoint chiamato dal cron job.
    1. Verifica e invia immediatamente nuovi PDF trovati.
    2. Invia un messaggio di "health check" giornaliero alle 7 del mattino.
    """
    print(f"\n--- Avvio controllo ({datetime.now()}) ---")
    state_changed = False # Flag per sapere se dobbiamo salvare lo stato alla fine
    current_state = load_state()
    sent_urls = set(current_state.get('sent', []))
    last_healthcheck_date_str = current_state.get('last_healthcheck_date')

    print(f"Caricati {len(sent_urls)} URL già inviati. Ultimo health check inviato il: {last_healthcheck_date_str}")

    # --- 1. Controllo e Invio Nuovi PDF ---
    all_pdfs_on_site = fetch_pdfs()
    new_pdfs = [pdf for pdf in all_pdfs_on_site if pdf['url'] not in sent_urls]

    if new_pdfs:
        print(f"Trovati {len(new_pdfs)} nuovi PDF. Invio in ordine inverso...")
        successful_sends = 0
        failed_sends = 0

        for pdf in reversed(new_pdfs): # Invia il più recente per ultimo
            if send_pdf(pdf):
                current_state['sent'].append(pdf['url'])
                successful_sends += 1
                state_changed = True # Lo stato è cambiato, dobbiamo salvarlo
            else:
                print(f"Invio fallito per {pdf['title']}. Verrà ritentato.")
                failed_sends += 1
        print(f"Invii PDF completati: {successful_sends} successi, {failed_sends} fallimenti.")
    else:
        print("Nessun nuovo PDF trovato in questo controllo.")

    # --- 2. Controllo per Messaggio Giornaliero di Health Check ---
    # Questo blocco viene eseguito indipendentemente dal fatto che siano stati trovati nuovi PDF
    current_hour = datetime.now().hour
    today_str = date.today().isoformat() # Formato YYYY-MM-DD

    print(f"Controllo health check: Ora={current_hour}, Oggi={today_str}, UltimoCheck={last_healthcheck_date_str}")

    # Invia solo se sono le 7 E non è già stato inviato oggi
    if current_hour == 7 and today_str != last_healthcheck_date_str:
        print("Ore 7 e health check non ancora inviato oggi. Tento l'invio...")
        # Puoi personalizzare questo messaggio come preferisci!
        health_message = "Buongiorno! 👋 Il tuo amichevole bot Fojanini è sveglio, operativo e pronto a cercare PDF anche oggi! 🤖📄"
        if send_info_message(health_message):
            # Se l'invio ha successo, aggiorna la data nello stato
            current_state['last_healthcheck_date'] = today_str
            state_changed = True # Lo stato è cambiato, dobbiamo salvarlo
            print(f"Messaggio health check inviato. Data aggiornata a {today_str}.")
        else:
            print("Invio messaggio health check fallito. Si ritenterà alla prossima esecuzione delle 7.")
    elif current_hour == 7:
         print("Health check giornaliero già inviato oggi.")
    #else: # Non serve stampare nulla se non sono le 7

    # --- 3. Salvataggio Stato (se necessario) ---
    if state_changed:
        print("Salvataggio stato aggiornato...")
        save_state(current_state)
    else:
        print("Nessuna modifica allo stato da salvare.")

    print("--- Controllo terminato ---")
    return 'Controllo completato', 200 # Risposta per il cron job

# --- AVVIO APPLICAZIONE (per hosting come Render) ---

if __name__ == '__main__':
    print("Avvio applicazione Flask...")
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
