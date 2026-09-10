# Sistema Semafórico Inteligente - Detecção de Pedestres

Sistema de monitoramento e controle automatizado de tráfego que utiliza Visão Computacional e Inteligência Artificial para detectar pedestres em áreas de espera e acionar ciclos semafóricos. Construído com Python, FastAPI, YOLO v8 e ByteTrack, operando com processamento em tempo real via stream de vídeo MJPEG.

## 1. Visão Geral

Este projeto implementa um protótipo didático de semáforo inteligente para travessia de pedestres. A aplicação combina detecção automática de pessoas em tempo real com uma máquina de estados que controla a sequência de sinalização, simulando uma solução IoT aplicada à mobilidade urbana, sem depender de hardware físico real.

O sistema foi organizado em camadas para refletir a arquitetura de um ambiente automatizado de tráfego:

- sensor: câmera ou simulação de presença;
- processamento: visão computacional e rastreamento de objetos;
- lógica de controle: máquina de estados e regras de decisão;
- interface: dashboard web com monitoramento e simulação dos semáforos;
- atuador: representação visual dos estados de sinalização na interface.

## 2. Arquitetura / Fluxo de Dados

| Etapa | Módulo | Componente | Função |
| :--- | :--- | :--- | :--- |
| 1 | Captura | Câmera / Vídeo | Gera frames de vídeo em tempo real via OpenCV. |
| 2 | Processamento | Visão Computacional | Detecta pessoas utilizando YOLO v8 e rastreia seus identificadores com ByteTrack. |
| 3 | Lógica de Espera | Validador de Regras | Calcula o tempo de permanência na área de espera, tolerando perdas curtas de detecção. |
| 4 | Máquina de Estados | Controlador Semafórico | Gerencia rigorosamente o ciclo de luzes e os tempos de segurança da via. |
| 5 | Interface Web | Painel de Monitoramento | Exibe os estados das luzes e transmite o feed de vídeo processado via MJPEG. |

```text
[1] SENSORAMENTO              [2] CONTROLE                  [3] API / WEB                     [4] ATUADOR
Câmera / presença simulada --> Controller --> FastAPI + WebSocket --> Interface HTML/JS
                              (máquina de estados)      (estado atual, eventos e vídeo)  (semáforos e painel)
```

O fluxo principal funciona em duas modalidades:

- Modo demonstração: sem câmera, usando presença simulada para ativar a travessia;
- Modo câmera: análise de vídeo em tempo real para identificar pedestres em uma área de espera.

## 3. Módulos e Pacotes

### Camada de domínio e negócio

- vision: módulo de visão computacional. Executa o modelo Ultralytics YOLOv8n para detecção e o algoritmo ByteTrack para rastrear o movimento e atribuir identificadores temporários.
- rules: módulo gerenciador de áreas e contadores. Valida os limites da área configurada, processa as regras de ausência e confirma se o pedestre atingiu a presença contínua exigida.
- controller: máquina de estados do semáforo. Recebe o gatilho da área de espera e executa rigorosamente as transições de luzes e tempos de segurança.
- api: roteamento e streaming. Expõe a interface, injeta o feed processado e fornece endpoints de controle e consulta do sistema.

### Camada web e apresentação

- app/main.py: inicializa a aplicação FastAPI e o servidor Uvicorn.
- static/index.html: dashboard acessível via navegador para monitoramento da interseção. Exibe o feed demarcado com caixas delimitadoras, estado das luzes e botões para iniciar, parar e reiniciar a simulação.

## 4. Requisitos Funcionais

| ID | Descrição | Prioridade |
| :--- | :--- | :--- |
| RF01 | O sistema deve detectar pessoas no vídeo utilizando o modelo YOLOv8n e rastrear seus identificadores com ByteTrack. | Alta |
| RF02 | O sistema deve permitir a configuração manual dos limites da área de espera. | Alta |
| RF03 | O sistema deve possuir um controlador, em máquina de estados, que gerencie as luzes do semáforo. | Alta |
| RF04 | O sistema deve transmitir o feed de vídeo processado com marcações para a interface web via protocolo MJPEG. | Alta |
| RF05 | O sistema deve permitir pausar, reiniciar e interromper a simulação por meio da interface web. | Média |
| RF06 | O sistema deve exibir os estados em tempo real dos semáforos na interface web. | Alta |
| RF07 | O sistema deve reconhecer presença contínua na zona de espera para ativar a travessia. | Alta |
| RF08 | O sistema deve tolerar perdas curtas de detecção sem disparar a sequência indevidamente. | Média |

## 5. Requisitos Não Funcionais (RNF)

| ID | Descrição | Categoria |
| :--- | :--- | :--- |
| RNF01 | O back-end deve ser desenvolvido em Python. | Tecnologia |
| RNF02 | A API deve ser construída com FastAPI e executada via servidor Uvicorn. | Arquitetura |
| RNF03 | A detecção de objetos deve utilizar YOLO Ultralytics e o rastreamento deve utilizar ByteTrack com processamento via OpenCV e PyTorch. | Tecnologia |
| RNF04 | O sistema não deve realizar reconhecimento facial, não deve gravar ou persistir vídeos e imagens processadas. | Segurança |
| RNF05 | O processamento de imagem e o controlador de estados devem rodar em threads separadas em um único processo. | Desempenho |
| RNF06 | A aplicação deve ser acessível via navegador web. | Usabilidade |

## 6. Regras de Negócio

- RN01 - Condição de Acionamento: para que a sequência de travessia seja iniciada, a pessoa detectada deve permanecer na área de espera por 10 segundos ininterruptos.
- RN02 - Tolerância de Ausência: breves perdas de detecção ou saídas da área são toleradas. A contagem de espera só é reiniciada quando a pessoa deixa a área por um intervalo curto e o rastreio é perdido.
- RN03 - Ciclo do Semáforo: após o acionamento, a máquina de estados executa rigorosamente a sequência: amarelo por 3 segundos, segurança com ambos em vermelho por 1 segundo, pedestres em verde por 8 segundos, ambos em vermelho por 1 segundo e retorno de veículos para verde.
- RN04 - Presença Contínua: se houver pessoas na área de espera imediatamente após o término do ciclo, uma nova contagem de espera deve ser iniciada.
- RN05 - Troca de Identificador: se o rastreador trocar o identificador de uma pessoa devido a oclusão, o sistema interpreta como um novo indivíduo e a contagem para aquela pessoa específica deve reiniciar.

## 7. Regras de Decisão da Lógica de Travessia

O controlador calcula o estado da interseção com base no tempo e na presença identificada na zona de espera.

- sem presença → fase idle, veículos em verde;
- presença detectada por tempo suficiente → transição para yellow;
- fase de segurança → todos os sinais ficam em vermelho;
- travessia dos pedestres → sinal dos pedestres em verde;
- retorno ao normal → os veículos voltam para verde.

### Parâmetros principais

- wait: tempo mínimo de permanência para iniciar a travessia;
- yellow: duração da fase amarela dos veículos;
- clearance: tempo de segurança entre fases;
- crossing: duração da travessia dos pedestres;
- grace: tolerância para ausência breve do pedestre.

## 8. Arquitetura e Dependências

- O modelo IA faz download dos pesos `yolov8n.pt` via internet na primeira execução ou pode ser carregado de um caminho local definido pela variável de ambiente `YOLO_MODEL`.
- As dependências do projeto estão organizadas em `requirements.txt` e `requirements-lock.txt`, com versões fixadas para padronizar o ambiente Windows.
- Variáveis de ambiente suportadas: `CAMERA_INDEX` para trocar o dispositivo de captura e `YOLO_MODEL` para apontar para um modelo previamente instalado.

## 9. Comunicação do Projeto

- O projeto expõe os estados do semáforo por meio de endpoints da API.
- A função `snapshot()` consolida os dados do controlador e o estado atual da simulação. O retorno é disponibilizado via requisição GET na rota `/api/state`.
- A comunicação contínua com a interface é feita pela rota `/ws` usando WebSocket. Esse endpoint envia o snapshot do sistema em intervalos curtos, permitindo a atualização em tempo real do painel.
- O streaming de vídeo é entregue pela rota `/video`, em formato MJPEG, para o navegador mostrar o feed processado com marcações das pessoas detectadas.

## 10. Integração e Estrutura de Execução

O código foi pensado para executar em um único processo, com threads separadas para o processamento de imagem e para o loop do controlador.

- `camera_loop()`: mantém a câmera ativa, executa a detecção e atualiza o estado de presença.
- `tick_loop()`: dispara a atualização da máquina de estados com base no tempo e na presença observada.
- `Controller.transition()`: gerencia o avanço das fases e registra eventos em `self.events`.

## 11. Casos de Uso

### 1. Operador do Centro de Controle de Tráfego Urbano

- Perfil: técnico ou engenheiro de tráfego que monitora a mobilidade da cidade.
- Necessidade: visualizar o estado dos semáforos em tempo real e ajustar parâmetros de operação.
- Cenário: em um cruzamento crítico, o operador acessa a interface web e observa o fluxo de pedestres e veículos, configurando a área de espera e monitorando as mudanças de fase.

### 2. Simulação Autônoma de Tráfego em Horário de Pico

- Perfil: sistema operando em modo automático no dia a dia.
- Necessidade: adaptar dinamicamente os ciclos de sinalização sem intervenção manual contínua.
- Cenário: em um ambiente de demonstração, a presença do pedestre é simulada e a lógica de travessia inicia automaticamente a sequência semafórica.

### 3. Equipe de Manutenção e Engenharia de Software

- Perfil: desenvolvedores e técnicos responsáveis pela infraestrutura do sistema.
- Necessidade: testar a integridade das rotas da API, diagnosticar falhas e avaliar a lógica de controle.
- Cenário: após ajustes de parâmetros, a equipe roda a suíte de testes em `tests/test_api.py` e `tests/test_controller.py` para validar o comportamento do semáforo.

## 12. Como Executar

### Pré-requisitos

- Python 3.11 ou 3.12
- pip / venv
- ambiente Windows recomendado
- câmera opcional para o modo webcam

### Instalação

```powershell
cd project-traffic-light-iot
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Para reproduzir o ambiente já validado com versões fixadas:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
```

### Execução local

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

A aplicação fica disponível em:

- Interface web: http://127.0.0.1:8000
- WebSocket de estado: ws://127.0.0.1:8000/ws
- Fluxo de vídeo: http://127.0.0.1:8000/video

Também é possível iniciar com o script Windows:

```powershell
./iniciar.bat
```

> O servidor deve ser encerrado com Ctrl+C e o sistema foi desenhado para manter um único processo de controle e câmera em memória compartilhada.

## 13. Modos de Operação

### 13.1 Demonstração

1. Abra a interface web.
2. Selecione Demonstração.
3. Clique em Iniciar simulação.
4. Ative Simular pessoa na área de espera.
5. A sequência ocorre automaticamente:
   - veículos amarelo por 3s;
   - ambos vermelhos por 1s;
   - pedestres verde por 8s;
   - ambos vermelhos por 1s;
   - veículos verde.

Se a presença continuar após o ciclo, uma nova espera pode ser iniciada. Em caso de ausência breve, o sistema tolera o intervalo; caso a pessoa saia da região de espera, a travessia não é disparada.

### 13.2 Webcam

1. Pare a simulação atual.
2. Selecione Webcam do notebook.
3. Inicie a captura.
4. Ajuste a área de espera do retângulo azul para delimitar o ponto de detecção.

Na primeira execução, o Ultralytics pode baixar o modelo `yolov8n.pt`. O processamento acontece no computador local e as imagens não são armazenadas pela aplicação.

Se necessário, escolha outra câmera antes de iniciar a aplicação:

```powershell
$env:CAMERA_INDEX = "1"
```

Também é possível apontar para um modelo já instalado:

```powershell
$env:YOLO_MODEL = "C:/caminho/para/modelo.pt"
```

## 14. Estrutura de Pastas

```text
project-traffic-light-iot/
├── app/
│   ├── __init__.py
│   ├── controller.py          <- lógica da máquina de estados
│   ├── main.py                <- API FastAPI, WebSocket e streaming de vídeo
│   └── __pycache__
├── static/
│   ├── app.js                 <- front-end e interações com a API
│   ├── index.html             <- interface da aplicação
│   └── style.css              <- estilos visuais dos semáforos
├── tests/
│   ├── test_api.py
│   └── test_controller.py
├── .gitignore
├── iniciar.bat
├── preparar_modelo.py
├── README.md
├── requirements.txt
├── requirements-lock.txt
└── .runtime/                  <- diretório de cache para modelos e configuração
```

## 15. Testes Automatizados

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Os testes cobrem a lógica de controle e os endpoints da API, ajudando a garantir que o comportamento do semáforo permaneça estável durante alterações futuras.

## 16. Troubleshooting

### Câmera não abre

- feche outros programas que usem a webcam;
- verifique permissões do Windows;
- confirme o índice da câmera;
- ajuste a variável de ambiente `CAMERA_INDEX`.

### Modelo YOLO não encontrado

Na primeira execução, o Ultralytics pode baixar o modelo `yolov8n.pt`. Caso o modelo já exista em outra pasta, defina a variável `YOLO_MODEL`.

### Porta em uso

Se a porta 8000 estiver ocupada, altere a porta no comando `uvicorn`.

### Simulação sem webcam

Use o modo demonstração para testar a lógica sem câmera e validar transições do semáforo sem processamento visual.

## 17. Observações e Extensões Futuras

- Este é um projeto didático e acadêmico, não um sistema real de sinalização viária.
- A câmera representa o sensor, o Python o controlador e a interface web representa os atuadores simulados.
- A arquitetura foi pensada para permitir extensões futuras, como integração com ESP32, sensores físicos, gateways industriais, MQTT e lógica de aprendizado de máquina.
- O sistema é executado localmente e depende do desempenho do computador em que a aplicação estiver rodando.

## 18. Considerações de Uso Real

Em uma implementação real, a câmera seria substituída por um sensor de presença ou um sistema de visão computacional mais robusto, e os sinais seriam acionados por LEDs, relés ou controladores industriais. Esse projeto funciona como protótipo funcional para demonstrar a arquitetura de um sistema IoT aplicado à mobilidade urbana.
