# WireGuard-VPN (wg-easy) – Setup-Runbook

Ziel: Sicherer Fernzugriff auf die App/den Server über WireGuard, mit Web-Oberfläche
(wg-easy v15) und Handy-Einrichtung per QR-Code. **Kostenlos**, läuft auf dem vorhandenen
Strato-VPS als eigenständiger Docker-Stack (unabhängig vom App-Deploy).

Empfohlene Nutzung (Skalierung: mehrere Teams, viele mobile Nutzer*innen):
**Admin-only** – App bleibt öffentlich (mobil reibungslos), nur `/admin/` übers VPN
(`ADMIN_ALLOW_CIDR` = VPN-Subnetz). Voll-VPN für alle Feldkräfte skaliert schlecht.

> Hinweis: Ab wg-easy **v14/v15** wird das Web-UI-Passwort NICHT mehr per Env/`wgpw` gesetzt,
> sondern über einen **Setup-Assistenten beim ersten Öffnen im Browser**. Nie ein Passwort in
> einen Shell-Befehl oder Chat tippen.

---

## 1. Firewall (als root)
```bash
ufw allow 51820/udp          # WireGuard-Port
ufw status                   # 22, 80, 443, 51820 offen; 51821 (Web-UI) NICHT
```

## 2. Verzeichnis + Compose anlegen
```bash
mkdir -p /srv/wireguard && cd /srv/wireguard && nano docker-compose.yml
```
Inhalt:
```yaml
services:
  wg-easy:
    image: ghcr.io/wg-easy/wg-easy:15
    container_name: wg-easy
    restart: unless-stopped
    environment:
      - INSECURE=true               # Web-UI ohne HTTPS – ok, weil nur lokal via SSH-Tunnel
    volumes:
      - etc_wireguard:/etc/wireguard
      - /lib/modules:/lib/modules:ro
    ports:
      - "51820:51820/udp"           # WireGuard
      - "127.0.0.1:51821:51821/tcp" # Web-UI NUR localhost (per SSH-Tunnel bedienen)
    cap_add:
      - NET_ADMIN
      - SYS_MODULE
    sysctls:
      - net.ipv4.ip_forward=1
      - net.ipv4.conf.all.src_valid_mark=1
volumes:
  etc_wireguard:
```

## 3. Starten
```bash
cd /srv/wireguard && docker compose up -d && docker compose logs --tail=20
```

## 4. Web-UI über SSH-Tunnel bedienen (vom eigenen PC)
```bash
ssh -L 51821:localhost:51821 root@<SERVER-IP>
```
Dann im Browser `http://localhost:51821` öffnen → **Setup-Assistent**:
- Admin-Benutzer + **frisches, einzigartiges Passwort** anlegen (nur hier im Browser eingeben).
- **Host** = `leistungsnachweis.eingliederungshilfe.cloud`.
- Das angezeigte **Client-Subnetz** notieren (v15 Standard meist `10.42.42.0/24`).

## 5. Gerät anlegen + Handy verbinden
- Web-UI → **„New Client"** → Name (z. B. „Mirko-Handy").
- **WireGuard-App** aufs Handy (App Store / Play Store, kostenlos) → „+" → „QR-Code scannen".
- Für Laptops: Config-Datei herunterladen und in die WireGuard-Desktop-App importieren.

## 6. Verbindung testen
Bei aktivem Tunnel bekommt das Gerät eine Adresse aus dem Client-Subnetz; die App
`https://leistungsnachweis.eingliederungshilfe.cloud` ist erreichbar. Im Web-UI erscheint der
Client als „verbunden" (Handshake).

## 7. `/admin/` ans VPN binden (Admin-only)
Client-Subnetz aus dem Assistenten (z. B. `10.42.42.0/24`) eintragen:
```bash
echo 'ADMIN_ALLOW_CIDR=10.42.42.0/24' >> /srv/fegh/deploy/.env.prod
cd /srv/fegh/deploy && docker compose up -d
```
`/admin/` ist ab jetzt nur mit aktivem VPN erreichbar; die App selbst bleibt für alle offen.

## Betrieb
- **Gerät sperren** (Verlust/Austritt): im Web-UI den Client löschen.
- **Updates:** `cd /srv/wireguard && docker compose pull && docker compose up -d`.
- Der Stack ist unabhängig vom App-Deploy – App-Updates berühren das VPN nicht.
