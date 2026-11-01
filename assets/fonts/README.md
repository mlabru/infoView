# Fontes

| Arquivo | Uso | Fonte / autor | Licença |
|---------|-----|---------------|---------|
| `LiberationSans-Regular.ttf` | todos os textos | Liberation Sans 2.1 — Red Hat / Google (Arimo) | SIL Open Font License 1.1 — `LICENSE-LiberationSans` |
| `DSEG7Classic-Regular.ttf` | dígitos do relógio | DSEG 0.46 (DSEG7 Classic) — keshikan, https://github.com/keshikan/DSEG | SIL Open Font License 1.1 — `LICENSE-DSEG` |

As duas são livres: podem ser redistribuídas com o projeto (com o arquivo de licença ao lado).

A Liberation Sans tem as mesmas métricas da Arial (que é proprietária e foi retirada daqui):
o layout não muda. No Raspberry Pi OS ela também existe em
`/usr/share/fonts/truetype/liberation/` (pacote `fonts-liberation`).

A DSEG7 Classic substituiu a DS-Digital (DS-DIGI.TTF, "All Rights Reserved", não livre). Os
dígitos da DSEG têm todos a mesma largura (os dois pontos não se mexem); ela é mais larga que a
DS-Digital, mas o relógio ajusta o tamanho da fonte à área ("88:88" + segundos), então o
layout se adapta sozinho. "DSEG" é nome reservado da fonte (OFL): o arquivo vai sem
modificações.

Os caminhos usados pelo código estão em `infoview/core/settings.py` (`DS_FONT_TEXT`,
`DS_FONT_DIGITAL`).
