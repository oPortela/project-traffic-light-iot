# Integração HTTP em três linguagens

Os exemplos usam somente bibliotecas padrão e o perfil rural `solo-horario-v1`.
Salve a resposta de criação do dispositivo fora do Git e configure `DEVICE_FILE`
com seu caminho. `INGESTION_URL` define a central (padrão localhost:8002).

```powershell
$env:DEVICE_FILE='deploy/secrets/solo-device.json'
python projects/examples/python/publish.py
node projects/examples/node/publish.mjs
go run projects/examples/go/main.go
```

Em produção, use HTTPS com certificado confiável. O exemplo envia uma leitura;
para retentativas, preserve o mesmo envelope e id_mensagem. Para armazenamento
offline, use a borda cifrada. Não inclua credenciais no JSON canônico.
