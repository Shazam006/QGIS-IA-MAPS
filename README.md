# QGIS-IA-MAPS

Complemento QGIS para automação cartográfica e geração de mapas com IA.

## Objetivo

O projeto cria uma ponte controlada entre um agente MCP e o QGIS, focada em automação de mapas e layouts. A V1 não tenta reproduzir todas as ferramentas do qgis-mcp original; ela expõe operações cartográficas de alto nível.

## Arquitetura

```text
Agente de IA
    |
    | MCP / stdio
    v
qgis-ia-maps-server (Python/FastMCP)
    |
    | TCP localhost
    v
QGIS-IA-MAPS Plugin
    |
    v
PyQGIS
```

## V1

- detectar projeto e camadas;
- criar layout A4/A3 em retrato ou paisagem;
- adicionar título, legenda, escala, norte e fonte;
- enquadrar mapa nas camadas escolhidas;
- aplicar estilo simples por categoria ou cor única;
- exportar PDF/PNG;
- salvar projeto;
- executar uma sequência de operações como um único fluxo.

## Segurança

A ponte TCP é local por padrão (`127.0.0.1:9877`). Não exponha essa porta diretamente à internet. A integração MCP externa deve usar autenticação/túnel apropriado quando necessária.

## Compatibilidade

Desenvolvimento inicial direcionado ao QGIS 3.34+ e Python 3.x embarcado no QGIS.

## Referência arquitetural

O projeto foi desenhado com base no padrão usado pelo `nkarasiak/qgis-mcp`: um processo MCP externo conversa com um servidor dentro do QGIS por socket local, e o servidor dentro do QGIS executa operações usando PyQGIS.
