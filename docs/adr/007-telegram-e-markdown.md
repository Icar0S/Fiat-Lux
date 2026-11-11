# ADR-007: Telegram + arquivo Markdown

- **Status:** aceito (2026-11-09)

## Contexto

Canal simples, gratuito e privado.

## Decisão

Bot do Telegram (HTML, partes ≤ 4.096 caracteres por seção, allowlist, reenvio sem formatação em caso de 400, feedback por `getUpdates`) e arquivo em `saidas/AAAA/MM/`. E-mail via SMTP como opção.

## Consequências

Sem servidor: o feedback é lido a cada execução. Alternativas: WhatsApp (API paga), site.

## Adendo (2026-11-11): e-mail como canal provisório

Enquanto o bot do Telegram não está configurado, a entrega padrão passou a ser por **e-mail**
(`[entrega] email = true`, `telegram = false`): SMTP da conta de quem envia (no Gmail, com senha
de app), STARTTLS na 587 ou SSL na 465, e a senha nunca vai sem TLS. Um e-mail por
destinatário, com HTML e texto puro; a Palavra da Semana leva o gráfico em anexo. O alerta de
falha vai ao `EMAIL_ADMIN` (sem ele, a quem envia). No banco de estado, que vai para a branch
`estado`, o destinatário de e-mail fica só como `email:` e 12 caracteres do SHA-256 do endereço,
o bastante para a idempotência. O código do Telegram continua: `telegram = true` o religa. O
feedback 👍/👎 só existe no Telegram.
