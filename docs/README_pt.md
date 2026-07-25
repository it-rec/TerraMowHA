# TerraMow para Home Assistant

<div align="center">
  <img src="images/terramow_logo.png" alt="TerraMow Logo" width="400">
</div>

🌐 [English](../README.md) · [Dansk](README_da.md) · [Deutsch](README_de.md) · [Español](README_es.md) · [Français](README_fr.md) · [Italiano](README_it.md) · [Nederlands](README_nl.md) · [Norsk (bokmål)](README_nb.md) · [Polski](README_pl.md) · **Português** · [Suomi](README_fi.md) · [Svenska](README_sv.md) · [Čeština](README_cs.md) · [中文](README_zh.md)

---

Esta é uma integração para o Home Assistant destinada aos corta-relvas robóticos TerraMow.

### Funcionalidades

**Controlo**
- Entidade corta-relva: iniciar, pausar e regressar à base
- Corte por zonas: entidade de seleção de zona e serviço `terramow.start_select_region`
- **Edição do agendamento** — os serviços `terramow.add_schedule` / `terramow.delete_schedule` escrevem intervalos de corte semanais no robô e verificam-nos por releitura. *Nota:* o firmware comercial atual ainda não aceita escritas do agendamento por MQTT local (a aplicação do fabricante usa Bluetooth/nuvem) — até que o firmware o permita, use o **blueprint de corte adaptado ao tempo** para agendar do lado do HA
- **Cartão de mapa interativo** — mapa vetorial do relvado com deslocamento e zoom para painéis: posição do robô em direto (colorida conforme a atividade, com modo de seguimento), comandos de iniciar / pausar / base no próprio cartão, indicadores de bateria / progresso / tempo restante, sombreado da área cortada com progresso por zona, trajeto de corte, estação base, zonas com seleção por toque para cortar, zonas proibidas e paredes virtuais, falhas ativas marcadas no local onde ocorreram, e um **mapa de calor de Wi-Fi** do relvado; um **botão de vista** alterna entre Ambos / Trajeto / Área / Wi-Fi. Compatível com temas, registando-se automaticamente e com editor gráfico (`custom:terramow-map-card`)
- Botão de corte de bordas
- Definições a partir do Home Assistant: altura de corte, velocidade, espaçamento, velocidade da lâmina, distância de corte de bordas, modo e ângulos da direção principal, corte cuidado dos cantos, modo de corte de bordas para erva alta
- Manutenção: botões de reposição para os contadores do disco de lâminas e da estação base

**Monitorização**
- Câmara de mapa em direto com trajeto de corte, posição do robô e estação base (mais uma câmara «só mapa», limpa, para painéis; resolução configurável nas opções)
- Bateria: nível, estado de carga, estado de temperatura, carregador ligado, interruptor de alimentação
- Progresso: área da sessão atual, progresso (%), duração e tipo de tarefa; tempo de corte acumulado, número de tarefas e área cortada
- Estado: missão / submissão / estado da missão, modo de funcionamento, modo de energia, motivo do regresso à base, deteção de chuva, indicador de problema, indicadores de gravação e conversão de dados
- **Sensor de falha** — a falha ativa como texto legível (por ex. *Robô encalhado*, *Robô levantado* ou *OK*), para que uma notificação ou assistente de voz possa dizer o que se passa sem processar um atributo com um template
- Sensor de tarefa em curso (mantém a missão ativa ao longo de falhas no sinal de presença) e um sensor da intensidade do sinal Wi-Fi do robô
- Mapa: estado, área, indicadores de detetado / construível / cópia de segurança em curso
- Agendamento: sensor do próximo início agendado e um **calendário do agendamento de corte** somente de leitura (o próximo corte aparece no cartão de calendário)
- Entidade de atualização de firmware, versão do firmware na página do dispositivo e sensor de compatibilidade de versão
- Todas as entidades atualizam de imediato com os envios do dispositivo — sem atraso de sondagem

**Diagnósticos avançados** (pontos de dados obtidos por engenharia inversa — sobretudo na categoria de entidade *Diagnóstico*, muitos desativados por predefinição; consulte as [notas sobre pontos de dados não oficiais](en/developers/data_point_unofficial.md))
- Erros e eventos: número de erros ativos (com a lista de erros em bruto como atributo) e código do último evento. Os códigos de erro conhecidos são traduzidos para texto legível através de um catálogo mantido pela comunidade (`error_codes.py`), que também descodifica o último código de erro do robô (dp_115)
- Móvel / 4G: modem ativado, intensidade do sinal (RSRP / RSRQ), tipo de ligação e uma leitura de *forçar rede móvel*
- Ambiente: nascer / pôr do sol comunicados pelo dispositivo, estado de luz do dia, aquecimento antiembaciamento, iluminação e aviso de meteorologia extrema (com URL informativo opcional)
- Segurança e definições avançadas: estado da deteção de desníveis e de inclinação, limiar do sensor de chuva, retoma automática após a chuva e o respetivo atraso, e uma leitura de *forçar uma só estação base*
- Modos de funcionamento: cadeias dos modos movimento / mapa / corte
- Cartografia e progresso: indicadores de orientação para a cartografia manual (reposicionamento / intervenção necessários, perímetro fechado) e uma percentagem de progresso da gravação do mapa

**Eventos e automação**
- **Entidade de evento do robô** — dispara um evento distinto em cada transição relevante (`mowing_started`, `paused`, `returning`, `docked`, `mowing_completed`, `error`), cada um com os campos da missão em bruto, para que as automações reajam a *ocorrências* sem sondar o estado de atividade
- Blueprints de automação importáveis com um clique (ver abaixo)

**Comodidades da integração**
- Deteção automática através de Zeroconf/mDNS
- Fluxo de reconfiguração (alterar host/IP sem voltar a adicionar) e fluxo de reautenticação
- **Avisos de reparação** — cartões de painel acionáveis para firmware incompatível e para a manutenção pendente da lâmina / da estação base
- Descarregamento de diagnósticos para facilitar os relatórios de erro
- Traduzida em 33 idiomas (bg, ca, cs, da, de, el, en, es, et, fi, fr, hr, hu, it, ja, ko, lt, lv, nb, nl, pl, pt, pt-BR, ro, ru, sk, sl, sr, sv, tr, uk, zh-Hans, zh-Hant)
- **Comandos confirmados** — o corte por zonas aguarda a confirmação dp_119 do dispositivo e comunica as rejeições em vez de «ter êxito» silenciosamente
- Comunicação local push baseada em MQTT — sem necessidade de nuvem

### Entidades suportadas

| Plataforma | Entidades |
| --- | --- |
| Corta-relva | Comando de iniciar / pausar / base com atividade em direto |
| Câmara | Mapa com trajeto, robô e estação base; variante limpa de «só mapa» |
| Sensor | Nível da bateria, estado da bateria, estado da temperatura da bateria, estado do mapa, área do mapa, altura de corte, velocidade de corte, modo de funcionamento, posição, tempo de corte / tarefas / área cortada acumulados, área / progresso / duração / tipo de tarefa da sessão atual, tarefa em curso, falha, tempo restante da lâmina e da estação base, próximo início agendado, compatibilidade de versão, estado da direção principal, modo de energia, motivo do regresso à base, missão, submissão, estado da missão. *Diagnóstico:* erros ativos, último evento, sinal Wi-Fi, móvel RSRP / RSRQ / tipo, nascer do sol, pôr do sol, modos movimento / mapa / corte, limiar do sensor de chuva, atraso de retoma após a chuva, progresso da gravação do mapa |
| Sensor binário | A carregar, navegação localizada, atualização de firmware em curso, interruptor de alimentação, problema, chuva detetada, mapa detetado / construível / cópia de segurança em curso, a gravar dados, conversão de dados em curso. *Diagnóstico:* móvel ativado, aquecimento antiembaciamento, iluminação, luz do dia, meteorologia extrema, deteção de desníveis / de inclinação, retoma automática após a chuva, forçar uma só estação base, forçar rede móvel, cartografia manual reposicionamento / intervenção / perímetro fechado, indicador de estado 134 (não descodificado) |
| Seleção | Seleção de zona, velocidade de corte, velocidade da lâmina, modo de direção principal, modo de corte de bordas para erva alta |
| Número | Altura de corte, distância de corte de bordas, espaçamento de corte, ângulo de direção única, intervalo de rotação automática do ângulo, ângulo da primeira / segunda direção |
| Interruptor | Corte cuidado dos cantos |
| Botão | Corte de bordas, repor temporizador da lâmina, repor temporizador da estação base |
| Atualização | Versão do firmware |
| Evento | Evento do robô (corte iniciado / pausado / a regressar / na base / concluído / erro) |
| Calendário | Agendamento de corte (próximo corte agendado) |

### Instalação

[![Abra a sua instância do Home Assistant e abra um repositório na Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=it-rec&repository=TerraMowHA&category=Integration)

#### Método 1: HACS (recomendado)
1. Certifique-se de que o [HACS](https://hacs.xyz/) está instalado
2. Use o botão acima para adicionar a integração ao HACS
3. Abra o HACS, procure «TerraMow» e selecione a integração
4. Instale-a e reinicie o Home Assistant

#### Método 2: Instalação manual
1. Copie a pasta `custom_components/terramow` para a pasta `/config/custom_components` do seu Home Assistant
2. Reinicie o Home Assistant
3. Vá a Definições → Dispositivos e serviços → Adicionar integração
4. Procure «TerraMow» e siga os passos de configuração

### Configuração

Os dispositivos na rede local são detetados automaticamente através de Zeroconf — aceite o dispositivo detetado e introduza a palavra-passe MQTT. Para a configuração manual são necessários os seguintes parâmetros:

- **Host**: endereço IP ou nome de host do dispositivo TerraMow
- **Palavra-passe**: palavra-passe MQTT para autenticação

**Alterar definições mais tarde**
- *Reconfigurar* (Definições → Dispositivos e serviços → TerraMow → Reconfigurar): altere o host/IP ou a palavra-passe no lugar, por ex. depois de o robô receber um novo endereço DHCP — não é preciso remover e voltar a adicionar a integração.
- *Opções* (Configurar):
  - **Resolução de saída do mapa** — maior é mais nítida, mas custa mais largura de banda e CPU em cada renderização.
  - **Tema do mapa** — `light` ou `dark`.
  - **Mostrar a área cortada** — sombreia a área já cortada sob a linha do trajeto.
  - **Tratar qualquer tarefa terminada como 100 % concluída** — alguns firmwares terminam uma tarefa sem emitir um sinal de conclusão, pelo que o progresso da sessão nunca salta para 100 % mesmo com o relvado acabado (aparece como «interrompida»). Ative esta opção para tratar qualquer tarefa terminada como concluída, tal como a aplicação do fabricante; deixe-a desativada para manter o valor honesto do contador. *Predefinição: desativado.*
- Se a palavra-passe do dispositivo mudar, o Home Assistant inicia automaticamente um fluxo de *reautenticação*.

### Requisitos

- Home Assistant 2024.6.0 ou posterior (a CI valida contra a versão atual do HA Core)
- Firmware TerraMow versão 6.6.0 ou posterior
- Aplicação TerraMow versão 1.6.0 ou posterior
- O mapa em direto e o trajeto de corte requerem a versão 3 do módulo HA do firmware; na versão 2 (por ex. S800) tudo o resto funciona, e o sensor de compatibilidade de versão comunica-o

### Dispositivos suportados

Esta integração funciona com corta-relvas robóticos TerraMow que exponham a interface MQTT/HTTP local — ou seja, qualquer modelo com o firmware necessário. É usada com a série S da TerraMow, incluindo o **S800** (que comunica a versão 2 do módulo HA do firmware) e unidades mais recentes na versão 3. Qualquer robô TerraMow com firmware 6.6.0+ e aplicação 1.6.0+ deve funcionar; o sensor de compatibilidade de versão e um aviso de reparação indicam se o firmware de uma unidade específica é demasiado antigo para uma dada funcionalidade.

### Serviços

#### `terramow.start_select_region`

Inicia o corte de uma lista de sub-regiões selecionadas.

```yaml
service: terramow.start_select_region
target:
  entity_id: lawn_mower.terramow
data:
  region_ids: [1, 2]
```

#### `terramow.add_schedule` / `terramow.delete_schedule`

Cria ou remove um intervalo de corte semanal no robô. Cada escrita é confirmada
junto do dispositivo (confirmação dp_119 mais uma releitura do agendamento).

```yaml
service: terramow.add_schedule
target:
  entity_id: lawn_mower.terramow
data:
  week_days: [tuesday, thursday]
  start_time: "07:45:00"
  end_time: "09:15:00"
```

`delete_schedule` recebe o `item_id` do intervalo (mostrado como uid do evento de
calendário e devolvido quando um intervalo é adicionado).

> **Nota:** o firmware comercial atual ainda não aceita escritas do agendamento
> por MQTT local (a aplicação do fabricante usa Bluetooth/nuvem). Até que o
> firmware o permita, use o **blueprint de corte adaptado ao tempo** para agendar
> do lado do HA.

### Cartão de mapa interativo

A integração inclui o seu próprio cartão Lovelace — registado automaticamente, sem recursos manuais nem instalação separada do frontend do HACS:

```yaml
type: custom:terramow-map-card
entity: lawn_mower.terramow
```

Desenha o relvado em vetores (nítido em qualquer zoom, segue o seu tema do HA): zonas, zonas proibidas, paredes virtuais, o trajeto de corte, a estação base e a posição do robô em direto. Arraste para deslocar, roda ou pinça para ampliar, toque duplo para reajustar. **Toque numa ou mais zonas** e prima o botão que aparece para cortar exatamente essas zonas (`terramow.start_select_region` nos bastidores).

Um **botão de vista** alterna o que o cartão sobrepõe ao relvado:

| Modo | Mostra |
| --- | --- |
| **Ambos** | a área cortada *e* o trajeto de corte (predefinido quando a área está ativa) |
| **Trajeto** | apenas o trajeto da tarefa atual e da anterior |
| **Área** | apenas o sombreado da área cortada, com progresso por zona |
| **Wi-Fi** | um **mapa de calor de Wi-Fi** do relvado, medido pelo próprio robô durante o corte (verde = forte). Os vazios entre passagens são interpolados a partir das medições vizinhas; o terreno nunca percorrido fica vazio |

O modo escolhido é memorizado por entidade no navegador. Opções e detalhes: consulte o [guia de painéis](en/dashboard.md#interactive-map-card) (em inglês). Os dados de mapa em direto requerem a versão 3 do módulo HA do firmware (tal como a câmara de mapa). O cartão está também disponível no seletor de cartões do painel como **TerraMow Map Card**, com um editor gráfico completo — sem necessidade de YAML.

### Exemplo de painel

Uma vista Lovelace pronta a usar (mapa em direto, comandos, indicador de progresso, resumo de estado) mais automações de notificação: consulte o [guia de painéis](en/dashboard.md) (em inglês).

### Blueprints de automação

Blueprints importáveis com um clique para as notificações mais comuns — cada um pede apenas a entidade TerraMow em questão e uma ação de notificação:

- **Corte adaptado ao tempo** — inicia o corte conforme o seu agendamento, ignorando-o automaticamente se for detetada ou prevista chuva
  [![Importar blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fweather_adaptive_mowing.yaml)
- **Notificação de problema** — quando o robô comunica uma falha
  [![Importar blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fproblem_notification.yaml)
- **Regresso devido à chuva** — quando o robô volta à base por causa da chuva
  [![Importar blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Frain_returned_notification.yaml)
- **Corte concluído** — quando uma tarefa de corte termina
  [![Importar blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fit-rec%2FTerraMowHA%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fterramow%2Fmowing_finished_notification.yaml)

**Usar a entidade de evento diretamente** — a entidade de evento do robô é o acionador mais flexível. O seu atributo `event_type` é um de `mowing_started`, `paused`, `returning`, `docked`, `mowing_completed`, `error`, e transporta os campos em bruto `mission`, `sub_mission`, `state`, `back_to_station_reason` e `has_error`:

```yaml
triggers:
  - trigger: state
    entity_id: event.terramow_mower_event
    attribute: event_type
    to: mowing_completed
actions:
  - action: notify.mobile_app_phone
    data:
      message: "O TerraMow terminou o corte 🌱"
```

### Avisos de reparação

A integração cria avisos de reparação acionáveis no Home Assistant (Definições → Dispositivos e serviços → Reparações) em vez de esconder os problemas em sensores:

- **Firmware incompatível / atualização necessária** — o firmware é demasiado antigo para a integração (ou para uma funcionalidade específica). Deriva da verificação de compatibilidade de versão; desaparece quando um firmware compatível se anuncia.
- **Manutenção da lâmina pendente** — o disco de lâminas atingiu o intervalo de manutenção recomendado de 240 horas. Limpe ou substitua as lâminas e prima o botão *Repor temporizador da lâmina* para o eliminar.
- **Manutenção da estação base pendente** — a estação base atingiu o intervalo de manutenção recomendado de 30 dias. Limpe-a e prima o botão *Repor temporizador da estação base* para o eliminar.

### Diagnósticos e resolução de problemas

- **Descarregar diagnósticos**: Definições → Dispositivos e serviços → TerraMow → menu de três pontos → *Descarregar diagnósticos* gera um instantâneo JSON depurado (estado do dispositivo, compatibilidade do firmware, caches de pontos de dados em bruto) — anexe-o aos relatórios de erro.
- **Descobrir funcionalidades não suportadas**: o robô publica mais pontos de dados do que os documentados. O primeiro payload de cada ponto de dados desconhecido é registado uma vez ao nível INFO; ative o registo de depuração para a integração `terramow` para os captar todos. Se encontrar um ponto de dados para uma funcionalidade em falta (por ex. alarme de elevação, interruptor do agendamento, códigos de erro), partilhe-o numa issue.

### Como os dados são atualizados

O TerraMow é uma integração **local push**. O robô executa um broker MQTT a bordo; o Home Assistant liga-se diretamente através da rede local (sem nuvem) e subscreve os tópicos de pontos de dados do dispositivo, pelo que os estados das entidades atualizam no instante em que o robô comunica uma alteração, e não num intervalo de sondagem. Os payloads maiores (o mapa, o trajeto em direto) são anunciados por MQTT e obtidos a pedido por HTTP local. Se o robô estiver em repouso ou fora da rede, a ligação é retentada com espera exponencial, e a entidade corta-relva expõe a perda de ligação como a sua atividade `error`.

**Os comandos falham de forma visível, não em silêncio.** Quando envia um comando — `dock`, `start_mowing`, `pause`, corte de bordas, corte por zonas ou qualquer alteração de definição — este é publicado com MQTT QoS 1 (uma reconexão breve guarda-o em buffer em vez de o descartar). Se o robô estiver offline ou inacessível, se o broker rejeitar a publicação, ou se um comando chegar mais depressa do que o dispositivo o consegue aceitar, a chamada ao serviço **falha com um erro** em vez de comunicar êxito silenciosamente. Assim, uma automação que chama `lawn_mower.dock` com o robô inacessível vê a falha (e pode tentar de novo ou notificar) em vez de acreditar que o robô está a caminho quando nunca recebeu o comando.

### Limitações conhecidas

- **Sem acesso na nuvem / remoto** — o Home Assistant tem de estar na mesma rede local do robô; não há alternativa pela nuvem.
- **Funcionalidades dependentes do firmware** — o mapa em direto e a vista do trajeto de corte requerem a versão 3 do módulo HA; na versão 2 (por ex. o S800) tudo o resto funciona, e o sensor de compatibilidade / o aviso de reparação comunica a limitação.
- **As atualizações de firmware** são feitas através da aplicação TerraMow, não a partir do Home Assistant; a entidade `update` do firmware é apenas informativa.
- **O sensor de posição e a câmara de mapa limpa estão desativados por predefinição** (o sensor de posição atualiza a cerca de 2 Hz); ative-os nas definições da entidade se precisar deles.
- **Muitas entidades de diagnóstico avançado estão desativadas por predefinição** e agrupadas na categoria *Diagnóstico* (móvel, nascer/pôr do sol, modos de funcionamento, indicadores de cartografia manual, etc.); provêm de pontos de dados obtidos por engenharia inversa, portanto ative apenas os que necessitar. Consulte as [notas sobre pontos de dados não oficiais](en/developers/data_point_unofficial.md).
- Alguns pontos de dados do dispositivo não estão documentados; os desconhecidos são registados uma vez para ajudar a descobrir funcionalidades em falta.

### Casos de uso

- **Notificações relacionadas com a chuva** — receba um aviso quando o robô regressar à base por causa da chuva (ver os blueprints acima).
- **Alertas de falha** — seja avisado no momento em que o robô comunica um problema (encalhado, levantado, bloqueado).
- **Corte por zonas a partir de automações** — chame `terramow.start_select_region` para cortar sub-regiões específicas conforme um agendamento ou a partir de um botão do painel.
- **Lembretes de manutenção** — os sensores do tempo restante da lâmina / da estação base e os botões de reposição permitem automatizar os lembretes de manutenção.
- **Mapa em direto num painel** — mostre a câmara de mapa com a posição do robô e o trajeto de corte (ver o guia de painéis).

### Idiomas

A integração está traduzida em: Български · Català · Čeština · Dansk · Deutsch · Eesti · Ελληνικά · English · Español · Français · Hrvatski · Italiano · 日本語 · 한국어 · Latviešu · Lietuvių · Magyar · Nederlands · Norsk (bokmål) · Polski · Português · Português (Brasil) · Română · Русский · Slovenčina · Slovenščina · Српски · Suomi · Svenska · Türkçe · Українська · 简体中文 · 繁體中文.

### Notas de atualização

- **v0.5.0**: os valores de estado das entidades passaram de maiúsculas para minúsculas (por ex. `MISSION_IDLE` → `mission_idle`) para cumprir os requisitos de tradução do Home Assistant. Automações ou templates que comparem cadeias de estado em bruto precisam de um ajuste único; os nomes apresentados não mudam.

### Suporte

Abra uma issue no [GitHub](https://github.com/it-rec/TerraMowHA/issues) para obter ajuda.

### Informação para desenvolvedores

Para desenvolvedores interessados em compreender ou estender esta integração (a documentação para desenvolvedores está em inglês):

- [Guia de contribuição](../CONTRIBUTING.md) — configuração, requisitos de qualidade (100 % de cobertura, `mypy --strict`, traduções), processo de PR e de lançamento
- [Arquitetura](ARCHITECTURE.md) — o funcionamento interno: ciclo de vida do hub, modelo de execução, catálogo de pontos de dados, pipeline de mapa/trajeto
- [Guia do desenvolvedor](en/developers.md) — o protocolo MQTT/HTTP do dispositivo tal como circula na rede
- [O que este fork acrescenta ao upstream](UPSTREAM_DELTA.md)

Para executar a bateria de testes localmente:

```bash
pip install -r requirements_test.txt
pytest tests/ --cov=custom_components/terramow --cov-fail-under=100
```

---

## Licença

Este projeto está licenciado sob a GNU General Public License v3.0 — consulte o ficheiro [LICENSE](../LICENSE) para mais detalhes.
