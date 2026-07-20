# Systemd unit per 2salti

Questa directory contiene le unit systemd versionate: sono la sorgente di
verità in repo per la configurazione dei service.

Dal 2026-07-19 (Macro 22) le unit sono divise per box, stesso pattern di
`deploy/gunicorn/` e `deploy/nginx/`: **le config di prod e dev divergono per
disegno** (path, nomi) e non vanno mai copiate da un box all'altro.

## File

- `prod/2salti.service` — unit gunicorn di produzione (`/opt/2salti-new`).
- `prod/2salti.service.d/override.conf` — drop-in con `ExecReload=` per
  supportare `systemctl reload`.
- `prod/2salti-ocrworker.service` — worker della coda OCR su prod (Macro 22).
- `dev/2salti-dev-ocrworker.service` — worker della coda OCR su dev
  (`/opt/2salti-dev`).

Non tutte le unit attive su sistema sono qui: i timer storici (monitor
integrità, ops check, pilot report, scheduler, autopull dev) vivono solo su
sistema e non sono ancora versionati. Il service e il timer di
`recover_stale_reports` arrivano col giro 2 della Macro 22.

> `.gitignore` ignora `*.service` e `*.timer` in tutto il repo e li riammette
> **solo** qui, con `!deploy/systemd/**/*.service` e `!deploy/systemd/**/*.timer`.
> I due asterischi non sono decorativi: con `deploy/systemd/*.service` le unit
> dentro `prod/` e `dev/` verrebbero ignorate in silenzio. Dopo aver aggiunto
> una unit nuova, verificare che compaia in
> `git ls-files --others --exclude-standard deploy/systemd/`.

## Procedura di deploy

Le unit attive su sistema vivono in `/etc/systemd/system/`. Per propagare
modifiche fatte in repo (esempio: prod).

```bash
sudo cp /opt/2salti-new/deploy/systemd/prod/2salti.service /etc/systemd/system/2salti.service
sudo mkdir -p /etc/systemd/system/2salti.service.d
sudo cp /opt/2salti-new/deploy/systemd/prod/2salti.service.d/override.conf /etc/systemd/system/2salti.service.d/override.conf
sudo systemctl daemon-reload
sudo systemctl reload 2salti  # oppure restart se cambia ExecStart
```

### Worker OCR (Macro 22)

Installazione ed enable, per box. Prod:

```bash
sudo cp /opt/2salti-new/deploy/systemd/prod/2salti-ocrworker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now 2salti-ocrworker.service
```

Dev:

```bash
sudo cp /opt/2salti-dev/deploy/systemd/dev/2salti-dev-ocrworker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now 2salti-dev-ocrworker.service
```

> **Trappola: unit Python + log applicativi → serve `PYTHONUNBUFFERED=1`.**
> Python bufferizza `stdout` a blocchi quando non scrive su un terminale, e
> sotto systemd non lo è mai: senza questa variabile il servizio gira
> regolarmente ma è **cieco in journald** — si vedono solo le righe di systemd,
> e il primo output applicativo compare quando il buffer si riempie (o mai, in
> un processo long-running che stampa poco). `stderr` invece è line-buffered e
> arriva subito, quindi il sintomo è asimmetrico: gli errori si vedono, il
> normale funzionamento no. Ogni unit nuova che esegue direttamente Python deve
> avere `Environment=PYTHONUNBUFFERED=1`. Dettaglio in OPS_RUNBOOK §3.17.

Il worker esce da solo (exit 0) quando si accorge che l'SHA di `HEAD` è
cambiato, ma **solo a coda vuota**, mai a metà job; `Restart=always` lo
rilancia col codice nuovo entro pochi secondi. Su prod, dove il pull è
manuale, resta buona norma un `sudo systemctl restart 2salti-ocrworker`
esplicito accanto al restart di `2salti`.

## Verifica post-deploy

```bash
sudo systemctl cat 2salti
sudo systemctl status 2salti
systemctl status 2salti-ocrworker         # worker OCR: deve essere active (running)
journalctl -u 2salti-ocrworker -n 50      # log del worker
curl -I -s https://2salti.com/ | head -3
```

## Importante

- Le modifiche fatte direttamente con `systemctl edit` o editing diretto di
  `/etc/systemd/system/*.service` **non vengono sincronizzate automaticamente**
  in repo. Vanno copiate qui manualmente dopo l'edit.
- Se cambi `ExecStart` o paths runtime serve `restart` non `reload`.
- Drift check byte-a-byte di una unit:
  `xxd /etc/systemd/system/2salti.service | diff - <(xxd deploy/systemd/prod/2salti.service)`
