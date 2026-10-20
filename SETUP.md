# Setup: Accounts, Tools & Azure

Reihenfolge einhalten. Alles in **Teil A** heute erledigen (ca. 1–2 h), Teil C erst wenn das Grundgerüst steht.

## A. Accounts (heute)

| # | Account | Wozu | Hinweis |
|---|---|---|---|
| 1 | **Hackathon-Anmeldung** | Teilnahme, Team registrieren | Regeln + exakte Deadline (Zeitzone!) lesen. Prüfen, ob der Hackathon **Azure-Credits** vergibt — dann diese statt Student-Guthaben nutzen |
| 2 | **Microsoft-Konto** | Login für Azure | Am besten mit der ETH-Mail, damit Azure for Students funktioniert |
| 3 | **Azure for Students** | Cloud + KI-Modelle | azure.microsoft.com/free/students · ca. 100 $ Guthaben, keine Kreditkarte, Verifizierung über ETH-Mail |
| 4 | **GitHub** | Öffentliches Repo (Pflicht) | Repo erst öffentlich schalten, wenn sicher keine Keys drin sind |
| 5 | **GitHub Student Developer Pack** | Copilot, Codespaces-Stunden u. a. | education.github.com/pack · Codespaces = Linux-x86-Rechner, ideal falls GRF auf dem Mac zickt |
| 6 | **YouTube** (oder Vimeo) | Demo-Video mit öffentlicher URL | Video öffentlich oder „nicht gelistet“ hochladen |
| 7 | *optional* **Hugging Face** | Vortrainierte Modelle laden | Nur falls ein Modell es verlangt |
| 8 | *optional* **Roboflow** | Vortrainierte Fußball-Modelle / Datasets | Nur falls ihr deren gehostete Modelle nutzt; `supervision` braucht keinen Account |

Teammitglieder: jede Person braucht eigenes GitHub + Microsoft-Konto. Azure-Abo **eines** Mitglieds nutzen und die anderen per
*Zugriffssteuerung (IAM) → Rolle „Contributor“* auf die Ressourcengruppe einladen.

## B. Lokale Tools (heute)

```bash
brew install azure-cli azd uv node git gh
```

Zusätzlich: **Docker Desktop** (für Google Research Football), **Claude Code** (habt ihr), optional VS Code.

Hinweis Apple Silicon: GRF ist Linux/x86. Wenn es in Docker zu langsam oder kaputt ist → **GitHub Codespaces** oder eine
kleine Azure-Linux-VM nehmen (VM nach Gebrauch **stoppen/löschen**).

## C. Azure-Ressourcen (sobald das Grundgerüst steht)

**Region:** eine Region mit guter Modell-Verfügbarkeit in Europa wählen, z. B. `swedencentral`. Alles in **eine** Ressourcengruppe.

```bash
az login
az group create -n rg-slidingdoors -l swedencentral
```

| Ressource | Wozu | Tier / Kosten | Wie |
|---|---|---|---|
| **Microsoft Foundry** (Resource + Project) | Modelle (Azure OpenAI), Agenten, Observability | Pay per Token | Portal ai.azure.com → Projekt anlegen in `rg-slidingdoors` |
| Modell-Deployment „klein & schnell“ | Analyst, Narrator live | günstig | Im Foundry-Katalog das aktuelle Mini-Modell der GPT-Familie deployen |
| Modell-Deployment „groß“ | Recap, schwierige Hypothesen | teurer | Aktuelles großes GPT-Modell, sparsam nutzen |
| **Event Hubs** | Live-Event-Stream (Hero-Tech) | Basic, wenige $/Monat | `az eventhubs namespace create -g rg-slidingdoors -n <name> --sku Basic` + Hub `match-events` |
| **Web PubSub** | Live-Updates ans Frontend | Free-Tier | `az extension add -n webpubsub` → `az webpubsub create -g rg-slidingdoors -n <name> --sku Free_F1` |
| **Container Apps** + **Container Registry** | Backend hosten | Consumption + ACR Basic | Später per `azd up` aus `infra/` |
| **Static Web Apps** | Frontend hosten | Free | Später per `azd up` |
| **Application Insights** | Monitoring, Latenz-Metriken | Free-Kontingent reicht | Wird mit Foundry/azd mit angelegt |
| *optional* **AI Speech** | TTS-Kommentar | F0 Free | Nur wenn Zeit bleibt |

**Wichtig:** Prüfe direkt nach dem Anlegen des Foundry-Projekts, ob du mit dem Student-Abo Modelle deployen kannst und wie hoch
das Quota (Tokens/min) ist. Wenn nicht: Hackathon-Credits oder Pay-as-you-go — das früh klären, nicht an Tag 5.

## D. Kostenkontrolle (Pflicht)

1. Portal → **Cost Management → Budgets** → Budget 50 $ mit E-Mail-Alarm bei 50 %, 80 %, 100 %.
2. Keine GPU-VMs dauerhaft laufen lassen.
3. Nach dem Hackathon: Demo-URL ggf. noch für die Jurierung laufen lassen, danach `az group delete -n rg-slidingdoors`.
4. Keys nach dem Hackathon **rotieren**.

## E. Secrets

- Alle Keys/Endpoints nur in `.env` (Vorlage: `.env.example`), `.env` steht in `.gitignore`.
- Für Azure nach Möglichkeit `DefaultAzureCredential` (Login via `az login`) statt API-Keys.
