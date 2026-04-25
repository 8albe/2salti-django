# Systemd unit per 2salti

Questa directory contiene la unit `2salti.service` e il drop-in
`override.conf`. Sono la sorgente di verità in repo per la
configurazione del service.

## File

- `2salti.service` — unit principale del service gunicorn.
- `2salti.service.d/override.conf` — drop-in con `ExecReload=`
  per supportare `systemctl reload`.

## Procedura di deploy

La unit attiva su sistema vive in `/etc/systemd/system/`. Per
propagare modifiche fatte in repo:

```bash
sudo cp /home/alberto/deploy/systemd/2salti.service /etc/systemd/system/2salti.service
sudo mkdir -p /etc/systemd/system/2salti.service.d
sudo cp /home/alberto/deploy/systemd/2salti.service.d/override.conf /etc/systemd/system/2salti.service.d/override.conf
sudo systemctl daemon-reload
sudo systemctl reload 2salti  # oppure restart se cambia ExecStart
```

## Verifica post-deploy

```bash
sudo systemctl cat 2salti
sudo systemctl status 2salti
curl -I -s https://2salti.com/ | head -3
```

## Importante

- Le modifiche fatte direttamente con `systemctl edit` o
  editing diretto di `/etc/systemd/system/2salti.service`
  **non vengono sincronizzate automaticamente** in repo.
  Vanno copiate qui manualmente dopo l'edit.
- Se cambi `ExecStart` o paths runtime serve `restart` non
  `reload`.
