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

def get_db():
    conn = sqlite3.connect('rpg.db')
    c = conn.cursor()

    # Crea tabella se non esiste
    c.execute('''CREATE TABLE IF NOT EXISTS characters
                 (user_id INTEGER PRIMARY KEY,
                  name TEXT,
                  razza TEXT,
                  classe TEXT,
                  descrizione TEXT,
                  level INTEGER DEFAULT 1,
                  exp INTEGER DEFAULT 0,
                  money INTEGER DEFAULT 100,
                  bank INTEGER DEFAULT 0)''')

    # Aggiungi colonna bank se manca
    try:
        c.execute("ALTER TABLE characters ADD COLUMN bank INTEGER DEFAULT 0")
        print("[DEBUG] Aggiunta colonna 'bank'")
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
                          "• /scheda → Visualizza la tua scheda completa\n"
                          "• /saldo → Visualizza portafoglio + banca + totale\n"
                          "• /deposita <quantità> → Deposita soldi in banca\n"
                          "• /preleva <quantità> → Preleva soldi dalla banca\n"
                          "• /help → Questo messaggio\n\n"
                          "Pronto a forgiare la tua leggenda? 🔥")

# Comando per iniziare la creazione della scheda (con gestione gruppo/privato)
@bot.message_handler(commands=['crea_scheda'], chat_types=['private', 'group', 'supergroup'])
def crea_scheda_start(message):
    user_id = message.from_user.id
    chat_type = message.chat.type

    # Se siamo in gruppo/supergroup, avvia creazione in privato
    if chat_type in ['group', 'supergroup']:
        try:
            bot.send_message(
                user_id,
                "Iniziamo la creazione della tua scheda in privato!\n\n"
                "**Passo 1/4 - Nome**\n"
                "Come si chiama il tuo personaggio?\n"
                "Rispondi solo con il nome (es: Aragorn, Luna, Grommash)"
            )
            creation_states[user_id] = {
                'step': 1,
                'data': {}
            }
            bot.reply_to(message, f"{message.from_user.first_name}, ti ho mandato la creazione in privato! 📩")
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

            try:
                print("[DEBUG] 1 - Chiamo get_db()")
                conn, c = get_db()
                print("[DEBUG] 2 - Connessione ok")

                print("[DEBUG] 3 - Eseguo INSERT")
                c.execute("""
                    INSERT OR REPLACE INTO characters
                    (user_id, name, razza, classe, descrizione, level, exp, money)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id,
                    data.get('name', 'Sconosciuto'),
                    data.get('razza', 'Non specificata'),
                    data.get('classe', 'Non specificata'),
                    data.get('descrizione', 'Nessuna descrizione'),
                    1,
                    0,
                    100
                ))
                print("[DEBUG] 4 - Query eseguita")
                conn.commit()
                print("[DEBUG] 5 - Commit ok")
                conn.close()
                print("[DEBUG] 6 - Connessione chiusa")

                print("[DEBUG] 7 - Genero scheda")
                scheda = (
                    f"**Scheda completata!**\n\n"
                    f"**Nome:** {data.get('name', 'Sconosciuto')}\n"
                    f"**Razza:** {data.get('razza', 'Non specificata')}\n"
                    f"**Classe:** {data.get('classe', 'Non specificata')}\n"
                    f"**Descrizione:**\n{data.get('descrizione', 'Nessuna descrizione')}\n\n"
                    f"Livello: 1   EXP: 0   Soldi: 100 💰\n"
                    f"Usa /scheda per rivederla."
                )
                print("[DEBUG] 8 - Invio scheda")
                bot.reply_to(message, scheda)

                print("[DEBUG] 9 - Rimuovo stato")
                del creation_states[user_id]

                print("[DEBUG] 10 - Invio messaggio finale")
                bot.reply_to(message, "Scheda salvata! 🎉 Ora puoi usare comandi normali.")

                return

            except Exception as e:
                print(f"[ERRORE CRITICO] {str(e)}")
                import traceback
                traceback.print_exc()
                bot.reply_to(message, f"Errore durante il salvataggio: {str(e)}\nControlla la console per dettagli.")
                return

        else:
            print(f"[DEBUG] Non FINE → aggiungo '{text}'")
            if 'descrizione' not in data:
                data['descrizione'] = text
            else:
                data['descrizione'] += "\n" + text
            bot.reply_to(message, "Ok, continua pure... (scrivi **FINE** quando hai finito)")

# Visualizza scheda salvata
@bot.message_handler(commands=['scheda'], chat_types=['private', 'group', 'supergroup'])
def mostra_scheda(message):
    user_id = message.from_user.id
    conn, c = get_db()
    c.execute("SELECT name, razza, classe, descrizione, level, exp, money, bank FROM characters WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()

    if row:
        name, razza, classe, desc, level, exp, money, bank = row
        scheda = (
            f"**La tua scheda**\n\n"
            f"**Nome:** {name}\n"
            f"**Razza:** {razza}\n"
            f"**Classe:** {classe}\n"
            f"**Descrizione:**\n{desc}\n\n"
            f"Livello: {level}   EXP: {exp}\n"
            f"**Portafoglio:** {money} 💰\n"
            f"**Banca:** {bank} 💰"
        )
        bot.reply_to(message, scheda)
    else:
        bot.reply_to(message, "Non hai ancora creato una scheda. Usa /crea_scheda!")

# Deposita soldi in banca
@bot.message_handler(commands=['deposita'], chat_types=['private', 'group', 'supergroup'])
def deposita(message):
    user_id = message.from_user.id
    args = message.text.split()

    if len(args) < 2:
        bot.reply_to(message, "Uso: /deposita <quantità>\nEsempio: /deposita 50")
        return

    try:
        amount = int(args[1])
        if amount <= 0:
            bot.reply_to(message, "La quantità deve essere positiva!")
            return
    except ValueError:
        bot.reply_to(message, "Inserisci un numero valido!")
        return

    conn, c = get_db()
    c.execute("SELECT money, bank FROM characters WHERE user_id = ?", (user_id,))
    row = c.fetchone()

    if not row:
        bot.reply_to(message, "Non hai ancora una scheda. Crea una con /crea_scheda!")
        conn.close()
        return

    pocket_money, bank_money = row

    if amount > pocket_money:
        bot.reply_to(message, f"Non hai abbastanza soldi in tasca! Hai solo {pocket_money} 💰")
        conn.close()
        return

    new_pocket = pocket_money - amount
    new_bank = bank_money + amount
    c.execute("UPDATE characters SET money = ?, bank = ? WHERE user_id = ?", (new_pocket, new_bank, user_id))
    conn.commit()
    conn.close()

    bot.reply_to(message, f"Hai depositato **{amount}** 💰 in banca!\n\nPortafoglio: {new_pocket} 💰\nBanca: {new_bank} 💰")

# Preleva soldi dalla banca
@bot.message_handler(commands=['preleva'], chat_types=['private', 'group', 'supergroup'])
def preleva(message):
    user_id = message.from_user.id
    args = message.text.split()

    if len(args) < 2:
        bot.reply_to(message, "Uso: /preleva <quantità>\nEsempio: /preleva 50")
        return

    try:
        amount = int(args[1])
        if amount <= 0:
            bot.reply_to(message, "La quantità deve essere positiva!")
            return
    except ValueError:
        bot.reply_to(message, "Inserisci un numero valido!")
        return

    conn, c = get_db()
    c.execute("SELECT money, bank FROM characters WHERE user_id = ?", (user_id,))
    row = c.fetchone()

    if not row:
        bot.reply_to(message, "Non hai ancora una scheda. Crea una con /crea_scheda!")
        conn.close()
        return

    pocket_money, bank_money = row

    if amount > bank_money:
        bot.reply_to(message, f"Non hai abbastanza soldi in banca! Hai solo {bank_money} 💰")
        conn.close()
        return

    new_pocket = pocket_money + amount
    new_bank = bank_money - amount
    c.execute("UPDATE characters SET money = ?, bank = ? WHERE user_id = ?", (new_pocket, new_bank, user_id))
    conn.commit()
    conn.close()

    bot.reply_to(message, f"Hai prelevato **{amount}** 💰 dalla banca!\n\nPortafoglio: {new_pocket} 💰\nBanca: {new_bank} 💰")

# Saldo totale (portafoglio + banca)
@bot.message_handler(commands=['saldo'], chat_types=['private', 'group', 'supergroup'])
def mostra_saldo(message):
    user_id = message.from_user.id
    conn, c = get_db()
    c.execute("SELECT money, bank FROM characters WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()

    if row:
        pocket, bank = row
        totale = pocket + bank
        risposta = (
            f"**Il tuo saldo**\n\n"
            f"Portafoglio: {pocket} 💰\n"
            f"Banca: {bank} 💰\n"
            f"**Totale:** {totale} 💰"
        )
        bot.reply_to(message, risposta)
    else:
        bot.reply_to(message, "Non hai ancora una scheda. Crea una con /crea_scheda!")

def main():
    print("Polling avviato (modalità sincrona)...")
    print("Il bot dovrebbe ora rispondere ai messaggi su Telegram")
    bot.infinity_polling(
        timeout=10,
        long_polling_timeout=5
    )

if __name__ == "__main__":
    print("Bot sta partendo... TOKEN ok")
    main()