# ADR-009: GitHub Actions + estado em branch

- **Status:** aceito (2026-11-09)

## Contexto

Execução agendada sem servidor próprio.

## Decisão

Cron diário (08:00 UTC = 05:00 Fortaleza) e semanal (sábado 20:00 UTC); `concurrency: fiat-lux`; `estado.sqlite` numa branch órfã `estado`; `biblia.sqlite` como asset de Release (`construir-indice.yml`); modelos do HF em `actions/cache`.

## Consequências

Requer criar a branch `estado` e os segredos; as actions devem ser fixadas por SHA antes de ir ao ar (§13.1). Alternativa B: VPS com systemd timer.
