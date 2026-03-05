import telebot
import sqlite3
import os
from dotenv import load_dotenv

# Carica il token dal file .env
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    print("ERRORE: BOT_TOKEN non trovato nel file .env!")
    exit(1)

bot = telebot.TeleBot(TOKEN)

# Dizionario per tenere traccia della creazione in corso per ogni utente
creation_states = {}  # user_id → {'step': int, 'data': dict}

# Bonus statistici per razza (valori aggiunti alle stat base)
razza_bonus = {
    'umano':      {'hp': 0,   'forza': 0,   'agilita': 0,   'difesa': 0},   # bilanciato
    'elfo':       {'hp': -2,  'forza': -3,  'agilita': +6,  'difesa': +1},  # agile e preciso
    'nano':       {'hp': +5,  'forza': +4,  'agilita': -3,  'difesa': +4},  # resistente
    'orco':       {'hp': +8,  'forza': +6,  'agilita': -4,  'difesa': +2},  # brutale
    'dragonoide': {'hp': +4,  'forza': +5,  'agilita': +2,  'difesa': +3},  # forte ma lento
    'gigante':    {'hp': +12, 'forza': +8,  'agilita': -6,  'difesa': +5},  # tank
}

def get_db():
    conn = sqlite3.connect('rpg.db')
    c = conn.cursor()

    # Crea tabella se non esiste (con statistiche)
    c.execute('''CREATE TABLE IF NOT EXISTS characters
                 (user_id INTEGER PRIMARY KEY,
                  name TEXT,
                  razza TEXT,
                  classe TEXT,
                  descrizione TEXT,
                  level INTEGER DEFAULT 1,
                  exp INTEGER DEFAULT 0,
                  money INTEGER DEFAULT 100,
                  hp INTEGER DEFAULT 20,
                  forza INTEGER DEFAULT 10,
                  agilita INTEGER DEFAULT 10,
                  difesa INTEGER DEFAULT 5)''')

    # Aggiungi colonne mancanti
    for col, default in [
        ('hp', 20),
        ('forza', 10),
        ('agilita', 10),
        ('difesa', 5)
    ]:
        try:
            c.execute(f"ALTER TABLE characters ADD COLUMN {col} INTEGER DEFAULT {default}")
        except sqlite3.OperationalError:
            pass

    conn.commit()
    return conn, c

# Benvenuto /start e /help
@bot.message_handler(commands=['start', 'help'], chat_types=['private', 'group', 'supergroup'])
def send_welcome(message):
    bot.reply_to(message, "Benvenuto, avventuriero! 🌟\n"
                          "Sono il tuo maestro di creazione personaggi per RPG.\n\n"
                          "Comandi disponibili:\n"
                          "• /crea_scheda → Crea il tuo eroe\n"
                          "• /scheda → Visualizza la tua scheda\n"
                          "• /razze → Elenco razze e bonus statistiche\n"
                          "• /help → Questo messaggio\n\n"
                          "Pronto a forgiare la tua leggenda? 🔥")

# Comando /razze per vedere i bonus di ogni razza
@bot.message_handler(commands=['razze'], chat_types=['private', 'group', 'supergroup'])
def lista_razze(message):
    elenco = "**Elenco razze e bonus statistiche**\n\n"
    elenco += "Statistiche base (senza bonus): HP 20, Forza 10, Agilità 10, Difesa 5\n\n"
    elenco += "Ecco i bonus/malus per ogni razza:\n\n"

    for razza, bonus in razza_bonus.items():
        elenco += f"**{razza.capitalize()}**:\n"
        elenco += f"  • HP:     {bonus['hp']:+d}\n"
        elenco += f"  • Forza:  {bonus['forza']:+d}\n"
        elenco += f"  • Agilità: {bonus['agilita']:+d}\n"
        elenco += f"  • Difesa: {bonus['difesa']:+d}\n\n"

    elenco += "Scegli la tua razza durante /crea_scheda!"
    bot.reply_to(message, elenco)

# Comando per iniziare la creazione della scheda (con gestione gruppo/privato)
@bot.message_handler(commands=['crea_scheda'], chat_types=['private', 'group', 'supergroup'])
def crea_scheda_start(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    chat_type = message.chat.type

    # Se siamo in gruppo/supergroup, avvia creazione in privato
    if chat_type in ['group', 'supergroup']:
        try:
            # Invia il primo messaggio in privato
            bot.send_message(
                user_id,
                "Iniziamo la creazione della tua scheda in privato!\n\n"
                "**Passo 1/4 - Nome**\n"
                "Come si chiama il tuo personaggio?\n"
                "Rispondi solo con il nome (es: Aragorn, Luna, Grommash)"
            )
            # Salva lo stato
            creation_states[user_id] = {
                'step': 1,
                'data': {}
            }
            # Avviso nel gruppo
            bot.reply_to(message, f"{message.from_user.first_name}, ti ho mandato la creazione della scheda in privato! 📩")
        except telebot.apihelper.ApiTelegramException as e:
            if "user not found" in str(e) or "bot was blocked" in str(e):
                bot.reply_to(message, "Non posso scriverti in privato! 😔\n"
                                      "Devi prima scrivermi in privato almeno una volta o sbloccarmi.")
            else:
                bot.reply_to(message, "Errore nell'avviare la creazione in privato. Riprova o contattami in privato.")
        return

    # Se siamo già in privato, procedi normalmente
    creation_states[user_id] = {
        'step': 1,
        'data': {}
    }
    bot.reply_to(message, "Iniziamo a creare la tua scheda personaggio!\n\n"
                          "**Passo 1/4 - Nome**\n"
                          "Come si chiama il tuo personaggio?\n"
                          "Rispondi solo con il nome (es: Aragorn, Luna, Grommash)")

# Handler per i messaggi durante la creazione (solo in privato)
@bot.message_handler(func=lambda msg: msg.from_user.id in creation_states, chat_types=['private'])
def handle_creation_steps(message):
    user_id = message.from_user.id
    if user_id not in creation_states:
        return

    state = creation_states[user_id]
    step = state['step']
    data = state['data']
    text = message.text.strip()

    if step == 1:  # Nome
        if not text:
            bot.reply_to(message, "Il nome non può essere vuoto. Scrivi il nome del personaggio.")
            return
        data['name'] = text
        state['step'] = 2
        bot.reply_to(message, "**Passo 2/4 - Razza**\n\n"
                              "Scegli una razza (o scrivine una personalizzata):\n"
                              "Umano / Elfo / Nano / Orco / Dragonoide / Gigante\n\n"
                              "Rispondi solo con la razza")

    elif step == 2:  # Razza
        if not text:
            bot.reply_to(message, "Devi scegliere una razza. Scrivi ad esempio: Elfo")
            return
        data['razza'] = text
        state['step'] = 3
        bot.reply_to(message, "**Passo 3/4 - Classe**\n\n"
                              "Scegli una classe (o personalizzala):\n"
                              "Guerriero / Mago / Ladro / Chierico / Mercante\n\n"
                              "Rispondi solo con la classe")

    elif step == 3:  # Classe
        if not text:
            bot.reply_to(message, "Devi scegliere una classe. Scrivi ad esempio: Mago")
            return
        data['classe'] = text
        state['step'] = 4
        bot.reply_to(message, "**Passo 4/4 - Descrizione**\n\n"
                              "Scrivi la storia o descrizione del tuo personaggio.\n"
                              "Puoi scrivere in più messaggi.\n\n"
                              "Quando hai finito scrivi solo la parola: FINE")

    elif step == 4:  # Descrizione
        raw_text = message.text
        text = message.text.strip()
        print(f"[DEBUG] Step 4 - RAW: '{raw_text}' (len {len(raw_text)})")
        print(f"[DEBUG] Step 4 - strip(): '{text}' (len {len(text)})")

        cleaned = ''.join(c for c in text.upper() if c.isalnum())
        print(f"[DEBUG] Pulito: '{cleaned}'")

        if "FINE" in cleaned or "FINITO" in cleaned:
            print(f"[DEBUG] === RICONOSCIUTO FINE! Variante: '{text}' ===")

            # Statistiche base
            hp = 20
            forza = 10
            agilita = 10
            difesa = 5

            # Applica bonus razza
            razza_scelta = data.get('razza', '').lower()
            if razza_scelta in razza_bonus:
                bonus = razza_bonus[razza_scelta]
                hp += bonus['hp']
                forza += bonus['forza']
                agilita += bonus['agilita']
                difesa += bonus['difesa']
                print(f"[DEBUG] Bonus razza '{razza_scelta}' applicati")

            # Salva nel database con statistiche
            conn, c = get_db()
            c.execute("""
                INSERT OR REPLACE INTO characters
                (user_id, name, razza, classe, descrizione, level, exp, money, hp, forza, agilita, difesa)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                data.get('name', 'Sconosciuto'),
                data.get('razza', 'Non specificata'),
                data.get('classe', 'Non specificata'),
                data.get('descrizione', 'Nessuna descrizione'),
                1,
                0,
                100,
                hp,
                forza,
                agilita,
                difesa
            ))
            conn.commit()
            conn.close()

            # Mostra scheda finale con statistiche
            scheda = (
                f"**Scheda completata!**\n\n"
                f"**Nome:** {data.get('name', 'Sconosciuto')}\n"
                f"**Razza:** {data.get('razza', 'Non specificata')}\n"
                f"**Classe:** {data.get('classe', 'Non specificata')}\n"
                f"**Descrizione:**\n{data.get('descrizione', 'Nessuna descrizione')}\n\n"
                f"Livello: 1   EXP: 0   Soldi: 100 💰\n"
                f"**HP:** {hp}   **Forza:** {forza}   **Agilità:** {agilita}   **Difesa:** {difesa}\n"
                f"Usa /scheda per rivederla."
            )
            bot.reply_to(message, scheda)

            # Rimuovi stato
            del creation_states[user_id]

            bot.reply_to(message, "Scheda salvata con successo! 🎉")
            return

        else:
            print(f"[DEBUG] Non FINE → aggiungo '{text}'")
            if 'descrizione' not in data:
                data['descrizione'] = text
            else:
                data['descrizione'] += "\n" + text
            bot.reply_to(message, "Ok, continua pure... (scrivi **FINE** quando hai finito)")

# Visualizza scheda salvata (con statistiche)
@bot.message_handler(commands=['scheda'], chat_types=['private', 'group', 'supergroup'])
def mostra_scheda(message):
    user_id = message.from_user.id
    conn, c = get_db()
    c.execute("SELECT name,