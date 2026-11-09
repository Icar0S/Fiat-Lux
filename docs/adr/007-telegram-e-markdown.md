# ADR-007: Telegram + arquivo Markdown

- **Status:** aceito (2026-11-09)

## Contexto

Canal simples, gratuito e privado.

## Decisão

Bot do Telegram (HTML, partes ≤ 4.096 caracteres por seção, allowlist, reenvio sem formatação em caso de 400, feedback por `getUpdates`) e arquivo em `saidas/AAAA/MM/`. E-mail via SMTP como opção.

## Consequências

Sem servidor: o feedback é lido a cada execução. Alternativas: WhatsApp (API paga), site.
