# VPN-Zugang & Admin-Schutz (WireGuard)

Der Django-Admin (`/admin/`) ist ein mächtiger Break-Glass-Bereich. Damit er **nicht aus dem
offenen Internet** erreichbar ist, wird er hinter ein **WireGuard-VPN** gelegt. Die eigentliche
App bleibt öffentlich erreichbar (TLS + 2FA + Login-Lockout) – das ist bewusst so gewählt.

!!! info "Warum nur `/admin/` hinter VPN – nicht die ganze App?"
    Die App soll von **mehreren Teams mit vielen mobilen Nutzer\*innen** verwendet werden. Ein VPN
    vor der **gesamten** App würde bedeuten, dass **jedes Diensthandy** dauerhaft per WireGuard
    verbunden sein muss – das skaliert schlecht und bremst die Vor-Ort-Dokumentation. Deshalb:
    App öffentlich (mit HTTPS, 2FA-Pflicht, `django-axes`-Lockout, HSTS), und nur der seltene
    Admin-Zugriff läuft über das VPN. Eine spätere Voll-VPN-Variante (Firewall sperrt 80/443
    außer aus dem VPN) ist möglich, wird für den Mehr-Team-Betrieb aber nicht empfohlen.

## Architektur

```
Internet ──► Caddy (443) ──► App (öffentlich, TLS+2FA)
                 │
                 └─ /admin/*  ──► nur erlaubt, wenn Quelle im zugelassenen Netz (VPN)

Admin-Gerät ──(WireGuard)──► wg-easy (VPN) ──► Server ──► Caddy sieht „Host-/VPN-Quelle"
```

- **wg-easy** (WireGuard mit Web-Oberfläche) läuft als **eigenständiger** Docker-Stack unter
  `/srv/wireguard/` – unabhängig vom App-Deploy (App-Updates berühren das VPN nicht).
- Das Web-Panel ist **nur auf `127.0.0.1:51821`** gebunden und wird über einen **SSH-Tunnel**
  bedient – es ist nicht aus dem Internet erreichbar. Offen nach außen ist nur der
  WireGuard-Port **`51820/udp`**.
- Kostenlos, Open Source, keine Lizenz- oder Pro-Gerät-Gebühr.

## Admin-Beschränkung in Caddy

Die `deploy/Caddyfile` sperrt `/admin/*`, wenn die Quell-IP **nicht** im zugelassenen Netz liegt:

```caddy
@admin_blocked {
    path /admin/*
    not remote_ip {$ADMIN_ALLOW_CIDR:127.0.0.1/32}
}
respond @admin_blocked "Zugriff auf diesen Bereich ist nur aus dem zugelassenen Netz erlaubt." 403
```

- Domain und zugelassenes Netz kommen aus `.env.prod` (`CADDY_DOMAIN`, `ADMIN_ALLOW_CIDR`),
  damit die `Caddyfile` **nicht lokal editiert** werden muss (sonst Merge-Konflikte bei jedem Deploy).
- Ohne gesetzte Variable ist `/admin/` von außen gesperrt (nur `127.0.0.1`) – **sicher per Default**.

!!! warning "Wichtiger Wert: `ADMIN_ALLOW_CIDR=172.18.0.1/32` (nicht das VPN-Client-Netz!)"
    wg-easy **maskiert** den VPN-Verkehr (NAT). Beim Hineinreichen über den Docker-Host kommt er
    bei Caddy als **Docker-Gateway-Adresse `172.18.0.1`** an – **nicht** als VPN-Client-IP
    (`10.8.0.x`). Direkter Internet-Verkehr zeigt dagegen immer die echte Client-IP. Deshalb wird
    `172.18.0.1/32` erlaubt: Nur VPN-/Host-Verkehr trägt diese Adresse, Bots aus dem Netz bleiben
    draußen. Verifiziert über das Caddy-Access-Log (`docker compose exec caddy tail /data/access.log` →
    Feld `remote_ip`). Fällt **sicher aus** (sperrt, öffnet nie), falls das Docker-Netz umnummeriert.

## Einrichtung (Kurzfassung)

Vollständiges Runbook: `deploy/wireguard-setup.md`. Wesentliche Schritte:

1. **Firewall:** `ufw allow 51820/udp`.
2. **Stack** unter `/srv/wireguard/docker-compose.yml` (Image `ghcr.io/wg-easy/wg-easy:15`,
   Web-UI nur `127.0.0.1:51821`), dann `docker compose up -d`.
3. **Web-Panel** per SSH-Tunnel öffnen: `ssh -L 51821:localhost:51821 root@<SERVER-IP>` →
   `http://localhost:51821` → **Setup-Assistent**: Admin-Konto + Passwort, Host = Domain.
4. **Gerät anlegen** → QR-Code mit der **WireGuard-App** (iOS/Android) scannen.
5. **`/admin/` binden:** `echo 'ADMIN_ALLOW_CIDR=172.18.0.1/32' >> /srv/fegh/deploy/.env.prod`
   und die App neu starten (`docker compose up -d`).

!!! note "wg-easy v15 statt v13"
    Ab Version 14/15 wird das Web-UI-Passwort **nicht** mehr per `wgpw`/`PASSWORD_HASH` gesetzt,
    sondern über den **Setup-Assistenten im Browser**. Ein Passwort niemals in einen Shell-Befehl
    oder Chat tippen.

## Test

| Situation | Aufruf `…/admin/` | Erwartung |
|-----------|-------------------|-----------|
| **VPN aus** | über Mobilfunk/Internet | **403** (gesperrt) |
| **VPN an** | WireGuard verbunden | **Django-Admin-Login** erscheint |
| beide | normale App (ohne `/admin/`) | immer erreichbar |

## Betrieb

- **Gerät sperren** (Verlust/Austritt): im wg-easy-Web-Panel den Client löschen.
- **Updates:** `cd /srv/wireguard && docker compose pull && docker compose up -d`.
- **Optionale Zusatzhärtung:** `/admin/` zusätzlich mit einem **Caddy-Passwort (Basic-Auth)**
  absichern – NAT-unabhängig, funktioniert unabhängig vom Docker-Netz.
