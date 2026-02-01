![Version](https://img.shields.io/badge/version-0.19.0-blue.svg)
![Home Assistant](https://img.shields.io/badge/home%20assistant-component-orange.svg)

Mail Agent för Home Assistant
Version: 0.19.0
Uppdaterad: 2025-12-18

Mail Agent är en intelligent "Custom Component" för Home Assistant som automatiserar hanteringen av inkommande post. Genom att kombinera Google Gemini (Generativ AI) med traditionell e-posthantering (IMAP/SMTP), fungerar komponenten som en smart sekreterare som läser dina mail, förstår innehållet (inklusive bilagor) och automatiskt bokar in möten i din kalender.

🚀 Nyheter i v0.18.0 (Restore & Stabilitet)
Denna version fokuserar på dataintegritet och driftstabilitet:
💾 Restore-funktionalitet: Sensorerna (t.ex. "Emails Processed") nollställs inte längre när du ändrar inställningar eller startar om Home Assistant. De minns sitt senaste värde.
🛡️ Ökad Stabilitet: Fixar för "Thread Safety" och robustare hantering av IMAP-svar (förhindrar krascher vid oväntade mail-format).
👁️ Full Insyn: Nya sensorer ger dig kontroll över vad agenten gör i realtid.

📊 Nya Entiteter
Integrationen skapar nu följande entiteter för varje konfigurerat konto:
binary_sensor.mail_agent_scanning: Visar PÅ när agenten aktivt söker efter och bearbetar mail.
binary_sensor.mail_agent_connected: Visar status för anslutningen till IMAP-servern.
sensor.mail_agent_last_scan: Tidsstämpel för när inkorgen senast kontrollerades framgångsrikt.
sensor.mail_agent_last_event_summary: Visar sammanfattningen av det senast hittade eventet (t.ex. "Tandläkartid 14:00").
sensor.mail_agent_emails_processed: En räknare som visar totalt antal mail agenten har analyserat.

📋 Huvudfunktioner
🧠 AI-Driven Analys: Använder Google Gemini för att förstå naturligt språk i mail och bifogade PDF-kallelser.
📅 Automatisk Kalenderbokning: Extraherar tid, plats och sammanfattning och skapar händelser i din kalender.
🔒 Trådsäkerhet: "Global Scanning Lock" förhindrar att samma mail bearbetas två gånger samtidigt.
📧 Robust SMTP: Skickar multipart-mail endast vid behov och hanterar bilagor korrekt.
🎨 Dashboard-ready: Bygg snygga statuspaneler i Lovelace med de nya sensorerna.

🔧 Installation
Ladda ner mappen mail_agent och placera den i /config/custom_components/.
Starta om Home Assistant.
Gå till Inställningar -> Enheter & Tjänster -> Lägg till integration.
Sök efter "Mail Agent" och följ guiden.

⚙️ Konfiguration (UI)
All konfiguration sker via gränssnittet. Inga YAML-filer behövs.
Anslutning: IMAP/SMTP server, port, användare, lösenord.
AI: Google Gemini API-nyckel och modellnamn.
Integrationer: Välj kalendrar och notifieringstjänster.
Logik: Anpassa sökintervall och debug-nivå.

### Nyhet: Typ "Förvaltare" (Fakturahantering)
Du kan nu välja mellan två arbetslägen för Mail Agent:
1. **Tolka kallelse (Standard):** Letar efter möten och bokningar för kalendern.
2. **Förvaltare (Fakturor):** En ny specialiserad roll för att hantera inkommande fakturor och förvaltningspost.

**Funktioner i Förvaltare-läget:**
*   **AI-analys:** Extraherar avsändare, förfallodatum, belopp och fakturanummer/OCR.
*   **Google Drive Lagring:** Sparar automatiskt PDF-bilagor (eller skapar PDF av mailet) i din Google Drive.
    *   Struktur: `Grundmapp/ÅÅÅÅ/Månad/` (t.ex. `Fakturor/2026/Februari/`).
    *   Filnamn: `Avsändare_Datum_Fakturanr_Summa_ID.pdf`.
*   **Notifieringar:** Skickar en Persistent Notification i HA med detaljer och länk till Drive-filen.

**Konfiguration för Förvaltare:**
För att aktivera detta läge behöver du:
1. Välja "Förvaltare" under inställningar.
2. Skapa ett **Google Cloud Service Account** och ladda ner JSON-nyckelfilen.
3. Dela din Google Drive-mapp med Service Account-mailadressen.
4. Ange sökvägen till JSON-filen (t.ex. `/config/service_account.json`) och namnet på grundmappen i konfigurationen.

🛠️ Felsökning
Sensorerna visar "Unknown"? Vänta till nästa sökintervall eller tvinga en omladdning av integrationen, så kommer de igång.
Inga mail hittas? Kontrollera att mailen är markerade som Olästa (Unseen) i din inkorg.

📄 Licens
Open Source för personligt bruk.
