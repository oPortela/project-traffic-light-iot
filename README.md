# Travessia · Simulador de semáforo IoT

Aplicação local em Python com interface web em português. A webcam detecta pessoas com YOLO e ByteTrack. Quando a mesma pessoa permanece na área de espera por 10 segundos, o controlador executa a sequência de travessia. Inclui um modo de demonstração que funciona sem câmera e sem carregar o modelo.

## Executar no Windows

Instale Python 3.11 ou 3.12 e abra o terminal nesta pasta:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Se você possui Python 3.11, substitua `py -3.12` por `py -3.11`. Abra http://127.0.0.1:8000 no navegador. Após instalar, você também pode dar dois cliques em `iniciar.bat`. Encerre o servidor com Ctrl+C. Execute somente um processo/worker: o controlador e a câmera são compartilhados em memória.

`requirements-lock.txt` registra as versões validadas em Python 3.12 no Windows. Para reproduzir esse ambiente, use `-r requirements-lock.txt` no comando de instalação.

Para testar apenas a demonstração, as dependências mínimas são `fastapi`, `uvicorn[standard]` e `httpx`; OpenCV, Ultralytics e PyTorch são necessários para a webcam.

## Demonstração

1. Selecione **Demonstração** e clique em **Iniciar simulação**.
2. Ative **Simular pessoa na área de espera**.
3. Após 10 segundos: veículos amarelo por 3 s → ambos vermelho por 1 s → pedestres verde por 8 s → ambos vermelho por 1 s → veículos verde.
4. Desative a presença para simular a saída. Parar/Reiniciar encerra a simulação, restaura os sinais e zera os eventos e contadores.

Se a presença continuar após o ciclo, uma nova espera começa. Saídas maiores que 0,8 s reiniciam a espera. Uma ausência breve é tolerada, mas uma pessoa ausente não inicia a travessia.

## Webcam

Pare a simulação, selecione **Webcam do notebook** e inicie. Na primeira utilização, o Ultralytics baixa os pesos `yolov8n.pt` (requer internet). A inicialização pode demorar. O vídeo só aparece depois da primeira inferência. As imagens são processadas no notebook e não são gravadas pela aplicação.

O ponto inferior central da caixa da pessoa deve estar dentro do retângulo azul. Para demonstrações sentado, aumente a Base para 100%. Pare a simulação para ajustar os limites da área e os tempos. Não há reconhecimento automático da pintura da faixa: a região é definida manualmente.

Para baixar o modelo e verificar suas dependências antecipadamente, sem abrir a webcam, execute `.\.venv\Scripts\python.exe preparar_modelo.py`.

Se a câmera não abrir, feche aplicativos que a utilizam e permita o acesso à câmera para aplicativos de desktop nas configurações do Windows. Para selecionar outro dispositivo, antes de iniciar o servidor:

```powershell
$env:CAMERA_INDEX = "1"
```

É possível definir `$env:YOLO_MODEL` com o caminho de um modelo compatível já baixado. O desempenho depende do processador, iluminação e enquadramento. O rastreador pode trocar o identificador em oclusões; nesse caso, a contagem daquela pessoa reinicia. O aplicativo não faz identificação facial.

## Estrutura

- `app/controller.py`: máquina de estados independente da câmera e do servidor.
- `app/main.py`: API FastAPI, WebSocket, vídeo MJPEG e processamento em threads.
- `static/`: interface, semáforos e controles.
- `tests/`: testes do controlador e da API.

O Python captura a câmera do computador em que o servidor está rodando. Publicar o backend em outro computador não dá acesso à webcam do visitante. As fontes visuais são opcionais, carregadas do Google Fonts, com fontes locais de fallback.

## Testes

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Este é um simulador acadêmico, não um controlador para sinalização de vias reais. A câmera representa o sensor, o Python o controlador e os semáforos da página os atuadores simulados. Uma extensão futura pode transmitir os estados por MQTT para LEDs em um ESP32.
