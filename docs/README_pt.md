# TerraMow para Home Assistant

<div align="center">
  <img src="images/terramow_logo.png" alt="TerraMow Logo" width="400">
</div>

🌐 [English](../README.md) · [Dansk](README_da.md) · [Deutsch](README_de.md) · [Español](README_es.md) · [Français](README_fr.md) · [Italiano](README_it.md) · [Nederlands](README_nl.md) · [Norsk (bokmål)](README_nb.md) · [Polski](README_pl.md) · **Português** · [Suomi](README_fi.md) · [Svenska](README_sv.md) · [Čeština](README_cs.md) · [中文](README_zh.md)

---

Esta é uma integração para o Home Assistant destinada aos corta-relvas robóticos TerraMow.

### Funcionalidades

**Controlo**
- Entidade de corta-relva: iniciar, pausar e regressar à base
- Corte por zonas: entidade de seleção de zona e serviço `terramow.start_select_region`
- Botão de corte das bordas
- Definições a partir do Home Assistant: altura de corte, velocidade, espaçamento, velocidade das lâminas, distância de corte das bordas, modo e ângulos da direção principal, corte minucioso dos cantos, modo de corte das bordas em relva alta
- Manutenção: botões de reposição dos contadores do disco de lâminas e da estação base

**Monitorização**
- Câmara de mapa em tempo real com trajeto de corte, posição do robô e estação base (mais uma câmara apenas com o mapa para painéis, com resolução configurável através das opções)
- Bateria: nível, estado de carregamento, estado da temperatura, carregador ligado, interruptor de alimentação
- Progresso do trabalho: área da sessão atual, progresso (%), duração e tipo de trabalho; tempo total de corte, número de trabalhos e área cortada
- Estado: missão / submissão / estado da missão, modo de operação, modo de energia, motivo do regresso à estação, deteção de chuva, indicador de problema, indicadores de gravação de dados e de conversão de dados
- Mapa: estado, área, indicadores de detetado / construível / em cópia de segurança
- Agenda: próximo início agendado
- Entidade de atualização de firmware, versão do firmware na página do dispositivo e sensor de compatibilidade de versões
- Todas as entidades são atualizadas instantaneamente com os envios push do dispositivo — sem atraso de polling

**Comodidades da integração**
- Descoberta automática via Zeroconf/mDNS
- Fluxo de reconfiguração (alterar o anfitrião/IP sem voltar a adicionar) e fluxo de reautenticação
- Transferência de diagnósticos para relatórios de erros mais fáceis
- Traduzida em 33 idiomas (bg, ca, cs, da, de, el, en, es, et, fi, fr, hr, hu, it, ja, ko, lt, lv, nb, nl, pl, pt, pt-BR, ro, ru, sk, sl, sr, sv, tr, uk, zh-Hans, zh-Hant)
- Comunicação push local baseada em MQTT — sem necessidade de nuvem

### Entidades suportadas

| Plataforma | Entidades |
| --- | --- |
| Corta-relva | Controlo de iniciar / pausar / regressar à base com atividade em tempo real |
| Câmara | Mapa com trajeto, robô e estação base; variante apenas com o mapa |
| Sensor | Nível da bateria, estado da bateria, estado da temperatura da bateria, estado do mapa, área do mapa, altura de corte, velocidade de corte, modo de operação, posição, tempo total de corte / trabalhos / área cortada, área / progresso / duração / tipo de trabalho da sessão atual, tempo restante das lâminas e da estação base, próximo início agendado, compatibilidade de versões, estado da direção principal, modo de energia, motivo do regresso à estação, missão, submissão, estado da missão |
| Sensor binário | A carregar, navegação localizada, atualização de firmware em curso, interruptor de alimentação, problema, chuva detetada, mapa detetado / construível / em cópia de segurança, a gravar dados, conversão de dados em curso |
| Seleção | Seleção de zona, velocidade de corte, velocidade das lâminas, modo da direção principal, modo de corte das bordas em relva alta |
| Número | Altura de corte, distância de corte das bordas, espaçamento de corte, ângulo de direção única, intervalo do ângulo de rotação automática, ângulo da primeira / segunda direção |
| Interruptor | Corte minucioso dos cantos |
| Botão | Corte das bordas, repor o temporizador das lâminas, repor o temporizador da estação base |
| Atualização | Versão do firmware |

### Instalação

#### Método 1: HACS (recomendado)
1. Certifique-se de que o [HACS](https://hacs.xyz/) está instalado
2. Utilize o botão acima para adicionar ao HACS
3. Vá a HACS → Integrações → + → pesquise por "TerraMow"
4. Instale e reinicie o Home Assistant

#### Método 2: Instalação manual
1. Copie a pasta `custom_components/terramow` para a pasta `/config/custom_components` do seu Home Assistant
2. Reinicie o Home Assistant
3. Vá a Definições → Dispositivos e serviços → Adicionar integração
4. Pesquise por "TerraMow" e siga os passos de configuração

### Configuração

Os dispositivos na rede local são descobertos automaticamente através do Zeroconf — aceite o dispositivo descoberto e introduza a palavra-passe MQTT. Para a configuração manual são necessários os seguintes parâmetros:

- **Anfitrião**: endereço IP ou nome de anfitrião do dispositivo TerraMow
- **Palavra-passe**: palavra-passe MQTT para autenticação

**Alterar as definições mais tarde**
- *Reconfigurar* (Definições → Dispositivos e serviços → TerraMow → Reconfigurar): altere o anfitrião/IP ou a palavra-passe diretamente, por exemplo depois de o corta-relva ter recebido um novo endereço DHCP — não é necessário remover e voltar a adicionar a integração.
- *Opções* (Configurar): defina a resolução de saída da câmara do mapa. Valores mais altos produzem uma imagem mais nítida no painel, à custa de largura de banda e de CPU por renderização.
- Se a palavra-passe do dispositivo mudar, o Home Assistant inicia automaticamente um fluxo de *reautenticação*.

### Requisitos

- Home Assistant 2023.9.3 ou posterior (testado com 2025.1.1)
- Firmware TerraMow versão 6.6.0 ou posterior
- APP TerraMow versão 1.6.0 ou posterior
- O mapa em tempo real e o trajeto de corte requerem firmware com o módulo HA na versão 3; na versão 2 (por exemplo, S800) tudo o resto funciona e o sensor de compatibilidade de versões assinala-o

### Serviços

#### `terramow.start_select_region`

Inicia o corte para uma lista de sub-regiões selecionadas.

```yaml
service: terramow.start_select_region
target:
  entity_id: lawn_mower.terramow
data:
  region_ids: [1, 2]
```

### Diagnósticos e resolução de problemas

- **Transferência de diagnósticos**: Definições → Dispositivos e serviços → TerraMow → menu de três pontos → *Transferir diagnósticos* produz um instantâneo JSON anonimizado (estado do dispositivo, compatibilidade do firmware, caches de pontos de dados em bruto) — anexe-o, por favor, aos relatórios de erros.
- **Descobrir funcionalidades não suportadas**: o corta-relva publica mais pontos de dados do que os documentados. O primeiro payload de cada ponto de dados desconhecido é registado uma vez ao nível INFO; ative o registo de depuração para a integração `terramow` para registar todos. Se encontrar um ponto de dados de uma funcionalidade em falta (por exemplo, alarme de elevação, interruptor de agenda, códigos de erro), partilhe-o num issue.

### Idiomas

A integração está traduzida em: Български · Català · Čeština · Dansk · Deutsch · Eesti · Ελληνικά · English · Español · Français · Hrvatski · Italiano · 日本語 · 한국어 · Latviešu · Lietuvių · Magyar · Nederlands · Norsk (bokmål) · Polski · Português · Português (Brasil) · Română · Русский · Slovenčina · Slovenščina · Српски · Suomi · Svenska · Türkçe · Українська · 简体中文 · 繁體中文.

### Notas de atualização

- **v0.5.0**: os valores de estado das entidades mudaram de maiúsculas para minúsculas (por exemplo, `MISSION_IDLE` → `mission_idle`) para cumprir os requisitos de tradução do Home Assistant. As automatizações ou modelos que comparam cadeias de estado em bruto necessitam de uma atualização única; os nomes apresentados mantêm-se inalterados.

### Suporte

Abra um issue no [GitHub](https://github.com/it-rec/TerraMowHA/issues) para obter suporte.

### Informações para programadores

Os programadores interessados em compreender ou expandir esta integração devem consultar o [Guia do Programador](en/developers.md).

Para executar o conjunto de testes localmente:

```bash
pip install -r requirements_test.txt
pytest tests/
```

---

## Licença

Este projeto está licenciado ao abrigo da GNU General Public License v3.0 — consulte o ficheiro [LICENSE](../LICENSE) para mais detalhes.
