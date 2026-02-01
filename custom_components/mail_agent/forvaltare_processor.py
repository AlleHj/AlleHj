# Version: 0.19.0
"""Processor för att hantera fakturor och förvaltningsmail."""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path

from google import genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from homeassistant.util import dt as dt_util
from .const import (
    LOGGER,
    CONF_GDRIVE_CREDENTIALS,
    CONF_GDRIVE_ROOT,
    CONF_GEMINI_API_KEY,
    CONF_GEMINI_MODEL,
    CONF_ENABLE_DEBUG
)

SVENSKA_MANADER = [
    "", "Januari", "Februari", "Mars", "April", "Maj", "Juni",
    "Juli", "Augusti", "September", "Oktober", "November", "December"
]

class ForvaltareProcessor:
    """Hanterar logiken för 'Förvaltare' (Fakturor)."""

    def __init__(self, hass, config):
        self.hass = hass
        self.gemini_api_key = config.get(CONF_GEMINI_API_KEY)
        self.gemini_model = config.get(CONF_GEMINI_MODEL)
        self.enable_debug = config.get(CONF_ENABLE_DEBUG)

        self.gdrive_credentials = config.get(CONF_GDRIVE_CREDENTIALS)
        self.gdrive_root = config.get(CONF_GDRIVE_ROOT)

    def process_email(self, sender, subject, body, attachment_paths):
        """
        Huvudmetod som anropas från MailAgentScanner.
        """
        if not self.gemini_api_key:
            if self.enable_debug:
                LOGGER.warning("Ingen API-nyckel för Gemini.")
            return None

        try:
            # 1. Anropa AI för analys
            ai_data = self._call_gemini(attachment_paths, subject, body, sender)

            if self.enable_debug:
                LOGGER.info("AI RESULTAT (Förvaltare):\n%s", json.dumps(ai_data, indent=2, ensure_ascii=False))

            # 2. Spara till Google Drive
            saved_file_url = None
            if attachment_paths and self.gdrive_credentials:
                # Vi sparar primärt första bilagan om det finns flera,
                # eller så kan vi behöva logik för att välja "rätt" PDF.
                # För enkelhetens skull, ta den första PDF:en.
                pdf_path = None
                for path in attachment_paths:
                    if str(path).lower().endswith(".pdf"):
                        pdf_path = path
                        break

                if pdf_path:
                    try:
                        saved_file_url = self._upload_to_drive(pdf_path, ai_data)
                    except Exception as e:
                        LOGGER.error("Fel vid uppladdning till Drive: %s", e)
                        self._notify_hass("Fel vid Drive-uppladdning", f"Kunde inte spara fakturan: {e}")
                elif self.enable_debug:
                    LOGGER.info("Ingen PDF hittades att spara.")

            # 3. Notifiera
            self._notify_hass_success(ai_data, saved_file_url)

            # Fire event
            self.hass.bus.fire("mail_agent.scanned_document", {
                "type": "forvaltare",
                "sender": sender,
                "subject": subject,
                "ai_data": ai_data,
                "drive_url": saved_file_url
            })

            return ai_data

        except Exception as e:
            LOGGER.error("Fel i ForvaltareProcessor: %s", e)
            return None

    def _call_gemini(self, file_paths, subject, body, sender):
        client = genai.Client(api_key=self.gemini_api_key)
        uploaded_files = []
        for path in file_paths:
            # Ladda upp endast PDFer till Gemini för analys
            if str(path).lower().endswith(".pdf"):
                uploaded_files.append(client.files.upload(file=path, config={'mime_type': 'application/pdf'}))

        now = dt_util.now()
        now_str = now.strftime('%Y-%m-%d')

        # Unikt ID för filnamnet
        unique_id = str(uuid.uuid4())[:8]

        prompt = f"""
        Du är en expert på fakturahantering och bokföring.
        Dagens datum är: {now_str}

        Din uppgift är att extrahera strukturerad data från detta mail (och eventuella PDF-bilagor).
        Informationen kan finnas i mailets text, ämne eller i PDF-filen. Leta noga överallt.

        Data att extrahera:
        1. **Avsändare**: Vem är betalningsmottagare? (T.ex. "Telia", "Fortum"). Om otydligt, använd avsändarnamnet: "{sender}".
        2. **Förfallodatum**: När ska fakturan vara betald? (Format: YYYY-MM-DD).
           - Leta efter "Förfallodatum", "Betalas senast", "Oss tillhanda".
           - Om förfallodatum saknas, leta efter Fakturadatum.
           - Om INGET datum hittas alls, använd dagens datum: {now_str}.
        3. **Summa**: Totalt belopp att betala. (Format: "1234.50" eller "1234"). Ta med valuta om möjligt men helst bara tal.
        4. **Fakturanummer**: OCR-nummer eller fakturanummer. Om saknas, sätt "Saknas".

        Konstruera ett filnamn enligt formatet:
        "Avsändare_Förfallodatum_Fakturanr_Summa_{unique_id}.pdf"
        Exempel: "Telia_2025-02-28_55112233_499kr_a1b2c3d4.pdf"
        (Ersätt mellanslag i filnamnet med understreck, ta bort ogiltiga tecken).

        Ämne: {subject}
        Text: {body}

        Svara strikt med JSON:
        {{
            "sender": "Namn",
            "due_date": "YYYY-MM-DD",
            "amount": "Summa",
            "invoice_number": "Nummer",
            "suggested_filename": "Filnamn.pdf",
            "is_invoice": boolean (True om det verkar vara en faktura/betalning)
        }}
        """

        contents = uploaded_files + [prompt]
        response = client.models.generate_content(
            model=self.gemini_model, contents=contents, config={'response_mime_type': 'application/json'}
        )

        # Städa upp filer hos Gemini
        for f in uploaded_files:
            try:
                client.files.delete(name=f.name)
            except Exception:
                pass

        try:
            data = json.loads(response.text)
            # Säkerställ fallback för datum om AI missade det
            if not data.get("due_date"):
                data["due_date"] = now_str
            return data
        except json.JSONDecodeError:
            LOGGER.error("Kunde inte tolka JSON från Gemini: %s", response.text)
            return {
                "sender": sender,
                "due_date": now_str,
                "amount": "?",
                "invoice_number": "Okänd",
                "suggested_filename": f"Okand_{now_str}_{unique_id}.pdf",
                "is_invoice": False
            }

    def _upload_to_drive(self, file_path, ai_data):
        """Laddar upp filen till Google Drive i struktur Grundmapp/ÅÅÅÅ/Månad/."""
        if not self.gdrive_credentials or not os.path.exists(self.gdrive_credentials):
            raise FileNotFoundError(f"Credentials-fil saknas: {self.gdrive_credentials}")

        creds = service_account.Credentials.from_service_account_file(
            self.gdrive_credentials, scopes=['https://www.googleapis.com/auth/drive']
        )
        service = build('drive', 'v3', credentials=creds)

        # 1. Hitta/Skapa Grundmapp
        root_id = self._get_folder_id(service, self.gdrive_root)
        if not root_id:
            # Om grundmappen inte hittas, kanske vi ska skapa den?
            # Eller så är self.gdrive_root redan ett ID.
            # Vi antar här att det är ett NAMN först, om misslyckas antar vi ID.
            # För enkelhetens skull i denna implementation skapar vi den i roten om den inte finns.
            root_id = self._create_folder(service, self.gdrive_root, None)

        # 2. Hämta datum för mappstruktur
        due_date_str = ai_data.get("due_date")
        try:
            date_obj = datetime.strptime(due_date_str, "%Y-%m-%d")
        except ValueError:
            date_obj = dt_util.now()

        year_str = str(date_obj.year)
        month_str = SVENSKA_MANADER[date_obj.month]

        # 3. Hitta/Skapa År-mapp
        year_folder_id = self._get_folder_id(service, year_str, parent_id=root_id)
        if not year_folder_id:
            year_folder_id = self._create_folder(service, year_str, root_id)

        # 4. Hitta/Skapa Månad-mapp
        month_folder_id = self._get_folder_id(service, month_str, parent_id=year_folder_id)
        if not month_folder_id:
            month_folder_id = self._create_folder(service, month_str, year_folder_id)

        # 5. Ladda upp filen
        filename = ai_data.get("suggested_filename", os.path.basename(file_path))

        file_metadata = {
            'name': filename,
            'parents': [month_folder_id]
        }
        # Konvertera till sträng för google-api-client
        media = MediaFileUpload(str(file_path), mimetype='application/pdf')

        file = service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()

        if self.enable_debug:
            LOGGER.info(f"Fil uppladdad till Drive ID: {file.get('id')}")

        return file.get('webViewLink')

    def _get_folder_id(self, service, folder_name, parent_id=None):
        """Hjälpfunktion för att hitta en mapps ID."""
        query = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false"
        if parent_id:
            query += f" and '{parent_id}' in parents"

        results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        items = results.get('files', [])

        if not items:
            return None
        return items[0]['id']

    def _create_folder(self, service, folder_name, parent_id=None):
        """Hjälpfunktion för att skapa en mapp."""
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        if parent_id:
            file_metadata['parents'] = [parent_id]

        file = service.files().create(body=file_metadata, fields='id').execute()
        return file.get('id')

    def _notify_hass(self, title, message):
        """Skicka persistent notification."""
        self.hass.async_create_task(
            self.hass.services.async_call(
                "persistent_notification", "create",
                {
                    "title": title,
                    "message": message,
                    "notification_id": f"mail_agent_error_{uuid.uuid4()}"
                }
            )
        )

    def _notify_hass_success(self, ai_data, drive_link):
        """Skicka bekräftelse på lyckad hantering."""
        sender = ai_data.get("sender", "Okänd")
        amount = ai_data.get("amount", "?")
        due = ai_data.get("due_date", "Okänt")

        msg = f"**Avsändare:** {sender}\n**Summa:** {amount}\n**Förfaller:** {due}\n\n"
        if drive_link:
            msg += f"[Öppna i Google Drive]({drive_link})"
        else:
            msg += "Sparad lokalt (Drive ej konfigurerat/misslyckades)."

        self.hass.async_create_task(
            self.hass.services.async_call(
                "persistent_notification", "create",
                {
                    "title": "Faktura Hanterad",
                    "message": msg,
                    "notification_id": f"mail_agent_invoice_{uuid.uuid4()}"
                }
            )
        )
