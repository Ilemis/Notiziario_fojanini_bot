# -*- coding: utf-8 -*-
# Importa le librerie necessarie
import os  # Per interagire con il sistema operativo (leggere variabili d'ambiente, gestire percorsi file)
import json # Per lavorare con i file JSON (leggere e scrivere lo stato)
import requests # Per effettuare richieste HTTP (scaricare pagine web e PDF)
from bs4 import BeautifulSoup # Per analizzare il codice HTML delle pagine web
from flask import Flask # Per creare una semplice applicazione web (necessaria per l'hosting su piattaforme come Render)
import urllib.parse # Libreria aggiunta per gestire correttamente nomi file con spazi o caratteri speciali negli URL

# Crea un'istanza dell'applicazione Flask
app = Flask(__name__)

# --- CONFIGURAZIONE ---
# Recupera le credenziali del bot Telegram e l'ID della chat dalle variabili d'ambiente
# Queste variabili DEVONO essere impostate nell'ambiente dove esegui lo script (es. su Render.com)
# Esempio: export TELEGRAM_TOKEN='iltuotoken'
#          export TELEGRAM_CHAT_ID='iltuochatid'
TOKEN = os.environ.get('TELEGRAM_TOKEN', 'YOUR_FALLBACK_TOKEN') # Usa os.environ.get per evitare errori se la variabile non è impostata
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', 'YOUR_FALLBACK_CHAT_ID')
# Nome del file usato per memorizzare gli URL dei PDF già inviati
STATE_FILE = 'state.json'
# L'URL della pagina web da cui estrarre i link ai PDF
URL = 'https://www.fondazionefojanini.it/blog/notiziaritecnici/'

# --- GESTIONE STATO ---

def load_state():
    """
    Carica lo stato (lista di URL già inviati) dal file JSON.
    Se il file non esiste, restituisce uno stato iniziale vuoto.
    """
    # Controlla se il file di stato esiste nella stessa cartella dello script
    if os.path.exists(STATE_FILE):
        try:
            # Apre il file in modalità lettura ('r')
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                # Legge il contenuto del file e lo interpreta come JSON
                state = json.load(f)
                # Assicura che la chiave 'sent' esista e sia una lista
                if 'sent' not in state or not isinstance(state.get('sent'), list):
                    print(f"Attenzione: Il file {STATE_FILE} non contiene una lista 'sent' valida. Inizializzo lo stato.")
                    return {'sent': []}
                return state
        except json.JSONDecodeError:
            # Se il file è corrotto o non è JSON valido, inizia con uno stato vuoto
            print(f"Errore: Impossibile decodificare {STATE_FILE}. Inizializzo lo stato.")
            return {'sent': []}
        except Exception as e:
            # Gestisce altri possibili errori di lettura file
            print(f"Errore durante la lettura di {STATE_FILE}: {e}. Inizializzo lo stato.")
            return {'sent': []}
    else:
        # Se il file non esiste, è la prima esecuzione o lo stato è stato perso
        print(f"File {STATE_FILE} non trovato. Inizializzo lo stato.")
        return {'sent': []} # Restituisce un dizionario con una lista vuota per 'sent'

def save_state(state):
    """
    Salva lo stato corrente (dizionario con la lista 'sent') nel file JSON.
    Sovrascrive il file esistente.
    """
    try:
        # Apre il file in modalità scrittura ('w')
        # 'encoding='utf-8'' è importante per gestire caratteri speciali
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            # Scrive il dizionario 'state' nel file in formato JSON
            # indent=4 rende il file JSON più leggibile per gli umani
            json.dump(state, f, indent=4, ensure_ascii=False)
    except Exception as e:
        # Gestisce possibili errori di scrittura file
        print(f"Errore durante il salvataggio di {STATE_FILE}: {e}")

# --- LOGICA PRINCIPALE ---

def fetch_pdfs():
    """
    Recupera i link ai PDF dalla pagina web specificata nell'URL.
    Estrae l'URL completo e il nome del file per ciascun PDF.
    Restituisce una lista di dizionari, ognuno rappresentante un PDF.
    """
    print(f"Recupero PDF da: {URL}")
    pdfs_found = [] # Lista per memorizzare i PDF trovati
    try:
        # Effettua una richiesta GET per scaricare il contenuto della pagina web
        # Imposta un timeout per evitare che la richiesta rimanga appesa indefinitamente
        response = requests.get(URL, timeout=30)
        # Controlla se la richiesta ha avuto successo (codice di stato HTTP 200 OK)
        response.raise_for_status() # Solleva un'eccezione per codici di errore (4xx, 5xx)

        # Analizza il contenuto HTML della pagina usando BeautifulSoup
        # 'html.parser' è il parser HTML integrato in Python
        soup = BeautifulSoup(response.text, 'html.parser')

        # Trova tutti i tag 'a' (link) che hanno un attributo 'href'
        for link_tag in soup.find_all('a', href=True):
            href = link_tag['href'] # Estrae il valore dell'attributo href

            # Controlla se l'href termina con '.pdf' (ignorando maiuscole/minuscole)
            if href.lower().endswith('.pdf'):
                # Costruisce l'URL assoluto del PDF partendo dall'URL base della pagina e dall'href relativo
                # Esempio: URL base 'https://site.com/page/' e href '../files/doc.pdf' -> 'https://site.com/files/doc.pdf'
                full_url = urllib.parse.urljoin(URL, href)

                # --- MODIFICA CHIAVE ---
                # Estrae il nome del file dall'URL completo.
                # Esempio: da 'https://.../files/nome bellissimo file.pdf' estrae 'nome bellissimo file.pdf'
                # urllib.parse.unquote decodifica eventuali caratteri speciali nell'URL (%20 per spazio, ecc.)
                file_name = os.path.basename(urllib.parse.unquote(full_url))

                # Crea un dizionario per rappresentare il PDF
                pdf_info = {
                    'url': full_url,
                    'title': file_name # Usa il nome del file estratto come 'title'
                }
                pdfs_found.append(pdf_info) # Aggiunge il dizionario alla lista

        # Rimuove eventuali duplicati basati sull'URL, mantenendo l'ordine di apparizione
        seen_urls = set()
        unique_pdfs = []
        for pdf in pdfs_found:
            if pdf['url'] not in seen_urls:
                seen_urls.add(pdf['url'])
                unique_pdfs.append(pdf)

        print(f"Trovati {len(unique_pdfs)} PDF unici.")
        return unique_pdfs # Restituisce la lista dei PDF unici

    except requests.exceptions.RequestException as e:
        # Gestisce errori di rete (connessione, timeout, DNS, etc.)
        print(f"Errore durante il recupero della pagina {URL}: {e}")
        return [] # Restituisce una lista vuota in caso di errore
    except Exception as e:
        # Gestisce altri errori imprevisti durante l'analisi HTML
        print(f"Errore imprevisto durante l'analisi della pagina: {e}")
        return [] # Restituisce una lista vuota

def send_pdf(pdf_info):
    """
    Scarica un singolo PDF dal suo URL e lo invia al canale Telegram specificato.
    Usa il nome file estratto come nome del documento inviato e come didascalia (caption).
    """
    print(f"Tentativo di invio PDF: {pdf_info['title']} ({pdf_info['url']})")
    try:
        # Scarica il contenuto del PDF dall'URL
        response = requests.get(pdf_info['url'], timeout=60) # Timeout più lungo per il download di file
        response.raise_for_status() # Controlla errori nel download

        # --- MODIFICA PER NOME FILE E DIDASCALIA ---
        # Il nome del file è già in pdf_info['title'] (es. 'documento bellissimo.pdf')
        file_name_with_ext = pdf_info['title']

        # Prepara una didascalia più pulita rimuovendo l'estensione .pdf (case-insensitive)
        caption_text = file_name_with_ext
        if caption_text.lower().endswith('.pdf'):
            caption_text = caption_text[:-4] # Rimuove gli ultimi 4 caratteri (".pdf")
        # Sostituisce eventuali underscore con spazi per una migliore leggibilità della didascalia
        caption_text = caption_text.replace('_', ' ')

        # Prepara i file da inviare tramite la richiesta POST
        # La tupla è (nome_file_desiderato, contenuto_binario_file)
        files_to_send = {
            'document': (file_name_with_ext, response.content)
        }

        # Prepara i dati del messaggio (chat ID e didascalia)
        message_data = {
            'chat_id': CHAT_ID,
            'caption': caption_text # Usa la didascalia pulita
        }

        # Costruisce l'URL dell'API di Telegram per inviare documenti
        telegram_api_url = f'https://api.telegram.org/bot{TOKEN}/sendDocument'

        # Effettua la richiesta POST all'API di Telegram
        api_response = requests.post(telegram_api_url, data=message_data, files=files_to_send, timeout=60)

        # Controlla la risposta dall'API di Telegram
        if api_response.status_code == 200:
            print(f"PDF '{pdf_info['title']}' inviato con successo.")
            return True # Indica che l'invio è andato a buon fine
        else:
            # Se Telegram restituisce un errore, stampa i dettagli
            print(f"Errore da API Telegram ({api_response.status_code}): {api_response.text}")
            return False # Indica che l'invio è fallito

    except requests.exceptions.RequestException as e:
        # Gestisce errori durante il download del PDF
        print(f"Errore durante il download del PDF {pdf_info['url']}: {e}")
        return False
    except Exception as e:
        # Gestisce altri errori imprevisti durante l'invio
        print(f"Errore imprevisto durante l'invio del PDF {pdf_info['title']}: {e}")
        return False

def send_info_message(message):
    """
    Invia un semplice messaggio di testo al canale Telegram specificato.
    Utile per notifiche (es. "nessun nuovo PDF").
    """
    print(f"Invio messaggio informativo: '{message}'")
    # URL dell'API di Telegram per inviare messaggi di testo
    telegram_api_url = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
    # Dati del messaggio (chat ID e testo)
    message_data = {
        'chat_id': CHAT_ID,
        'text': message
    }
    try:
        # Effettua la richiesta POST all'API di Telegram
        api_response = requests.post(telegram_api_url, data=message_data, timeout=30)
        # Controlla se l'invio ha avuto successo
        if api_response.status_code == 200:
            print("Messaggio informativo inviato.")
            return True
        else:
            print(f"Errore invio messaggio informativo ({api_response.status_code}): {api_response.text}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"Errore di rete durante invio messaggio informativo: {e}")
        return False
    except Exception as e:
        print(f"Errore imprevisto durante invio messaggio informativo: {e}")
        return False

# --- ROUTE FLASK (Punto di ingresso per servizi come Render) ---

@app.route('/', methods=['GET'])
def check_new():
    """
    Endpoint web principale. Viene chiamato periodicamente (es. da un cron job su Render).
    Controlla se ci sono nuovi PDF sul sito rispetto all'ultimo controllo e li invia.
    """
    print("\n--- Avvio controllo nuovi PDF ---")

    # 1. Carica lo stato precedente (lista degli URL dei PDF già inviati)
    current_state = load_state()
    sent_urls = set(current_state.get('sent', [])) # Usa un set per ricerche più veloci
    print(f"Caricati {len(sent_urls)} URL già inviati.")

    # 2. Recupera la lista attuale dei PDF dal sito web
    all_pdfs_on_site = fetch_pdfs()

    # 3. Identifica i PDF che non sono ancora stati inviati
    # Controlla se l'URL del PDF è presente nel set degli URL già inviati
    new_pdfs = [pdf for pdf in all_pdfs_on_site if pdf['url'] not in sent_urls]

    # 4. Gestisce l'invio dei nuovi PDF trovati
    if new_pdfs:
        print(f"Trovati {len(new_pdfs)} nuovi PDF.")
        successful_sends = 0
        failed_sends = 0
        # Itera su ogni nuovo PDF trovato
        for pdf in new_pdfs:
            # Tenta di inviare il PDF a Telegram
            if send_pdf(pdf):
                # Se l'invio ha successo, aggiunge l'URL alla lista dei 'sent' nello stato
                current_state['sent'].append(pdf['url'])
                successful_sends += 1
            else:
                # Se l'invio fallisce, non aggiunge l'URL (verrà ritentato al prossimo ciclo)
                print(f"Invio fallito per {pdf['title']}. Verrà ritentato.")
                failed_sends += 1

        print(f"Invii completati: {successful_sends} successi, {failed_sends} fallimenti.")
        # Salva lo stato aggiornato (con i nuovi URL aggiunti) nel file JSON
        # Salva lo stato solo se ci sono stati invii riusciti per evitare scritture inutili
        if successful_sends > 0:
             print("Salvataggio stato aggiornato...")
             save_state(current_state)
    else:
        # Se non ci sono nuovi PDF, invia un messaggio informativo (opzionale)
        print("Nessun nuovo PDF trovato.")
        # Potresti commentare la riga seguente se non vuoi ricevere questo messaggio ogni volta
        # send_info_message("Nessun nuovo PDF trovato dall'ultimo controllo.")

    print("--- Controllo terminato ---")
    # Restituisce una risposta HTTP 200 OK per indicare che il controllo è stato eseguito
    # Questo è richiesto da molte piattaforme di hosting come Render per sapere che il servizio è attivo
    return 'Controllo completato', 200

# --- ESECUZIONE DELL'APPLICAZIONE ---

if __name__ == '__main__':
    # Questa parte viene eseguita solo se lo script viene lanciato direttamente (non importato come modulo)
    # Avvia il server di sviluppo Flask
    # host='0.0.0.0' rende il server accessibile dall'esterno (necessario per Render)
    # port=10000 è la porta su cui il server ascolterà (Render di solito assegna una porta, ma questa è un default comune)
    # debug=True è utile durante lo sviluppo per vedere errori dettagliati, MA NON USARLO IN PRODUZIONE
    print("Avvio applicazione Flask...")
    # Ottieni la porta da una variabile d'ambiente se disponibile (comune su piattaforme PaaS)
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port) # Rimuovi debug=True per la produzione
