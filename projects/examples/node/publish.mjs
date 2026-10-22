import { readFile } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';

const device = JSON.parse(await readFile(process.env.DEVICE_FILE, 'utf8'));
const [inquilino, site, dominio, dispositivo] = device.topico_base.split('/');
const message = {
  versao: '1.0', id_mensagem: randomUUID(), timestamp: new Date().toISOString(),
  inquilino, site, dominio, dispositivo, tipo: 'telemetria',
  dados: { umidade_solo: { valor: 45, unidade: '%' } },
};
const response = await fetch(`${process.env.INGESTION_URL ?? 'http://127.0.0.1:8002'}/api/v1/ingestao`, {
  method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${device.credencial.token}` },
  body: JSON.stringify(message), signal: AbortSignal.timeout(10_000),
});
if (response.status !== 202) throw new Error(`Ingestion rejected: HTTP ${response.status}`);
console.log(await response.text());
