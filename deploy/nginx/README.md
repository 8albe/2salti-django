# Config nginx per 2salti

Questa directory contiene le copie canoniche in repo delle config
nginx dei due siti (prod e dev). Il file attivo vive **fuori repo**
(`/etc/nginx/sites-available/`) e la sincronizzazione è manuale,
stesso pattern della unit systemd (`deploy/systemd/`, OPS_RUNBOOK §9)
e delle config gunicorn (`deploy/gunicorn/`, OPS_RUNBOOK §9).

## File

- `prod/2salti` — copia canonica di
  `/etc/nginx/sites-available/2salti` (symlink in `sites-enabled/`).
- `dev/2salti-dev` — copia canonica di
  `/etc/nginx/sites-available/2salti-dev` (symlink in `sites-enabled/`).

## Procedura di deploy

```bash
sudo cp /home/alberto/deploy/nginx/prod/2salti /etc/nginx/sites-available/2salti
sudo nginx -t && sudo systemctl reload nginx

sudo cp /home/alberto/deploy/nginx/dev/2salti-dev /etc/nginx/sites-available/2salti-dev
sudo nginx -t && sudo systemctl reload nginx
```

`nginx -t` prima del reload è obbligatorio: un errore di sintassi
nel file copiato non deve mai arrivare a un reload che uccide il
proxy in produzione.

## Verifica post-deploy

```bash
diff /home/alberto/deploy/nginx/prod/2salti /etc/nginx/sites-available/2salti
diff /home/alberto/deploy/nginx/dev/2salti-dev /etc/nginx/sites-available/2salti-dev
curl -I -s https://2salti.com/ | head -3
```

## Importante

- Le modifiche fatte direttamente su `/etc/nginx/sites-available/`
  **non si sincronizzano da sole** in repo: vanno riportate qui a
  mano, altrimenti il prossimo deploy dal repo le cancella (stesso
  drift descritto in OPS_RUNBOOK §9 per la unit systemd). Caso reale:
  il fix `proxy_read_timeout 300s` in `prod/2salti` (2026-07-19,
  OPS_RUNBOOK §3.16) è stato applicato direttamente sul sistema
  prima di essere versionato qui — vedi OPS_RUNBOOK §10.17.
- Le due config **divergono volutamente** (dev non ha
  `proxy_read_timeout` esteso, usa un blocco `proxy_set_header`
  esplicito invece di `include proxy_params`): non copiare la prod
  sul dev o viceversa.
- Il file legacy `2salti_nginx_config` citato in `CLAUDE.md` e nel
  vecchio `.gitignore` non è mai esistito in questa copia del repo;
  questa directory lo sostituisce come copia canonica.
