## 8. OCR — Perfezionamento e affidabilità

Stato: 🔄 In corso

Miglioramento accuracy, preprocessing, gestione errori, dataset test, qualità dati estratti.

### 8.1 Pipeline esistente

- [x] Provider astratto (`vision_providers.py`), GPT-4V in prod, mock in test
- [x] Quality gate (`ocr_quality_gate.py`) pre-EXTRACTED
- [x] Dedup via SHA-256 (`hash_service.py`)
- [x] Raw response salvata (`OCRRawResponse`) per audit
- [x] Workflow stati referto completo (UPLOADED → PROCESSING → EXTRACTED → VALIDATED → PUBLISHED + branch NEEDS_REVIEW/REJECTED)

### 8.2 Affidabilità da migliorare

- [ ] Dataset di test con referti reali rappresentativi (accuracy baseline misurabile)
- [ ] Gestione multi-page PDF: concatenazione pagine prima dell'estrazione
- [ ] Metriche qualità: success rate per campo, tempo medio upload→publish
- [ ] Cluster E KO residui — guardia early-return in `ocr_service.py:254` che cortocircuita exception path per NEEDS_REVIEW
- [ ] Cluster D KO residui — verifica `MatchReportUploadForm.clean()` interroga davvero `MatchReport.objects.filter(file_hash=…)`

---

← [Macro precedente](7_profilo_fan.md) | → [Macro successiva](9_sistema_sponsor.md)
