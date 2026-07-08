# WireGuard-VPN (wg-easy) – Setup-Runbook

Ziel: Sicherer Fernzugriff auf die App/den Server über WireGuard, mit Web-Oberfläche
(wg-easy) und Handy-Einrichtung per QR-Code. **Kostenlos**, läuft auf dem vorhandenen
Strato-VPS als eigenständiger Docker-Stack (unabhängig vom App-Deploy).

Zwei Nutzungsstufen (erst VPN aufbauen, dann entscheiden):
- **A · Admin-only:** App bleibt öffentlich (mobil reibungslos), nur `/admin/` übers VPN –
  dazu `ADMIN_ALLOW_CIDR=10.8.0.0/24` in der App-`.env.prod`.
- **B · Voll-VPN:** App aus dem Internet gesperrt (Firewall 80/443 nur aus dem VPN),
  alle Geräte per WireGuard. Maximale Sicherheit, jedes Diensthandy braucht „always-on".

---

## 1. Firewall (als root)
```bash
ufw allow 51820/udp          # WireGuard-Port
ufw status                   # 22, 80, 443, 51820 offen; 51821 (Web-UI) NICHT
```

## 2. Verzeichnis + Compose anlegen
```bash
mkdir -p /srv/wireguard && cd /srv/wireguard
```
`/srv/wireguard/docker-compose.yml` mit diesem Inhalt anlegen (`nano docker-compose.yml`):
```yaml
services:
  wg-easy:
    image: ghcr.io/wg-easy/wg-easy:13
    container_name: wg-easy
    restart: unless-stopped
    environment:
      - WG_HOST=leistungsnachweis.eingliederungshilfe.cloud   # oder die öffentliche IP
      - PASSWORD_HASH=ERSETZEN                                  # siehe Schritt 3 ($ verdoppeln!)
      - WG_DEFAULT_ADDRESS=10.8.0.x
      - WG_DEFAULT_DNS=9.9.9.9
      - WG_ALLOWED_IPS=0.0.0.0/0, ::/0     # Voll-Tunnel: alles durch die VPN (einfach & sicher)
      - WG_PERSISTENT_KEEPALIVE=25         # hält die Verbindung mobil stabil
    volumes:
      - ./wg-data:/etc/wireguard
    ports:
      - "51820:51820/udp"                  # WireGuard (in der Firewall offen)
      - "127.0.0.1:51821:51821/tcp"        # Web-UI NUR localhost -> per SSH-Tunnel bedienen
    cap_add: [NET_ADMIN, SYS_MODULE]
    sysctls:
      - net.ipv4.ip_forward=1
      - net.ipv4.conf.all.src_valid_mark=1
```

## 3. Web-UI-Passwort als Hash erzeugen
```bash
docker run --rm ghcr.io/wg-easy/wg-easy:13 wgpw 'DEIN-SICHERES-PASSWORT'
```
Ausgabe z. B. `PASSWORD_HASH='$2a$12$abc…'`. Den Hash (zwischen den Anführungszeichen)
in die Compose eintragen und dabei **jedes `$` verdoppeln** (Docker-Compose-Regel), also
`$2a$12$…` → `$$2a$$12$$…`.

## 4. Starten
```bash
cd /srv/wireguard && docker compose up -d
docker compose logs --tail=20        # sollte "Listening on ... :51820" o. Ä. zeigen
```

## 5. Web-UI über SSH-Tunnel bedienen (vom eigenen PC)
```bash
ssh -L 51821:localhost:51821 root@<SERVER-IP>
```
Dann im Browser `http://localhost:51821` öffnen, mit dem Passwort aus Schritt 3 anmelden.
(Die Web-UI ist bewusst NICHT im Internet erreichbar – nur über diesen Tunnel.)

## 6. Gerät anlegen + Handy verbinden
- Im Web-UI **„New Client"** → Name (z. B. „Mirko-Handy") → Client wird angelegt.
- **WireGuard-App** aufs Handy (App Store / Play Store, kostenlos) → „+" → „QR-Code scannen"
  → den im Web-UI angezeigten QR scannen → Tunnel aktivieren.
- Für Laptops: Config-Datei herunterladen und in die WireGuard-Desktop-App importieren.

## 7. Verbindung testen
Auf dem Handy bei aktivem Tunnel: das Gerät bekommt eine `10.8.0.x`-Adresse; die App
`https://leistungsnachweis.eingliederungshilfe.cloud` ist erreichbar. Im Web-UI wird der
Client als „verbunden" (Handshake) angezeigt.

## 8. Danach: Zugriff absichern
- **Variante A (Admin-only):**
  ```bash
  echo 'ADMIN_ALLOW_CIDR=10.8.0.0/24' >> /srv/fegh/deploy/.env.prod
  cd /srv/fegh/deploy && docker compose up -d
  ```
  `/admin/` ist ab jetzt nur mit aktivem VPN erreichbar (Caddy sieht die `10.8.0.x`-Quelle).
- **Variante B (Voll-VPN):** zusätzlich am Server 80/443 nur aus dem VPN erlauben
  (z. B. `ufw` Regeln auf `10.8.0.0/24` beschränken) – das besprechen wir separat, weil
  dann alle Geräte immer per VPN verbunden sein müssen.

## Betrieb
- **Gerät sperren** (Verlust/Austritt): im Web-UI den Client löschen/deaktivieren.
- **Updates:** `cd /srv/wireguard && docker compose pull && docker compose up -d`.
- Der Stack ist unabhängig vom App-Deploy – App-Updates berühren das VPN nicht.
