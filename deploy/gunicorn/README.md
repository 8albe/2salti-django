# Config gunicorn per 2salti

Questa directory contiene le copie canoniche in repo delle config
gunicorn dei due box di deploy. I file attivi vivono **fuori repo**
(`gunicorn_config.py` è in `.gitignore` alla root) e la
sincronizzazione è manuale, come per la unit systemd
(`deploy/systemd/`, OPS_RUNBOOK §9).

## File

- `prod/gunicorn_config.py` — copia canonica di
  `/opt/2salti-new/gunicorn_config.py` (caricata dalla unit
  `2salti.service` via `--config`).
- `dev/gunicorn_config.py` — copia canonica di
  `/opt/2salti-dev/gunicorn_config.py` (unit `2salti-dev.service`).

## Procedura di deploy

```bash
cp /home/alberto/deploy/gunicorn/prod/gunicorn_config.py /opt/2salti-new/gunicorn_config.py
sudo systemctl reload 2salti   # SIGHUP: gunicorn rilegge la config e ricicla i worker

cp /home/alberto/deploy/gunicorn/dev/gunicorn_config.py /opt/2salti-dev/gunicorn_config.py
sudo systemctl reload 2salti-dev
```

Se la modifica tocca `bind` o altri parametri letti solo all'avvio
del master, serve `restart` invece di `reload`.

## Verifica post-deploy

```bash
diff /home/alberto/deploy/gunicorn/prod/gunicorn_config.py /opt/2salti-new/gunicorn_config.py
diff /home/alberto/deploy/gunicorn/dev/gunicorn_config.py /opt/2salti-dev/gunicorn_config.py
curl -I -s https://2salti.com/ | head -3
```

## Importante

- Le modifiche fatte direttamente sui file in `/opt/` **non si
  sincronizzano da sole** in repo: vanno riportate qui a mano,
  altrimenti il prossimo deploy dal repo le cancella (stesso
  drift descritto in OPS_RUNBOOK §9 per la unit systemd).
- Le due config **divergono volutamente** (socket, numero worker,
  logging): non copiare la prod sul dev o viceversa.
