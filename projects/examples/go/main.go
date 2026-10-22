package main

import (
    "bytes"
    "crypto/rand"
    "encoding/json"
    "fmt"
    "io"
    "net/http"
    "os"
    "strings"
    "time"
)

func run() error {
    raw, err := os.ReadFile(os.Getenv("DEVICE_FILE"))
    if err != nil { return err }
    var device struct {
        Base string `json:"topico_base"`
        Credential struct { Token string `json:"token"` } `json:"credencial"`
    }
    if err = json.Unmarshal(raw, &device); err != nil { return err }
    parts := strings.Split(device.Base, "/")
    if len(parts) != 4 { return fmt.Errorf("invalid device topic") }
    id := make([]byte, 16)
    if _, err = rand.Read(id); err != nil { return err }
    id[6], id[8] = (id[6]&0x0f)|0x40, (id[8]&0x3f)|0x80
    message := map[string]any{
        "versao": "1.0", "id_mensagem": fmt.Sprintf("%x-%x-%x-%x-%x", id[:4], id[4:6], id[6:8], id[8:10], id[10:]),
        "timestamp": time.Now().UTC().Format(time.RFC3339Nano), "inquilino": parts[0], "site": parts[1],
        "dominio": parts[2], "dispositivo": parts[3], "tipo": "telemetria",
        "dados": map[string]any{"umidade_solo": map[string]any{"valor": 45, "unidade": "%"}},
    }
    payload, err := json.Marshal(message)
    if err != nil { return err }
    base := os.Getenv("INGESTION_URL")
    if base == "" { base = "http://127.0.0.1:8002" }
    req, err := http.NewRequest(http.MethodPost, base+"/api/v1/ingestao", bytes.NewReader(payload))
    if err != nil { return err }
    req.Header.Set("Content-Type", "application/json")
    req.Header.Set("Authorization", "Bearer "+device.Credential.Token)
    client := &http.Client{Timeout: 10*time.Second}
    response, err := client.Do(req)
    if err != nil { return err }
    defer response.Body.Close()
    if response.StatusCode != 202 { return fmt.Errorf("ingestion rejected: HTTP %d", response.StatusCode) }
    _, err = io.Copy(os.Stdout, response.Body)
    return err
}

func main() {
    if err := run(); err != nil { fmt.Fprintln(os.Stderr, err); os.Exit(1) }
}
