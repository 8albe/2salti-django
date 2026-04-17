#!/bin/bash
echo "Installing ops timers..."
sudo cp /home/alberto/2salti-ops-*.service /etc/systemd/system/
sudo cp /home/alberto/2salti-ops-*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now 2salti-ops-morning.timer
sudo systemctl enable --now 2salti-ops-afternoon.timer
sudo systemctl enable --now 2salti-ops-evening.timer
echo "Ops timers installed and enabled."
